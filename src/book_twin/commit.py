"""Commit validati degli artefatti di analisi (PROGETTO.md §1.2, §5).

La fedeltà è imposta in scrittura: ogni artefatto entra solo da qui, validato
con JSON Schema + regole deterministiche sul twin (chunk_ids esistenti e del
capitolo giusto, anchors presenti nei chunk citati, coverage completo).
Commit fallito = CommitError con messaggio esatto: l'LLM corregge e riprova.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import jsonschema

from .indexer import build_index
from .schemas import CHAPTER_CARD_SCHEMA, SYNTHESIS_SCHEMA
from .status import (
    load_status,
    log_event,
    mark_chapter_committed,
    mark_synthesis_committed,
    pending_chapters,
    save_status,
)
from .utils import append_log, read_jsonl, write_jsonl


class CommitError(Exception):
    """Commit rifiutato: il messaggio dice esattamente cosa correggere."""


def normalize_for_anchor(s: str) -> str:
    """Normalizzazione per il confronto anchors: lowercase, deaccento,
    whitespace compresso (PROGETTO.md §5.2)."""
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", s).strip()


def _load_json(path: Path, what: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise CommitError(f"File non trovato: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CommitError(f"{what}: JSON non valido ({e})")


def _schema_check(data: dict, schema: dict, what: str) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        e = errors[0]
        where = "/".join(str(p) for p in e.absolute_path) or "(radice)"
        raise CommitError(f"{what}: schema violato in `{where}`: {e.message}")


def _chunks_by_id(book_dir: Path) -> dict[str, dict]:
    rows = read_jsonl(book_dir / "knowledge" / "chunks.jsonl")
    return {r["id"]: r for r in rows}


def _check_chunk_ids(chunk_ids: list[str], chapter_id: str, chunks: dict[str, dict],
                     context: str) -> None:
    for cid in chunk_ids:
        if cid not in chunks:
            raise CommitError(f"{context}: chunk_id inesistente: {cid}")
        owner = chunks[cid].get("chapter_id", "")
        if owner != chapter_id:
            raise CommitError(
                f"{context}: chunk_id {cid} appartiene a {owner}, non a {chapter_id}"
            )


def _check_anchor(anchor: str, chunk_ids: list[str], chunks: dict[str, dict],
                  context: str) -> None:
    norm = normalize_for_anchor(anchor)
    if len(norm.split()) < 3:
        raise CommitError(f"{context}: anchor troppo corta (minimo 3 parole): {anchor!r}")
    for cid in chunk_ids:
        if norm in normalize_for_anchor(chunks[cid].get("text", "")):
            return
    raise CommitError(
        f"{context}: anchor non trovata nei chunk citati {chunk_ids}: {anchor!r}"
    )


def card_path(book_dir: Path, chapter_id: str) -> Path:
    return Path(book_dir) / "analysis" / "chapters" / f"{chapter_id}.json"


def _log_rejection(book_dir: Path, status: dict, what: str, error: CommitError) -> None:
    """Registra in STATUS.log anche i commit rifiutati (timestamp + motivo)."""
    reason = str(error).replace("\n", " ")
    if len(reason) > 200:
        reason = reason[:200] + "…"
    log_event(status, f"{what} rifiutato: {reason}")
    save_status(book_dir, status)


def commit_chapter(book_dir: Path, chapter_id: str, card_file: Path) -> dict:
    """Valida e registra la scheda capitolo. Ritorna la card accettata."""
    book_dir = Path(book_dir)
    status = load_status(book_dir)
    try:
        return _commit_chapter_checked(book_dir, status, chapter_id, card_file)
    except CommitError as e:
        _log_rejection(book_dir, status, f"commit-chapter {chapter_id}", e)
        raise


def _commit_chapter_checked(book_dir: Path, status: dict, chapter_id: str,
                            card_file: Path) -> dict:
    card = _load_json(card_file, "scheda capitolo")
    _schema_check(card, CHAPTER_CARD_SCHEMA, "scheda capitolo")

    if chapter_id not in status["chapters"]:
        known = ", ".join(sorted(status["chapters"]))
        raise CommitError(f"capitolo sconosciuto: {chapter_id} (esistono: {known})")
    if card["chapter_id"] != chapter_id:
        raise CommitError(
            f"chapter_id della scheda ({card['chapter_id']}) diverso dal capitolo "
            f"richiesto ({chapter_id})"
        )

    # Anti-troncamento: coverage completo e coerente con STATUS.
    parts_total = status["chapters"][chapter_id]["parts_total"]
    cov = card["coverage"]
    if cov["parts_total"] != parts_total:
        raise CommitError(
            f"coverage.parts_total={cov['parts_total']} ma il capitolo ha "
            f"{parts_total} parti (vedi STATUS.json)"
        )
    if cov["parts_read"] != parts_total:
        raise CommitError(
            f"coverage incompleto: lette {cov['parts_read']}/{parts_total} parti. "
            f"Leggi tutte le parti con `booktwin chapter <dir> N --part i/{parts_total}` e riprova"
        )

    if normalize_for_anchor(card["tesi"]) == normalize_for_anchor(card["riassunto"]):
        raise CommitError("tesi uguale al riassunto: la tesi deve essere distinta")

    chunks = _chunks_by_id(book_dir)
    for i, con in enumerate(card["concetti"]):
        _check_chunk_ids(con["chunk_ids"], chapter_id, chunks, f"concetti[{i}] ({con['name']})")
    for i, cl in enumerate(card["claims"]):
        ctx = f"claims[{i}]"
        _check_chunk_ids(cl["chunk_ids"], chapter_id, chunks, ctx)
        anchors = cl.get("anchors") or []
        if cl["tipo"] == "testo" and not anchors:
            raise CommitError(f"{ctx}: tipo 'testo' richiede almeno una anchor")
        for a in anchors:
            _check_anchor(a, cl["chunk_ids"], chunks, ctx)
    for i, p in enumerate(card.get("passaggi", [])):
        _check_chunk_ids([p["chunk_id"]], chapter_id, chunks, f"passaggi[{i}]")
        _check_anchor(p["testo"], [p["chunk_id"]], chunks, f"passaggi[{i}]")
    for i, cs in enumerate(card.get("chunk_summaries", [])):
        _check_chunk_ids([cs["chunk_id"]], chapter_id, chunks, f"chunk_summaries[{i}]")

    # Accettata: scrivi la scheda, aggiorna chunk (summary/keywords) e indice.
    out = card_path(book_dir, chapter_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

    summaries = {cs["chunk_id"]: cs["summary"] for cs in card.get("chunk_summaries", [])}
    keywords: dict[str, list[str]] = {}
    for con in card["concetti"]:
        for cid in con["chunk_ids"]:
            keywords.setdefault(cid, [])
            if con["name"] not in keywords[cid]:
                keywords[cid].append(con["name"])
    rows = read_jsonl(book_dir / "knowledge" / "chunks.jsonl")
    for r in rows:
        if r["id"] in summaries:
            r["summary"] = summaries[r["id"]]
        if r["id"] in keywords:
            r["keywords"] = keywords[r["id"]]
    write_jsonl(book_dir / "knowledge" / "chunks.jsonl", rows)
    build_index(book_dir)

    mark_chapter_committed(status, chapter_id)
    save_status(book_dir, status)
    append_log(book_dir, f"- commit-chapter {chapter_id} accettato.")
    return card


def commit_synthesis(book_dir: Path, synthesis_file: Path) -> dict:
    """Valida e scrive la sintesi; aggrega i JSONL knowledge dalle schede."""
    book_dir = Path(book_dir)
    status = load_status(book_dir)
    try:
        return _commit_synthesis_checked(book_dir, status, synthesis_file)
    except CommitError as e:
        _log_rejection(book_dir, status, "commit-synthesis", e)
        raise


def _commit_synthesis_checked(book_dir: Path, status: dict, synthesis_file: Path) -> dict:
    pending = pending_chapters(status)
    if pending:
        raise CommitError(
            "sintesi rifiutata: capitoli non ancora committati: " + ", ".join(sorted(pending))
        )
    data = _load_json(synthesis_file, "sintesi")
    _schema_check(data, SYNTHESIS_SCHEMA, "sintesi")
    for i, con in enumerate(data["concetti_globali"]):
        for chid in con["chapter_ids"]:
            if chid not in status["chapters"]:
                raise CommitError(
                    f"concetti_globali[{i}] ({con['name']}): chapter_id inesistente: {chid}"
                )

    (book_dir / "analysis" / "synthesis.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Aggrega i JSONL knowledge dalle schede capitolo committate.
    claims, concepts, questions, objections, applications = [], [], [], [], []
    for chid in sorted(status["chapters"]):
        card = json.loads(card_path(book_dir, chid).read_text(encoding="utf-8"))
        for cl in card["claims"]:
            claims.append({**cl, "chapter_id": chid})
        for con in card["concetti"]:
            concepts.append({**con, "chapter_id": chid})
        questions += [{"text": q, "chapter_id": chid} for q in card.get("domande", [])]
        objections += [{"text": o, "chapter_id": chid} for o in card.get("obiezioni", [])]
        applications += [{"text": a, "chapter_id": chid} for a in card.get("applicazioni", [])]
    k = book_dir / "knowledge"
    write_jsonl(k / "claims.jsonl", claims)
    write_jsonl(k / "concepts.jsonl", concepts)
    write_jsonl(k / "questions.jsonl", questions)
    write_jsonl(k / "objections.jsonl", objections)
    write_jsonl(k / "applications.jsonl", applications)

    mark_synthesis_committed(status)
    save_status(book_dir, status)
    append_log(book_dir, "- commit-synthesis accettato; knowledge JSONL aggregati.")
    return data


# --------------------------------------------------------------------------- #
# RENDER — Markdown leggibile derivato dal JSON (il JSON resta fonte di verità)
# --------------------------------------------------------------------------- #
def _md_list(items: list, fmt=lambda x: x) -> str:
    return "\n".join(f"- {fmt(i)}" for i in items) if items else "- (vuoto)"


def render_chapter_card(card: dict) -> str:
    cov = card["coverage"]
    return f"""# {card['chapter_id']} — {card['title']}

