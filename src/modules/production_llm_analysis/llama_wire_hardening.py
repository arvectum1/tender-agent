from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from src.modules.production_llm_analysis import llama_schema_constraint as constraint
from src.modules.production_llm_analysis.evidence import canonical_json_bytes
from src.modules.production_llm_analysis.schemas import ProductionLLMAnalysisRequest
from src.shared.llm.transport import HTTPResponse

_PATCH_MARKER = "_arv001_llama_wire_hardening_v1"
_LIVE_CLAIM_KEYS = frozenset(
    {"claim_id", "field_path", "value", "evidence_references"}
)
_LIVE_REFERENCE_KEYS = frozenset({"fragment_id", "quote"})
_SAFE_CODES = frozenset(
    {
        "provider_wire_claim_object_invalid",
        "provider_wire_claim_extra_field",
        "provider_wire_provider_confidence_prohibited",
        "provider_wire_duplicate_claim_conflict",
    }
)

_Rewrite = Callable[..., tuple[HTTPResponse, str]]
_BASE_REWRITE: _Rewrite = constraint._rewrite_server_grounded_response


def _decoded_claims(
    response: HTTPResponse,
) -> tuple[dict[str, Any], dict[str, Any], list[Any]] | None:
    """Return the provider envelope/content/claims when safely decodable.

    The helper is deliberately structural only. It never logs, persists or
    returns provider text beyond the current process.
    """

    try:
        envelope = json.loads(response.body.decode("utf-8"))
        content_text = envelope["choices"][0]["message"]["content"]
        if not isinstance(content_text, str):
            return None
        content = json.loads(content_text)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None
    if (
        not isinstance(envelope, dict)
        or not isinstance(content, dict)
        or not isinstance(content.get("claims"), list)
    ):
        return None
    return envelope, content, content["claims"]


def _raise_invalid(
    code: str,
    *,
    response: HTTPResponse,
    retry_count: int,
    attempt_latencies_ms: tuple[int, ...],
    total_latency_ms: int | None,
) -> None:
    raise constraint._invalid_response(
        code,
        raw_response_sha256=hashlib.sha256(response.body).hexdigest(),
        retry_count=retry_count,
        attempt_latencies_ms=attempt_latencies_ms,
        total_latency_ms=total_latency_ms,
    )


def _prevalidate_live_claim_shape(
    response: HTTPResponse,
    *,
    retry_count: int,
    attempt_latencies_ms: tuple[int, ...],
    total_latency_ms: int | None,
) -> None:
    decoded = _decoded_claims(response)
    if decoded is None:
        return
    _envelope, _content, claims = decoded
    for claim in claims:
        if not isinstance(claim, dict):
            _raise_invalid(
                "provider_wire_claim_object_invalid",
                response=response,
                retry_count=retry_count,
                attempt_latencies_ms=attempt_latencies_ms,
                total_latency_ms=total_latency_ms,
            )
        if "provider_confidence" in claim:
            # The live llama schema intentionally removes provider confidence.
            # Confidence is server-validated metadata, not model authority.
            _raise_invalid(
                "provider_wire_provider_confidence_prohibited",
                response=response,
                retry_count=retry_count,
                attempt_latencies_ms=attempt_latencies_ms,
                total_latency_ms=total_latency_ms,
            )
        if set(claim) - _LIVE_CLAIM_KEYS:
            _raise_invalid(
                "provider_wire_claim_extra_field",
                response=response,
                retry_count=retry_count,
                attempt_latencies_ms=attempt_latencies_ms,
                total_latency_ms=total_latency_ms,
            )
        references = claim.get("evidence_references")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, dict):
                _raise_invalid(
                    "provider_wire_reference_schema_invalid",
                    response=response,
                    retry_count=retry_count,
                    attempt_latencies_ms=attempt_latencies_ms,
                    total_latency_ms=total_latency_ms,
                )
            if set(reference) - _LIVE_REFERENCE_KEYS:
                _raise_invalid(
                    "provider_wire_reference_schema_invalid",
                    response=response,
                    retry_count=retry_count,
                    attempt_latencies_ms=attempt_latencies_ms,
                    total_latency_ms=total_latency_ms,
                )
            fragment_id = reference.get("fragment_id")
            if fragment_id is not None and not isinstance(fragment_id, str):
                _raise_invalid(
                    "provider_wire_reference_schema_invalid",
                    response=response,
                    retry_count=retry_count,
                    attempt_latencies_ms=attempt_latencies_ms,
                    total_latency_ms=total_latency_ms,
                )


