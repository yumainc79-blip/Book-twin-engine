"""STEP 4 — estrazione robusta: tabelle, sup/note, PDF (de-sillabazione,
testatine, pages_map)."""
from pathlib import Path

import pytest

from book_twin.converters import read_book, read_html, read_pdf


def test_html_table_becomes_markdown(tmp_path):
    html = """<html><body>
    <h1>Capitolo</h1>
    <p>Testo prima della tabella.</p>
    <table>
      <tr><th>Anno</th><th>Valore</th></tr>
      <tr><td>2020</td><td>10</td></tr>
      <tr><td>2021</td><td>20</td></tr>
    </table>
    </body></html>"""
    p = tmp_path / "t.html"
    p.write_text(html, encoding="utf-8")
    text, _, _ = read_html(p)
    assert "| Anno | Valore |" in text
    assert "| 2020 | 10 |" in text
    # le celle non vengono duplicate come paragrafi sciolti
    assert text.count("2020") == 1


def test_sup_without_link_preserved_as_exponent(tmp_path):
    html = "<html><body><p>L'area è 10<sup>2</sup> metri quadri.</p></body></html>"
    p = tmp_path / "e.html"
    p.write_text(html, encoding="utf-8")
    text, _, _ = read_html(p)
    assert "10^2" in text


def test_sup_note_extracted(tmp_path):
    html = """<html><body>
    <p>Affermazione importante<sup><a href="#fn1">12</a></sup> del testo.</p>
    <p id="fn1">12. Testo della nota a piè di pagina.</p>
    </body></html>"""
    p = tmp_path / "n.html"
    p.write_text(html, encoding="utf-8")
    text, _, meta = read_html(p)
    assert "[n.12]" in text          # marcatore inline
    assert "importante" in text      # frase non spezzata
    notes = meta.get("notes") or []
    assert any("Testo della nota" in n["text"] for n in notes)
    # il corpo della nota non resta nel testo principale
    assert "Testo della nota" not in text


def _make_pdf(path: Path):
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4)
    for page_n in range(1, 5):
        y = 800
        c.drawString(72, y, "IL MIO LIBRO")  # testatina ripetuta su 4 pagine
        y -= 24
        if page_n == 1:
            c.drawString(72, y, "Questo testo spiega il com-")
            y -= 16
            c.drawString(72, y, "portamento del sistema nel tempo.")
            y -= 16
        for i in range(6):
            c.drawString(72, y, f"Contenuto della pagina {page_n}, riga {i}, con testo utile.")
            y -= 16
        c.drawString(290, 40, str(page_n))  # numero di pagina isolato
        c.showPage()
    c.save()


def test_pdf_dehyphenation_header_and_pages_map(tmp_path):
    pdf = tmp_path / "libro.pdf"
    _make_pdf(pdf)
    text, pages, meta = read_pdf(pdf)
    assert "comportamento" in text          # sillabazione ricomposta
    assert "com-\n" not in text
    assert "IL MIO LIBRO" not in text       # testatina rimossa
    assert "<!-- page" not in text          # niente marker pagina nel canonico
    pages_map = meta["pages_map"]
    assert len(pages_map) == 4
    assert pages_map[0] == {"offset": 0, "page": 1}
    # la mappa punta davvero al testo della pagina giusta
    off3 = next(e["offset"] for e in pages_map if e["page"] == 3)
    assert "pagina 3" in text[off3:off3 + 200]


def test_pdf_ingest_populates_chunk_pages(tmp_path):
    from book_twin.repository import create_book_repository
    from book_twin.utils import read_jsonl
    pdf = tmp_path / "libro.pdf"
    _make_pdf(pdf)
    text, pages, meta = read_book(pdf)
    out = tmp_path / "twin"
    create_book_repository(source_path=pdf, out_dir=out, language="it",
                           full_text=text, pages=pages, metadata=meta, force=True)
    assert (out / "canonical" / "pages_map.json").exists()
    chunks = read_jsonl(out / "knowledge" / "chunks.jsonl")
    assert chunks
    assert any(c["page_start"] is not None for c in chunks)
    first = chunks[0]
    assert first["page_start"] == 1
    assert first["page_end"] >= first["page_start"]
