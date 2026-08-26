from __future__ import annotations

import hashlib
import json

import pytest

from src.modules.procurement_analysis.r10_1_producer import R10_1AnalysisRejectedError
from src.modules.production_llm_analysis import llama_schema_constraint as constraint
from src.modules.production_llm_analysis.evidence import build_evidence_packet
from src.modules.production_llm_analysis.llama_schema_constraint import (
    _SERVER_CLAIM_ID_SENTINEL,
    _SERVER_FRAGMENT_QUOTE_SENTINEL,
    _SERVER_FRAGMENT_VALUE_SENTINEL,
    _parse_success_response_with_safe_diagnostics,
    _run_production_analysis_with_safe_diagnostics,
)
from src.modules.production_llm_analysis.llama_wire_hardening import (
    _SAFE_CODES,
    hardened_rewrite_server_grounded_response,
)
from src.modules.production_llm_analysis.openai_compatible import (
    OpenAICompatibleProductionLLMProvider,
)
from src.modules.production_llm_analysis.schemas import EvidenceFragmentInput
from src.modules.production_llm_analysis.service import build_production_llm_request
from src.shared.llm.transport import HTTPResponse

from .conftest import make_policy

_ALLOWED_FIELD = "requirements.technical_requirements"


def _request():
    packet = build_evidence_packet(
        customer_id="customer",
        project_id="project",
        procurement_case_id="case",
        run_id="run",
        registry_number="registry",
        fragments=[
            EvidenceFragmentInput(
                document_id="document",
                document_name="document.txt",
                chunk_id="chunk-1",
                locator={"document_order": 0, "chunk_index": 0},
                text="Exact source sentence one.",
            )
        ],
    )
    return build_production_llm_request(
        evidence_packet=packet,
        provider="openai_compatible",
        provider_wire_contract_version="compact-safe-v1",
        model="arvectum-gemma4-12b-q4km",
        prompt_id="r10.1-batched-compact",
        prompt_version="v2",
        output_schema_id="r10.1-map",
        output_schema_version="v2",
        grounding_policy_version="v1",
        budget_policy=make_policy(),
        batch_plan_version="test-plan",
        batch_plan_hash="1" * 64,
        batch_hash="2" * 64,
        batch_ordinal=1,
        batch_count=1,
        corpus_evidence_hash="3" * 64,
        map_mode=True,
        max_claims=3,
        allowed_field_paths=[_ALLOWED_FIELD],
    )


def _claim(fragment_id: str, **extra):
    claim = {
        "claim_id": _SERVER_CLAIM_ID_SENTINEL,
        "field_path": _ALLOWED_FIELD,
        "value": _SERVER_FRAGMENT_VALUE_SENTINEL,
        "evidence_references": [
            {
                "fragment_id": fragment_id,
                "quote": _SERVER_FRAGMENT_QUOTE_SENTINEL,
            }
        ],
    }
    claim.update(extra)
    return claim


def _response(claims) -> HTTPResponse:
    payload = {
        "id": "local-request",
        "choices": [
            {
                "message": {
                    "content": json.dumps({"claims": claims})
                }
            }
        ],
    }
    return HTTPResponse(
        status_code=200,
        headers={},
        body=json.dumps(payload).encode(),
    )


def _activate_hardening(monkeypatch) -> None:
    monkeypatch.setattr(
        constraint,
        "_rewrite_server_grounded_response",
        hardened_rewrite_server_grounded_response,
    )
    monkeypatch.setattr(
        constraint,
        "_SAFE_INVALID_RESPONSE_CODES",
        frozenset(set(constraint._SAFE_INVALID_RESPONSE_CODES) | set(_SAFE_CODES)),
    )


def _provider_for(response: HTTPResponse):
    class _Provider:
        def generate(self, provider_request):
            adapter = OpenAICompatibleProductionLLMProvider.__new__(
                OpenAICompatibleProductionLLMProvider
            )
            adapter._clock = lambda: 0.0
            return _parse_success_response_with_safe_diagnostics(
                adapter,
                response=response,
                request=provider_request,
                attempt_latencies_ms=[1],
                retry_count=0,
                analysis_started=0.0,
            )

    return _Provider()


def test_exact_duplicate_server_grounded_claim_is_deduplicated(monkeypatch):
    _activate_hardening(monkeypatch)
    request = _request()
    fragment_id = request.evidence_packet.fragments[0].fragment_id
    response = _response([_claim(fragment_id), _claim(fragment_id)])
    raw_hash = hashlib.sha256(response.body).hexdigest()

    adapter = OpenAICompatibleProductionLLMProvider.__new__(
        OpenAICompatibleProductionLLMProvider
    )
    adapter._clock = lambda: 0.0
    result = _parse_success_response_with_safe_diagnostics(
        adapter,
        response=response,
        request=request,
        attempt_latencies_ms=[1],
        retry_count=0,
        analysis_started=0.0,
    )

    assert len(result.claims) == 1
    assert result.claims[0].value == request.evidence_packet.fragments[0].text
    assert result.raw_response_sha256 == raw_hash


def test_extra_claim_key_gets_distinct_safe_code(monkeypatch):
    _activate_hardening(monkeypatch)
    request = _request()
    fragment_id = request.evidence_packet.fragments[0].fragment_id
    response = _response([_claim(fragment_id, unexpected="value")])

    with pytest.raises(
        R10_1AnalysisRejectedError,
        match="evidence_batch_invalid_response:provider_wire_claim_extra_field",
    ):
        _run_production_analysis_with_safe_diagnostics(
            request,
            _provider_for(response),
        )


def test_provider_confidence_is_rejected_as_prohibited_live_field(monkeypatch):
    _activate_hardening(monkeypatch)
    request = _request()
    fragment_id = request.evidence_packet.fragments[0].fragment_id
    response = _response([_claim(fragment_id, provider_confidence="not-a-number")])

    with pytest.raises(
        R10_1AnalysisRejectedError,
        match=(
            "evidence_batch_invalid_response:"
            "provider_wire_provider_confidence_prohibited"
        ),
    ):
        _run_production_analysis_with_safe_diagnostics(
            request,
            _provider_for(response),
        )
