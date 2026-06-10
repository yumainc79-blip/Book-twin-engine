"""STATUS.json: macchina a stati per capitolo/fase (PROGETTO.md §5.1).

Lo stato è ripristinabile: uno ZIP parziale ricaricato in una sessione nuova
riprende da qui. Ogni evento rilevante viene appeso a `log`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__ as ENGINE_VERSION

PHASES = ["ingested", "analyzing", "synthesized", "author_modeled", "verified", "packed"]


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def status_path(book_dir: Path) -> Path:
    return Path(book_dir) / "STATUS.json"


def init_status(book_dir: Path, book_hash: str, chapters: list[dict]) -> dict:
    """chapters: [{"id": "ch001", "title": ..., "file": ..., "hash": ..., "parts_total": N}]"""
    status = {
        "engine_version": ENGINE_VERSION,
        "book_hash": book_hash,
        "phase": "ingested",
        "chapters": {
            c["id"]: {
                "title": c.get("title", ""),
                "file": c.get("file", ""),
                "status": "pending",
                "hash": c["hash"],
                "parts_total": c["parts_total"],
            }
            for c in chapters
        },
        "synthesis": "pending",
        "author_model": "pending",
        "log": [],
    }
    save_status(book_dir, status)
    return status


def load_status(book_dir: Path) -> dict:
    p = status_path(book_dir)
    if not p.exists():
        raise FileNotFoundError(f"STATUS.json non trovato in {book_dir}. Prima esegui ingest.")
    return json.loads(p.read_text(encoding="utf-8"))


def save_status(book_dir: Path, status: dict) -> None:
    status_path(book_dir).write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def log_event(status: dict, message: str) -> None:
    status["log"].append(f"{_now()} {message}")


def mark_chapter_committed(status: dict, chapter_id: str) -> None:
    ch = status["chapters"][chapter_id]
    ch["status"] = "committed"
    ch["committed_at"] = _now()
    if status["phase"] == "ingested":
        status["phase"] = "analyzing"
    log_event(status, f"commit-chapter {chapter_id} accettato")


def mark_synthesis_committed(status: dict) -> None:
    status["synthesis"] = "committed"
    status["phase"] = "synthesized"
    log_event(status, "commit-synthesis accettato")


def pending_chapters(status: dict) -> list[str]:
    return [cid for cid, c in status["chapters"].items() if c["status"] != "committed"]


def next_action(status: dict) -> str:
    pending = pending_chapters(status)
    if pending:
        cid = sorted(pending)[0]
        parts = status["chapters"][cid]["parts_total"]
        how = f"leggilo con `booktwin chapter <dir> {int(cid[2:])}" + (
            f" --part 1/{parts}`" if parts > 1 else "`"
        )
        return f"analizza {cid}: {how}, poi `booktwin commit-chapter <dir> {int(cid[2:])} --file card.json`"
    if status["synthesis"] != "committed":
        return "tutti i capitoli sono committati: `booktwin commit-synthesis <dir> --file synthesis.json`"
    return "analisi completa: `booktwin render <dir>` e `booktwin pack <dir>`"


def render_status(status: dict) -> str:
    done = [cid for cid, c in status["chapters"].items() if c["status"] == "committed"]
    pending = pending_chapters(status)
    lines = [
        f"Fase: {status['phase']}",
        f"Engine: {status['engine_version']}  |  book_hash: {status['book_hash'][:18]}…",
        f"Capitoli: {len(done)}/{len(status['chapters'])} committati",
    ]
    for cid in sorted(status["chapters"]):
        c = status["chapters"][cid]
        mark = "x" if c["status"] == "committed" else " "
        lines.append(f"  [{mark}] {cid}  parti: {c['parts_total']}  {c.get('title', '')}")
    lines.append(f"Sintesi: {status['synthesis']}  |  Author model: {status['author_model']}")
    if pending:
        lines.append(f"Mancanti: {', '.join(sorted(pending))}")
    lines.append(f"Prossima azione: {next_action(status)}")
    return "\n".join(lines)
