from __future__ import annotations

import re
import statistics

from .models import Chapter, Chunk
from .utils import slugify, normalize_whitespace

# Heading Markdown: livello = numero di '#'.
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
# Capitoli/Parti dichiarati testualmente (riga senza '#'), usati come fallback.
TEXT_CHAPTER_RE = re.compile(
    r"^\s*(capitolo|chapter|parte|part)\s+([0-9]+|[ivxlcdm]+|[a-zàèéìòù]+)\b.*$",
    re.IGNORECASE,
)
# Paratesto da scartare (front/back matter) quando drop_frontmatter=True.
# I drop sono loggati e reversibili con l'azione `undrop` dell'override:
# l'aggressività è sicura per design.
FRONTBACK_RE = re.compile(
    r"^\s*("
    r"indice|sommario|copyright|frontespizio|il libro|l['’]autore|colophon|"
    r"bibliografia|ringraziamenti|nota dell['’]autore|indice dei nomi|note|"
    r"contents|landmarks|table of contents|index|"
    r"letture di approfondimento|per approfondire|approfondimenti|"
    r"indice analitico|indice delle figure|indice delle tavole|"
    r"elenco delle abbreviazioni|abbreviazioni|glossario|crediti|"
    r"fonti delle illustrazioni|riferimenti bibliografici|"
    r"bibliography|further reading|acknowledg(e)?ments|glossary"
    r")\b",
    re.IGNORECASE,
)


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """Ritorna [(line_idx, level, title)] per ogni heading Markdown."""
    out: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            title = m.group(2).strip()
            if title and len(title) <= 160:
                out.append((idx, len(m.group(1)), title))
    return out


def _segment_lengths(boundaries: list[int], total_lines: int, lines: list[str]) -> list[int]:
    lengths: list[int] = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else total_lines
        lengths.append(len("\n".join(lines[start:end])))
    return lengths


def _choose_level(headings: list[tuple[int, int, str]], lines: list[str],
                  min_segments: int = 2, max_segments: int = 80,
                  min_median: int = 700) -> int | None:
    """Sceglie il livello di heading PIÙ ALTO (shallow) che dia una segmentazione sensata.

    Preferenza: 2..80 segmenti con lunghezza mediana >= min_median.
    Se nessun livello soddisfa la mediana, si rilassa al livello shallow con 2..80 segmenti.
    """
    levels = sorted({lvl for _, lvl, _ in headings})
    relaxed_fallback: int | None = None
    for lvl in levels:
        boundaries = [idx for idx, l, _ in headings if l == lvl]
        count = len(boundaries)
        if not (min_segments <= count <= max_segments):
            continue
        if relaxed_fallback is None:
            relaxed_fallback = lvl
        median_len = statistics.median(_segment_lengths(boundaries, len(lines), lines))
        if median_len >= min_median:
            return lvl
    return relaxed_fallback


DIVIDER_MAX_CHARS = 200
_BODY_LINE_CHARS = 80


def _is_divider(ch: Chapter) -> bool:
    """Divisore (es. 'PARTE PRIMA'): segmento <200 char e senza paragrafo di corpo
    (nessuna riga non-heading sopra gli 80 char)."""
    if len(ch.text) >= DIVIDER_MAX_CHARS:
        return False
    for line in ch.text.splitlines():
        s = line.strip()
        if s and not HEADING_RE.match(line) and len(s) > _BODY_LINE_CHARS:
            return False
    return True


def _merge_dividers(chapters: list[Chapter], events: list[str]) -> list[Chapter]:
    """La fusione automatica si applica SOLO ai divisori (STEP 4); ogni fusione
    viene loggata."""
    merged: list[Chapter] = []
    for ch in chapters:
        if merged and _is_divider(ch):
            prev = merged[-1]
            prev.text = (prev.text + "\n\n" + ch.text).strip()
            events.append(f"merge: divisore '{ch.title}' fuso nel precedente '{prev.title}'")
        else:
            merged.append(ch)
    # Divisori iniziali: assorbiti dal successivo.
    while len(merged) > 1 and _is_divider(merged[0]):
        events.append(f"merge: divisore iniziale '{merged[0].title}' fuso in '{merged[1].title}'")
        merged[1].text = (merged[0].text + "\n\n" + merged[1].text).strip()
        merged.pop(0)
    return merged


