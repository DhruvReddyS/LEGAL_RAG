"""The judgment index against a real Qdrant, in a collection of its own.

The fake evaluates filter objects the way this code expects them to behave. This
checks that Qdrant agrees, on payloads shaped as ingestion writes them. It never
touches a serving collection.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from qdrant_client import models

from app.core.qdrant import create_qdrant_client
from app.services.held_material import check_treatment
from app.services.judgment_index import JudgmentIndex
from tests.advocate_fakes import judgment_chunk


def _points() -> list[models.PointStruct]:
    records = [
        judgment_chunk("one", "ARNESH KUMAR vs STATE OF BIHAR Crl.A. No. 1277/2014", 1, "Arrest should not be mechanical.", year=2014),
        judgment_chunk("one", "ARNESH KUMAR vs STATE OF BIHAR Crl.A. No. 1277/2014", 2, "Second page of it.", year=2014),
        judgment_chunk(
            "two", "RAVI SHANKAR vs UNION OF INDIA W.P.(C) No. 12/2024", 1,
            "Arnesh Kumar v. State of Bihar was followed here.",
            court="High Court of Andhra Pradesh", year=2024, cited_cases=("Arnesh Kumar v. State",),
        ),
        judgment_chunk("held-back", "NOISE vs NOISE", 1, "Noise.", tier="quarantine"),
    ]
    act = judgment_chunk("act", "An Act", 1, "A section of an Act.")
    act.payload["source_type"] = "act"
    records.append(act)
    return [
        models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, record.id)), vector={}, payload=record.payload)
        for record in records
    ]


@pytest_asyncio.fixture(loop_scope="session")
async def collection():
    client = create_qdrant_client()
    name = f"advocate_track_index_test_{uuid.uuid4().hex}"
    await client.create_collection(collection_name=name, vectors_config={})
    await client.upsert(collection_name=name, points=_points(), wait=True)
    try:
        yield client, name
    finally:
        await client.delete_collection(collection_name=name)
        await client.close()


@pytest.mark.integration
async def test_it_counts_judgments_not_chunks_and_not_other_documents(collection) -> None:
    client, name = collection
    coverage = await JudgmentIndex(client, name).coverage()
    assert coverage.judgments_held == 2
    assert coverage.by_court == {"Supreme Court of India": 1, "High Court of Andhra Pradesh": 1}


@pytest.mark.integration
async def test_treatment_follows_real_edges_and_fetches_real_passages(collection) -> None:
    client, name = collection
    result = await check_treatment(index=JudgmentIndex(client, name), reference_text="Arnesh Kumar v. State of Bihar")
    assert [row["document_id"] for row in result["held"]] == ["one"]
    citing = result["cited_by"][0]
    assert citing["document_id"] == "two"
    assert "was followed here" in citing["passages"][0]["window"]
    assert citing["passages"][0]["words_near_reference"] == [{"word": "followed", "cautionary": False}]


@pytest.mark.integration
async def test_a_document_is_read_in_page_order(collection) -> None:
    client, name = collection
    chunks = await JudgmentIndex(client, name).document_chunks("one")
    assert [chunk["page_start"] for chunk in chunks] == [1, 2]
    assert await JudgmentIndex(client, name).document_chunks("held-back") == []


def test_the_filter_names_the_values_ingestion_actually_stores() -> None:
    from app.services.judgment_index import JUDGMENT_SOURCE_TYPES

    assert {"SUPREME_COURT_JUDGMENT", "HIGH_COURT_JUDGMENT"} <= set(JUDGMENT_SOURCE_TYPES)
