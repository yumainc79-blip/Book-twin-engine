"""
Server MCP del Book Twin.

Espone un Book Twin generato a un client MCP (Claude Desktop, Claude Code, ...) così che
un LLM in chat possa interrogarlo direttamente, con retrieval reale, senza incollare file.

- tools: search_book, grounded_context, read_chapter, list_chapters, get_concepts,
  get_claims, get_analysis;
- resources: book://metadata, book://analysis/{section}, book://chapter/{ref};
- prompts: dialogue_integrated, simulated_author.

La logica è in funzioni pure (sotto), indipendenti dal pacchetto `mcp` e quindi testabili.
Il cablaggio FastMCP è in `build_server()`; `mcp` è una dipendenza opzionale importata lì.

Avvio:  book-twin-mcp <cartella_twin>     (oppure variabile BOOK_TWIN_DIR)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from .indexer import build_context, search_index
from .utils import read_jsonl

MAX_CHAPTER_CHARS = 50_000
ANALYSIS_FILES = {
    "00": "tesi", "tesi": "tesi", "tesi_centrale": "tesi",
    "01": "mappa", "mappa": "mappa",
    "02": "riassunto", "riassunto": "riassunto",
    "03": "argomentazione", "argomentazione": "argomentazione",
    "04": "concetti", "concetti": "concetti",
    "05": "glossario", "glossario": "glossario",
    "06": "domande", "domande": "domande",
    "07": "limiti", "limiti": "limiti", "critiche": "limiti",
    "08": "collegamenti", "collegamenti": "collegamenti",
}


# --------------------------------------------------------------------------- #
# Logica pura (nessuna dipendenza da `mcp`)
# --------------------------------------------------------------------------- #
def book_metadata(book_dir: Path) -> dict:
    cfg = book_dir / "book.config.yaml"
    if not cfg.exists():
        return {}
    try:
        return yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def list_chapters(book_dir: Path) -> list[dict]:
    out = []
    chap_dir = book_dir / "canonical" / "chapters"
    if not chap_dir.exists():
        return out
    for f in sorted(chap_dir.glob("*.md")):
        order = f.stem[:3]
        title = ""
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip():
                title = line.lstrip("# ").strip()
                break
        out.append({"order": order, "title": title, "file": f.name})
    return out


def search_book(book_dir: Path, query: str, top_k: int = 8, hybrid: bool = True) -> list[dict]:
    rows = search_index(book_dir, query, top_k=top_k, hybrid=hybrid)
    return [
        {
            "id": r["id"],
            "chapter_title": r.get("chapter_title", ""),
            "score": round(float(r.get("score", 0.0)), 4),
            "text": r.get("text", ""),
        }
        for r in rows
    ]


def grounded_context(book_dir: Path, question: str, top_k: int = 8) -> str:
    rows = search_index(book_dir, question, top_k=top_k)
    return build_context(rows)


def read_chapter(book_dir: Path, ref: str) -> str:
    chap_dir = book_dir / "canonical" / "chapters"
    if not chap_dir.exists():
        return ""
    ref = (ref or "").strip()
    files = sorted(chap_dir.glob("*.md"))
    target = None
    if ref.isdigit():
        prefix = ref.zfill(3)
        target = next((f for f in files if f.stem[:3] == prefix), None)
    if target is None and ref:
        low = ref.lower()
        target = next((f for f in files if low in f.name.lower()), None)
        if target is None:
            for f in files:
                head = f.read_text(encoding="utf-8", errors="ignore")[:200].lower()
                if low in head:
                    target = f
                    break
    if target is None:
        return ""
    return target.read_text(encoding="utf-8", errors="ignore")[:MAX_CHAPTER_CHARS]


def get_concepts(book_dir: Path) -> list[dict]:
    p = book_dir / "knowledge" / "concepts.jsonl"
    return read_jsonl(p) if p.exists() else []


def get_claims(book_dir: Path) -> list[dict]:
    p = book_dir / "knowledge" / "claims.jsonl"
    return read_jsonl(p) if p.exists() else []


def get_analysis(book_dir: Path, section: str) -> str:
    key = ANALYSIS_FILES.get((section or "").strip().lower())
    ana = book_dir / "analysis"
    if not ana.exists():
        return ""
    if key is None:
        # prova match diretto sul nome file
        m = next((f for f in ana.glob("*.md") if (section or "").lower() in f.name.lower()), None)
        return m.read_text(encoding="utf-8", errors="ignore") if m else ""
    # i file iniziano con NN_ ; mappiamo via numero o via parola chiave nel nome
    num = next((k for k, v in ANALYSIS_FILES.items() if v == key and k.isdigit()), None)
    target = None
    if num:
        target = next((f for f in ana.glob(f"{num}_*.md")), None)
    if target is None:
        target = next((f for f in ana.glob("*.md") if key in f.name.lower()), None)
    return target.read_text(encoding="utf-8", errors="ignore") if target else ""


def get_prompt_text(book_dir: Path, name: str) -> str:
    mapping = {
        "dialogue_integrated": book_dir / "dialogue" / "dialogue_protocol.md",
        "dialogue": book_dir / "dialogue" / "dialogue_protocol.md",
        "simulated_author": book_dir / "personas" / "simulated_author.md",
        "persona": book_dir / "personas" / "main_dialogue_persona.md",
        "reader_reflection": book_dir / "reader_reflection" / "reader_reflection.md",
    }
    p = mapping.get((name or "").strip().lower())
    if p and p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    return ""


def resolve_book_dir(argv: list[str] | None = None) -> Path:
    argv = argv if argv is not None else sys.argv[1:]
    if argv:
        return Path(argv[0]).expanduser().resolve()
    env = os.environ.get("BOOK_TWIN_DIR")
    if env:
        return Path(env).expanduser().resolve()
    raise SystemExit(
        "Specifica la cartella del Book Twin: `book-twin-mcp <cartella>` "
        "oppure imposta BOOK_TWIN_DIR."
    )


# --------------------------------------------------------------------------- #
# Cablaggio FastMCP (richiede il pacchetto opzionale `mcp`)
# --------------------------------------------------------------------------- #
def build_server(book_dir: Path):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - dipende dall'ambiente
        raise SystemExit(
            "Il server MCP richiede il pacchetto 'mcp'. Installa con: pip install 'book-twin-engine[mcp]'"
        ) from exc

    meta = book_metadata(book_dir)
    title = meta.get("title", book_dir.name)
    author = meta.get("author", "Autore")
    mcp = FastMCP(f"book-twin: {title}")

    @mcp.tool()
    def search(query: str, top_k: int = 8, hybrid: bool = True) -> list[dict]:
        """Cerca nel libro (FTS5/BM25 + embedding se disponibili). Ritorna chunk con id, capitolo, testo."""
        return search_book(book_dir, query, top_k=top_k, hybrid=hybrid)

    @mcp.tool()
    def context(question: str, top_k: int = 8) -> str:
        """Recupera e assembla il contesto testuale piu rilevante per una domanda, pronto per rispondere."""
        return grounded_context(book_dir, question, top_k=top_k)

    @mcp.tool()
    def chapter(ref: str) -> str:
        """Leggi il testo canonico di un capitolo per numero (es. '3') o per titolo (sottostringa)."""
        return read_chapter(book_dir, ref)

    @mcp.tool()
    def chapters() -> list[dict]:
        """Elenca i capitoli canonici (numero, titolo, file)."""
        return list_chapters(book_dir)

    @mcp.tool()
    def concepts() -> list[dict]:
        """Concetti chiave estratti dall'analisi."""
        return get_concepts(book_dir)

    @mcp.tool()
    def claims() -> list[dict]:
        """Tesi/affermazioni estratte dall'analisi."""
        return get_claims(book_dir)

    @mcp.tool()
    def analysis(section: str) -> str:
        """Leggi un file di analisi: numero '00'-'08' o parola chiave (tesi, mappa, concetti, limiti, ...)."""
        return get_analysis(book_dir, section)

    @mcp.resource("book://metadata")
    def _metadata() -> str:
        return yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)

    @mcp.resource("book://analysis/{section}")
    def _analysis(section: str) -> str:
        return get_analysis(book_dir, section)

    @mcp.resource("book://chapter/{ref}")
    def _chapter(ref: str) -> str:
        return read_chapter(book_dir, ref)

    @mcp.prompt()
    def dialogue_integrated() -> str:
        """Protocollo di dialogo integrato, vincolato al testo del libro."""
        protocol = get_prompt_text(book_dir, "dialogue_integrated")
        return (
            f"Sono {author}, in simulazione testualmente vincolata: parliamo.\n\n"
            f"Usa i tool (search, context, chapter, analysis) per fondare ogni risposta sul testo. "
            f"Distingui [testo]/[inferenza]/[speculazione] e cita gli ID dei chunk.\n\n{protocol}"
        )

    @mcp.prompt()
    def simulated_author() -> str:
        """Persona dell'autore simulato in prima persona (vincolata al testo)."""
        return get_prompt_text(book_dir, "simulated_author")

    return mcp


def main() -> None:
    book_dir = resolve_book_dir()
    if not book_dir.exists():
        raise SystemExit(f"Cartella non trovata: {book_dir}")
    build_server(book_dir).run()


if __name__ == "__main__":
    main()
