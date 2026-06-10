from __future__ import annotations

import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import snowballstemmer
import yaml

from .utils import read_jsonl

# Caratteri con significato sintattico in FTS5: rimossi prima del MATCH.
_FTS_SPECIAL_RE = re.compile(r'["():^*\\]')


def _query_tokens(q: str) -> list[str]:
    cleaned = _FTS_SPECIAL_RE.sub(" ", q or "")
    return [t for t in cleaned.split() if t]


def sanitize_query(q: str) -> str:
    """Rende sicura una query arbitraria per FTS5 MATCH.

    Rimuove i caratteri sintattici (`"():^*` e backslash) e neutralizza gli
    operatori FTS5 (AND, OR, NOT, NEAR) trattandoli come parole: ogni token
    viene quotato, quindi `"tok1" OR "tok2" …`. Stringa vuota se non resta
    alcun token.
    """
    return " OR ".join(f'"{t}"' for t in _query_tokens(q))


# --------------------------------------------------------------------------- #
# Stemming (parametrico su `language`; implementato per "it")
# --------------------------------------------------------------------------- #
_STEM_LANGS = {"it": "italian"}
_STEMMER_CACHE: dict[str, object] = {}


def get_stemmer(language: str | None):
    """Stemmer Snowball per la lingua, o None se non supportata (no-stem)."""
    key = (language or "").strip().lower()[:2]
    name = _STEM_LANGS.get(key)
    if name is None:
        return None
    if key not in _STEMMER_CACHE:
        try:
            _STEMMER_CACHE[key] = snowballstemmer.stemmer(name)
        except Exception:
            _STEMMER_CACHE[key] = None
    return _STEMMER_CACHE[key]


