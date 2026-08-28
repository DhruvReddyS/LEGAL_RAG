from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, Case, GeneratedDocument, User
from app.routers.documents import DraftingRuntime, get_drafting_runtime
from app.schemas.documents import FIRFacts
from app.services.retrieval import RetrievalHit
from main import app
from tests.helpers import provision_test_user


class FakeDraftLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def structured(self, prompt, schema):
        self.calls += 1
        assert schema is FIRFacts
        assert "Never infer" in prompt
        return FIRFacts(
            complainant_name="Anita Rao",
            incident_date="2026-08-24",
            incident_time="18:30",
            incident_location="Cubbon Park, Bengaluru",
            subject_or_property="brown Labrador named Bruno",
            suspected_offence_or_circumstance="Missing; theft is not confirmed",
            witness_details=["A walker saw a red hatchback nearby"],
            identification_details=["Collar number PET-204"],
            narrative="Bruno went missing during an evening walk; the available facts do not confirm theft.",
            requested_action="Record the complaint, help trace Bruno, and investigate if evidence indicates an offence.",
        )


class FakeDraftRetrieval:
    def __init__(self) -> None:
        self.calls = []

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return [
            RetrievalHit(
                point_id="authority-point",
                payload={
                    "chunk_id": "fir-authority-1",
                    "title": "Official FIR Registration Advisory",
                    "source_type": "government_guidance",
                    "section": "154 CrPC",
                    "page_start": 1,
                    "page_end": 2,
                    "text": "Where information discloses a cognizable offence, registration is mandatory.",
                },
                dense_score=0.7,
                sparse_score=0.8,
                fused_score=0.5,
                reranker_score=0.96,
            )
        ]


@pytest.mark.asyncio
async def test_missing_dog_fir_draft_is_grounded_versioned_and_owner_isolated() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    fake_llm = FakeDraftLLM()
    fake_retrieval = FakeDraftRetrieval()
    app.dependency_overrides[get_drafting_runtime] = lambda: DraftingRuntime(
        retrieval=fake_retrieval, llm=fake_llm
    )
    user_ids: list[uuid.UUID] = []
    case_id: uuid.UUID | None = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            tokens = []
            for index in range(2):
                body = await provision_test_user(
                    name=f"Draft Officer {index}",
                    email=f"draft-officer-{index}-{suffix}@example.com",
                    password=password,
                    role="police",
                )
                tokens.append(body["access_token"])
                user_ids.append(uuid.UUID(body["user"]["id"]))

            owner_headers = {"Authorization": f"Bearer {tokens[0]}"}
            other_headers = {"Authorization": f"Bearer {tokens[1]}"}
            created = await client.post(
                "/cases", json={"title": "Bruno missing complaint"}, headers=owner_headers
            )
            assert created.status_code == 201, created.text
            case_id = uuid.UUID(created.json()["id"])
            description = (
                "I am Anita Rao. My brown Labrador Bruno, collar PET-204, went missing "
                "near Cubbon Park on 24 August 2026 around 6:30 PM. A walker noticed a "
                "red hatchback, but nobody saw Bruno being taken. Please help trace him."
            )

            denied = await client.post(
                f"/cases/{case_id}/documents/draft",
                json={"doc_type": "fir", "case_description": description},
                headers=other_headers,
            )
            assert denied.status_code == 403
            assert fake_llm.calls == 0

            versions = []
            for _ in range(2):
                drafted = await client.post(
                    f"/cases/{case_id}/documents/draft",
                    json={"doc_type": "fir", "case_description": description},
                    headers=owner_headers,
                )
                assert drafted.status_code == 201, drafted.text
                body = drafted.json()
                versions.append(body["version"])
                assert body["status"] == "draft"
                assert body["missing_fields"] == []
                assert body["facts"]["subject_or_property"] == "brown Labrador named Bruno"
                assert body["authorities"][0]["chunk_id"] == "fir-authority-1"
                assert "[SRC:fir-authority-1]" in body["rendered_text"]
                assert "theft is not confirmed" in body["rendered_text"]
                assert "DRAFT FOR REVIEW" in body["disclaimer"]
            assert versions == [1, 2]
            assert all(not call[1]["filters"].current_only for call in fake_retrieval.calls)

            async with AsyncSessionLocal() as session:
                count = await session.scalar(
                    select(func.count(GeneratedDocument.id)).where(
                        GeneratedDocument.case_id == case_id,
                        GeneratedDocument.doc_type == "fir",
                    )
                )
                assert count == 2
        finally:
            app.dependency_overrides.pop(get_drafting_runtime, None)
            async with AsyncSessionLocal() as session:
                if case_id:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(
                        delete(GeneratedDocument).where(GeneratedDocument.case_id == case_id)
                    )
                    await session.execute(delete(Case).where(Case.id == case_id))
                if user_ids:
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


def test_incomplete_fir_never_silently_invents_required_facts() -> None:
    from app.agents.drafting_agent import missing_fir_fields, render_fir

    facts = FIRFacts(narrative="My dog is missing. I do not know when or where it happened.")
    missing = missing_fir_fields(facts)
    rendered = render_fir(facts, [])

    assert missing == [
        "complainant_name",
        "incident_date",
        "incident_location",
        "subject_or_property",
    ]
    assert rendered.count("[INFORMATION REQUIRED]") >= 4
    assert "do not insert a section without review" in rendered


def test_explicit_missing_pet_and_collar_are_recovered_without_inference() -> None:
    from app.agents.drafting_agent import recover_explicit_missing_item

    facts = FIRFacts(
        narrative="Bruno went missing, but nobody saw him being taken.",
        suspected_offence_or_circumstance=None,
    )
    recovered = recover_explicit_missing_item(
        facts,
        "My brown Labrador Bruno, collar PET-204, went missing near the park.",
    )

    assert recovered.subject_or_property == "brown Labrador Bruno"
    assert recovered.identification_details == ["Collar number PET-204"]
    assert recovered.suspected_offence_or_circumstance is None