def _renumber(chapters: list[Chapter]) -> list[Chapter]:
    order = 1
    for ch in chapters:
        if ch.title == "Materiale introduttivo":
            ch.order = 0
            ch.id = "chapter_000"
            continue
        ch.order = order
        ch.id = f"chapter_{order:03d}_{slugify(ch.title, 48)}"
        order += 1
    return chapters


def _build(boundaries: list[int], titles: list[str], lines: list[str],
           drop_frontmatter: bool, events: list[str],
           dropped: list[dict]) -> list[Chapter]:
    raw: list[Chapter] = []
    seq = 0

    # Materiale prima del primo capitolo.
    first = boundaries[0]
    if first > 0:
        pre = "\n".join(lines[:first]).strip()
        if len(pre) > 300:
            ch = Chapter(id="chapter_000", title="Materiale introduttivo", order=0, text=pre)
            ch._seq = seq  # posizione originale (per undrop)
            raw.append(ch)
    seq += 1

    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(lines)
        title = titles[i]
        body = "\n".join(lines[start:end]).strip()
        seq += 1
        if drop_frontmatter and FRONTBACK_RE.match(title):
            dropped.append({"title": title, "text": body, "seq": seq})
            events.append(f"drop: paratesto '{title}' scartato (FRONTBACK_RE; reversibile con undrop)")
            continue
        ch = Chapter(id="tmp", title=title, order=0, text=body)
        ch._seq = seq
        raw.append(ch)

    return _renumber(_merge_dividers(raw, events))


def split_chapters(
    text: str,
    drop_frontmatter: bool = True,
    events: list[str] | None = None,
    dropped: list[dict] | None = None,
) -> list[Chapter]:
    events = events if events is not None else []
    dropped = dropped if dropped is not None else []
    text = normalize_whitespace(text)
    lines = text.splitlines()
    headings = _headings(lines)

    if headings:
        level = _choose_level(headings, lines)
        if level is not None:
            sel = [(idx, title) for idx, lvl, title in headings if lvl == level]
            boundaries = [idx for idx, _ in sel]
            titles = [t for _, t in sel]
            chapters = _build(boundaries, titles, lines, drop_frontmatter, events, dropped)
            if len(chapters) >= 2 or (len(chapters) == 1 and len(chapters[0].text) >= DIVIDER_MAX_CHARS):
                return chapters

    # Fallback 1: capitoli dichiarati testualmente.
    text_bounds = [(i, ln.strip()) for i, ln in enumerate(lines) if TEXT_CHAPTER_RE.match(ln)]
    if len(text_bounds) >= 2:
        boundaries = [i for i, _ in text_bounds]
        titles = [t for _, t in text_bounds]
        chapters = _build(boundaries, titles, lines, drop_frontmatter, events, dropped)
        if len(chapters) >= 2:
            return chapters

    # Fallback finale.
    return [Chapter(id="chapter_001", title="Libro completo", order=1, text=text)]


# --------------------------------------------------------------------------- #
# Override struttura: chapters.override.yaml (merge, split_at, rename, drop, undrop)
# --------------------------------------------------------------------------- #
class OverrideError(ValueError):
    pass


def load_override(path) -> list[dict]:
    import yaml
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise OverrideError("override non valido: atteso `actions: [...]`")
    return actions


def _find_by_order(chapters: list[Chapter], order: int, action: str) -> Chapter:
    for ch in chapters:
        if ch.order == order:
            return ch
    raise OverrideError(f"{action}: capitolo {order} inesistente")


