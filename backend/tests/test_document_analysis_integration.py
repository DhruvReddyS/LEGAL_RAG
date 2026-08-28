from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, Case, CaseDocument, GeneratedDocument, User
from app.routers.document_analysis import AnalyzerRuntime, get_analyzer_runtime
from app.services.retrieval import RetrievalHit
from main import app
from tests.helpers import provision_test_user


class FakeAnalyzerClient:
    def __init__(self, *, case_id: uuid.UUID, document_id: uuid.UUID) -> None:
        self.private_point = SimpleNamespace(
            id=uuid.uuid4(),
            payload={
                "chunk_id": "case-chunk-demo",
                "case_id": str(case_id),
                "document_id": str(document_id),
                "storage_object_id": str(uuid.uuid4()),
                "title": "Demo statement",
                "doc_type": "witness_statement",
                "page_start": 1,
                "page_end": 1,
                "text": "The witness recorded the incident date and location.",
            },
        )

    async def scroll(self, **kwargs):
        return [self.private_point], None

    async def retrieve(self, **kwargs):
        return [self.private_point]


class FakeAnalyzerRetrieval:
    def __init__(self, *, case_id: uuid.UUID, document_id: uuid.UUID) -> None:
        self.client = FakeAnalyzerClient(case_id=case_id, document_id=document_id)

    async def search(self, query, **kwargs):
        return [
            RetrievalHit(
                point_id=str(uuid.uuid4()),
                payload={
                    "chunk_id": "gold-section-154",
                    "title": "Code of Criminal Procedure",
                    "act_name": "Code of Criminal Procedure",
                    "source_type": "act",
                    "section": "Section 154",
                    "page_start": 42,
                    "page_end": 42,
                    "text": "Section 154 concerns information in cognizable cases.",
                    "corpus_tier": "gold",
                    "quality_status": "accepted",
                    "is_current": False,
                },
                dense_score=0.8,
                sparse_score=0.7,
                fused_score=0.75,
                reranker_score=0.75,
            )
        ]


class FakeAnalyzerLlm:
    async def structured(self, prompt, schema, **kwargs):
        return schema.model_validate(
            {
                "summary": "The statement records an incident date and location.",
                "key_clauses": [
                    {
                        "text": "An incident date and location are recorded.",
                        "severity": "information",
                        "source_chunk_ids": ["case-chunk-demo"],
                    }
                ],
                "risks": [
                    {
                        "text": "The account still requires professional corroboration.",
                        "severity": "review",
                        "source_chunk_ids": ["case-chunk-demo"],
                    }
                ],
                "applicable_sections": [
                    {
                        "label": "Section 154 CrPC",
                        "rationale": "Potentially relevant to recording cognizable information.",
                    },
                    {
                        "label": "Section 999 Imaginary Act",
                        "rationale": "This hallucinated section must be rejected.",
                    },
                ],
            }
        )


