from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.arv001.complete_corpus_contract import (
    AcceptanceBlocked,
    _resolve_regular_file,
    prepare_documents,
)
from src.tender_research import document_text_extractor


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_resolves_renamed_intake_file_by_frozen_content_identity(tmp_path: Path) -> None:
    payload = b"frozen-eis-source-bytes"
    renamed = tmp_path / "01-normalized-source.xml"
    renamed.write_bytes(payload)

    resolved = _resolve_regular_file(
        tmp_path,
        "original-eis-source.xml",
        expected_sha256=_sha256(payload),
        expected_size_bytes=len(payload),
    )

    assert resolved == renamed.resolve()


def test_prepare_documents_uses_frozen_identity_when_intake_name_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"real-frozen-eis-bytes"
    renamed = tmp_path / "01-normalized-source.xml"
    renamed.write_bytes(payload)
    original_name = "original-eis-source.xml"

    monkeypatch.setattr(
        document_text_extractor,
        "extract_text",
        lambda _path, *, max_chars: (
            document_text_extractor.EXTRACTED_STATUS,
            "deterministic extracted procurement text",
        ),
    )

    prepared = prepare_documents(
        physical=[
            {
                "original_name": original_name,
                "sha256": _sha256(payload),
                "size_bytes": len(payload),
                "content_type": "application/xml",
                "document_kind": "notice",
                "source_type": "EIS",
            }
        ],
        metadata={
            "files": [
                {
                    "original_name": original_name,
                    "stored_name": original_name,
                    "source_url": None,
                }
            ]
        },
        intake_root=tmp_path,
        max_chars=10_000,
        chunk_size=1_000,
        chunk_overlap=100,
    )

    assert len(prepared) == 1
    assert prepared[0].original_name == original_name
    assert prepared[0].stored_name == original_name
    assert prepared[0].path == renamed.resolve()
    assert prepared[0].sha256 == _sha256(payload)
    assert prepared[0].size_bytes == len(payload)


def test_wrong_name_candidate_does_not_override_matching_frozen_identity(
    tmp_path: Path,
) -> None:
    expected = b"expected-frozen-bytes"
    (tmp_path / "original-eis-source.xml").write_bytes(b"wrong-bytes")
    renamed = tmp_path / "01-normalized-source.xml"
    renamed.write_bytes(expected)

    resolved = _resolve_regular_file(
        tmp_path,
        "original-eis-source.xml",
        expected_sha256=_sha256(expected),
        expected_size_bytes=len(expected),
    )

    assert resolved == renamed.resolve()


def test_duplicate_content_identity_fails_closed_as_ambiguous(tmp_path: Path) -> None:
    payload = b"duplicate-frozen-bytes"
    (tmp_path / "first.xml").write_bytes(payload)
    (tmp_path / "second.xml").write_bytes(payload)

    with pytest.raises(AcceptanceBlocked, match="^stored_file_mapping_not_unique$"):
        _resolve_regular_file(
            tmp_path,
            "missing-original.xml",
            expected_sha256=_sha256(payload),
            expected_size_bytes=len(payload),
        )


def test_missing_content_identity_fails_closed(tmp_path: Path) -> None:
    payload = b"present-but-not-expected"
    (tmp_path / "renamed.xml").write_bytes(payload)

    with pytest.raises(AcceptanceBlocked, match="^stored_file_identity_not_found$"):
        _resolve_regular_file(
            tmp_path,
            "original.xml",
            expected_sha256=_sha256(b"different"),
            expected_size_bytes=len(b"different"),
        )


def test_unsafe_stored_name_remains_rejected(tmp_path: Path) -> None:
    payload = b"bytes"

    with pytest.raises(AcceptanceBlocked, match="^stored_name_unsafe$"):
        _resolve_regular_file(
            tmp_path,
            "../outside.xml",
            expected_sha256=_sha256(payload),
            expected_size_bytes=len(payload),
        )
