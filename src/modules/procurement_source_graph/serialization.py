"""Single production serializer for graph, cardinality, and field provenance."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .model import CanonicalProcurementModel, StructuredSourceFragment


@dataclass(frozen=True)
class ProvenanceRecord:
    canonical_item_id: str
    field_name: str
    selected_value: str
    normalized_value: str
    operator: str
    unit: str
    context: str
    source_fragment_key: str
    parent_fragment_key: str
    document_instance_id: str
    source_type: str
    locator: str
    raw_value: str
    provenance_kind: str
    resolution_reason: str
    production_model_hash: str


def provenance_records(model: CanonicalProcurementModel) -> list[ProvenanceRecord]:
    records: list[ProvenanceRecord] = []
    for item in model.canonical_items:
        values = {"name": item.official_name, "quantity": item.quantity, "unit": item.unit}
        for field_name, source in item.field_provenance.items():
            fragment = source.fragment
            raw_value = str(getattr(fragment, field_name, None) or fragment.name or fragment.raw_text)
            selected = str(values.get(field_name) if field_name in values else getattr(fragment, field_name, None) or "")
            records.append(ProvenanceRecord(
                item.canonical_item_id, field_name, selected, selected, "", fragment.unit if field_name == "quantity" else "", "",
                fragment.fragment_key, "", fragment.document_instance_id, fragment.source_type, fragment.locator, raw_value,
                fragment.provenance_kind, "direct compatible item fragment", model.production_model_hash,
            ))
        for characteristic in item.characteristics:
            key = characteristic.get("source_fragment_key", "")
            records.append(ProvenanceRecord(
                item.canonical_item_id, "characteristic." + str(characteristic.get("name", "")).lower(),
                str(characteristic.get("display_value", "")), str(characteristic.get("value", "")), str(characteristic.get("operator") or ""),
                str(characteristic.get("unit") or ""), str(characteristic.get("name") or ""), key,
                str(characteristic.get("parent_fragment_key") or ""), "", "", str(characteristic.get("locator") or ""),
                str(characteristic.get("raw_value") or ""), "direct_source", "direct child characteristic", model.production_model_hash,
            ))
    return records


def _serialize_fragment(fragment: StructuredSourceFragment) -> dict[str, Any]:
    """Return a JSON-native fragment projection without changing persisted bytes.

    ``dataclasses.asdict`` preserves tuple fields as tuples. JSON encoding writes
    those tuples as arrays, and decoding them yields lists, so the historical
    in-memory graph could differ from its own persisted JSON representation.
    Normalize the only tuple field at the serializer boundary so equality is
    stable across a JSON round-trip while the emitted JSON remains unchanged.
    """

    payload = asdict(fragment)
    payload["characteristics"] = list(fragment.characteristics)
    return payload


def serialize_graph(model: CanonicalProcurementModel, fragments: list[StructuredSourceFragment], graph_version: str) -> dict[str, Any]:
    return {
        "graph_version": graph_version,
        "production_model_hash": model.production_model_hash,
        "structured_fragments": [_serialize_fragment(fragment) for fragment in fragments],
        "parent_child_edges": [
            {"parent": fragment.parent_fragment_key, "child": fragment.fragment_key}
            for fragment in fragments if fragment.parent_fragment_key
        ],
        "cross_source_matches": model.cross_source_matches,
        "canonical_item_edges": [
            {"canonical_item_id": item.canonical_item_id, "source_fragment_key": source.fragment.fragment_key, "field_name": field, "relationship": "selected"}
            for item in model.canonical_items for field, source in item.field_provenance.items()
        ],
        "cardinality_decisions": model.cardinality_decisions,
    }
