from __future__ import annotations

import sqlite3
from pathlib import Path

from .utils import read_jsonl


def build_index(book_dir: Path) -> Path:
    chunks_path = book_dir / "knowledge" / "chunks.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError(f"Non trovo {chunks_path}. Prima esegui ingest.")

    db_path = book_dir / "knowledge" / "retrieval.sqlite"
    chunks = read_jsonl(chunks_path)

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("DROP TABLE IF EXISTS chunks")
        cur.execute("DROP TABLE IF EXISTS chunks_fts")
        cur.execute(
            """
            CREATE TABLE chunks (
                id TEXT PRIMARY KEY,
                chapter_id TEXT,
                chapter_title TEXT,
                ord INTEGER,
                text TEXT,
                summary TEXT,
                keywords TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                id UNINDEXED,
                chapter_id UNINDEXED,
                chapter_title,
                text,
                summary,
                keywords
            )
            """
        )
        for row in chunks:
            keywords = ", ".join(row.get("keywords") or [])
            cur.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row.get("chapter_id", ""),
                    row.get("chapter_title", ""),
                    row.get("order", 0),
                    row.get("text", ""),
                    row.get("summary", ""),
                    keywords,
                ),
            )
            cur.execute(
                "INSERT INTO chunks_fts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row.get("chapter_id", ""),
                    row.get("chapter_title", ""),
                    row.get("text", ""),
                    row.get("summary", ""),
                    keywords,
                ),
            )
        con.commit()
    finally:
        con.close()

    return db_path


def search_index(book_dir: Path, query: str, top_k: int = 8) -> list[dict]:
    db_path = book_dir / "knowledge" / "retrieval.sqlite"
    if not db_path.exists():
        build_index(book_dir)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        try:
            rows = cur.execute(
                """
                SELECT c.id, c.chapter_id, c.chapter_title, c.ord, c.text,
                       bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.id
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            safe = " OR ".join([f'"{part}"' for part in query.split() if part.strip()])
            rows = cur.execute(
                """
                SELECT c.id, c.chapter_id, c.chapter_title, c.ord, c.text,
                       bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.id
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (safe or query, top_k),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()