def _dedupe_server_grounded_claims(
    response: HTTPResponse,
    *,
    raw_response_sha256: str,
    retry_count: int,
    attempt_latencies_ms: tuple[int, ...],
    total_latency_ms: int | None,
) -> HTTPResponse:
    decoded = _decoded_claims(response)
    if decoded is None:
        return response
    envelope, content, claims = decoded
    seen: dict[str, dict[str, Any]] = {}
    unique: list[Any] = []
    changed = False
    for claim in claims:
        if not isinstance(claim, dict):
            return response
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str):
            return response
        previous = seen.get(claim_id)
        if previous is None:
            seen[claim_id] = claim
            unique.append(claim)
            continue
        if canonical_json_bytes(previous) != canonical_json_bytes(claim):
            raise constraint._invalid_response(
                "provider_wire_duplicate_claim_conflict",
                raw_response_sha256=raw_response_sha256,
                retry_count=retry_count,
                attempt_latencies_ms=attempt_latencies_ms,
                total_latency_ms=total_latency_ms,
            )
        # Once server-owned grounding has rewritten claim identity/value/quote,
        # an exact duplicate carries no additional factual content. Collapse it
        # deterministically instead of letting the generic parser reject the same
        # semantic claim twice.
        changed = True
    if not changed:
        return response
    content["claims"] = unique
    envelope["choices"][0]["message"]["content"] = canonical_json_bytes(content).decode(
        "utf-8"
    )
    return HTTPResponse(
        status_code=response.status_code,
        headers=response.headers,
        body=canonical_json_bytes(envelope),
    )


def hardened_rewrite_server_grounded_response(
    response: HTTPResponse,
    request: ProductionLLMAnalysisRequest,
    *,
    retry_count: int,
    attempt_latencies_ms: tuple[int, ...],
    total_latency_ms: int | None,
) -> tuple[HTTPResponse, str]:
    """Harden the llama-only wire boundary without weakening grounding.

    Structural violations receive distinct safe codes before Pydantic collapses
    them into ``provider_wire_claim_schema_invalid``. Exact duplicate claims are
    deduplicated only after server-owned grounding has made their full semantics
    byte-identical. Conflicting duplicates still fail closed.
    """

    if request.provider_wire_contract_version not in {"compact-safe-v1", "compact-safe-v2"}:
        return _BASE_REWRITE(
            response,
            request,
            retry_count=retry_count,
            attempt_latencies_ms=attempt_latencies_ms,
            total_latency_ms=total_latency_ms,
        )

    _prevalidate_live_claim_shape(
        response,
        retry_count=retry_count,
        attempt_latencies_ms=attempt_latencies_ms,
        total_latency_ms=total_latency_ms,
    )
    rewritten, raw_response_sha256 = _BASE_REWRITE(
        response,
        request,
        retry_count=retry_count,
        attempt_latencies_ms=attempt_latencies_ms,
        total_latency_ms=total_latency_ms,
    )
    rewritten = _dedupe_server_grounded_claims(
        rewritten,
        raw_response_sha256=raw_response_sha256,
        retry_count=retry_count,
        attempt_latencies_ms=attempt_latencies_ms,
        total_latency_ms=total_latency_ms,
    )
    return rewritten, raw_response_sha256


setattr(hardened_rewrite_server_grounded_response, _PATCH_MARKER, True)


def install_llama_wire_hardening() -> None:
    """Install the ARV-001 llama-only structural hardening idempotently."""

    global _BASE_REWRITE
    current = constraint._rewrite_server_grounded_response
    if bool(getattr(current, _PATCH_MARKER, False)):
        return
    _BASE_REWRITE = current
    constraint._rewrite_server_grounded_response = hardened_rewrite_server_grounded_response
    constraint._SAFE_INVALID_RESPONSE_CODES = frozenset(
        set(constraint._SAFE_INVALID_RESPONSE_CODES) | set(_SAFE_CODES)
    )
