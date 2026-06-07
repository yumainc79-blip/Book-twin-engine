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


def _read_optional(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def answer_question(book_dir: Path, question: str, provider: str = "none", model: str | None = None, mode: str = "integrated") -> str:
    rows = search_index(book_dir, question, top_k=8)
    context = build_context(rows)
    client = get_client(provider)

    prompt_for_ai = _read_optional(book_dir / "prompt_for_ai.md", 5000)
    author_model = _read_optional(book_dir / "author_model" / "author_model.md", 5000)
    dialogue_protocol = _read_optional(book_dir / "dialogue" / "dialogue_protocol.md", 5000)
    reader_reflection = _read_optional(book_dir / "reader_reflection" / "reader_reflection.md", 3500)

    prompt = f"""Rispondi in italiano alla domanda usando il Book Twin.

Modalità richiesta: {mode}

Istruzioni principali dal Book Twin:
{prompt_for_ai}

Modello dell'autore:
{author_model}

Protocollo dialogico:
{dialogue_protocol}

Riflessione del lettore:
{reader_reflection}

Domanda:
{question}

Contesto recuperato:
{context}

Regole obbligatorie:
1. Se rispondi come autore simulato, parla in prima persona ma dichiara la simulazione testualmente vincolata.
2. Formula consigliata: "Sono l'autore in simulazione testualmente vincolata: parliamo." Se conosci il nome autore dai file, usa quel nome.
3. Distingui:
   - direttamente supportato dal testo;
   - inferito dal testo;
   - estensione speculativa.
4. Cita chunk e capitolo quando possibile.
5. Integra, se utile:
   - cosa direbbe l'autore;
   - dove il testo lo sostiene;
   - cosa implica per il lettore;
   - limiti della teoria e possibili fraintendimenti del lettore.
6. Non inventare elementi non presenti nel contesto.
7. Non fare diagnosi del lettore.
"""
    return client.complete(prompt, model=model).text
