#!/usr/bin/env python3
"""Discover the existing frozen ARV-001 candidate/intake pair without mutation.

This helper scans caller-controlled private roots in priority order, identifies
candidate manifests, and proves a candidate/intake pairing by validating the
accepted corpus contract and successfully preparing all 10 declared physical
source files from the proposed intake root.

A broad private root is allowed to exceed the directory-scan guard only if a
higher-priority bounded root has already produced a fully verified accepted-
corpus pair. No verification is skipped: every returned pair independently
proves the accepted corpus SHA, the 10-physical/6-logical document contract and
successful source-byte preparation.

No provider, EIS, download, durable-root write, or accepted-evidence mutation
occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.arv001.complete_corpus_contract import (
    DEFAULT_CORPUS_SHA256,
    AcceptanceBlocked,
    load_candidate,
    prepare_documents,
    validate_document_set,
)
from scripts.arv001.corpus_hash_resolver import resolve_corpus_hash_profile
from scripts.arv001.run_complete_corpus_acceptance_split_roots import (
    build_ephemeral_candidate_view,
)
from src.shared.config.settings import get_settings

_REQUIRED_CANDIDATE_FILES = {
    "physical-files.json",
    "logical-documents.json",
    "document-set-summary.json",
    "deterministic-parse-summary.json",
    "intake-summary.json",
    "metadata.json",
}
_MAX_DISCOVERED_DIRECTORIES = 5000
_SCOPE_TOO_LARGE = "decision_useful_discovery_scope_too_large"


def _is_safe_directory(path: Path) -> bool:
    try:
        return path.is_dir() and not path.is_symlink()
    except OSError:
        return False


def _resolved_unique_roots(search_roots: list[Path]) -> list[Path]:
    values: list[Path] = []
    seen: set[Path] = set()
    for value in search_roots:
        resolved = value.expanduser().resolve(strict=False)
        if resolved in seen or not _is_safe_directory(resolved):
            continue
        seen.add(resolved)
        values.append(resolved)
    return values


def _candidate_roots(search_roots: list[Path]) -> list[Path]:
    found: set[Path] = set()
    visited = 0
    for search_root in search_roots:
        root = search_root.expanduser().resolve(strict=False)
        if not _is_safe_directory(root):
            continue
        for current, dirs, files in os.walk(root, followlinks=False):
            visited += 1
            if visited > _MAX_DISCOVERED_DIRECTORIES:
                raise AcceptanceBlocked(_SCOPE_TOO_LARGE)
            dirs[:] = [
                value
                for value in dirs
                if not (Path(current) / value).is_symlink()
                and value not in {".git", "node_modules", ".venv", "venv"}
            ]
            if _REQUIRED_CANDIDATE_FILES.issubset(set(files)):
                found.add(Path(current).resolve())
    return sorted(found)


def _intake_candidates(candidate: Path, search_roots: list[Path]) -> list[Path]:
    values: set[Path] = {candidate}
    resolved_search_roots = {
        value.expanduser().resolve(strict=False) for value in search_roots
    }
    # The durable ARV-001 layout keeps candidate summaries and normalized source
    # bytes close to one another. Search near relatives and immediate children
    # of explicit private roots, but never use the broad search root itself as
    # an intake candidate: content-identity resolution recursively scans intake.
    for value in (candidate.parent, candidate.parent.parent):
        resolved = value.resolve(strict=False)
        if resolved in resolved_search_roots:
            continue
        if _is_safe_directory(resolved):
            values.add(resolved)
            try:
                children = list(resolved.iterdir())
            except OSError:
                children = []
            for child in children:
                if _is_safe_directory(child):
                    values.add(child.resolve())
    for root in resolved_search_roots:
        if not _is_safe_directory(root):
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            children = []
        for child in children:
            if _is_safe_directory(child):
                values.add(child.resolve())
    return sorted(values)


def _candidate_signature(candidate: Path) -> str:
    digest = hashlib.sha256()
    for name in sorted(_REQUIRED_CANDIDATE_FILES):
        path = candidate / name
        if path.is_symlink() or not path.is_file():
            raise AcceptanceBlocked("decision_useful_candidate_artifact_unsafe")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def _pair_is_valid(candidate: Path, intake: Path, expected_corpus_sha: str) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix="arv001-input-discovery-") as tmp:
            view = Path(tmp) / "view"
            build_ephemeral_candidate_view(
                candidate_root=candidate,
                intake_root=intake,
                view_root=view,
            )
            values, _shapes = load_candidate(view)
            physical = values.get("physical-files.json")
            metadata = values.get("metadata.json")
            if not isinstance(physical, list) or len(physical) != 10:
                return False
            if not isinstance(metadata, dict):
                return False
            profile = resolve_corpus_hash_profile(physical, expected_corpus_sha)
            if profile.sha256 != expected_corpus_sha:
                return False
            validate_document_set(values, 10)
            summary = values.get("document-set-summary.json")
            if not isinstance(summary, dict):
                return False
            if int(summary.get("logical_document_count") or 0) != 6:
                return False

            settings = get_settings()
            prepared = prepare_documents(
                physical=physical,
                metadata=metadata,
                intake_root=intake,
                max_chars=settings.document_extract_max_chars,
                chunk_size=settings.rag_chunk_size_chars,
                chunk_overlap=settings.rag_chunk_overlap_chars,
            )
            if len(prepared) != 10:
                return False
            if any(
                item.path.is_symlink()
                or not item.path.is_file()
                or not item.sha256
                or item.size_bytes <= 0
                for item in prepared
            ):
                return False
            return True
    except (AcceptanceBlocked, OSError, ValueError, KeyError, TypeError):
        return False


def _matches_for_candidates(
    candidates: list[Path],
    *,
    intake_search_roots: list[Path],
    expected_corpus_sha: str,
) -> list[tuple[Path, Path]]:
    matches: list[tuple[Path, Path]] = []
    for candidate in candidates:
        for intake in _intake_candidates(candidate, intake_search_roots):
            if _pair_is_valid(candidate, intake, expected_corpus_sha):
                matches.append((candidate, intake))
    return sorted(set(matches))


def discover_inputs(
    *, search_roots: list[Path], expected_corpus_sha: str = DEFAULT_CORPUS_SHA256
) -> dict[str, Any]:
    """Return a verified pair from the first priority scope that can prove one.

    Roots are intentionally evaluated one at a time. This prevents an unrelated
    oversized root (for example all of ``/private/tmp``) from blocking a valid
    pair that is already available in a narrower accepted-runtime root. If no
    verified pair exists in any bounded root and at least one requested root
    exceeded the scan guard, discovery still fails closed with the original
    scope-too-large code.
    """

    roots = _resolved_unique_roots(search_roots)
    matches: list[tuple[Path, Path]] = []
    selected_scope: Path | None = None
    oversized_scopes: list[Path] = []

    for root in roots:
        try:
            candidates = _candidate_roots([root])
        except AcceptanceBlocked as exc:
            if str(exc) != _SCOPE_TOO_LARGE:
                raise
            oversized_scopes.append(root)
            continue

        root_matches = _matches_for_candidates(
            candidates,
            intake_search_roots=roots,
            expected_corpus_sha=expected_corpus_sha,
        )
        if root_matches:
            matches = root_matches
            selected_scope = root
            break

    if not matches:
        if oversized_scopes:
            raise AcceptanceBlocked(_SCOPE_TOO_LARGE)
        raise AcceptanceBlocked("decision_useful_frozen_input_pair_not_found")

    # Every surviving pair independently proved the exact accepted corpus SHA,
    # complete document-set contract and successful 10-file preparation. Path
    # duplication is therefore a private-storage concern, not evidence identity.
    # Prefer the narrowest intake root to minimize resolver scan scope.
    matches.sort(
        key=lambda value: (
            -len(value[1].parts),
            -len(value[0].parts),
            str(value[1]),
            str(value[0]),
        )
    )
    candidate, intake = matches[0]
    return {
        "status": "FOUND",
        "candidate_root": str(candidate),
        "intake_root": str(intake),
        "candidate_artifact_signature": _candidate_signature(candidate),
        "verified_pair_count": len(matches),
        "physical_document_count": 10,
        "logical_document_count": 6,
        "frozen_corpus_sha256": expected_corpus_sha,
        "source_bytes_verified": True,
        "selected_discovery_scope": str(selected_scope) if selected_scope else None,
        "oversized_scopes_skipped_before_match": len(oversized_scopes),
        "provider_calls_performed": False,
        "eis_requests_performed": False,
        "git_mutations": 0,
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--search-root",
        action="append",
        type=Path,
        dest="search_roots",
        help="Private root to scan. May be supplied more than once.",
    )
    parser.add_argument("--expected-corpus-sha", default=DEFAULT_CORPUS_SHA256)
    return parser.parse_args()


def main() -> int:
    args = _args()
    search_roots = args.search_roots or [
        Path.home() / ".local/share/arvectum/arv001",
        Path("/private/tmp"),
    ]
    try:
        result = discover_inputs(
            search_roots=search_roots,
            expected_corpus_sha=args.expected_corpus_sha,
        )
    except AcceptanceBlocked as exc:
        code = str(exc)
        if not code.isascii() or len(code) > 200:
            code = "decision_useful_input_discovery_failed"
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "failure_code": code,
                    "provider_calls_performed": False,
                    "eis_requests_performed": False,
                    "git_mutations": 0,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
