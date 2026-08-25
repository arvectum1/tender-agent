"""Diagnostic wrapper for the canonical ARV-001 zero-generation contour.

The underlying orchestrator intentionally sanitizes arbitrary exception text, but
its broad final exception handler labels every late failure as
``runtime_start_failed``. It can also collapse a safe child reason to
``application_persistence_failed`` when the final stderr line is a warning or a
repository reason contains a filename such as ``metadata.json``.

This wrapper preserves only already-safe machine reason codes while keeping
arbitrary text and filesystem paths redacted. It does not change the provider
boundary: ``full_pre_provider_canonical`` remains a zero-generation contour.
"""

from __future__ import annotations

import re

from scripts.arv001 import full_pre_provider as implementation
from scripts.arv001 import full_pre_provider_canonical as canonical

_ORIGINAL_EXCEPTION_REASON_CODE = implementation._exception_reason_code
_SAFE_REASON_CODE = re.compile(r"[a-z0-9_:-]{1,120}")
_SAFE_CHILD_REASON_CODE = re.compile(r"[a-z0-9_.:-]{1,300}")


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


def main() -> int:
    implementation._exception_reason_code = canonical_exception_reason_code
    implementation._safe_child_failure = canonical_safe_child_failure
    return canonical.main()


if __name__ == "__main__":
    raise SystemExit(main())
