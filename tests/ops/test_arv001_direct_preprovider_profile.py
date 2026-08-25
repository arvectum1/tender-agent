from __future__ import annotations

import hashlib
import json

import pytest

from scripts.arv001 import run_complete_corpus_acceptance as runner
from scripts.arv001.corpus_hash_resolver import BoundCorpusHashResolver


def _bound_physical() -> tuple[list[dict[str, object]], str]:
    physical = [
        {
            "original_name": "B.xml",
            "sha256": "b" * 64,
            "size_bytes": 20,
            "ignored": "not-bound",
        },
        {
            "original_name": "A.xml",
            "sha256": "a" * 64,
            "size_bytes": 10,
            "ignored": "not-bound",
        },
    ]
    projected = [
        {key: item[key] for key in ("original_name", "sha256", "size_bytes")}
        for item in sorted(physical, key=lambda item: str(item["original_name"]))
    ]
    payload = (
        json.dumps(
            projected,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return physical, hashlib.sha256(payload).hexdigest()


def test_bound_resolver_profile_satisfies_direct_preprovider_diagnostic_contract() -> None:
    physical, expected_sha = _bound_physical()
    resolver = BoundCorpusHashResolver(expected_sha)

    assert resolver(physical) == expected_sha
    assert resolver.profile is not None

    profile = runner._verified_diagnostic_bound_profile(
        resolver.profile.sanitized(), expected_sha
    )

    assert profile == {
        "fields": ["original_name", "sha256", "size_bytes"],
        "serialization": "canonical_compact_newline",
        "sha256": expected_sha,
        "ordering": "original_name_unicode_codepoint_ascending",
    }


def test_direct_preprovider_diagnostic_contract_stays_fail_closed_without_profile() -> None:
    _, expected_sha = _bound_physical()

    with pytest.raises(
        runner.AcceptanceBlocked,
        match="^diagnostic_bound_corpus_hash_profile_missing_or_invalid$",
    ):
        runner._verified_diagnostic_bound_profile(None, expected_sha)
