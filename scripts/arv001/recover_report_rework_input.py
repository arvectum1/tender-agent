#!/usr/bin/env python3
"""Recover the accepted ARV-001 canonical report for report-only rework.

The helper is read-only. It searches only caller-supplied roots for finalized
controlled-evidence manifests, matches the exact accepted ARV-001 execution
and provider-policy identity, requires byte identity with the Product Owner-
rejected report, and verifies the canonical report against the publication
SHA recorded in the manifest. It performs no provider, EIS, database, Git, or
network I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked

_MANIFEST_NAME = "controlled-evidence.manifest.json"
_MANIFEST_VERSION = "r10.1-controlled-provider-evidence-v3"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_ACCEPTED_CLAIMS = 21
_EXPECTED_BATCH_COUNT = 14
_EXPECTED_PROVIDER = "openai_compatible"
_EXPECTED_MODEL = "arvectum-gemma4-12b-it-qat-q4_0"
_EXPECTED_POLICY_VERSION = "arv001-local-provider-gemma4-it-qat-q4_0-v2"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceBlocked("recovery_manifest_unreadable_or_invalid") from exc


def _execution_matches(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    accepted = value.get("accepted_claims")
    rejected = value.get("rejected_claims")
    return bool(
        value.get("status") == "success"
        and value.get("canonical_input_eligible") is True
        and value.get("accepted_claim_count") == _EXPECTED_ACCEPTED_CLAIMS
        and isinstance(accepted, list)
        and len(accepted) == _EXPECTED_ACCEPTED_CLAIMS
        and all(
            isinstance(claim, dict) and claim.get("support_status") == "supported"
            for claim in accepted
        )
        and value.get("rejected_claim_count") == 0
        and rejected == []
        and value.get("batch_count") == _EXPECTED_BATCH_COUNT
        and value.get("provider_call_count") == _EXPECTED_BATCH_COUNT
        and value.get("retry_count") == 0
        and value.get("raw_response_stored") is False
    )


def _stable_identity_matches(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("provider") == _EXPECTED_PROVIDER
        and value.get("model") == _EXPECTED_MODEL
        and value.get("approval_policy_version") == _EXPECTED_POLICY_VERSION
        and value.get("batch_count") == _EXPECTED_BATCH_COUNT
    )


def _candidate_from_manifest(
    manifest_path: Path, *, rejected_report_sha256: str
) -> dict[str, str] | None:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return None
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        return None
    executions = manifest.get("executions")
    if (
        manifest.get("manifest_version") != _MANIFEST_VERSION
        or manifest.get("repeat_count") != 2
        or manifest.get("repeat_identity_verified") is not True
        or not _stable_identity_matches(manifest.get("stable_identity"))
        or not isinstance(executions, list)
        or len(executions) != 2
        or not all(_execution_matches(item) for item in executions)
    ):
        return None

    controlled_root = manifest_path.parent
    report_path = controlled_root / "execution-1" / "report.html"
    canonical_path = controlled_root / "execution-1" / "canonical_report.json"
    if (
        report_path.is_symlink()
        or canonical_path.is_symlink()
        or not report_path.is_file()
        or not canonical_path.is_file()
    ):
        return None
    if _sha256_file(report_path) != rejected_report_sha256:
        return None

    publication = executions[0].get("publication")
    expected_canonical_sha = (
        publication.get("canonical_report_file_sha256")
        if isinstance(publication, dict)
        else None
    )
    if (
        not isinstance(expected_canonical_sha, str)
        or not _SHA256_RE.fullmatch(expected_canonical_sha)
        or _sha256_file(canonical_path) != expected_canonical_sha
    ):
        return None

    return {
        "controlled_root": str(controlled_root.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _sha256_file(manifest_path),
        "rejected_report_path": str(report_path.resolve()),
        "rejected_report_sha256": rejected_report_sha256,
        "canonical_output_path": str(canonical_path.resolve()),
        "canonical_output_sha256": expected_canonical_sha,
    }


def recover_report_rework_input(
    *, rejected_report: Path, search_roots: list[Path]
) -> dict[str, str]:
    rejected_raw = rejected_report.expanduser()
    if rejected_raw.is_symlink() or not rejected_raw.is_file():
        raise AcceptanceBlocked("rejected_report_not_found")
    rejected = rejected_raw.resolve()
    if not search_roots:
        raise AcceptanceBlocked("recovery_search_roots_missing")
    rejected_sha = _sha256_file(rejected)

    manifests: dict[str, Path] = {}
    for raw_root in search_roots:
        expanded = raw_root.expanduser()
        if expanded.is_symlink() or not expanded.is_dir():
            continue
        root = expanded.resolve()
        for path in root.rglob(_MANIFEST_NAME):
            if path.is_symlink() or not path.is_file():
                continue
            manifests.setdefault(str(path.resolve()), path)

    matches: list[dict[str, str]] = []
    for manifest_path in sorted(manifests.values(), key=lambda item: str(item.resolve())):
        candidate = _candidate_from_manifest(
            manifest_path, rejected_report_sha256=rejected_sha
        )
        if candidate is not None:
            matches.append(candidate)

    if not matches:
        raise AcceptanceBlocked("accepted_controlled_evidence_not_found")
    if len(matches) != 1:
        raise AcceptanceBlocked("accepted_controlled_evidence_ambiguous")
    return matches[0]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover the exact accepted ARV-001 canonical report read-only."
    )
    parser.add_argument("--rejected-report", type=Path, required=True)
    parser.add_argument(
        "--search-root",
        type=Path,
        action="append",
        required=True,
        help="Root to scan recursively; repeat for multiple private roots.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    result = recover_report_rework_input(
        rejected_report=args.rejected_report,
        search_roots=list(args.search_root),
    )
    print(
        json.dumps(
            {
                "status": "accepted_report_rework_input_recovered",
                "task": "ARV-001",
                **result,
                "provider_calls_performed": False,
                "eis_requests_performed": False,
                "quality_acceptance_rerun": False,
                "evidence_mutated": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
