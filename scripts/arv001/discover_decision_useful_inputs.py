#!/usr/bin/env python3
"""Discover the existing frozen ARV-001 candidate/intake pair without mutation.

Discovery is deliberately fail-closed, but it must not require a complete walk
of a large private root before checking a candidate that has already been
encountered. Candidate manifests are therefore yielded and verified while the
scope is being traversed. The directory guard remains unchanged: if no fully
verified pair is proven before the guard is exhausted, discovery fails closed.

Every returned pair independently proves the accepted corpus SHA, the
10-physical/6-logical document contract and successful source-byte preparation.
No provider, EIS, download, durable-root write, or accepted-evidence mutation
occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
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
_PRUNED_DIRECTORY_NAMES = {".git", "node_modules", ".venv", "venv", "__pycache__"}
_PRIORITY_MARKERS = (
    "arv001",
    "candidate",
    "prepared",
    "acceptance",
    "controlled-evidence",
    "final",
    "runtime",
    "corpus",
    "intake",
    "source",
)


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


def _directory_priority(path: Path) -> tuple[int, int, str]:
    """Deterministically put ARV-001/candidate-shaped directories first."""

    name = path.name.casefold()
    hits = sum(1 for marker in _PRIORITY_MARKERS if marker in name)
    # A shallower candidate normally represents the durable/root artifact set;
    # marker count dominates depth and lexical order keeps traversal stable.
    return (-hits, len(path.parts), name)


def _iter_candidate_roots(search_root: Path) -> Iterator[tuple[Path, int]]:
    """Yield candidate manifests immediately while traversing one bounded scope.

    The traversal is explicit depth-first rather than a collect-then-validate
    ``os.walk``. This is the critical property: once a manifest is encountered,
    the caller can prove its corpus/source bytes before unrelated directories
    consume the scan budget.
    """

    root = search_root.expanduser().resolve(strict=False)
    if not _is_safe_directory(root):
        return

    stack: list[Path] = [root]
    visited = 0
    while stack:
        current = stack.pop()
        if not _is_safe_directory(current):
            continue
        visited += 1
        if visited > _MAX_DISCOVERED_DIRECTORIES:
            raise AcceptanceBlocked(_SCOPE_TOO_LARGE)

        try:
            entries = list(os.scandir(current))
        except OSError:
            continue

        files: set[str] = set()
        children: list[Path] = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False):
                    files.add(entry.name)
                elif (
                    entry.name not in _PRUNED_DIRECTORY_NAMES
                    and entry.is_dir(follow_symlinks=False)
                ):
                    children.append(Path(entry.path).resolve(strict=False))
            except OSError:
                continue

        if _REQUIRED_CANDIDATE_FILES.issubset(files):
            yield current.resolve(), visited

        # LIFO stack: push lower-priority children first so priority candidates
        # are visited next without sacrificing deterministic full traversal.
        children.sort(key=_directory_priority, reverse=True)
        stack.extend(children)


def _candidate_roots(search_roots: list[Path]) -> list[Path]:
    """Compatibility collector; production discovery verifies the stream inline."""

    found: set[Path] = set()
    for search_root in search_roots:
        for candidate, _visited in _iter_candidate_roots(search_root):
            found.add(candidate)
    return sorted(found)


def _intake_candidates(candidate: Path, search_roots: list[Path]) -> list[Path]:
    """Return safe likely source roots with local relatives before broad roots."""

    values: list[Path] = []
    seen: set[Path] = set()
    resolved_search_roots = {
        value.expanduser().resolve(strict=False) for value in search_roots
    }

    def add(value: Path, *, allow_search_root: bool = False) -> None:
        resolved = value.expanduser().resolve(strict=False)
        if resolved in seen:
            return
        if not allow_search_root and resolved in resolved_search_roots:
            return
        if not _is_safe_directory(resolved):
            return
        seen.add(resolved)
        values.append(resolved)

    def add_children(value: Path) -> None:
        resolved = value.expanduser().resolve(strict=False)
        if not _is_safe_directory(resolved):
            return
        try:
            children = [
                child.resolve(strict=False)
                for child in resolved.iterdir()
                if _is_safe_directory(child)
                and child.name not in _PRUNED_DIRECTORY_NAMES
            ]
        except OSError:
            return
        children.sort(key=_directory_priority)
        for child in children:
            add(child)

    # Candidate itself can be a combined candidate/intake layout. Nearby durable
    # relatives are much more likely than arbitrary top-level private storage.
    add(candidate, allow_search_root=True)
    add_children(candidate.parent)
    add(candidate.parent)
    add_children(candidate.parent.parent)
    add(candidate.parent.parent)

    # Explicit roots themselves are intentionally not used as intake candidates:
    # content-identity resolution can recurse through intake. Only direct safe
    # children are considered as a final bounded fallback.
    for root in search_roots:
        add_children(root)
    return values


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


def _verified_intake_for_candidate(
    candidate: Path,
    *,
    search_roots: list[Path],
    expected_corpus_sha: str,
) -> tuple[Path | None, int]:
    attempts = 0
    for intake in _intake_candidates(candidate, search_roots):
        attempts += 1
        if _pair_is_valid(candidate, intake, expected_corpus_sha):
            return intake, attempts
    return None, attempts


def _result(
    *,
    candidate: Path,
    intake: Path,
    expected_corpus_sha: str,
    selected_scope: Path,
    oversized_scopes: int,
    candidate_manifests_checked: int,
    directories_scanned_before_match: int,
    intake_pairs_checked: int,
) -> dict[str, Any]:
    return {
        "status": "FOUND",
        "candidate_root": str(candidate),
        "intake_root": str(intake),
        "candidate_artifact_signature": _candidate_signature(candidate),
        "verified_pair_count": 1,
        "physical_document_count": 10,
        "logical_document_count": 6,
        "frozen_corpus_sha256": expected_corpus_sha,
        "source_bytes_verified": True,
        "selected_discovery_scope": str(selected_scope),
        "oversized_scopes_skipped_before_match": oversized_scopes,
        "candidate_manifests_checked": candidate_manifests_checked,
        "directories_scanned_before_match": directories_scanned_before_match,
        "intake_pairs_checked": intake_pairs_checked,
        "provider_calls_performed": False,
        "eis_requests_performed": False,
        "git_mutations": 0,
    }


def discover_inputs(
    *, search_roots: list[Path], expected_corpus_sha: str = DEFAULT_CORPUS_SHA256
) -> dict[str, Any]:
    """Return the first fully verified pair encountered in priority traversal.

    Candidate manifests are validated as soon as they are encountered. A valid
    accepted-corpus pair therefore wins before unrelated directories can exhaust
    the guard. Invalid manifests do not weaken fail-closed behavior: traversal
    continues, and exhausting a scope without a proven pair remains a failure.
    """

    roots = _resolved_unique_roots(search_roots)
    oversized_scopes: list[Path] = []
    candidate_manifests_checked = 0
    intake_pairs_checked = 0

    for root in roots:
        try:
            for candidate, directories_scanned in _iter_candidate_roots(root):
                candidate_manifests_checked += 1
                intake, attempts = _verified_intake_for_candidate(
                    candidate,
                    search_roots=roots,
                    expected_corpus_sha=expected_corpus_sha,
                )
                intake_pairs_checked += attempts
                if intake is not None:
                    return _result(
                        candidate=candidate,
                        intake=intake,
                        expected_corpus_sha=expected_corpus_sha,
                        selected_scope=root,
                        oversized_scopes=len(oversized_scopes),
                        candidate_manifests_checked=candidate_manifests_checked,
                        directories_scanned_before_match=directories_scanned,
                        intake_pairs_checked=intake_pairs_checked,
                    )
        except AcceptanceBlocked as exc:
            if str(exc) != _SCOPE_TOO_LARGE:
                raise
            oversized_scopes.append(root)
            continue

    if oversized_scopes:
        raise AcceptanceBlocked(_SCOPE_TOO_LARGE)
    raise AcceptanceBlocked("decision_useful_frozen_input_pair_not_found")


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