Coverage: {cov['parts_read']}/{cov['parts_total']} parti lette.

## Funzione nel libro

{card['funzione']}

## Riassunto

{card['riassunto']}

## Tesi

{card['tesi']}

## Concetti

{_md_list(card['concetti'], lambda c: f"**{c['name']}**: {c['definition']} [{', '.join(c['chunk_ids'])}]")}

## Claims

{_md_list(card['claims'], lambda c: f"[{c['tipo']}] {c['claim']} [{', '.join(c['chunk_ids'])}]")}

## Passaggi decisivi

{_md_list(card.get('passaggi', []), lambda p: f"“{p['testo']}” [{p['chunk_id']}]")}

## Domande

{_md_list(card.get('domande', []))}

## Obiezioni

{_md_list(card.get('obiezioni', []))}

## Applicazioni

{_md_list(card.get('applicazioni', []))}

## Cosa memorizzare

{card['cosa_memorizzare']}
"""


def render_synthesis(data: dict) -> str:
    return f"""# Sintesi del libro

## Tesi centrale

{data['tesi_centrale']}

## Formula

{data['formula']}

## Mappa

{_md_list(data['mappa'])}

## Argomentazione

{data['argomentazione']}

## Concetti globali

{_md_list(data['concetti_globali'], lambda c: f"**{c['name']}**: {c['definition']} [{', '.join(c['chapter_ids'])}]")}

## Domande profonde

{_md_list(data['domande_profonde'])}

## Limiti

{_md_list(data['limiti'])}

## Collegamenti esterni (speculativi)

I collegamenti seguenti vanno oltre il testo: trattali come [speculazione].

{_md_list(data.get('collegamenti_esterni', []))}
"""


def render_twin(book_dir: Path) -> list[Path]:
    """Genera i .md derivati in analysis/rendered/ dai JSON committati."""
    book_dir = Path(book_dir)
    out_dir = book_dir / "analysis" / "rendered"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for f in sorted((book_dir / "analysis" / "chapters").glob("ch*.json")):
        card = json.loads(f.read_text(encoding="utf-8"))
        p = out_dir / f"{f.stem}.md"
        p.write_text(render_chapter_card(card), encoding="utf-8")
        written.append(p)
    syn = book_dir / "analysis" / "synthesis.json"
    if syn.exists():
        data = json.loads(syn.read_text(encoding="utf-8"))
        p = out_dir / "synthesis.md"
        p.write_text(render_synthesis(data), encoding="utf-8")
        written.append(p)
    return written
