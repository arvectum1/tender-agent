from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.arv001.complete_corpus_contract import (
    AcceptanceBlocked,
    _resolve_regular_file,
)


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
