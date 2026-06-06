from __future__ import annotations

import re
from pathlib import Path

from .llm import get_client
from .utils import read_jsonl, safe_write_text, write_jsonl


def top_terms(text: str, n: int = 25) -> list[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ]{4,}", text.lower())
    stop = {
        "della", "delle", "degli", "dallo", "dalla", "dalle", "sono", "come", "questo", "questa",
        "quello", "quella", "anche", "perche", "perché", "nella", "nelle", "allo", "alla", "agli",
        "essere", "avere", "senza", "dopo", "prima", "quando", "dove", "solo", "tutto", "tutti",
        "chapter", "capitolo", "with", "that", "this", "from", "have", "were", "their", "there",
    }
    counts: dict[str, int] = {}
    for w in words:
        if w in stop:
            continue
        counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def analyze_book(book_dir: Path, provider: str = "none", model: str | None = None, max_chars_per_chapter: int = 12000) -> None:
    chunks = read_jsonl(book_dir / "knowledge" / "chunks.jsonl")
    if not chunks:
        raise FileNotFoundError("chunks.jsonl mancante o vuoto. Prima esegui ingest.")

    client = get_client(provider)

    by_chapter: dict[str, list[dict]] = {}
    for ch in chunks:
        by_chapter.setdefault(ch["chapter_id"], []).append(ch)

    chapter_summaries: list[dict] = []
    for chapter_id, rows in by_chapter.items():
        title = rows[0].get("chapter_title") or chapter_id
        text = "\n\n".join(r["text"] for r in rows)[:max_chars_per_chapter]
        prompt = f"""Analizza il capitolo seguente in italiano.

Titolo: {title}

Produci una scheda Markdown con:
- funzione del capitolo nel libro;
- riassunto breve;
- riassunto esteso;
- tesi principale;
- argomenti;
- concetti chiave;
- esempi e definizioni;
- passaggi decisivi;
- collegamenti;
- domande aperte;
- possibili obiezioni;
- applicazioni pratiche;
- cosa memorizzare.

Testo:
{text}
"""
        response = client.complete(prompt, model=model).text
        path = book_dir / "analysis" / "chapters" / f"{chapter_id}.md"
        safe_write_text(path, f"# Analisi — {title}\n\n{response}\n")
        chapter_summaries.append({"chapter_id": chapter_id, "title": title, "summary": response[:3000]})

    full_context = "\n\n".join(f"## {x['title']}\n{x['summary']}" for x in chapter_summaries)
    synthesis_prompt = f"""Sintetizza il libro in italiano usando queste analisi di capitolo.

Produci:
1. tesi centrale;
2. mappa del libro;
3. riassunto completo;
4. struttura dell'argomentazione;
5. concetti chiave;
6. domande profonde;
7. limiti e critiche;
8. cosa memorizzare.

Analisi capitoli:
{full_context[:24000]}
"""
    synthesis = client.complete(synthesis_prompt, model=model).text
    safe_write_text(book_dir / "analysis" / "02_riassunto_completo.md", "# Riassunto completo\n\n" + synthesis + "\n")

    all_text = "\n\n".join(r["text"] for r in chunks)
    terms = top_terms(all_text, 40)
    concepts = [
        {
            "concept_id": f"concept_{i:03d}",
            "name": term,
            "definition": "",
            "aliases": [],
            "related_concepts": [],
            "chapters": [],
        }
        for i, term in enumerate(terms, start=1)
    ]
    write_jsonl(book_dir / "knowledge" / "concepts.jsonl", concepts)
    safe_write_text(
        book_dir / "analysis" / "04_concetti_chiave.md",
        "# Concetti chiave\n\n" + "\n".join(f"- {t}" for t in terms) + "\n",
    )

    questions = [
        {"id": "q_001", "question": "Qual è la tesi centrale del libro?", "type": "global"},
        {"id": "q_002", "question": "Quali concetti ritornano più spesso?", "type": "global"},
        {"id": "q_003", "question": "Quali sono le possibili obiezioni alla tesi del libro?", "type": "critical"},
        {"id": "q_004", "question": "Quali capitoli sono indispensabili per capire l'opera?", "type": "study"},
    ]
    write_jsonl(book_dir / "knowledge" / "questions.jsonl", questions)
    safe_write_text(
        book_dir / "analysis" / "06_domande_profonde.md",
        "# Domande profonde\n\n" + "\n".join(f"- {q['question']}" for q in questions) + "\n",
    )
