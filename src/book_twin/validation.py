"""Validazione strutturale del Book Twin v2 (PROGETTO.md §4 `validate`).

Controlla il layout §3 e la coerenza tra STATUS.json, canonical/ e gli
artefatti committati. La validazione di contenuto avviene al commit
(`commit.py`); la verifica di fedeltà delle citazioni arriva con `verify`
(STEP 5).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from .schemas import CHAPTER_CARD_SCHEMA, SYNTHESIS_SCHEMA
from .utils import read_jsonl


@dataclass
class Report:
    ok: bool = True
    checks: list[tuple[bool, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, passed: bool, label: str) -> None:
        self.checks.append((passed, label))
        if not passed:
            self.ok = False

    def render(self) -> str:
        lines = [("[PASS] " if p else "[FAIL] ") + lbl for p, lbl in self.checks]
        if self.notes:
            lines += ["", "Note:"] + [f"- {n}" for n in self.notes]
        lines += ["", ("RISULTATO: OK" if self.ok else "RISULTATO: FALLITO")]
        return "\n".join(lines)


REQUIRED_FILES = [
    "book.config.yaml",
    "STATUS.json",
    "canonical/book.md",
    "knowledge/chunks.jsonl",
]
REQUIRED_DIRS = [
    "canonical/chapters",
    "canonical/notes",
    "analysis/chapters",
    "analysis/rendered",
    "knowledge",
    "sessions",
    "logs",
]
KNOWLEDGE_JSONL = [
    "knowledge/claims.jsonl", "knowledge/concepts.jsonl", "knowledge/questions.jsonl",
    "knowledge/objections.jsonl", "knowledge/applications.jsonl",
]


def validate_twin(book_dir: Path) -> Report:
    book_dir = Path(book_dir)
    r = Report()

    for rel in REQUIRED_FILES:
        r.add((book_dir / rel).exists(), f"file presente: {rel}")
    for rel in REQUIRED_DIRS:
        p = book_dir / rel
        r.add(p.exists() and p.is_dir(), f"cartella presente: {rel}")
    for rel in KNOWLEDGE_JSONL:
        r.add((book_dir / rel).exists(), f"jsonl presente: {rel}")
    if not r.ok:
        return r

    try:
        status = json.loads((book_dir / "STATUS.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.add(False, f"STATUS.json parseable ({e})")
        return r
    for key in ["engine_version", "book_hash", "phase", "chapters", "synthesis", "author_model"]:
        r.add(key in status, f"STATUS.json contiene `{key}`")
    if not r.ok:
        return r

    # Coerenza capitoli: file canonici presenti, chunk con chapter_id noti.
    chapter_ids = set(status["chapters"])
    missing_files = [
        c["file"] for c in status["chapters"].values()
        if not (book_dir / "canonical" / "chapters" / c["file"]).exists()
    ]
    r.add(not missing_files, f"file canonici dei capitoli presenti ({len(missing_files)} mancanti)")
    if missing_files:
        r.notes.append("mancanti: " + ", ".join(missing_files[:8]))

    chunks = read_jsonl(book_dir / "knowledge" / "chunks.jsonl")
    r.add(len(chunks) > 0, f"chunks.jsonl non vuoto ({len(chunks)} chunk)")
    orphans = sorted({c.get("chapter_id", "?") for c in chunks} - chapter_ids)
    r.add(not orphans, f"chunk con chapter_id noti ({len(orphans)} orfani)")
    if orphans:
        r.notes.append("chapter_id orfani: " + ", ".join(orphans[:8]))
    bad_hash = [
        c["id"] for c in chunks
        if c.get("chapter_hash") != status["chapters"].get(c.get("chapter_id"), {}).get("hash")
    ]
    r.add(not bad_hash, f"hash capitolo coerenti nei chunk ({len(bad_hash)} incoerenti)")

    # Capitoli committati: la scheda esiste ed è valida per lo schema.
    validator = jsonschema.Draft202012Validator(CHAPTER_CARD_SCHEMA)
    for cid in sorted(chapter_ids):
        if status["chapters"][cid]["status"] != "committed":
            continue
        p = book_dir / "analysis" / "chapters" / f"{cid}.json"
        if not p.exists():
            r.add(False, f"scheda committata presente: {cid}")
            continue
        errs = list(validator.iter_errors(json.loads(p.read_text(encoding="utf-8"))))
        r.add(not errs, f"scheda valida per schema: {cid}")

    if status["synthesis"] == "committed":
        p = book_dir / "analysis" / "synthesis.json"
        if p.exists():
            errs = list(
                jsonschema.Draft202012Validator(SYNTHESIS_SCHEMA).iter_errors(
                    json.loads(p.read_text(encoding="utf-8"))
                )
            )
            r.add(not errs, "synthesis.json valida per schema")
        else:
            r.add(False, "synthesis.json presente (STATUS la dichiara committata)")

    return r
