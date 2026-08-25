"""Diagnostic wrapper for the canonical ARV-001 zero-generation contour.

The underlying orchestrator intentionally sanitizes arbitrary exception text, but
its broad final exception handler labels every late failure as
``runtime_start_failed``. It can also collapse a safe child reason to
``application_persistence_failed`` when the final stderr line is a warning or a
repository reason contains a filename such as ``metadata.json``.

This wrapper preserves only already-safe machine reason codes while keeping
arbitrary text and filesystem paths redacted. It also normalizes the three
post-child boundaries (descriptor parse, strict prepared DB verification, and
request reconstruction) into safe machine codes so a non-RuntimeError there does
not fall back to the misleading ``runtime_start_failed`` label.

It does not change the provider boundary: ``full_pre_provider_canonical`` remains
a zero-generation contour.
"""

from __future__ import annotations

import re

from scripts.arv001 import full_pre_provider as implementation
from scripts.arv001 import full_pre_provider_canonical as canonical

_ORIGINAL_EXCEPTION_REASON_CODE = implementation._exception_reason_code
_ORIGINAL_PARSE_PRIVATE_DESCRIPTOR = implementation.parse_private_descriptor
_ORIGINAL_RECONSTRUCT_REQUESTS = implementation._reconstruct_actual_batch_requests
_ORIGINAL_VERIFY_PREPARED_DATABASE_WITH_REASON = (
    canonical._verify_prepared_database_with_reason
)
_SAFE_REASON_CODE = re.compile(r"[a-z0-9_:-]{1,120}")
_SAFE_CHILD_REASON_CODE = re.compile(r"[a-z0-9_.:-]{1,300}")
_SAFE_EXCEPTION_CLASS = re.compile(r"[a-z][a-z0-9_]{0,80}")


def _safe_machine_reason(exc: Exception, fallback: str) -> str:
    """Return a stable safe code without exposing exception prose or paths."""

    candidates = [getattr(exc, "code", None), str(exc).strip().lower()]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        value = candidate.strip().lower()
        if _SAFE_REASON_CODE.fullmatch(value) and ("_" in value or ":" in value):
            return value
    name = exc.__class__.__name__.lower()
    safe_name = name if _SAFE_EXCEPTION_CLASS.fullmatch(name) else "exception"
    return f"{fallback}:{safe_name}"


def canonical_exception_reason_code(exc: Exception, phase: str) -> str:
    """Preserve a safe repository reason code without exposing arbitrary text."""

    message = str(exc).strip().lower()
    if isinstance(exc, RuntimeError) and _SAFE_REASON_CODE.fullmatch(message):
        return message
    return _ORIGINAL_EXCEPTION_REASON_CODE(exc, phase)


def canonical_safe_child_failure(stderr: str) -> str:
    """Recover the nearest safe child reason even when stderr has trailing noise."""

    for raw in reversed(stderr.splitlines()):
        value = raw.strip().lower()
        if not _SAFE_CHILD_REASON_CODE.fullmatch(value):
            continue
        # Avoid treating generic single words or dotted log fragments as reason
        # codes. Repository reason codes use an underscore and/or a namespace
        # separator; filenames may legitimately add a dot after that separator.
        if "_" not in value and ":" not in value:
            continue
        return value
    return "application_persistence_failed"


def diagnostic_parse_private_descriptor(*args, **kwargs):
    """Expose a safe descriptor-parse reason instead of a generic runtime label."""

    try:
        return _ORIGINAL_PARSE_PRIVATE_DESCRIPTOR(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - intentionally sanitize all failures.
        raise RuntimeError(
            _safe_machine_reason(exc, "private_descriptor_parse_failed")
        ) from None


def diagnostic_verify_prepared_database_with_reason(*args, **kwargs):
    """Preserve strict verifier codes and sanitize unexpected verifier failures."""

    try:
        return _ORIGINAL_VERIFY_PREPARED_DATABASE_WITH_REASON(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - intentionally sanitize all failures.
        raise RuntimeError(
            _safe_machine_reason(exc, "prepared_database_verification_failed")
        ) from None


def diagnostic_reconstruct_actual_batch_requests(*args, **kwargs):
    """Expose a safe reconstruction failure code without leaking DB contents."""

    try:
        return _ORIGINAL_RECONSTRUCT_REQUESTS(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - intentionally sanitize all failures.
        raise RuntimeError(
            _safe_machine_reason(exc, "request_reconstruction_failed")
        ) from None


def main() -> int:
    implementation._exception_reason_code = canonical_exception_reason_code
    implementation._safe_child_failure = canonical_safe_child_failure
    implementation.parse_private_descriptor = diagnostic_parse_private_descriptor
    implementation._reconstruct_actual_batch_requests = (
        diagnostic_reconstruct_actual_batch_requests
    )
    canonical._verify_prepared_database_with_reason = (
        diagnostic_verify_prepared_database_with_reason
    )
    return canonical.main()


if __name__ == "__main__":
    raise SystemExit(main())
