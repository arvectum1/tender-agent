from __future__ import annotations

from src.modules.production_llm_analysis.evidence import build_evidence_packet
from src.modules.production_llm_analysis.llama_schema_constraint import (
    build_live_compact_llama_schema,
)
from src.modules.production_llm_analysis.schemas import (
    CompactWireProviderClaim,
    EvidenceFragmentInput,
)
from src.modules.production_llm_analysis.service import build_production_llm_request

from .conftest import make_policy


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
                text="Exact source sentence.",
            )
        ],
    )
    return build_production_llm_request(
        evidence_packet=packet,
        provider="openai_compatible",
        provider_wire_contract_version="compact-safe-v1",
        model="arvectum-gemma4-12b-it-qat-q4_0",
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
        allowed_field_paths=["requirements.technical_requirements"],
    )


def test_compact_wire_claim_requires_exactly_one_evidence_reference():
    schema = CompactWireProviderClaim.model_json_schema()
    references = schema["properties"]["evidence_references"]

    assert "evidence_references" in schema["required"]
    assert references["minItems"] == 1
    assert references["maxItems"] == 1


def test_live_llama_schema_preserves_required_exact_reference():
    schema = build_live_compact_llama_schema(_request())
    claim = schema["properties"]["claims"]["items"]
    references = claim["properties"]["evidence_references"]

    assert "evidence_references" in claim["required"]
    assert references["minItems"] == 1
    assert references["maxItems"] == 1
