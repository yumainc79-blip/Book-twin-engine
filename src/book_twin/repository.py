"""Layout Book Twin v2 (PROGETTO.md §3): ingest deterministico e packaging.

L'ingest produce solo artefatti deterministici (testo canonico, chunk, indice,
STATUS): nessun placeholder di analisi — l'analisi entra via `booktwin commit-*`.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import __version__ as ENGINE_VERSION
from .models import BookDocument, Chunk
from .status import init_status, load_status, log_event, save_status, sha256_text
from .structure import apply_overrides, chunk_text, load_override, split_chapters
from .utils import (
    append_log,
    first_non_empty_line,
    safe_write_text,
    slugify,
    write_json,
    write_jsonl,
)

DEFAULT_PART_CHARS = 20_000
OVERRIDE_FILE_NAME = "chapters.override.yaml"


def split_parts(text: str, part_chars: int = DEFAULT_PART_CHARS) -> list[str]:
    """Divide un capitolo in parti di ~part_chars su confini di paragrafo.

    Deterministica: stesso testo → stesse parti. Sempre ≥1 parte.
    """
    if len(text) <= part_chars:
        return [text]
    paragraphs = re.split(r"(\n\s*\n)", text)  # conserva i separatori
    parts: list[str] = []
    buf = ""
    for piece in paragraphs:
        if buf and len(buf) + len(piece) > part_chars:
            parts.append(buf)
            buf = piece.lstrip("\n")
        else:
            buf += piece
        # paragrafo singolo più lungo di part_chars: taglio duro
        while len(buf) > part_chars:
            parts.append(buf[:part_chars])
            buf = buf[part_chars:]
    if buf.strip():
        parts.append(buf)
    return parts or [text]


def chapter_file_name(order: int, title: str) -> str:
    return f"{order:03d}_{slugify(title, 60)}.md"


def _segment_book(full_text: str, override_path: Path | None,
                  events: list[str]) -> list:
    """split_chapters + override opzionale, con ID v2 e log eventi."""
    dropped: list[dict] = []
    chapters = split_chapters(full_text, events=events, dropped=dropped)
    if override_path is not None:
        actions = load_override(override_path)
        chapters = apply_overrides(chapters, dropped, actions, events)
        events.append(f"override applicato da {Path(override_path).name} ({len(actions)} azioni)")
    for ch in chapters:
        ch.id = f"ch{ch.order:03d}"
    return chapters


def _chunks_v2(chapters: list) -> list[Chunk]:
    chunks = chunk_text(chapters)
    counters: dict[str, int] = {}
    for c in chunks:
        counters[c.chapter_id] = counters.get(c.chapter_id, 0) + 1
        c.id = f"chunk_{c.chapter_id}_{counters[c.chapter_id]:04d}"
    return chunks


def _page_at(pages_map: list[dict], offset: int) -> int | None:
    page = None
    for entry in pages_map:
        if entry["offset"] <= offset:
            page = entry["page"]
        else:
            break
    return page


def _assign_chunk_pages(full_text: str, chapters: list, chunks: list[Chunk],
                        pages_map: list[dict]) -> None:
    """Popola page_start/page_end nei chunk dalla pages_map (solo PDF).
    Best-effort: il chunk viene localizzato nel testo canonico per prefisso."""
    chapter_offset = {ch.id: full_text.find(ch.text[:80]) for ch in chapters}
    for c in chunks:
        base = chapter_offset.get(c.chapter_id, -1)
        start = full_text.find(c.text[:60], max(base, 0))
        if start < 0:
            continue
        end_probe = full_text.find(c.text[-60:], start)
        end = (end_probe + 60) if end_probe >= 0 else (start + len(c.text))
        c.page_start = _page_at(pages_map, start)
        c.page_end = _page_at(pages_map, end)


def create_book_repository(
    source_path: Path,
    out_dir: Path,
    language: str,
    full_text: str,
    pages: list,
    metadata: dict,
    force: bool = False,
    part_chars: int = DEFAULT_PART_CHARS,
    override_path: Path | None = None,
) -> tuple[BookDocument, list[Chunk]]:
    out_dir = Path(out_dir)
    if out_dir.exists():
        if not force:
            raise FileExistsError(f"La cartella {out_dir} esiste già. Usa --force per sovrascrivere.")
        shutil.rmtree(out_dir)

    for d in [
        "canonical/chapters",
        "canonical/notes",
        "analysis/chapters",
        "analysis/rendered",
        "knowledge",
        "sessions",
        "logs",
    ]:
        (out_dir / d).mkdir(parents=True, exist_ok=True)

    title = metadata.get("title") or first_non_empty_line(full_text, Path(source_path).stem)
    author = metadata.get("author") or metadata.get("creator") or "Autore"

    # ID v2: chapter_id = chNNN (stabile sull'ordine), chunk_chNNN_MMMM scopato
    # per capitolo. Re-ingest di testo invariato → ID invariati.
    events: list[str] = []
    chapters = _segment_book(full_text, override_path, events)
    chunks = _chunks_v2(chapters)

    pages_map = metadata.get("pages_map") or []
    if pages_map:
        write_json(out_dir / "canonical" / "pages_map.json", pages_map)
        _assign_chunk_pages(full_text, chapters, chunks, pages_map)

    notes = metadata.get("notes") or []
    if notes:
        body = "\n\n".join(f"[n.{n['ref']}] {n.get('text') or '(testo non risolto)'}"
                           for n in notes)
        safe_write_text(out_dir / "canonical" / "notes" / "notes.md",
                        f"# Note estratte (best-effort)\n\n{body}\n")

    doc = BookDocument(
        title=title,
        source_path=str(source_path),
        language=language,
        full_text=full_text,
        pages=pages,
        chapters=chapters,
        metadata={**metadata, "author": author},
    )

    safe_write_text(out_dir / "canonical" / "book.md", full_text)
    chapter_hashes: dict[str, str] = {}
    status_chapters: list[dict] = []
    for ch in chapters:
        name = chapter_file_name(ch.order, ch.title)
        safe_write_text(out_dir / "canonical" / "chapters" / name, ch.text)
        h = sha256_text(ch.text)
        chapter_hashes[ch.id] = h
        status_chapters.append({
            "id": ch.id,
            "title": ch.title,
            "file": name,
            "hash": h,
            "parts_total": len(split_parts(ch.text, part_chars)),
        })

    rows = []
    for c in chunks:
        row = c.to_json()
        row["chapter_hash"] = chapter_hashes.get(c.chapter_id, "")
        rows.append(row)
    write_jsonl(out_dir / "knowledge" / "chunks.jsonl", rows)
    for name in ["claims", "concepts", "questions", "objections", "applications"]:
        write_jsonl(out_dir / "knowledge" / f"{name}.jsonl", [])

    safe_write_text(
        out_dir / "book.config.yaml",
        yaml.safe_dump(
            {
                "title": title,
                "author": author,
                "language": language,
                "source_path": str(source_path),
                "engine_version": ENGINE_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "ingested",
                "part_chars": part_chars,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )

    status = init_status(out_dir, book_hash=sha256_text(full_text), chapters=status_chapters)
    for ev in events:
        log_event(status, ev)
        append_log(out_dir, f"- {ev}")
    save_status(out_dir, status)

    if override_path is not None:
        # l'override applicato fa parte del twin: riproducibile dalla tripla
        # (libro, engine, override)
        shutil.copyfile(override_path, out_dir / OVERRIDE_FILE_NAME)

    append_log(out_dir, f"- Ingest completato da `{source_path}`.")
    append_log(out_dir, f"- Capitoli rilevati: {len(chapters)}.")
    append_log(out_dir, f"- Chunk generati: {len(chunks)}.")
    return doc, chunks


def restructure_twin(book_dir: Path, override_path: Path) -> list:
    """Ri-segmenta il twin da canonical/book.md applicando l'override.

    Consentito SOLO a zero capitoli committati: il checkpoint struttura del
    RUNBOOK avviene prima del loop di analisi, così la rinumerazione non può
    mai rompere citazioni esistenti.
    """
    book_dir = Path(book_dir)
    status = load_status(book_dir)
    committed = [cid for cid, c in status["chapters"].items() if c["status"] == "committed"]
    if committed:
        raise ValueError(
            "restructure rifiutato: capitoli già committati ("
            + ", ".join(sorted(committed))
            + "). L'override struttura è consentito solo prima del loop di analisi; "
            "per ripartire usa `booktwin ingest --force --override`."
        )

    full_text = (book_dir / "canonical" / "book.md").read_text(encoding="utf-8")
    cfg = yaml.safe_load((book_dir / "book.config.yaml").read_text(encoding="utf-8")) or {}
    part_chars = int(cfg.get("part_chars", DEFAULT_PART_CHARS))

    events: list[str] = []
    chapters = _segment_book(full_text, override_path, events)
    chunks = _chunks_v2(chapters)

    pages_map_path = book_dir / "canonical" / "pages_map.json"
    if pages_map_path.exists():
        pages_map = json.loads(pages_map_path.read_text(encoding="utf-8"))
        _assign_chunk_pages(full_text, chapters, chunks, pages_map)

    # Riscrivi capitoli canonici, chunk e STATUS (log preservato).
    chapters_dir = book_dir / "canonical" / "chapters"
    for f in chapters_dir.glob("*.md"):
        f.unlink()
    chapter_hashes: dict[str, str] = {}
    status_chapters: list[dict] = []
    for ch in chapters:
        name = chapter_file_name(ch.order, ch.title)
        safe_write_text(chapters_dir / name, ch.text)
        h = sha256_text(ch.text)
        chapter_hashes[ch.id] = h
        status_chapters.append({
            "id": ch.id, "title": ch.title, "file": name, "hash": h,
            "parts_total": len(split_parts(ch.text, part_chars)),
        })
    rows = []
    for c in chunks:
        row = c.to_json()
        row["chapter_hash"] = chapter_hashes.get(c.chapter_id, "")
        rows.append(row)
    write_jsonl(book_dir / "knowledge" / "chunks.jsonl", rows)

    old_log = status.get("log", [])
    status = init_status(book_dir, book_hash=status["book_hash"], chapters=status_chapters)
    status["log"] = old_log
    for ev in events:
        log_event(status, ev)
        append_log(book_dir, f"- {ev}")
    log_event(status, "restructure applicato")
    save_status(book_dir, status)

    shutil.copyfile(override_path, book_dir / OVERRIDE_FILE_NAME)

    from .indexer import build_index
    build_index(book_dir)
    append_log(book_dir, f"- restructure: {len(chapters)} capitoli, {len(chunks)} chunk.")
    return chapters


# --------------------------------------------------------------------------- #
# PACK — MANIFEST.json + ZIP (complete | partial)
# --------------------------------------------------------------------------- #
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def twin_completeness(status: dict) -> str:
    """'complete' se tutti i capitoli e la sintesi sono committati, altrimenti 'partial'."""
    all_chapters = all(c["status"] == "committed" for c in status["chapters"].values())
    if all_chapters and status["synthesis"] == "committed":
        return "complete"
    return "partial"


def pack_twin(book_dir: Path) -> Path:
    """MANIFEST.json + ZIP `<dir>.zip`. Uno ZIP parziale è legale (§1.4)."""
    book_dir = Path(book_dir)
    status = load_status(book_dir)
    completeness = twin_completeness(status)

    hashed_files: dict[str, str] = {}
    for pattern in ["knowledge/*.jsonl", "analysis/chapters/*.json", "analysis/synthesis.json",
                    "STATUS.json", "canonical/book.md", OVERRIDE_FILE_NAME]:
        for f in sorted(book_dir.glob(pattern)):
            if f.is_file():
                hashed_files[f.relative_to(book_dir).as_posix()] = _sha256_file(f)

    # Le directory vuote del layout (es. sessions/, canonical/notes/) non
    # sopravvivono allo ZIP: placeholder .gitkeep così il twin estratto
    # passa validate.
    for d in sorted(book_dir.rglob("*")):
        if d.is_dir() and not any(d.iterdir()):
            (d / ".gitkeep").write_text("", encoding="utf-8")

    manifest = {
        "engine_version": ENGINE_VERSION,
        "packed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": completeness,
        "book_hash": status["book_hash"],
        "chapters_total": len(status["chapters"]),
        "chapters_committed": sum(
            1 for c in status["chapters"].values() if c["status"] == "committed"
        ),
        "synthesis": status["synthesis"],
        "author_model": status["author_model"],
        "files": hashed_files,
    }
    (book_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if completeness == "complete":
        status["phase"] = "packed"
    log_event(status, f"pack eseguito: {completeness}")
    save_status(book_dir, status)

    # book.config.yaml.status allineato alla fase corrente di STATUS.json.
    cfg_path = book_dir / "book.config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg["status"] = status["phase"]
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")

    zip_path = book_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(book_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f"{book_dir.name}/{f.relative_to(book_dir).as_posix()}")
    append_log(book_dir, f"- pack: {zip_path.name} ({completeness}).")
    return zip_path
