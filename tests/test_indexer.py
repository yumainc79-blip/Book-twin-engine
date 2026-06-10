from pathlib import Path

import numpy as np

import book_twin.indexer as indexer
from book_twin.converters import read_book
from book_twin.indexer import build_index, sanitize_query, search_index
from book_twin.repository import create_book_repository


SYNTH = """# La coscienza

""" + ("La tesi centrale cita la rivoluzione cognitiva: perché la coscienza non e riducibile alla materia fisica. " * 30) + """

# La gravita

""" + ("La gravita curva lo spazio e il tempo secondo la relativita. Ogni interpretazione corretta lo conferma. " * 50) + """
"""


class FakeEmbedder:
    """Embedder deterministico bag-of-words con hashing, senza rete."""

    dim = 64

    def encode(self, texts):
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for i, t in enumerate(texts):
            for w in t.lower().split():
                out[i, hash(w) % self.dim] += 1.0
        return out


def _twin(tmp_path: Path) -> Path:
    src = tmp_path / "book.md"
    src.write_text(SYNTH, encoding="utf-8")
    text, pages, meta = read_book(src)
    out = tmp_path / "twin"
    create_book_repository(source_path=src, out_dir=out, language="it",
                           full_text=text, pages=pages, metadata=meta, force=True)
    return out


def test_fts_fallback_without_embeddings(tmp_path, monkeypatch):
    # Nessun embedder disponibile -> niente npz, ricerca solo FTS ma con risultati.
    monkeypatch.setattr(indexer, "get_embedder", lambda model=None: None)
    out = _twin(tmp_path)
    build_index(out)
    assert not indexer._emb_path(out).exists()
    rows = search_index(out, "coscienza", top_k=5)
    assert rows
    assert any("coscienza" in (r["text"] or "").lower() for r in rows)


def test_hybrid_with_fake_embedder(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "get_embedder", lambda model=None: FakeEmbedder())
    out = _twin(tmp_path)
    build_index(out, embeddings=True)
    assert indexer._emb_path(out).exists()
    rows = search_index(out, "gravita relativita", top_k=5, hybrid=True)
    assert rows
    assert any("gravita" in (r["text"] or "").lower() for r in rows)
    # ogni riga fusa ha uno score RRF
    assert all("score" in r for r in rows)


def test_hybrid_flag_off_uses_fts(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "get_embedder", lambda model=None: FakeEmbedder())
    out = _twin(tmp_path)
    build_index(out, embeddings=True)
    rows = search_index(out, "coscienza", top_k=5, hybrid=False)
    assert rows  # con hybrid disattivato torna comunque risultati FTS


# --------------------------------------------------------------------------- #
# STEP 1 — sanitize_query: nessun crash su input arbitrario
# --------------------------------------------------------------------------- #
def test_sanitize_query_quotes_tokens():
    assert sanitize_query("tesi centrale") == '"tesi" OR "centrale"'
    # caratteri sintattici FTS5 rimossi
    assert sanitize_query('a"b (c) ^d *e f\\g') == '"a" OR "b" OR "c" OR "d" OR "e" OR "f" OR "g"'
    # operatori neutralizzati come parole (quotati)
    assert sanitize_query("NEAR AND tesi") == '"NEAR" OR "AND" OR "tesi"'
    # input vuoto o solo speciali -> stringa vuota
    assert sanitize_query("") == ""
    assert sanitize_query('"() ^* \\') == ""


def test_search_survives_arbitrary_input(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "get_embedder", lambda model=None: None)
    out = _twin(tmp_path)
    build_index(out)
    # query ostili o con sintassi FTS: nessuna eccezione e i token
    # significativi presenti nel testo vengono trovati
    cases = {
        'tesi" injected': "tesi",
        "NEAR AND tesi": "tesi",
        'cita la "rivoluzione cognitiva"': "rivoluzione",
        "perché?": "perché",
    }
    for query, expected in cases.items():
        rows = search_index(out, query, top_k=5)
        assert rows, f"nessun risultato per {query!r}"
        assert any(expected in (r["text"] or "").lower() for r in rows), query


def test_search_empty_query_returns_no_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "get_embedder", lambda model=None: None)
    out = _twin(tmp_path)
    build_index(out)
    assert search_index(out, '"() ^* \\', top_k=5) == []
    assert search_index(out, "", top_k=5) == []


# --------------------------------------------------------------------------- #
# STEP 3 — stemming italiano
# --------------------------------------------------------------------------- #
def _fts_only(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "get_embedder", lambda model=None: None)
    out = _twin(tmp_path)
    build_index(out)
    return out


def test_stem_finds_inflected_form(tmp_path, monkeypatch):
    out = _fts_only(tmp_path, monkeypatch)
    # il testo contiene "interpretazione" (singolare): il plurale deve trovarlo
    rows = search_index(out, "interpretazioni", top_k=5)
    assert rows
    assert any("interpretazione" in (r["text"] or "").lower() for r in rows)


def test_accented_and_plain_equivalent(tmp_path, monkeypatch):
    out = _fts_only(tmp_path, monkeypatch)
    with_accent = search_index(out, "perché", top_k=5)
    without = search_index(out, "perche", top_k=5)
    assert with_accent and without
    assert with_accent[0]["id"] == without[0]["id"]
    assert "perché" in with_accent[0]["text"].lower()


def test_exact_match_ranking_not_worse(tmp_path, monkeypatch):
    out = _fts_only(tmp_path, monkeypatch)
    rows = search_index(out, "coscienza", top_k=5)
    assert rows
    # il match esatto resta in testa
    assert "coscienza" in rows[0]["text"].lower()


def test_unsupported_language_no_stem_no_error(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "get_embedder", lambda model=None: None)
    src = tmp_path / "book.md"
    src.write_text(SYNTH, encoding="utf-8")
    text, pages, meta = read_book(src)
    out = tmp_path / "twin_xx"
    create_book_repository(source_path=src, out_dir=out, language="xx",
                           full_text=text, pages=pages, metadata=meta, force=True)
    build_index(out)
    rows = search_index(out, "coscienza", top_k=5)
    assert rows  # comportamento no-stem, nessun errore
    # forma flessa NON trovata senza stemming: conferma che lo stem era off
    assert indexer.get_stemmer("xx") is None


def test_legacy_index_without_stem_columns_degrades(tmp_path, monkeypatch, capsys):
    import sqlite3
    out = _fts_only(tmp_path, monkeypatch)
    # ricrea lo schema FTS pre-STEP 3 (senza colonne stem)
    db = out / "knowledge" / "retrieval.sqlite"
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    cur.execute("DROP TABLE chunks_fts")
    cur.execute(
        "CREATE VIRTUAL TABLE chunks_fts USING fts5(id UNINDEXED, chapter_id UNINDEXED, "
        "chapter_title, text, summary, keywords)"
    )
    cur.execute(
        "INSERT INTO chunks_fts SELECT id, chapter_id, chapter_title, text, summary, keywords FROM chunks"
    )
    con.commit()
    con.close()

    rows = search_index(out, "coscienza", top_k=5)
    assert rows  # nessun crash, ricerca degradata ma funzionante
    err = capsys.readouterr().err
    assert "booktwin index" in err  # nota che suggerisce la rigenerazione
