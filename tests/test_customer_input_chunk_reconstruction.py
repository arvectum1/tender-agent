from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.modules.customer_pilot.input_resolver import (
    _reconstruct_persisted_document_text,
)


def _chunk(index: int, start: int | None, end: int | None, text: str):
    return SimpleNamespace(
        chunk_index=index,
        char_start=start,
        char_end=end,
        text=text,
    )


def test_reconstructs_overlapping_chunks_without_duplication():
    original = (
        '<purchaseObject><name>Топливо дизельное</name>'
        '<quantity>140</quantity><okpd2>19.20.21.300</okpd2></purchaseObject>'
    )
    split = 64
    overlap = 18
    chunks = [
        _chunk(0, 0, split, original[:split]),
        _chunk(1, split - overlap, len(original), original[split - overlap :]),
    ]

    rebuilt = _reconstruct_persisted_document_text(chunks)

    assert rebuilt == original
    assert "Топливо дизельное" in rebuilt
    assert "140" in rebuilt
    assert "19.20.21.300" in rebuilt


def test_reconstruction_preserves_trimmed_boundary_gaps_as_whitespace():
    chunks = [
        _chunk(0, 0, 3, "ABC"),
        _chunk(1, 5, 8, "DEF"),
    ]

    assert _reconstruct_persisted_document_text(chunks) == "ABC  DEF"


def test_reconstruction_fails_closed_on_conflicting_overlap():
    chunks = [
        _chunk(0, 0, 4, "ABCD"),
        _chunk(1, 2, 6, "XXEF"),
    ]

    with pytest.raises(HTTPException) as caught:
        _reconstruct_persisted_document_text(chunks)

    assert caught.value.status_code == 409
    assert caught.value.detail == (
        "Persisted procurement intake chunks overlap inconsistently"
    )


def test_legacy_chunks_without_offsets_keep_historical_join_behavior():
    chunks = [
        _chunk(0, None, None, "first"),
        _chunk(1, None, None, "second"),
    ]

    assert _reconstruct_persisted_document_text(chunks) == "first\n\nsecond"
