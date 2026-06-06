from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from .models import BookDocument, Chapter, Chunk
from .structure import chunk_text, split_chapters
from .utils import (
    append_log,
    first_non_empty_line,
    safe_write_text,
    slugify,
    write_json,
    write_jsonl,
)


ANALYSIS_FILES = {
    "00_tesi_centrale.md": "# Tesi centrale\n\nDa generare con `book-twin analyze`.\n",
    "01_mappa_del_libro.md": "# Mappa del libro\n\nDa generare con `book-twin analyze`.\n",
    "02_riassunto_completo.md": "# Riassunto completo\n\nDa generare con `book-twin analyze`.\n",
    "03_argomentazione.md": "# Argomentazione\n\nDa generare con `book-twin analyze`.\n",
    "04_concetti_chiave.md": "# Concetti chiave\n\nDa generare con `book-twin analyze`.\n",
    "05_glossario.md": "# Glossario\n\nDa generare con `book-twin analyze`.\n",
    "06_domande_profonde.md": "# Domande profonde\n\nDa generare con `book-twin analyze`.\n",
    "07_limiti_e_critiche.md": "# Limiti e critiche\n\nDa generare con `book-twin analyze`.\n",
    "08_collegamenti_esterni.md": "# Collegamenti esterni\n\nDa generare con `book-twin analyze`.\n",
}


PERSONAS = {
    "faithful_exegete.md": """# Esegeta fedele

Rispondi solo in base al testo disponibile nel Book Twin.

Regole:
1. Distingui testo esplicito, inferenza e speculazione.
2. Cita sempre capitolo o chunk quando possibile.
3. Se il testo non basta, dichiaralo.
4. Non attribuire intenzioni all'autore senza evidenza.
""",
    "simulated_author.md": """# Autore simulato

Non sei l'autore reale. Sei una simulazione testualmente vincolata.

Regole:
1. Rispondi usando il quadro concettuale del libro.
2. Distingui:
   - direttamente supportato;
   - inferito;
   - speculativo.
3. Non inventare elementi biografici.
4. Cita chunk/capitoli quando possibile.
""",
    "critical_reviewer.md": """# Critico severo

Analizza premesse, argomenti, omissioni, contraddizioni e limiti.

Regole:
1. Non fare demolizione retorica.
2. Distingui critica fondata e dubbio interpretativo.
3. Cita sempre il punto testuale criticato.
""",
    "socratic_tutor.md": """# Tutor socratico

Aiuta l'utente a capire il libro tramite domande progressive.

Regole:
1. Una domanda alla volta.
2. Parti dal testo.
3. Aumenta la profondità gradualmente.
4. Non sostituirti alla riflessione dell'utente.
""",
}


PROMPTS = {
    "analyze_chapter.md": """Analizza il capitolo seguente.

Produci:
- funzione del capitolo nel libro;
- riassunto breve;
- riassunto esteso;
- tesi;
- argomenti;
- concetti;
- esempi;
- definizioni;
- passaggi decisivi;
- collegamenti;
- obiezioni;
- applicazioni;
- cosa memorizzare.

Testo:
{{text}}
""",
    "extract_claims.md": """Estrai i claim principali dal testo. Per ogni claim indica evidenza, confidenza e possibili limiti.

Testo:
{{text}}
""",
    "extract_concepts.md": """Estrai concetti, definizioni, alias e relazioni dal testo.

Testo:
{{text}}
""",
    "synthesize_book.md": """Sintetizza il libro usando i riassunti dei capitoli. Distingui tesi centrale, struttura argomentativa, concetti, tensioni, limiti.

Materiale:
{{text}}
""",
    "answer_grounded.md": """Rispondi alla domanda usando solo il contesto recuperato.

Domanda:
{{question}}

Contesto:
{{context}}

Regole:
- Distingui supportato, inferito e speculativo.
- Cita chunk e capitoli.
- Se il contesto non basta, dichiaralo.
""",
    "dialogue_as_author.md": """Rispondi come autore simulato testualmente vincolato.

Domanda:
{{question}}

Contesto:
{{context}}

Regole:
- Non sei l'autore reale.
- Usa il quadro concettuale del libro.
- Distingui testo esplicito, inferenza e speculazione.
- Cita evidenze.
""",
}


def create_book_repository(
    source_path: Path,
    out_dir: Path,
    language: str,
    full_text: str,
    pages: list,
    metadata: dict,
    force: bool = False,
) -> tuple[BookDocument, list[Chunk]]:
    if out_dir.exists():
        if not force:
            raise FileExistsError(f"La cartella {out_dir} esiste già. Usa --force per sovrascrivere.")
        shutil.rmtree(out_dir)

    for d in [
        "canonical/chapters",
        "canonical/pages",
        "canonical/figures",
        "canonical/tables",
        "canonical/notes",
        "analysis/chapters",
        "knowledge",
        "indexes",
        "personas",
        "prompts",
        "exports/obsidian",
        "logs",
    ]:
        (out_dir / d).mkdir(parents=True, exist_ok=True)

    title = metadata.get("title") or first_non_empty_line(full_text, source_path.stem)
    chapters = split_chapters(full_text)
    chunks = chunk_text(chapters)

    doc = BookDocument(
        title=title,
        source_path=str(source_path),
        language=language,
        full_text=full_text,
        pages=pages,
        chapters=chapters,
        metadata=metadata,
    )

    write_core_files(out_dir, doc, chunks)
    append_log(out_dir, f"- Ingest completato da `{source_path}`.")
    append_log(out_dir, f"- Capitoli rilevati: {len(chapters)}.")
    append_log(out_dir, f"- Chunk generati: {len(chunks)}.")
    return doc, chunks


