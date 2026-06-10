from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .commit import CommitError, commit_chapter, commit_synthesis, render_twin
from .converters import ConversionError, read_book
from .indexer import build_context, build_index, search_index
from .repository import (
    DEFAULT_PART_CHARS,
    create_book_repository,
    pack_twin,
    restructure_twin,
    split_parts,
)
from .structure import OverrideError
from .status import load_status, render_status
from .validation import validate_twin

app = typer.Typer(help="Book Twin Engine: toolkit deterministico per Book Twin LLM-native.")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"booktwin {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Mostra la versione dell'engine ed esci.",
    ),
) -> None:
    """Book Twin Engine."""


def _chapter_id(num: int) -> str:
    return f"ch{num:03d}"


def _fail(message: str, code: int = 1) -> None:
    console.print(f"[red]Errore:[/red] {message}")
    raise typer.Exit(code)


@app.command()
def ingest(
    source: Path = typer.Argument(..., exists=True, help="Libro sorgente."),
    out: Path = typer.Option(..., "--out", "-o", help="Cartella di output del Book Twin."),
    language: str = typer.Option("it", "--language", "-l", help="Lingua principale."),
    force: bool = typer.Option(False, "--force", help="Sovrascrivi output esistente."),
    part_chars: int = typer.Option(
        DEFAULT_PART_CHARS, "--part-chars",
        help="Dimensione (~caratteri) delle parti di lettura dei capitoli.",
    ),
    embeddings: bool = typer.Option(
        True, "--embeddings/--no-embeddings",
        help="Calcola embedding locali (se sentence-transformers è disponibile).",
    ),
    override: Path = typer.Option(
        None, "--override", exists=True,
        help="chapters.override.yaml con azioni merge/split_at/rename/drop/undrop.",
    ),
):
    """Estrazione + segmentazione + chunk + indice + STATUS (layout v2)."""
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
            part_chars=part_chars,
            override_path=override,
        )
        build_index(out, embeddings=embeddings)
    except ConversionError as e:
        _fail(f"conversione: {e}")
    except Exception as e:
        _fail(str(e))

    console.print(f"[green]Book Twin creato:[/green] {out}")
    console.print(f"Titolo: {doc.title}")
    console.print(f"Capitoli: {len(doc.chapters)}")
    console.print(f"Chunk: {len(chunks)}")
    console.print("Prossimo passo: `booktwin status` per vedere il piano di analisi.")


@app.command()
def restructure(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    override: Path = typer.Option(..., "--override", exists=True,
                                  help="chapters.override.yaml da applicare."),
):
    """Ri-segmenta il twin con l'override (solo a zero capitoli committati)."""
    try:
        chapters = restructure_twin(book_dir, override)
    except (OverrideError, ValueError, FileNotFoundError) as e:
        _fail(str(e))
    console.print(f"[green]Restructure applicato:[/green] {len(chapters)} capitoli.")
    console.print("Verifica con `booktwin status`.")


