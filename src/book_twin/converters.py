from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import Page
from .utils import normalize_whitespace

# Un blocco che è SOLO un numero o un numerale romano isolato (marcatore/divisorio).
_NUMERIC_ONLY_RE = re.compile(r"^[\divxlcdmIVXLCDM]{1,4}[.\):]?$")
_BLOCK_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "blockquote", "figcaption"]


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


def _is_note_link(a) -> bool:
    cls = " ".join(a.get("class", [])).lower()
    return ("note" in cls or "fn" in cls or "footnote" in cls) and a.get_text(strip=True).isdigit()


def _resolve_note_text(soup, href: str) -> str:
    """Best-effort: risolve href="#id" nel documento e ne estrae (rimuovendolo) il testo."""
    if not href or not href.startswith("#"):
        return ""
    target = soup.find(id=href[1:])
    if target is None:
        return ""
    txt = re.sub(r"\s+", " ", target.get_text(" ", strip=True)).strip()
    target.decompose()
    return txt


def _clean_soup(soup, notes: list | None = None):
    """Rimuove rumore e tratta i <sup> (PROGETTO.md STEP 4):

    - <sup> contenente <a> (o <a> con classe di nota) → marcatore inline [n.X];
      il testo della nota, se risolvibile nello stesso documento, finisce in `notes`;
    - <sup> SENZA link → conservato come ^contenuto (gli esponenti sopravvivono);
    - <script>/<style> e link di nota residui rimossi.
    """
    for tag in soup(["script", "style"]):
        tag.decompose()
    for sup in soup.find_all("sup"):
        a = sup.find("a")
        if a is not None:
            ref = sup.get_text(strip=True) or "?"
            if notes is not None:
                note_text = _resolve_note_text(soup, a.get("href", "") if a else "")
                notes.append({"ref": ref, "text": note_text})
            sup.replace_with(f"[n.{ref}]")
        else:
            content = sup.get_text(strip=True)
            if content:
                sup.replace_with(f"^{content}")
            else:
                sup.decompose()
    # Link di nota/footnote fuori da <sup> il cui testo è solo cifre.
    for a in soup.find_all("a"):
        if _is_note_link(a):
            ref = a.get_text(strip=True)
            if notes is not None:
                notes.append({"ref": ref, "text": _resolve_note_text(soup, a.get("href", ""))})
            a.replace_with(f"[n.{ref}]")
    return soup