def apply_overrides(
    chapters: list[Chapter],
    dropped: list[dict],
    actions: list[dict],
    events: list[str],
) -> list[Chapter]:
    """Applica le azioni dell'override e rinumera. I numeri di capitolo nelle
    azioni si riferiscono alla numerazione CORRENTE al momento dell'azione
    (ogni azione rinumera)."""
    chapters = list(chapters)
    for n, act in enumerate(actions):
        kind = (act.get("action") or "").strip().lower()
        if kind == "merge":
            orders = act.get("chapters") or []
            if len(orders) < 2:
                raise OverrideError(f"azione {n} merge: servono ≥2 capitoli")
            targets = [_find_by_order(chapters, o, "merge") for o in orders]
            base = targets[0]
            for t in targets[1:]:
                base.text = (base.text + "\n\n" + t.text).strip()
                chapters.remove(t)
            events.append(f"override merge: {orders} → '{base.title}'")
        elif kind == "split_at":
            ch = _find_by_order(chapters, int(act.get("chapter", -1)), "split_at")
            marker = act.get("at") or ""
            pos = ch.text.find(marker)
            if not marker or pos <= 0:
                raise OverrideError(
                    f"azione {n} split_at: marker non trovato nel capitolo {ch.order}: {marker!r}"
                )
            new_title = act.get("title") or marker.lstrip("# ").strip()[:80]
            rest = ch.text[pos:].strip()
            ch.text = ch.text[:pos].strip()
            new_ch = Chapter(id="tmp", title=new_title, order=ch.order + 1, text=rest)
            chapters.insert(chapters.index(ch) + 1, new_ch)
            events.append(f"override split_at: capitolo {ch.order} diviso → '{new_title}'")
        elif kind == "rename":
            ch = _find_by_order(chapters, int(act.get("chapter", -1)), "rename")
            old = ch.title
            ch.title = act.get("title") or ch.title
            events.append(f"override rename: '{old}' → '{ch.title}'")
        elif kind == "drop":
            ch = _find_by_order(chapters, int(act.get("chapter", -1)), "drop")
            chapters.remove(ch)
            dropped.append({"title": ch.title, "text": ch.text,
                            "seq": getattr(ch, "_seq", 10_000)})
            events.append(f"override drop: capitolo '{ch.title}' scartato")
        elif kind == "undrop":
            wanted = (act.get("title") or "").strip().lower()
            match = next(
                (d for d in dropped if wanted and wanted in d["title"].strip().lower()), None
            )
            if match is None:
                titles = ", ".join(d["title"] for d in dropped) or "(nessuno)"
                raise OverrideError(
                    f"azione {n} undrop: '{act.get('title')}' non tra i segmenti scartati: {titles}"
                )
            dropped.remove(match)
            new_ch = Chapter(id="tmp", title=match["title"], order=0, text=match["text"])
            new_ch._seq = match.get("seq", 10_000)
            insert_at = next(
                (i for i, c in enumerate(chapters)
                 if getattr(c, "_seq", -1) > new_ch._seq),
                len(chapters),
            )
            chapters.insert(insert_at, new_ch)
            events.append(f"override undrop: '{match['title']}' ripristinato")
        else:
            raise OverrideError(f"azione {n}: tipo sconosciuto {act.get('action')!r}")
        chapters = _renumber(chapters)
    return chapters


def chunk_text(chapters: list[Chapter], target_chars: int = 2200, overlap_chars: int = 250) -> list[Chunk]:
    chunks: list[Chunk] = []
    order = 1
    for chapter in chapters:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter.text) if p.strip()]
        buf = ""
        for p in paragraphs:
            if len(buf) + len(p) + 2 <= target_chars:
                buf = (buf + "\n\n" + p).strip()
            else:
                if buf:
                    chunks.append(
                        Chunk(
                            id=f"chunk_{order:05d}",
                            chapter_id=chapter.id,
                            chapter_title=chapter.title,
                            order=order,
                            text=buf,
                            page_start=chapter.page_start,
                            page_end=chapter.page_end,
                        )
                    )
                    order += 1
                    tail = buf[-overlap_chars:] if overlap_chars > 0 else ""
                    buf = (tail + "\n\n" + p).strip()
                else:
                    for i in range(0, len(p), target_chars):
                        part = p[i : i + target_chars]
                        chunks.append(
                            Chunk(
                                id=f"chunk_{order:05d}",
                                chapter_id=chapter.id,
                                chapter_title=chapter.title,
                                order=order,
                                text=part,
                                page_start=chapter.page_start,
                                page_end=chapter.page_end,
                            )
                        )
                        order += 1
                    buf = ""
        if buf:
            chunks.append(
                Chunk(
                    id=f"chunk_{order:05d}",
                    chapter_id=chapter.id,
                    chapter_title=chapter.title,
                    order=order,
                    text=buf,
                    page_start=chapter.page_start,
                    page_end=chapter.page_end,
                )
            )
            order += 1
    return chunks
