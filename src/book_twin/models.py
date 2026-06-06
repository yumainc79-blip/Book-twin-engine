from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class Page:
    page_number: int
    text: str


@dataclass
class Chapter:
    id: str
    title: str
    order: int
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class Chunk:
    id: str
    chapter_id: str
    chapter_title: str
    order: int
    text: str
    page_start: int | None = None
    page_end: int | None = None
    summary: str = ""
    keywords: list[str] | None = None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        if data["keywords"] is None:
            data["keywords"] = []
        return data


@dataclass
class BookDocument:
    title: str
    source_path: str
    language: str
    full_text: str
    pages: list[Page]
    chapters: list[Chapter]
    metadata: dict[str, Any]