def _table_to_markdown(table) -> str:
    """Converte <table> in tabella Markdown (una riga per <tr>)."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [
            re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip()
            for td in tr.find_all(["th", "td"])
        ]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _blocks_to_markdown(soup) -> list[str]:
    """Converte i blocchi rilevanti in righe Markdown.

    - cattura solo il <blockquote> di livello superiore (salta gli elementi annidati al suo interno,
      per evitare doppioni p/li dentro citazioni);
    - salta i blocchi che sono solo un numero/numerale romano isolato;
    - usa get_text(" ") così acronimi e corsivi restano INLINE nella frase.
    """
    lines: list[str] = []
    for el in soup.find_all(_BLOCK_TAGS + ["table"]):
        # Evita doppioni: gli elementi dentro blockquote/table li cattura il contenitore.
        if el.name != "blockquote" and el.find_parent("blockquote") is not None:
            continue
        if el.name != "table" and el.find_parent("table") is not None:
            continue
        if el.name == "table":
            md = _table_to_markdown(el)
            if md:
                lines.append(md)
            continue
        txt = el.get_text(" ", strip=True)
        # I text-node del sorgente possono contenere newline interni: comprimi ogni
        # whitespace a spazio singolo così il blocco resta UNA sola riga (niente righe spurie).
        txt = re.sub(r"\s+", " ", txt).strip()
        # gli esponenti restano attaccati alla base: "10 ^2" → "10^2"
        txt = re.sub(r"\s+\^", "^", txt)
        if not txt:
            continue
        if _NUMERIC_ONLY_RE.match(txt):
            continue
        if el.name == "h1":
            lines.append(f"# {txt}")
        elif el.name == "h2":
            lines.append(f"## {txt}")
        elif el.name in {"h3", "h4"}:
            lines.append(f"### {txt}")
        elif el.name == "li":
            lines.append(f"- {txt}")
        else:  # p, blockquote, figcaption
            lines.append(txt)
    return lines


def read_html(path: Path) -> tuple[str, list[Page], dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ConversionError("beautifulsoup4 non installato.") from exc

    html = path.read_text(encoding="utf-8", errors="ignore")
    notes: list[dict] = []
    soup = _clean_soup(BeautifulSoup(html, "html.parser"), notes=notes)
    lines = _blocks_to_markdown(soup)
    text = "\n\n".join(lines) if lines else soup.get_text("\n")
    meta = {"converter": "html-bs4"}
    if notes:
        meta["notes"] = notes
    return normalize_whitespace(text), [], meta


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


# Riga che è solo un numero di pagina (arabo o romano).
_PAGE_NUMBER_RE = re.compile(r"^\s*[\divxlcdmIVXLCDM]{1,6}\s*$")
# Sillabazione a fine riga: ricomposta solo se entrambe le metà sono minuscole.
_HYPHEN_RE = re.compile(r"([a-zà-ÿ])-\n\s*([a-zà-ÿ])")


def _dehyphenate(text: str) -> str:
    return _HYPHEN_RE.sub(r"\1\2", text)


def _running_lines(raw_pages: list[str], edge: int = 2, min_repeats: int = 4,
                   max_len: int = 60) -> set[str]:
    """Testatine/piè di pagina: righe corte ripetute ≥min_repeats volte a
    inizio/fine pagina."""
    from collections import Counter
    counter: Counter[str] = Counter()
    for raw in raw_pages:
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        for l in set(lines[:edge] + lines[-edge:]):
            if len(l) <= max_len:
                counter[l] += 1
    return {l for l, n in counter.items() if n >= min_repeats}


def _clean_pdf_page(raw: str, running: set[str], edge: int = 2) -> str:
    lines = raw.splitlines()
    # indici delle righe non vuote, per individuare la zona inizio/fine pagina
    nonempty = [i for i, l in enumerate(lines) if l.strip()]
    edge_idx = set(nonempty[:edge] + nonempty[-edge:])
    kept: list[str] = []
    for i, l in enumerate(lines):
        s = l.strip()
        if s and _PAGE_NUMBER_RE.match(s):
            continue
        if i in edge_idx and s in running:
            continue
        kept.append(l)
    return _dehyphenate("\n".join(kept))


def read_pdf(path: Path) -> tuple[str, list[Page], dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ConversionError("pypdf non installato.") from exc

    reader = PdfReader(str(path))
    raw_pages: list[str] = []
    for page in reader.pages:
        try:
            raw_pages.append(page.extract_text() or "")
        except Exception:
            raw_pages.append("")

    running = _running_lines(raw_pages)
    pages: list[Page] = []
    pages_map: list[dict] = []
    parts: list[str] = []
    offset = 0
    for i, raw in enumerate(raw_pages, start=1):
        cleaned = normalize_whitespace(_clean_pdf_page(raw, running))
        pages.append(Page(page_number=i, text=cleaned))
        if not cleaned:
            continue
        # mappa offset→pagina costruita PRIMA di ogni altra trasformazione:
        # niente marker pagina nel testo canonico
        pages_map.append({"offset": offset, "page": i})
        parts.append(cleaned)
        offset += len(cleaned) + 2  # separatore "\n\n"

    full = "\n\n".join(parts)
    if not full.strip():
        raise ConversionError("PDF senza testo estraibile. Serve OCR o Marker/OCR nello step successivo.")
    meta = {"converter": "pypdf", "page_count": len(pages), "pages_map": pages_map}
    return full, pages, meta


def read_epub(path: Path) -> tuple[str, list[Page], dict]:
    try:
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ConversionError("ebooklib e beautifulsoup4 devono essere installati.") from exc

    book = epub.read_epub(str(path))

    def _first_meta(field: str) -> str | None:
        try:
            vals = book.get_metadata("DC", field)
            if vals:
                return vals[0][0]
        except Exception:
            pass
        return None

    title = _first_meta("title")
    author = _first_meta("creator")

    # Leggi i documenti NELL'ORDINE DELLO SPINE (get_items() è non ordinato e scombina i capitoli).
    parts: list[str] = []
    notes: list[dict] = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None:
            continue
        try:
            content = item.get_content()
        except Exception:
            continue
        # Le note sono risolte best-effort SOLO dentro lo stesso documento spine
        # (href cross-file non risolti: resta il marcatore [n.X]).
        soup = _clean_soup(BeautifulSoup(content, "html.parser"), notes=notes)
        section_lines = _blocks_to_markdown(soup)
        if section_lines:
            parts.append("\n\n".join(section_lines))

    meta = {"converter": "ebooklib", "title": title, "author": author}
    if notes:
        meta["notes"] = notes
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
