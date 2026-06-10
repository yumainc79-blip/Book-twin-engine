import pytest

from book_twin.structure import (
    OverrideError,
    apply_overrides,
    chunk_text,
    split_chapters,
)


def _ch(title, n):
    return f"# {title}\n\n" + ("Frase di contenuto sufficientemente lunga per superare la soglia. " * n)


def test_level_aware_keeps_subheadings_inside():
    # Due capitoli h1; ciascuno ha sottosezioni h2 che NON devono diventare capitoli.
    text = (
        _ch("Capitolo Uno", 30)
        + "\n\n## Sottosezione 1.1\n\n"
        + ("dettaglio. " * 40)
        + "\n\n## Sottosezione 1.2\n\n"
        + ("dettaglio. " * 40)
        + "\n\n"
        + _ch("Capitolo Due", 30)
        + "\n\n## Sottosezione 2.1\n\n"
        + ("dettaglio. " * 40)
    )
    chapters = split_chapters(text)
    assert len(chapters) == 2
    assert chapters[0].title == "Capitolo Uno"
    # la sottosezione resta DENTRO il capitolo
    assert "Sottosezione 1.1" in chapters[0].text


def test_drop_frontmatter():
    text = (
        "# Indice\n\n" + ("voce indice. " * 50)
        + "\n\n" + _ch("Capitolo Uno", 40)
        + "\n\n" + _ch("Capitolo Due", 40)
        + "\n\n# Bibliografia\n\n" + ("riferimento. " * 50)
    )
    titles = [c.title for c in split_chapters(text, drop_frontmatter=True)]
    assert "Indice" not in titles
    assert "Bibliografia" not in titles
    assert "Capitolo Uno" in titles and "Capitolo Due" in titles


def test_short_dividers_merged():
    # Un divisore corto ("PARTE PRIMA") non deve diventare un capitolo a sé.
    text = (
        _ch("Prefazione", 40)
        + "\n\n# PARTE PRIMA\n\nbreve.\n\n"
        + _ch("Capitolo Uno", 40)
    )
    titles = [c.title for c in split_chapters(text)]
    assert "PARTE PRIMA" not in titles


def test_fallback_single_chapter():
    chapters = split_chapters("Testo senza heading. " * 100)
    assert len(chapters) == 1
    assert chapters[0].title == "Libro completo"


def test_chunk_text():
    chapters = split_chapters("# Capitolo 1\n\n" + ("paragrafo lungo di prova. " * 200))
    chunks = chunk_text(chapters, target_chars=500)
    assert chunks
    assert chunks[0].id.startswith("chunk_")


# --------------------------------------------------------------------------- #
# STEP 4 — fusione solo divisori, log eventi, override
# --------------------------------------------------------------------------- #
def test_short_real_chapter_not_swallowed():
    # Capitolo corto (<400 char) ma con paragrafo di corpo: NON è un divisore.
    short_body = ("Questo capitolo breve contiene comunque un paragrafo di corpo "
                  "con una frase reale e completa che supera gli ottanta caratteri.")
    text = _ch("Capitolo Uno", 40) + f"\n\n# Capitolo Breve\n\n{short_body}\n\n" + _ch("Capitolo Tre", 40)
    titles = [c.title for c in split_chapters(text)]
    assert "Capitolo Breve" in titles


def test_merges_and_drops_are_logged():
    events, dropped = [], []
    text = (
        "# Indice\n\n" + ("voce indice. " * 50)
        + "\n\n" + _ch("Capitolo Uno", 40)
        + "\n\n# PARTE SECONDA\n\nbreve.\n\n"
        + _ch("Capitolo Due", 40)
    )
    split_chapters(text, events=events, dropped=dropped)
    assert any("drop" in e and "Indice" in e for e in events)
    assert any("merge" in e and "PARTE SECONDA" in e for e in events)
    assert any(d["title"] == "Indice" for d in dropped)


def test_frontback_extended_patterns():
    text = (
        _ch("Capitolo Uno", 40)
        + "\n\n# Letture di approfondimento\n\n" + ("titolo, autore. " * 40)
        + "\n\n# Indice analitico\n\n" + ("voce, 123. " * 40)
    )
    titles = [c.title for c in split_chapters(text)]
    assert "Letture di approfondimento" not in titles
    assert "Indice analitico" not in titles


def _three_chapters():
    text = _ch("Uno", 40) + "\n\n" + _ch("Due", 40) + "\n\n" + _ch("Tre", 40)
    events, dropped = [], []
    return split_chapters(text, events=events, dropped=dropped), dropped


def test_override_merge_and_rename():
    chapters, dropped = _three_chapters()
    events = []
    out = apply_overrides(chapters, dropped, [
        {"action": "merge", "chapters": [2, 3]},
        {"action": "rename", "chapter": 1, "title": "Apertura"},
    ], events)
    assert [c.title for c in out] == ["Apertura", "Due"]
    assert out[0].order == 1 and out[1].order == 2
    assert "Tre" in out[1].text  # testo fuso, non perso


def test_override_split_at():
    chapters, dropped = _three_chapters()
    chapters[1].text += "\n\n## Sezione interna\n\nNuovo contenuto della sezione interna."
    out = apply_overrides(chapters, dropped, [
        {"action": "split_at", "chapter": 2, "at": "## Sezione interna", "title": "Sezione interna"},
    ], [])
    titles = [c.title for c in out]
    assert titles == ["Uno", "Due", "Sezione interna", "Tre"]
    assert [c.order for c in out] == [1, 2, 3, 4]


def test_override_drop_and_undrop():
    text = (
        "# Indice\n\n" + ("voce indice. " * 50)
        + "\n\n" + _ch("Capitolo Uno", 40)
        + "\n\n" + _ch("Capitolo Due", 40)
    )
    events, dropped = [], []
    chapters = split_chapters(text, events=events, dropped=dropped)
    # l'Indice è stato scartato in automatico: undrop lo ripristina in testa
    out = apply_overrides(chapters, dropped, [
        {"action": "undrop", "title": "Indice"},
        {"action": "drop", "chapter": 3},
    ], events)
    assert [c.title for c in out] == ["Indice", "Capitolo Uno"]
    assert any("undrop" in e for e in events)
    assert any(d["title"] == "Capitolo Due" for d in dropped)


def test_override_errors():
    chapters, dropped = _three_chapters()
    with pytest.raises(OverrideError, match="inesistente"):
        apply_overrides(chapters, dropped, [{"action": "rename", "chapter": 99, "title": "X"}], [])
    chapters, dropped = _three_chapters()
    with pytest.raises(OverrideError, match="sconosciuto"):
        apply_overrides(chapters, dropped, [{"action": "boom"}], [])
    chapters, dropped = _three_chapters()
    with pytest.raises(OverrideError, match="non tra i segmenti"):
        apply_overrides(chapters, dropped, [{"action": "undrop", "title": "Fantasma"}], [])
