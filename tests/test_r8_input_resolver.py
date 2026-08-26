from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.customer_pilot.input_resolver import resolve_customer_run_inputs
from src.shared.db.base import Base
from src.tender_research.models import (
    ProcurementDocumentChunk,
    ProcurementTender,
    ProcurementTenderDocument,
)


def _seed(factory, *, reverse: bool):
    """Persist the same intake in deliberately different insert order."""
    with factory() as session:
        stamp = datetime(2026, 7, 22, tzinfo=UTC)
        tenders = [
            ProcurementTender(
                source="fixture", external_id="older", registry_number="0379100000726000101",
                title="older", updated_at=stamp,
            ),
            ProcurementTender(
                source="fixture", external_id="selected", registry_number="0379100000726000101",
                title="selected", updated_at=stamp,
            ),
        ]
        for tender in reversed(tenders) if reverse else tenders:
            session.add(tender)
        session.flush()
        selected = next(item for item in tenders if item.external_id == "selected")
        documents = [
            ProcurementTenderDocument(
                tender_id=selected.id, file_name="А-спецификация.txt",
                download_status="downloaded", text_extraction_status="completed",
                sha256=None,
            ),
            ProcurementTenderDocument(
                tender_id=selected.id, file_name="Б-извещение.txt",
                download_status="downloaded", text_extraction_status="completed",
                sha256="b" * 64,
            ),
        ]
        for document in reversed(documents) if reverse else documents:
            session.add(document)
        session.flush()
        chunks = [
            ProcurementDocumentChunk(
                tender_id=selected.id, document_id=documents[0].id, chunk_index=1,
                text="second specification chunk", text_hash="1" * 64,
                # This fixture intentionally models legacy sparse offsets so the
                # resolver retains the historical separator-join compatibility path.
                char_start=26, char_end=52, token_estimate=4,
                source_file_name=documents[0].file_name,
            ),
            ProcurementDocumentChunk(
                tender_id=selected.id, document_id=documents[0].id, chunk_index=0,
                text="first specification chunk", text_hash="2" * 64,
                char_start=0, char_end=25, token_estimate=4,
                source_file_name=documents[0].file_name,
            ),
            ProcurementDocumentChunk(
                tender_id=selected.id, document_id=documents[1].id, chunk_index=0,
                text="notice chunk", text_hash="3" * 64,
                char_start=0, char_end=12, token_estimate=2,
                source_file_name=documents[1].file_name,
            ),
        ]
        for chunk in reversed(chunks) if reverse else chunks:
            session.add(chunk)
        session.commit()
        return [document.id for document in documents]


def test_resolver_reads_real_persisted_documents_in_deterministic_order(tmp_path):
    snapshots = []
    for reverse in (False, True):
        engine = create_engine(f"sqlite:///{tmp_path / f'intake-{reverse}.db'}")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        _seed(factory, reverse=reverse)
        with factory() as session:
            resolved = resolve_customer_run_inputs(session, "0379100000726000101")
        snapshots.append(
            (
                resolved.registry_number,
                [document.display_name for document in resolved.documents],
                [document.text for document in resolved.documents],
                # The identity order is server-derived, rather than supplied by a caller.
                resolved.source_document_ids,
            )
        )
    assert snapshots[0] == snapshots[1]
    # The records carry generated UUIDs in each database, but canonical source
    # identities are derived from stable content, not those UUIDs.
    assert all(len(value) == 64 for value in snapshots[0][3])
    assert snapshots[0][1] == ["А-спецификация.txt", "Б-извещение.txt"]
    assert snapshots[0][2][0] == "first specification chunk\n\nsecond specification chunk"
