import json
from pathlib import Path

import pytest

from book_twin.converters import read_book
from book_twin.indexer import build_index
from book_twin.repository import create_book_repository
from book_twin import mcp_server as M

_CH = ("La coscienza e il tema centrale; l'informazione struttura il reale. ") * 60
SYNTH = f"""# Capitolo Uno

{_CH}

# Capitolo Due

{_CH}
"""


@pytest.fixture
def twin(tmp_path):
    src = tmp_path / "book.md"
    src.write_text(SYNTH, encoding="utf-8")
    text, pages, meta = read_book(src)
    out = tmp_path / "twin"
    create_book_repository(source_path=src, out_dir=out, language="it",
                           full_text=text, pages=pages, metadata=meta, force=True)
    build_index(out)
    # In v0.5 l'analisi la fa l'LLM esecutore: fabbrichiamo gli artefatti minimi
    # che il server MCP legge (analysis md + knowledge jsonl).
    (out / "analysis" / "00_tesi_centrale.md").write_text(
        "# Tesi centrale\n\nLa coscienza e irriducibile.\n", encoding="utf-8"
    )
    (out / "knowledge" / "concepts.jsonl").write_text(
        json.dumps({"name": "coscienza", "definition": "unita cosciente"}) + "\n",
        encoding="utf-8",
    )
    (out / "knowledge" / "claims.jsonl").write_text(
        json.dumps({"claim": "La coscienza e irriducibile.", "chapter": "001"}) + "\n",
        encoding="utf-8",
    )
    return out


def test_list_chapters(twin):
    chs = M.list_chapters(twin)
    assert len(chs) == 2
    assert chs[0]["order"] == "001"
    assert "Uno" in chs[0]["title"]


def test_search_book(twin):
    rows = M.search_book(twin, "coscienza", top_k=3)
    assert rows
    assert any("coscienza" in r["text"].lower() for r in rows)
    assert "score" in rows[0] and "id" in rows[0]


def test_grounded_context(twin):
    ctx = M.grounded_context(twin, "coscienza", top_k=3)
    assert "coscienza" in ctx.lower()
    assert "[" in ctx  # header [chunk_id | capitolo]


def test_read_chapter_by_number_and_title(twin):
    by_num = M.read_chapter(twin, "2")
    assert "Capitolo Due" in by_num
    by_title = M.read_chapter(twin, "Uno")
    assert "Capitolo Uno" in by_title
    assert M.read_chapter(twin, "999") == ""


def test_concepts_and_claims(twin):
    assert isinstance(M.get_concepts(twin), list)
    assert M.get_claims(twin)


def test_get_analysis_by_number_and_keyword(twin):
    assert M.get_analysis(twin, "00").strip()
    assert M.get_analysis(twin, "tesi").strip()
    assert "irriducibile" in M.get_analysis(twin, "tesi").lower()


def test_metadata_has_engine_version(twin):
    import book_twin
    meta = M.book_metadata(twin)
    assert meta.get("engine_version") == book_twin.__version__


def test_resolve_book_dir(tmp_path, monkeypatch):
    assert M.resolve_book_dir([str(tmp_path)]) == tmp_path.resolve()
    monkeypatch.setenv("BOOK_TWIN_DIR", str(tmp_path))
    assert M.resolve_book_dir([]) == tmp_path.resolve()
    monkeypatch.delenv("BOOK_TWIN_DIR", raising=False)
    with pytest.raises(SystemExit):
        M.resolve_book_dir([])


def test_build_server_registers_tools(twin):
    pytest.importorskip("mcp")
    import asyncio
    srv = M.build_server(twin)
    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert {"search", "context", "chapter", "analysis"} <= names
