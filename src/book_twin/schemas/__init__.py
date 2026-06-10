"""JSON Schema degli artefatti di analisi (PROGETTO.md §5).

I controlli che richiedono i dati del twin (esistenza dei chunk_ids, anchors
nel testo, coverage vs STATUS) sono in `commit.py`: qui c'è solo la forma.
"""
from __future__ import annotations

CHAPTER_ID_PATTERN = r"^ch\d{3}$"
CHUNK_ID_PATTERN = r"^chunk_ch\d{3}_\d{4}$"

_NONEMPTY = {"type": "string", "minLength": 1}
_CHUNK_IDS = {
    "type": "array",
    "minItems": 1,
    "items": {"type": "string", "pattern": CHUNK_ID_PATTERN},
}

# §5.2 — Scheda capitolo analysis/chapters/chNNN.json
CHAPTER_CARD_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "chapter_id", "title", "coverage", "funzione", "riassunto", "tesi",
        "concetti", "claims", "passaggi", "domande", "obiezioni",
        "applicazioni", "cosa_memorizzare",
    ],
    "properties": {
        "chapter_id": {"type": "string", "pattern": CHAPTER_ID_PATTERN},
        "title": _NONEMPTY,
        "coverage": {
            "type": "object",
            "required": ["parts_read", "parts_total"],
            "properties": {
                "parts_read": {"type": "integer", "minimum": 0},
                "parts_total": {"type": "integer", "minimum": 1},
            },
        },
        "funzione": _NONEMPTY,
        "riassunto": {"type": "string", "minLength": 300},
        "tesi": _NONEMPTY,
        "concetti": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "definition", "chunk_ids"],
                "properties": {
                    "name": _NONEMPTY,
                    "definition": _NONEMPTY,
                    "chunk_ids": _CHUNK_IDS,
                },
            },
        },
        "claims": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["claim", "tipo", "chunk_ids"],
                "properties": {
                    "claim": _NONEMPTY,
                    "tipo": {"type": "string", "enum": ["testo", "inferenza"]},
                    "chunk_ids": _CHUNK_IDS,
                    "anchors": {"type": "array", "items": _NONEMPTY},
                },
            },
        },
        "passaggi": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["testo", "chunk_id"],
                "properties": {
                    "testo": _NONEMPTY,
                    "chunk_id": {"type": "string", "pattern": CHUNK_ID_PATTERN},
                },
            },
        },
        "domande": {"type": "array", "items": _NONEMPTY},
        "obiezioni": {"type": "array", "items": _NONEMPTY},
        "applicazioni": {"type": "array", "items": _NONEMPTY},
        "cosa_memorizzare": _NONEMPTY,
        # Facoltativo: summary per chunk, ricopiate in chunks.jsonl al commit.
        "chunk_summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["chunk_id", "summary"],
                "properties": {
                    "chunk_id": {"type": "string", "pattern": CHUNK_ID_PATTERN},
                    "summary": _NONEMPTY,
                },
            },
        },
    },
}

# §5.3 — analysis/synthesis.json
SYNTHESIS_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "tesi_centrale", "formula", "mappa", "argomentazione",
        "concetti_globali", "domande_profonde", "limiti", "collegamenti_esterni",
    ],
    "properties": {
        "tesi_centrale": _NONEMPTY,
        "formula": _NONEMPTY,
        "mappa": {"type": "array", "minItems": 1, "items": _NONEMPTY},
        "argomentazione": _NONEMPTY,
        "concetti_globali": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "definition", "chapter_ids"],
                "properties": {
                    "name": _NONEMPTY,
                    "definition": _NONEMPTY,
                    "chapter_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "pattern": CHAPTER_ID_PATTERN},
                    },
                },
            },
        },
        "domande_profonde": {"type": "array", "minItems": 1, "items": _NONEMPTY},
        "limiti": {"type": "array", "minItems": 1, "items": _NONEMPTY},
        "collegamenti_esterni": {"type": "array", "items": _NONEMPTY},
    },
}
