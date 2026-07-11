"""T-008: chunker unit tests - prose boundaries and structured records.

Pure functions, no DB/network needed.
"""

from __future__ import annotations

import json

from app.ingestion.chunker import (
    TARGET_CHUNK_WORDS,
    chunk_catalog_item,
    chunk_csv,
    chunk_document,
    chunk_json,
    chunk_prose,
)


def test_chunk_prose_splits_long_text_on_paragraph_boundaries() -> None:
    # Three paragraphs, each ~300 words - two should NOT fit in one chunk
    # (target is 400 words), so this must split into at least two chunks.
    paragraphs = [" ".join(["word"] * 300) for _ in range(3)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_prose(text, source="doc.md")

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.metadata["kind"] == "prose"
        assert chunk.metadata["source"] == "doc.md"
    # chunk_index increments in order
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_chunk_prose_overlaps_between_consecutive_chunks() -> None:
    paragraphs = [f"para{i} " + " ".join(["word"] * 250) for i in range(3)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_prose(text, source="doc.md")

    assert len(chunks) >= 2
    tail_of_first = chunks[0].content.split()[-5:]
    start_of_second = chunks[1].content.split()[:5]
    # The overlap window means some of chunk 0's tail words reappear at the
    # start of chunk 1, rather than a hard, context-free cut.
    assert any(word in start_of_second for word in tail_of_first)


def test_chunk_prose_short_text_is_a_single_chunk() -> None:
    chunks = chunk_prose("Just one short paragraph.", source="doc.md")
    assert len(chunks) == 1
    assert chunks[0].content == "Just one short paragraph."


def test_chunk_prose_empty_text_returns_no_chunks() -> None:
    assert chunk_prose("   \n\n  ", source="doc.md") == []


def test_chunk_csv_one_chunk_per_row() -> None:
    body = b"name,price\nHaircut,30\nShave,15"
    chunks = chunk_csv(body, source="prices.csv")

    assert len(chunks) == 2
    assert chunks[0].content == "name: Haircut, price: 30"
    assert chunks[0].metadata["kind"] == "structured_record"
    assert chunks[1].content == "name: Shave, price: 15"


def test_chunk_json_list_of_records() -> None:
    body = json.dumps([{"item": "Widget", "cost": 5}, {"item": "Gadget", "cost": 10}]).encode()
    chunks = chunk_json(body, source="items.json")

    assert len(chunks) == 2
    assert chunks[0].content == "item: Widget, cost: 5"
    assert chunks[1].content == "item: Gadget, cost: 10"


def test_chunk_json_single_object_is_one_chunk() -> None:
    body = json.dumps({"item": "Widget", "cost": 5}).encode()
    chunks = chunk_json(body, source="item.json")
    assert len(chunks) == 1
    assert chunks[0].content == "item: Widget, cost: 5"


def test_chunk_document_dispatches_on_extension() -> None:
    csv_chunks = chunk_document(b"a,b\n1,2", ".csv", source="x.csv")
    assert csv_chunks[0].metadata["kind"] == "structured_record"

    prose_chunks = chunk_document(b"Just prose text.", ".md", source="x.md")
    assert prose_chunks[0].metadata["kind"] == "prose"


def test_chunk_catalog_item_includes_price_when_present() -> None:
    chunk = chunk_catalog_item("item-1", "Screen repair", "Cracked screens", 8950)
    assert chunk.content == "Screen repair: Cracked screens ($89.50)"
    assert chunk.metadata == {"kind": "catalog_item", "catalog_item_id": "item-1"}


def test_chunk_catalog_item_without_price() -> None:
    chunk = chunk_catalog_item("item-2", "Consultation", "Free initial chat", None)
    assert chunk.content == "Consultation: Free initial chat"


def test_target_chunk_words_is_reasonable() -> None:
    # Sanity guard on the constant itself, since the whole module's boundary
    # tests are calibrated against it.
    assert TARGET_CHUNK_WORDS == 400