@pytest.mark.asyncio
async def test_document_analysis_is_owned_grounded_and_audited() -> None:
    suffix = uuid.uuid4().hex
    user_ids: list[uuid.UUID] = []
    case_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            registrations = []
            for index in range(2):
                account = await provision_test_user(
                    name=f"Analyzer Officer {index}",
                    email=f"analyzer-{index}-{suffix}@example.com",
                    password="CorrectHorseBattery99!",
                    role="police",
                )
                registrations.append(account)
                user_ids.append(uuid.UUID(account["user"]["id"]))
            citizen = await provision_test_user(
                name="Analyzer Citizen",
                email=f"analyzer-citizen-{suffix}@example.com",
                password="CorrectHorseBattery99!",
                role="citizen",
            )
            user_ids.append(uuid.UUID(citizen["user"]["id"]))
            owner_headers = {"Authorization": f"Bearer {registrations[0]['access_token']}"}
            other_headers = {"Authorization": f"Bearer {registrations[1]['access_token']}"}
            citizen_headers = {"Authorization": f"Bearer {citizen['access_token']}"}
            created = await client.post(
                "/cases", json={"title": "Analyzer isolation case"}, headers=owner_headers
            )
            assert created.status_code == 201, created.text
            case_id = uuid.UUID(created.json()["id"])
            async with AsyncSessionLocal() as session:
                document = CaseDocument(
                    case_id=case_id,
                    file_url="s3://test/analyzer.txt",
                    doc_type="witness_statement",
                    ocr_text="The witness recorded the incident date and location.",
                )
                session.add(document)
                await session.commit()
                await session.refresh(document)
                document_id = document.id

            fake = FakeAnalyzerRetrieval(case_id=case_id, document_id=document_id)
            app.dependency_overrides[get_analyzer_runtime] = lambda: AnalyzerRuntime(
                retrieval=fake,
                llm=FakeAnalyzerLlm(),
            )
            path = f"/documents/analyze?case_id={case_id}"
            denied_owner = await client.post(
                path, json={"document_id": str(document_id)}, headers=other_headers
            )
            assert denied_owner.status_code == 403
            denied_citizen = await client.post(
                path, json={"document_id": str(document_id)}, headers=citizen_headers
            )
            assert denied_citizen.status_code == 403

            response = await client.post(
                path,
                json={"document_id": str(document_id), "focus": "procedure and missing proof"},
                headers=owner_headers,
            )
            assert response.status_code == 201, response.text
            body = response.json()
            assert set(("summary", "key_clauses", "risks", "applicable_sections")) <= body.keys()
            assert len(body["applicable_sections"]) == 1
            assert body["applicable_sections"][0]["label"] == "Section 154 CrPC"
            assert body["applicable_sections"][0]["evidence"]["current_status"] == "status_unverified"
            assert body["rejected_section_count"] == 1
            assert body["key_clauses"][0]["evidence"][0]["chunk_id"] == "case-chunk-demo"
            latest = await client.get(
                f"/documents/analyses/latest?case_id={case_id}&document_id={document_id}",
                headers=owner_headers,
            )
            assert latest.status_code == 200, latest.text
            assert latest.json()["id"] == body["id"]
            assert latest.json()["version"] == 1

            listed = await client.get(
                f"/cases/{case_id}/documents/indexed", headers=owner_headers
            )
            assert listed.status_code == 200, listed.text
            assert listed.json()["total"] == 1
            assert listed.json()["documents"][0]["chunk_count"] == 1
            assert (
                await client.get(
                    f"/cases/{case_id}/documents/indexed", headers=other_headers
                )
            ).status_code == 403

            inspected = await client.get(
                f"/cases/{case_id}/sources/{fake.client.private_point.id}",
                headers=owner_headers,
            )
            assert inspected.status_code == 200, inspected.text
            inspection = inspected.json()
            assert inspection["source_title"] == "Demo statement"
            assert inspection["page_start"] == 1
            assert inspection["retrieved_passage"]
            assert inspection["verification_status"] == "verified"
            assert inspection["current_status"] == "not_applicable"
            assert (
                await client.get(
                    f"/cases/{case_id}/sources/{fake.client.private_point.id}",
                    headers=other_headers,
                )
            ).status_code == 403

            async with AsyncSessionLocal() as session:
                generated = await session.get(GeneratedDocument, uuid.UUID(body["id"]))
                assert generated is not None
                assert generated.content["document_id"] == str(document_id)
        finally:
            app.dependency_overrides.clear()
            async with AsyncSessionLocal() as session:
                if case_id:
                    await session.execute(
                        delete(AuditLog).where(
                            (AuditLog.resource_id == case_id)
                            | (AuditLog.metadata_["case_id"].astext == str(case_id))
                        )
                    )
                    await session.execute(delete(GeneratedDocument).where(GeneratedDocument.case_id == case_id))
                    await session.execute(delete(CaseDocument).where(CaseDocument.case_id == case_id))
                    await session.execute(delete(Case).where(Case.id == case_id))
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