def write_core_files(out_dir: Path, doc: BookDocument, chunks: list[Chunk]) -> None:
    safe_write_text(out_dir / "README.md", render_book_readme(doc))
    safe_write_text(out_dir / "llms.txt", render_llms_txt(doc))
    safe_write_text(
        out_dir / "book.config.yaml",
        yaml.safe_dump(
            {
                "title": doc.title,
                "language": doc.language,
                "source_path": doc.source_path,
                "status": "ingested",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )

    safe_write_text(out_dir / "canonical" / "book.md", doc.full_text)
    write_json(
        out_dir / "canonical" / "book.json",
        {
            "title": doc.title,
            "source_path": doc.source_path,
            "language": doc.language,
            "metadata": doc.metadata,
            "chapter_count": len(doc.chapters),
            "chunk_count": len(chunks),
        },
    )

    for chapter in doc.chapters:
        name = f"{chapter.order:03d}_{slugify(chapter.title, 60)}.md"
        safe_write_text(out_dir / "canonical" / "chapters" / name, chapter.text)
        safe_write_text(out_dir / "analysis" / "chapters" / name, render_chapter_analysis_placeholder(chapter))

    for page in doc.pages:
        safe_write_text(out_dir / "canonical" / "pages" / f"page_{page.page_number:04d}.md", page.text)

    for filename, content in ANALYSIS_FILES.items():
        safe_write_text(out_dir / "analysis" / filename, content)

    for filename, content in PERSONAS.items():
        safe_write_text(out_dir / "personas" / filename, content)

    for filename, content in PROMPTS.items():
        safe_write_text(out_dir / "prompts" / filename, content)

    write_jsonl(out_dir / "knowledge" / "chunks.jsonl", [c.to_json() for c in chunks])
    write_jsonl(out_dir / "knowledge" / "claims.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "concepts.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "entities.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "relations.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "citations.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "timeline.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "questions.jsonl", [])
    write_json(out_dir / "knowledge" / "book_graph.json", {"nodes": [], "edges": []})
    write_json(out_dir / "indexes" / "manifest.json", {"fts": "knowledge/retrieval.sqlite"})

    safe_write_text(out_dir / "exports" / "study_guide.md", "# Study guide\n\nDa generare.\n")
    safe_write_text(out_dir / "exports" / "anki_flashcards.csv", "Front,Back\n")


def render_book_readme(doc: BookDocument) -> str:
    return f"""# {doc.title}

Questa cartella è un Book Twin: una rappresentazione strutturata e interrogabile del libro.

## File principali

- `llms.txt`: mappa per AI.
- `canonical/book.md`: testo ricostruito.
- `canonical/chapters/`: capitoli ricostruiti.
- `analysis/`: analisi interpretativa.
- `knowledge/chunks.jsonl`: chunk citabili.
- `knowledge/retrieval.sqlite`: indice testuale SQLite FTS.
- `personas/`: modalità di dialogo.
- `prompts/`: prompt riutilizzabili.

## Comandi utili

```bash
book-twin index .
book-twin search . "tema"
book-twin ask . "domanda"
book-twin analyze .
```
"""


def render_llms_txt(doc: BookDocument) -> str:
    return f"""# {doc.title}

## Purpose

This repository contains an AI-native reconstruction of a book.

## Use rules

- Prefer `knowledge/chunks.jsonl` and `knowledge/retrieval.sqlite` for grounded retrieval.
- Use `analysis/` for interpretation.
- Use `canonical/` for reconstructed text.
- Distinguish direct textual evidence, inference, and speculation.
- Cite chapter IDs and chunk IDs whenever possible.

## Core files

- `canonical/book.md`
- `canonical/book.json`
- `canonical/chapters/`
- `knowledge/chunks.jsonl`
- `knowledge/claims.jsonl`
- `knowledge/concepts.jsonl`
- `analysis/00_tesi_centrale.md`
- `analysis/01_mappa_del_libro.md`
- `personas/simulated_author.md`

## Suggested interaction modes

- faithful exegete
- simulated author
- critical reviewer
- socratic tutor
"""


def render_chapter_analysis_placeholder(chapter: Chapter) -> str:
    return f"""# Analisi — {chapter.title}

## Funzione del capitolo nel libro

Da generare.

## Riassunto breve

Da generare.

## Riassunto esteso

Da generare.

## Tesi principale

Da generare.

## Argomenti

Da generare.

## Concetti chiave

Da generare.

## Esempi e definizioni

Da generare.

## Passaggi decisivi

Da generare.

## Collegamenti con altri capitoli

Da generare.

## Domande aperte

Da generare.

## Possibili obiezioni

Da generare.

## Applicazioni pratiche

Da generare.

## Cosa memorizzare

Da generare.
"""
