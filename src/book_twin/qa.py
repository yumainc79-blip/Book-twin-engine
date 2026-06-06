from __future__ import annotations

from pathlib import Path

from .indexer import search_index
from .llm import get_client


def build_context(rows: list[dict], max_chars: int = 14000) -> str:
    parts = []
    total = 0
    for r in rows:
        header = f"[{r['id']} | {r.get('chapter_title','')}]"
        block = f"{header}\n{r.get('text','')}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)


def answer_question(book_dir: Path, question: str, provider: str = "none", model: str | None = None, mode: str = "faithful") -> str:
    rows = search_index(book_dir, question, top_k=8)
    context = build_context(rows)
    client = get_client(provider)

    prompt = f"""Rispondi in italiano alla domanda usando solo il contesto recuperato dal Book Twin.

Modalità: {mode}

Domanda:
{question}

Contesto:
{context}

Regole:
1. Distingui chiaramente:
   - direttamente supportato dal testo;
   - inferito dal testo;
   - speculativo.
2. Cita chunk e capitolo quando possibile.
3. Se il contesto non basta, dillo.
4. Non inventare elementi non presenti nel contesto.
"""
    return client.complete(prompt, model=model).text