def _deaccent(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def stem_tokens(stemmer, text: str) -> list[str]:
    """Token stemmati e deaccentati. Deaccento PRIMA dello stemming così
    `perché` e `perche` producono lo stesso stem."""
    out = []
    for tok in re.findall(r"\w+", (text or "").lower()):
        tok = _deaccent(tok)
        if tok:
            out.append(_deaccent(stemmer.stemWord(tok)))
    return out


def _stem_text(stemmer, text: str) -> str:
    return " ".join(stem_tokens(stemmer, text)) if stemmer else ""


def _book_language(book_dir: Path) -> str | None:
    cfg = Path(book_dir) / "book.config.yaml"
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        return data.get("language")
    except Exception:
        return None

# Modello multilingue compatto, adatto all'italiano. Usato solo se
# sentence-transformers è installato E i pesi sono scaricabili localmente.
DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_EMBEDDER_CACHE: dict[str, object] = {}


def get_embedder(model_name: str | None = None):
    """Carica un embedder LOCALE (sentence-transformers) se disponibile.

    Ritorna un oggetto con metodo .encode(list[str]) -> np.ndarray, oppure None
    se la libreria non è installata o il modello non è caricabile (es. niente
    rete per scaricare i pesi). Mai un'API esterna obbligatoria: fallback a FTS.
    """
    name = model_name or DEFAULT_EMBED_MODEL
    if name in _EMBEDDER_CACHE:
        return _EMBEDDER_CACHE[name]
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = SentenceTransformer(name)
    except Exception:
        _EMBEDDER_CACHE[name] = None
        return None
    _EMBEDDER_CACHE[name] = model
    return model


def _emb_path(book_dir: Path) -> Path:
    return book_dir / "knowledge" / "embeddings.npz"


def _embed_input(row: dict) -> str:
    parts = [row.get("summary", ""), ", ".join(row.get("keywords") or []), row.get("text", "")]
    return "\n".join(p for p in parts if p).strip()


def _build_embeddings(book_dir: Path, chunks: list[dict], embedder) -> bool:
    try:
        import numpy as np

        texts = [_embed_input(r) for r in chunks]
        vecs = np.asarray(embedder.encode(texts), dtype="float32")
        if vecs.ndim != 2 or len(vecs) != len(chunks):
            return False
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
        ids = np.array([r["id"] for r in chunks], dtype=object)
        np.savez(_emb_path(book_dir), ids=ids, vectors=vecs)
        return True
    except Exception:
        return False


def build_index(
    book_dir: Path,
    embeddings: bool = True,
    embed_model: str | None = None,
    language: str | None = None,
) -> Path:
    """(Ri)costruisce l'indice FTS. Le colonne stemmate (`text_stem`,
    `summary_stem`) vengono popolate se la lingua è supportata; questo vale
    anche quando l'indice è ricostruito da commit-chapter (summary/keywords
    committati dopo l'ingest). Se `language` è None si legge da book.config.yaml.
    """
    chunks_path = book_dir / "knowledge" / "chunks.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError(f"Non trovo {chunks_path}. Prima esegui ingest.")

    db_path = book_dir / "knowledge" / "retrieval.sqlite"
    chunks = read_jsonl(chunks_path)
    stemmer = get_stemmer(language or _book_language(book_dir))

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
                keywords,
                text_stem,
                summary_stem
            )
            """
        )
        for row in chunks:
            keywords = ", ".join(row.get("keywords") or [])
            text = row.get("text", "")
            summary = row.get("summary", "")
            cur.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row.get("chapter_id", ""),
                    row.get("chapter_title", ""),
                    row.get("order", 0),
                    text,
                    summary,
                    keywords,
                ),
            )
            cur.execute(
                "INSERT INTO chunks_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row.get("chapter_id", ""),
                    row.get("chapter_title", ""),
                    text,
                    summary,
                    keywords,
                    _stem_text(stemmer, text),
                    _stem_text(stemmer, summary),
                ),
            )
        con.commit()
    finally:
        con.close()

    # Embedding opzionali, ACCANTO a FTS. Se non disponibili, FTS resta valido.
    if embeddings:
        embedder = get_embedder(embed_model)
        if embedder is not None:
            _build_embeddings(book_dir, chunks, embedder)

    return db_path


def build_context(rows: list[dict], max_chars: int = 14000) -> str:
    """Assembla il contesto dai risultati di ricerca, con header citabile."""
    parts = []
    total = 0
    for r in rows:
        header = f"[{r['id']} | {r.get('chapter_title', '')}]"
        block = f"{header}\n{r.get('text', '')}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)


def _has_stem_columns(cur) -> bool:
    try:
        cols = {r[1] for r in cur.execute("PRAGMA table_info(chunks_fts)")}
    except sqlite3.OperationalError:
        return False
    return "text_stem" in cols


def _match_expression(query: str, stemmer) -> str:
    """Espressione MATCH: colonne originali con i token sanitizzati, in OR con
    le colonne stemmate sui token stemmati (se la lingua è supportata)."""
    safe = sanitize_query(query)
    if not safe or stemmer is None:
        return safe
    stems = " OR ".join(f'"{s}"' for s in stem_tokens(stemmer, query) if s)
    if not stems:
        return safe
    return (
        f"({{chapter_title text summary keywords}} : ({safe})) "
        f"OR ({{text_stem summary_stem}} : ({stems}))"
    )


def _fts_rows(cur, query: str, limit: int, stemmer=None, legacy: bool = False) -> list[dict]:
    sql = """
        SELECT c.id, c.chapter_id, c.chapter_title, c.ord, c.text,
               bm25(chunks_fts) AS score
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.id
        WHERE chunks_fts MATCH ?
        ORDER BY score
        LIMIT ?
    """
    match = sanitize_query(query) if legacy else _match_expression(query, stemmer)
    if not match:
        return []
    try:
        rows = cur.execute(sql, (match, limit)).fetchall()
    except sqlite3.OperationalError:
        # La sanitizzazione dovrebbe rendere impossibile arrivare qui:
        # ultima rete di sicurezza, mai un crash su input arbitrario.
        return []
    return [dict(r) for r in rows]


def _semantic_ranking(book_dir: Path, query: str, limit: int, embed_model: str | None):
    """Ritorna lista di id ordinati per similarità coseno, o None se non disponibile."""
    emb_file = _emb_path(book_dir)
    if not emb_file.exists():
        return None
    embedder = get_embedder(embed_model)
    if embedder is None:
        return None
    try:
        import numpy as np

        data = np.load(emb_file, allow_pickle=True)
        ids = list(data["ids"])
        vectors = data["vectors"]
        q = np.asarray(embedder.encode([query]), dtype="float32")[0]
        n = np.linalg.norm(q)
        q = q / (n if n else 1.0)
        sims = vectors @ q
        order = np.argsort(-sims)[:limit]
        return [str(ids[i]) for i in order]
    except Exception:
        return None


def search_index(
    book_dir: Path,
    query: str,
    top_k: int = 8,
    hybrid: bool = True,
    embed_model: str | None = None,
) -> list[dict]:
    """Ricerca ibrida FTS5/BM25 + embedding (se disponibili), con fusione RRF.

    Se gli embedding non sono presenti o il modello non è caricabile, degrada in
    modo trasparente alla sola ricerca testuale FTS.
    """
    db_path = book_dir / "knowledge" / "retrieval.sqlite"
    if not db_path.exists():
        build_index(book_dir)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        legacy = not _has_stem_columns(cur)
        if legacy:
            print(
                "Nota: indice senza colonne stemmate (pre-0.5 STEP 3): ricerca senza "
                "stemming. Rigenera con `booktwin index <dir>`.",
                file=sys.stderr,
            )
        stemmer = None if legacy else get_stemmer(_book_language(book_dir))
        candidate_n = max(top_k * 3, top_k)
        fts = _fts_rows(cur, query, candidate_n, stemmer=stemmer, legacy=legacy)

        sem_ids = _semantic_ranking(book_dir, query, candidate_n, embed_model) if hybrid else None

        if not sem_ids:
            return fts[:top_k]

        # Reciprocal Rank Fusion tra ranking FTS e semantico.
        k0 = 60.0
        scores: dict[str, float] = {}
        for rank, row in enumerate(fts):
            scores[row["id"]] = scores.get(row["id"], 0.0) + 1.0 / (k0 + rank)
        for rank, cid in enumerate(sem_ids):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k0 + rank)

        fused_ids = sorted(scores, key=lambda c: -scores[c])[:top_k]
        rows = []
        for cid in fused_ids:
            r = cur.execute(
                "SELECT id, chapter_id, chapter_title, ord, text FROM chunks WHERE id = ?",
                (cid,),
            ).fetchone()
            if r:
                d = dict(r)
                d["score"] = scores[cid]
                rows.append(d)
        return rows
    finally:
        con.close()
