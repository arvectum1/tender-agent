"""Diagnostic wrapper for the canonical ARV-001 zero-generation contour.

The underlying orchestrator intentionally sanitizes arbitrary exception text, but
its broad final exception handler labels every late failure as
``runtime_start_failed``.  That can hide a repository-owned reason code emitted
later by the controlled pre-provider child.  This wrapper preserves only an
already-safe, single-token reason code while keeping arbitrary text redacted.

It does not change the provider boundary: ``full_pre_provider_canonical`` remains
a zero-generation contour and this module merely improves fail-closed diagnosis.
"""

from __future__ import annotations

import re

from scripts.arv001 import full_pre_provider as implementation
from scripts.arv001 import full_pre_provider_canonical as canonical

_ORIGINAL_EXCEPTION_REASON_CODE = implementation._exception_reason_code
_SAFE_REASON_CODE = re.compile(r"[a-z0-9_:-]{1,120}")


def canonical_exception_reason_code(exc: Exception, phase: str) -> str:
    """Preserve a safe repository reason code without exposing arbitrary text."""

    message = str(exc).strip().lower()
    if isinstance(exc, RuntimeError) and _SAFE_REASON_CODE.fullmatch(message):
        return message
    return _ORIGINAL_EXCEPTION_REASON_CODE(exc, phase)


def main() -> int:
    implementation._exception_reason_code = canonical_exception_reason_code
    return canonical.main()


if __name__ == "__main__":
    raise SystemExit(main())
