"""PILOT-001-D04.2 fresh-goods reconciliation and evidence binding.

The historical supply-item reconciler was intentionally permissive: any shared
word of five or more characters could make two rows look like the same item.
That is unsafe for fresh-goods documents (for example, distinct products that
only share ``свежие``) and can also leave the public primary source pointing at
one row while ``evidence_id`` still points at another source.

This patch keeps the legacy merger for field reconciliation, but gives it only
conservative name-compatible groups and then binds the primary evidence tuple
(document, row, evidence id and raw fragment) atomically to the source row that
the merged item actually presents.
"""

from __future__ import annotations

from typing import Any, Iterable

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy


_INSTALLED = False
_ORIGINAL_MERGE_SUPPLY_ITEMS: Any = None


def _normalized_name(value: str | None) -> str:
    return _legacy._normalize_supply_name_key(value or "").strip()


def _name_tokens(value: str | None) -> set[str]:
    return {
        token
        for token in _normalized_name(value).split()
        if len(token) >= 5
    }


def _safe_supply_name_match(left: str | None, right: str | None) -> bool:
    """Return True only for names close enough to reconcile as one line item.

    Exact normalized names remain mergeable.  A fuzzy match requires at least
    two shared substantial tokens and 80% coverage of the larger token set.
    This deliberately prefers duplicate rows over silently collapsing different
    goods on a generic adjective such as ``свежие``.
    """

    left_key = _normalized_name(left)
    right_key = _normalized_name(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True

    # Preserve a common legacy case where one extractor adds a short qualifier
    # around an otherwise identical source name.
    if min(len(left_key), len(right_key)) >= 12 and (
        left_key in right_key or right_key in left_key
    ):
        shorter = left_key if len(left_key) <= len(right_key) else right_key
        longer = right_key if shorter == left_key else left_key
        shorter_tokens = _name_tokens(shorter)
        longer_tokens = _name_tokens(longer)
        if shorter_tokens and len(shorter_tokens & longer_tokens) == len(shorter_tokens):
            extra_tokens = longer_tokens - shorter_tokens
            if len(extra_tokens) <= 1:
                return True

    left_tokens = _name_tokens(left_key)
    right_tokens = _name_tokens(right_key)
    if not left_tokens or not right_tokens:
        return False
    common = left_tokens & right_tokens
    if len(common) < 2:
        return False
    return len(common) / max(len(left_tokens), len(right_tokens)) >= 0.8


def _partition_name_compatible(items: list[Any]) -> list[list[Any]]:
    """Build stable groups without transitive single-token bridge merges."""

    groups: list[list[Any]] = []
    for item in items:
        for group in groups:
            if all(
                _safe_supply_name_match(
                    getattr(item, "name", None),
                    getattr(member, "name", None),
                )
                for member in group
            ):
                group.append(item)
                break
        else:
            groups.append([item])
    return groups


def _candidate_rank(candidate: Any, merged: Any) -> tuple[int, int, int, int]:
    candidate_name = _normalized_name(getattr(candidate, "name", None))
    merged_name = _normalized_name(getattr(merged, "name", None))
    return (
        int(candidate_name == merged_name),
        int(getattr(candidate, "source_kind", None) == getattr(merged, "source_kind", None)),
        int(getattr(candidate, "name_source_type", None) == "structured_direct_name"),
        int(str(getattr(candidate, "confidence", "")).lower() == "high"),
    )


def _bind_primary_evidence(merged: Any, source_items: list[Any]) -> None:
    """Keep the displayed primary provenance and evidence locator inseparable."""

    displayed_document = str(getattr(merged, "source_document", "") or "")
    same_document = [
        candidate
        for candidate in source_items
        if str(getattr(candidate, "source_document", "") or "") == displayed_document
        and _safe_supply_name_match(
            getattr(candidate, "name", None),
            getattr(merged, "name", None),
        )
    ]
    if not same_document:
        return

    source = max(same_document, key=lambda candidate: _candidate_rank(candidate, merged))
    # These fields jointly identify the primary evidence displayed to an
    # operator.  Updating only source_document is exactly the D04.2 failure.
    for attribute in (
        "source_document",
        "source_kind",
        "source_row_number",
        "evidence_id",
        "raw_fragment",
        "source_record_id",
    ):
        if hasattr(merged, attribute):
            setattr(merged, attribute, getattr(source, attribute, None))

    evidence_id = getattr(source, "evidence_id", None)
    evidence_ids = list(getattr(merged, "evidence_ids", None) or [])
    if evidence_id and evidence_id not in evidence_ids:
        evidence_ids.append(evidence_id)
    if hasattr(merged, "evidence_ids"):
        merged.evidence_ids = evidence_ids


def _merge_supply_items_with_bound_evidence(items: Iterable[Any]) -> list[Any]:
    source_items = list(items)
    if not source_items:
        return []

    merged_items: list[Any] = []
    for group in _partition_name_compatible(source_items):
        group_merged = list(_ORIGINAL_MERGE_SUPPLY_ITEMS(group))
        for merged in group_merged:
            _bind_primary_evidence(merged, group)
            merged_items.append(merged)
    return merged_items


def install() -> None:
    """Install the D04.2 reconciler exactly once before public facades load."""

    global _INSTALLED, _ORIGINAL_MERGE_SUPPLY_ITEMS
    if _INSTALLED:
        return
    _ORIGINAL_MERGE_SUPPLY_ITEMS = _legacy._merge_supply_items
    _legacy._merge_supply_items = _merge_supply_items_with_bound_evidence
    _INSTALLED = True
