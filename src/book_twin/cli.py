from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .analyzer import analyze_book
from .converters import ConversionError, read_book
from .indexer import build_index, search_index
from .qa import answer_question
from .repository import create_book_repository

app = typer.Typer(help="Create AI-native Book Twin repositories.")
console = Console()


@app.command()
def ingest(
    source: Path = typer.Argument(..., exists=True, help="Libro sorgente."),
    out: Path = typer.Option(..., "--out", "-o", help="Cartella di output del Book Twin."),
    language: str = typer.Option("it", "--language", "-l", help="Lingua principale."),
    force: bool = typer.Option(False, "--force", help="Sovrascrivi output esistente."),
):
    """Importa un libro e crea la cartella Book Twin."""
    try:
        text, pages, metadata = read_book(source)
        doc, chunks = create_book_repository(
            source_path=source,
            out_dir=out,
            language=language,
            full_text=text,
            pages=pages,
            metadata=metadata,
            force=force,
        )
        db = build_index(out)
    except ConversionError as e:
        console.print(f"[red]Errore conversione:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Errore:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Book Twin creato:[/green] {out}")
    console.print(f"Titolo: {doc.title}")
    console.print(f"Capitoli: {len(doc.chapters)}")
    console.print(f"Chunk: {len(chunks)}")
    console.print(f"Indice: {db}")


@app.command()
def index(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
):
    """Crea o ricrea l'indice SQLite FTS."""
    db = build_index(book_dir)
    console.print(f"[green]Indice creato:[/green] {db}")


@app.command()
def search(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    query: str = typer.Argument(..., help="Query di ricerca."),
    top_k: int = typer.Option(8, "--top-k", "-k"),
):
    """Cerca nel libro tramite indice testuale."""
    rows = search_index(book_dir, query, top_k=top_k)
    table = Table(title=f"Risultati per: {query}")
    table.add_column("Chunk")
    table.add_column("Capitolo")
    table.add_column("Estratto")

    for r in rows:
        excerpt = (r.get("text") or "").replace("\n", " ")
        if len(excerpt) > 220:
            excerpt = excerpt[:220] + "..."
        table.add_row(r.get("id", ""), r.get("chapter_title", ""), excerpt)
    console.print(table)


@app.command()
def ask(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    question: str = typer.Argument(..., help="Domanda da porre al libro."),
    provider: str = typer.Option("none", "--provider", help="none | openai | ollama"),
    model: Optional[str] = typer.Option(None, "--model"),
    mode: str = typer.Option("faithful", "--mode", help="faithful | simulated_author | critical | socratic"),
):
    """Risponde a una domanda usando retrieval sui chunk."""
    answer = answer_question(book_dir, question, provider=provider, model=model, mode=mode)
    console.print(answer)


@app.command()
def analyze(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    provider: str = typer.Option("none", "--provider", help="none | openai | ollama"),
    model: Optional[str] = typer.Option(None, "--model"),
):
    """Genera analisi Markdown e conoscenza strutturata."""
    analyze_book(book_dir, provider=provider, model=model)
    console.print(f"[green]Analisi completata:[/green] {book_dir / 'analysis'}")


@app.command()
def init_drive_layout(
    root: Path = typer.Argument(..., help="Cartella radice, per esempio Google Drive/Book Twins."),
):
    """Crea una struttura biblioteca pronta per Google Drive."""
    for d in ["_system/templates", "_system/prompts", "_catalog", "books", "exports"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "_catalog" / "catalog.md").write_text("# Catalogo Book Twins\n\n", encoding="utf-8")
    (root / "_catalog" / "catalog.json").write_text('{"books": []}\n', encoding="utf-8")
    console.print(f"[green]Layout Drive creato:[/green] {root}")


if __name__ == "__main__":
    app()
