from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import Page
from .utils import normalize_whitespace


class ConversionError(RuntimeError):
    pass


def read_book(path: Path) -> tuple[str, list[Page], dict]:
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md", ".markdown"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return normalize_whitespace(text), [], {"converter": "plain-text"}

    if suffix in {".html", ".htm"}:
        return read_html(path)

    if suffix == ".docx":
        return read_docx(path)

    if suffix == ".pdf":
        return read_pdf(path)

    if suffix == ".epub":
        return read_epub(path)

    if suffix in {".mobi", ".azw3"}:
        return read_via_calibre(path)

    raise ConversionError(f"Formato non supportato: {suffix}")


def read_html(path: Path) -> tuple[str, list[Page], dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ConversionError("beautifulsoup4 non installato.") from exc

    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()

    lines: list[str] = []
    for el in soup.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        if el.name == "h1":
            lines.append(f"# {txt}")
        elif el.name == "h2":
            lines.append(f"## {txt}")
        elif el.name == "h3":
            lines.append(f"### {txt}")
        elif el.name == "li":
            lines.append(f"- {txt}")
        else:
            lines.append(txt)
    text = "\n\n".join(lines) if lines else soup.get_text("\n")
    return normalize_whitespace(text), [], {"converter": "html-bs4"}


def read_docx(path: Path) -> tuple[str, list[Page], dict]:
    try:
        import docx
    except ImportError as exc:
        raise ConversionError("python-docx non installato.") from exc

    document = docx.Document(str(path))
    lines: list[str] = []
    for p in document.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        style = (p.style.name or "").lower()
        if "heading 1" in style or "titolo 1" in style:
            lines.append(f"# {txt}")
        elif "heading 2" in style or "titolo 2" in style:
            lines.append(f"## {txt}")
        elif "heading 3" in style or "titolo 3" in style:
            lines.append(f"### {txt}")
        else:
            lines.append(txt)
    return normalize_whitespace("\n\n".join(lines)), [], {"converter": "python-docx"}


def read_pdf(path: Path) -> tuple[str, list[Page], dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ConversionError("pypdf non installato.") from exc

    reader = PdfReader(str(path))
    pages: list[Page] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(Page(page_number=i, text=normalize_whitespace(text)))

    full = "\n\n".join(f"\n\n<!-- page:{p.page_number} -->\n\n{p.text}" for p in pages if p.text)
    if not full.strip():
        raise ConversionError("PDF senza testo estraibile. Serve OCR o Marker/OCR nello step successivo.")
    return normalize_whitespace(full), pages, {"converter": "pypdf", "page_count": len(pages)}


def read_epub(path: Path) -> tuple[str, list[Page], dict]:
    try:
        from ebooklib import epub
        from ebooklib import ITEM_DOCUMENT
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ConversionError("ebooklib e beautifulsoup4 devono essere installati.") from exc

    book = epub.read_epub(str(path))
    parts: list[str] = []
    title = None
    try:
        titles = book.get_metadata("DC", "title")
        if titles:
            title = titles[0][0]
    except Exception:
        pass

    for item in book.get_items():
        if item.get_type() == ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            for tag in soup(["script", "style"]):
                tag.extract()
            section_lines: list[str] = []
            for el in soup.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
                txt = el.get_text(" ", strip=True)
                if not txt:
                    continue
                if el.name == "h1":
                    section_lines.append(f"# {txt}")
                elif el.name == "h2":
                    section_lines.append(f"## {txt}")
                elif el.name == "h3":
                    section_lines.append(f"### {txt}")
                elif el.name == "li":
                    section_lines.append(f"- {txt}")
                else:
                    section_lines.append(txt)
            if section_lines:
                parts.append("\n\n".join(section_lines))
    meta = {"converter": "ebooklib", "title": title}
    return normalize_whitespace("\n\n".join(parts)), [], meta


def read_via_calibre(path: Path) -> tuple[str, list[Page], dict]:
    exe = shutil.which("ebook-convert")
    if not exe:
        raise ConversionError("Calibre ebook-convert non trovato. Installa Calibre oppure converti manualmente in EPUB.")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / (path.stem + ".epub")
        result = subprocess.run([exe, str(path), str(out)], capture_output=True, text=True)
        if result.returncode != 0:
            raise ConversionError(f"Conversione Calibre fallita: {result.stderr[-1000:]}")
        text, pages, meta = read_epub(out)
        meta["preconverter"] = "calibre-ebook-convert"
        return text, pages, meta
