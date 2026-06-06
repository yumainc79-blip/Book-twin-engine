from __future__ import annotations

import re

from .models import Chapter, Chunk
from .utils import slugify, normalize_whitespace


CHAPTER_PATTERNS = [
    re.compile(r"^\s{0,3}#{1,3}\s+(.+?)\s*$"),
    re.compile(r"^\s*(capitolo|chapter)\s+([0-9ivxlcdm]+|\w+)(?:\s*[-—:]\s*(.*))?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(parte|part)\s+([0-9ivxlcdm]+|\w+)(?:\s*[-—:]\s*(.*))?\s*$", re.IGNORECASE),
]


def detect_title(line: str) -> str | None:
    for pat in CHAPTER_PATTERNS:
        m = pat.match(line.strip())
        if not m:
            continue
        if line.lstrip().startswith("#"):
            return m.group(1).strip()
        return line.strip()
    return None


def split_chapters(text: str) -> list[Chapter]:
    text = normalize_whitespace(text)
    lines = text.splitlines()

    starts: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        title = detect_title(line)
        if title and len(title) <= 160:
            starts.append((idx, title))

    if not starts:
        return [Chapter(id="chapter_001", title="Libro completo", order=1, text=text)]

    chapters: list[Chapter] = []
    first_idx = starts[0][0]
    if first_idx > 5:
        pre_text = "\n".join(lines[:first_idx]).strip()
        if len(pre_text) > 300:
            chapters.append(Chapter(id="chapter_000", title="Materiale introduttivo", order=0, text=pre_text))

    for pos, (start_idx, title) in enumerate(starts, start=1):
        end_idx = starts[pos][0] if pos < len(starts) else len(lines)
        ch_text = "\n".join(lines[start_idx:end_idx]).strip()
        cid = f"chapter_{pos:03d}_{slugify(title, 48)}"
        chapters.append(Chapter(id=cid, title=title, order=pos, text=ch_text))

    tiny = sum(1 for c in chapters if len(c.text) < 500)
    if len(chapters) > 20 and tiny / len(chapters) > 0.65:
        return [Chapter(id="chapter_001", title="Libro completo", order=1, text=text)]

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
