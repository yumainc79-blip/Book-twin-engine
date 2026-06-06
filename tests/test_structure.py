from book_twin.structure import split_chapters, chunk_text


def test_split_chapters_markdown():
    text = "# Titolo\n\n## Capitolo 1\n\nTesto uno.\n\n## Capitolo 2\n\nTesto due."
    chapters = split_chapters(text)
    assert len(chapters) >= 2


def test_chunk_text():
    chapters = split_chapters("Capitolo 1\n\n" + ("paragrafo.\n\n" * 100))
    chunks = chunk_text(chapters, target_chars=500)
    assert chunks
    assert chunks[0].id.startswith("chunk_")
