from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.ingestion.embedder import EmbeddedText
from app.ingestion.init_qdrant import POLICE_CASE_DATA
from app.models import AuditLog, Case, CaseDocument, StorageObject, User
from app.routers.storage import get_retrieval_service
from app.services.storage import create_s3_client
from main import app
from tests.helpers import provision_test_user


class FakePrivateQdrant:
    def __init__(self) -> None:
        self.upserts = []
        self.deletes = []

    async def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    async def scroll(self, **kwargs):
        return [], None

    async def delete(self, **kwargs):
        self.deletes.append(kwargs)


class FakeIndexingRetrieval:
    def __init__(self) -> None:
        self.client = FakePrivateQdrant()
        self.embedding_calls: list[list[str]] = []

    async def embed_documents(self, texts, *, batch_size):
        self.embedding_calls.append(texts)
        return [EmbeddedText(dense=[0.1], sparse={3: 0.8}) for _ in texts]


@pytest.mark.asyncio
async def test_text_evidence_indexing_is_idempotent_and_private() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    fake = FakeIndexingRetrieval()
    app.dependency_overrides[get_retrieval_service] = lambda: fake
    user_ids: list[uuid.UUID] = []
    case_id: uuid.UUID | None = None
    object_id: uuid.UUID | None = None
    stored_bucket: str | None = None
    stored_key: str | None = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            tokens = []
            for index in range(2):
                body = await provision_test_user(
                    name=f"Evidence Officer {index}",
                    email=f"evidence-officer-{index}-{suffix}@example.com",
                    password=password,
                    role="police",
                )
                tokens.append(body["access_token"])
                user_ids.append(uuid.UUID(body["user"]["id"]))

            owner_headers = {"Authorization": f"Bearer {tokens[0]}"}
            other_headers = {"Authorization": f"Bearer {tokens[1]}"}
            created = await client.post(
                "/cases", json={"title": "Missing dog evidence"}, headers=owner_headers
            )
            assert created.status_code == 201, created.text
            case_id = uuid.UUID(created.json()["id"])

            evidence = (
                b"The complainant's brown Labrador Bruno disappeared near Cubbon Park "
                b"at 18:30. A red hatchback was seen nearby. Collar number PET-204."
            )
            uploaded = await client.post(
                f"/cases/{case_id}/storage/objects",
                headers=owner_headers,
                files={"file": ("dog-statement.txt", evidence, "text/plain")},
            )
            assert uploaded.status_code == 201, uploaded.text
            stored = uploaded.json()
            object_id = uuid.UUID(stored["id"])
            stored_bucket, stored_key = stored["bucket"], stored["object_key"]

            denied = await client.post(
                f"/cases/{case_id}/storage/objects/{object_id}/index",
                json={"doc_type": "witness_statement"},
                headers=other_headers,
            )
            assert denied.status_code == 403
            assert fake.embedding_calls == []

            first = await client.post(
                f"/cases/{case_id}/storage/objects/{object_id}/index",
                json={"doc_type": "witness_statement"},
                headers=owner_headers,
            )
            assert first.status_code == 201, first.text
            assert first.json()["pages"] == 1
            assert first.json()["chunks"] == 1

            second = await client.post(
                f"/cases/{case_id}/storage/objects/{object_id}/index",
                json={"doc_type": "witness_statement"},
                headers=owner_headers,
            )
            assert second.status_code == 201, second.text
            assert second.json()["document_id"] == first.json()["document_id"]
            assert len(fake.client.upserts) == 2
            assert all(
                call["collection_name"] == POLICE_CASE_DATA
                for call in fake.client.upserts
            )
            first_point = fake.client.upserts[0]["points"][0]
            second_point = fake.client.upserts[1]["points"][0]
            assert first_point.id == second_point.id
            assert first_point.payload["case_id"] == str(case_id)
            assert first_point.payload["corpus_scope"] == "private_case"
            assert "Bruno" in first_point.payload["text"]

            async with AsyncSessionLocal() as session:
                count = await session.scalar(
                    select(func.count(CaseDocument.id)).where(CaseDocument.case_id == case_id)
                )
                assert count == 1
        finally:
            app.dependency_overrides.pop(get_retrieval_service, None)
            if stored_bucket and stored_key:
                await asyncio.to_thread(
                    create_s3_client().delete_object,
                    Bucket=stored_bucket,
                    Key=stored_key,
                )
            async with AsyncSessionLocal() as session:
                if case_id:
                    await session.execute(
                        delete(AuditLog).where(
                            (AuditLog.resource_id == case_id)
                            | (AuditLog.metadata_["case_id"].astext == str(case_id))
                        )
                    )
                    await session.execute(delete(StorageObject).where(StorageObject.case_id == case_id))
                    await session.execute(delete(CaseDocument).where(CaseDocument.case_id == case_id))
                    await session.execute(delete(Case).where(Case.id == case_id))
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
