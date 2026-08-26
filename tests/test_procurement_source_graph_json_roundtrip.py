from __future__ import annotations

import json
from dataclasses import asdict

from src.modules.procurement_source_graph.model import (
    CanonicalProcurementModel,
    StructuredSourceFragment,
)
from src.modules.procurement_source_graph.serialization import serialize_graph


def _model() -> CanonicalProcurementModel:
    return CanonicalProcurementModel(
        procurement_number="0388100001826000047",
        procurement_scope="goods",
        canonical_items=[],
        unresolved_candidates=[],
        source_graph_summary={"fragments": 1, "confirmed": 0, "unresolved": 0},
        quality_issues=[],
        production_model_hash="a" * 64,
    )


def test_source_graph_is_stable_across_json_roundtrip() -> None:
    fragment = StructuredSourceFragment(
        fragment_key="fragment-1",
        document_instance_id="document-1",
        source_type="technical_specification",
        locator="row-1",
        row_role="item",
        name="Дизельное топливо",
        characteristics=("Евро-5", "зимнее"),
    )

    graph = serialize_graph(_model(), [fragment], "procurement-source-graph-v2")

    assert graph["structured_fragments"][0]["characteristics"] == [
        "Евро-5",
        "зимнее",
    ]
    assert json.loads(json.dumps(graph, ensure_ascii=False, indent=2)) == graph


def test_json_native_projection_does_not_change_wire_json() -> None:
    fragment = StructuredSourceFragment(
        fragment_key="fragment-1",
        document_instance_id="document-1",
        source_type="technical_specification",
        locator="row-1",
        row_role="item",
        name="Дизельное топливо",
        characteristics=("Евро-5",),
    )

    graph = serialize_graph(_model(), [fragment], "procurement-source-graph-v2")
    historical_fragment = asdict(fragment)

    historical_graph = dict(graph)
    historical_graph["structured_fragments"] = [historical_fragment]

    assert json.dumps(graph, ensure_ascii=False, indent=2) == json.dumps(
        historical_graph,
        ensure_ascii=False,
        indent=2,
    )