@app.command()
def status(book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin.")):
    """Stato leggibile: fase, capitoli fatti/mancanti, prossima azione."""
    try:
        console.print(render_status(load_status(book_dir)))
    except FileNotFoundError as e:
        _fail(str(e))


@app.command()
def chapter(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    number: int = typer.Argument(..., help="Numero del capitolo (es. 4 per ch004)."),
    part: str = typer.Option(
        None, "--part", help="Parte da leggere, formato i/k (es. 2/3).",
    ),
    parts: bool = typer.Option(
        False, "--parts", help="Stampa solo quante parti servono per questo capitolo.",
    ),
):
    """Stampa il testo canonico del capitolo (intero o una parte i/k)."""
    try:
        st = load_status(book_dir)
    except FileNotFoundError as e:
        _fail(str(e))
    cid = _chapter_id(number)
    if cid not in st["chapters"]:
        _fail(f"capitolo inesistente: {cid} (esistono: {', '.join(sorted(st['chapters']))})")
    info = st["chapters"][cid]
    text = (book_dir / "canonical" / "chapters" / info["file"]).read_text(encoding="utf-8")

    import yaml
    cfg = yaml.safe_load((book_dir / "book.config.yaml").read_text(encoding="utf-8")) or {}
    pieces = split_parts(text, int(cfg.get("part_chars", DEFAULT_PART_CHARS)))

    if parts:
        console.print(str(len(pieces)))
        return
    if part is None:
        if len(pieces) > 1:
            console.print(
                f"[yellow]Nota:[/yellow] {cid} ha {len(pieces)} parti; "
                f"per la lettura integrale a pezzi usa --part i/{len(pieces)}."
            )
        print(f"=== {cid} — {info['title']} (1/1) ===")
        print(text)
        return
    try:
        i_s, k_s = part.split("/")
        i, k = int(i_s), int(k_s)
    except ValueError:
        _fail("formato --part non valido: usa i/k, es. 2/3")
    if k != len(pieces):
        _fail(f"questo capitolo ha {len(pieces)} parti, non {k}: usa --part i/{len(pieces)}")
    if not (1 <= i <= k):
        _fail(f"parte fuori intervallo: {i}/{k}")
    print(f"=== {cid} — {info['title']} (parte {i}/{k}) ===")
    print(pieces[i - 1])


@app.command("commit-chapter")
def commit_chapter_cmd(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    number: int = typer.Argument(..., help="Numero del capitolo (es. 4 per ch004)."),
    file: Path = typer.Option(..., "--file", "-f", help="Scheda capitolo JSON."),
):
    """Valida (schema + chunk_ids + anchors + coverage) e registra la scheda."""
    try:
        commit_chapter(book_dir, _chapter_id(number), file)
    except (CommitError, FileNotFoundError) as e:
        _fail(f"commit rifiutato: {e}")
    console.print(f"[green]commit-chapter {_chapter_id(number)} accettato.[/green]")


@app.command("commit-synthesis")
def commit_synthesis_cmd(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    file: Path = typer.Option(..., "--file", "-f", help="Sintesi JSON."),
):
    """Valida e scrive la sintesi; aggrega i JSONL knowledge."""
    try:
        commit_synthesis(book_dir, file)
    except (CommitError, FileNotFoundError) as e:
        _fail(f"commit rifiutato: {e}")
    console.print("[green]commit-synthesis accettato.[/green]")


@app.command()
def index(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    embeddings: bool = typer.Option(
        True, "--embeddings/--no-embeddings",
        help="Calcola embedding locali (se sentence-transformers è disponibile).",
    ),
):
    """Crea o ricrea l'indice SQLite FTS (+ embedding opzionali)."""
    db = build_index(book_dir, embeddings=embeddings)
    console.print(f"[green]Indice creato:[/green] {db}")


@app.command()
def search(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    query: str = typer.Argument(..., help="Query di ricerca."),
    top_k: int = typer.Option(8, "--top-k", "-k"),
    hybrid: bool = typer.Option(
        True, "--hybrid/--no-hybrid",
        help="Fonde FTS + embedding (se disponibili). --no-hybrid usa solo FTS.",
    ),
):
    """Cerca nel libro tramite indice testuale (+ semantico se disponibile)."""
    rows = search_index(book_dir, query, top_k=top_k, hybrid=hybrid)
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
def context(
    book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin."),
    question: str = typer.Argument(..., help="Domanda."),
    top_k: int = typer.Option(8, "--top-k", "-k"),
):
    """Stampa il contesto assemblato (header [chunk_id | capitolo]); la risposta la dà l'LLM."""
    rows = search_index(book_dir, question, top_k=top_k)
    print(build_context(rows))


@app.command()
def render(book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin.")):
    """Genera i .md derivati dai JSON committati in analysis/rendered/."""
    written = render_twin(book_dir)
    console.print(f"[green]Render completato:[/green] {len(written)} file in analysis/rendered/")


@app.command()
def pack(book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin.")):
    """Valida → MANIFEST.json → ZIP (status complete|partial dichiarato)."""
    report = validate_twin(book_dir)
    if not report.ok:
        console.print(report.render())
        _fail("pack annullato: la validazione strutturale fallisce")
    zip_path = pack_twin(book_dir)
    import json
    manifest = json.loads((Path(book_dir) / "MANIFEST.json").read_text(encoding="utf-8"))
    console.print(f"[green]ZIP creato:[/green] {zip_path} (status: {manifest['status']})")


@app.command()
def validate(book_dir: Path = typer.Argument(..., exists=True, help="Cartella Book Twin.")):
    """Validazione strutturale completa del layout v2. Esce ≠0 se fallisce."""
    report = validate_twin(book_dir)
    console.print(report.render())
    if not report.ok:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
