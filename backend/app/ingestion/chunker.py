"""T-008: turn raw document bytes into chunk texts + metadata.

Two shapes, per database.md section 4's ``metadata.kind``:

- Prose (``.md``/``.txt``/``.pdf``): heading/paragraph-aware splits, target
  ~400 tokens with 15% overlap so a fact near a chunk boundary still has
  context on both sides. No tokenizer dependency is added for this - tokens
  are approximated as whitespace-separated words, which is close enough for
  a target chunk size (not a token-accounting hard rule anywhere in scope).
- Structured (``.csv``/``.json`` rows, and ``catalog_items``): one chunk per
  record, rendered as a flat "key: value, ..." text form - no LLM formats
  these, it's a deterministic string join.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pypdf import PdfReader

TARGET_CHUNK_WORDS = 400
OVERLAP_RATIO = 0.15


@dataclass(frozen=True)
class Chunk:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def extract_text(body: bytes, ext: str) -> str:
    """Raw bytes -> plain text, dispatched on file extension."""
    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(body))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return body.decode("utf-8")


def chunk_prose(text: str, *, source: str) -> list[Chunk]:
    """Paragraph-aware sliding window, ~400 words per chunk, 15% overlap.

    Headings (markdown ``#`` lines) naturally start their own paragraph once
    surrounded by blank lines, which is how most prose documents are written,
    so no separate heading-detection pass is needed.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[list[str]] = []
    current: list[str] = []
    current_words = 0
    overlap_words = max(1, int(TARGET_CHUNK_WORDS * OVERLAP_RATIO))

    for paragraph in paragraphs:
        words = paragraph.split()
        if current and current_words + len(words) > TARGET_CHUNK_WORDS:
            chunks.append(current)
            tail = " ".join(current).split()[-overlap_words:]
            current = list(tail)
            current_words = len(current)
        current.extend(words)
        current_words += len(words)

    if current:
        chunks.append(current)

    return [
        Chunk(
            content=" ".join(words),
            metadata={"source": source, "chunk_index": i, "kind": "prose"},
        )
        for i, words in enumerate(chunks)
    ]


def _render_record(record: dict[str, Any]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in record.items() if value not in (None, ""))


def chunk_csv(body: bytes, *, source: str) -> list[Chunk]:
    text = body.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    return [
        Chunk(
            content=_render_record(row),
            metadata={"source": source, "chunk_index": i, "kind": "structured_record"},
        )
        for i, row in enumerate(rows)
    ]


def chunk_json(body: bytes, *, source: str) -> list[Chunk]:
    data = json.loads(body.decode("utf-8"))
    records = data if isinstance(data, list) else [data]
    return [
        Chunk(
            content=_render_record(record) if isinstance(record, dict) else str(record),
            metadata={"source": source, "chunk_index": i, "kind": "structured_record"},
        )
        for i, record in enumerate(records)
    ]


def chunk_document(body: bytes, ext: str, *, source: str) -> list[Chunk]:
    """Dispatch on extension: prose splitting for .md/.txt/.pdf, one chunk per
    record for .csv/.json."""
    if ext == ".csv":
        return chunk_csv(body, source=source)
    if ext == ".json":
        return chunk_json(body, source=source)
    return chunk_prose(extract_text(body, ext), source=source)


def chunk_catalog_item(item_id: str, name: str, description: str, price_cents: int | None) -> Chunk:
    price_part = f" (${price_cents / 100:.2f})" if price_cents is not None else ""
    content = f"{name}: {description}{price_part}" if description else f"{name}{price_part}"
    return Chunk(content=content, metadata={"kind": "catalog_item", "catalog_item_id": item_id})
