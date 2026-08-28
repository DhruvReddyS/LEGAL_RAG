from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.ingestion.embedder import EmbeddedText
from app.ingestion.extract import ExtractedPage
from app.models import AuditLog, CorpusIntake, CorpusSource, StorageObject, User
from app.models.enums import CorpusSourceType, UserRole
from app.models.storage import StorageNamespace
from app.services.admin import publish_corpus_intake
from app.services.storage import DocumentStorageService
from main import app


class _FakeQdrant:
    def __init__(self) -> None:
        self.points = []

    async def upsert(self, **kwargs) -> None:
        self.points.extend(kwargs["points"])


class _FakeRetrieval:
    def __init__(self) -> None:
        self.client = _FakeQdrant()

    async def embed_documents(self, texts: list[str], batch_size: int):
        del batch_size
        return [EmbeddedText(dense=[0.1] * 1024, sparse={1: 0.5}) for _ in texts]


@pytest.mark.asyncio
async def test_admin_manages_professional_lifecycle_and_non_admin_is_denied() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    admin = User(
        name="Control Plane Admin",
        email=f"admin-control-{suffix}@example.com",
        hashed_password=hash_password(password),
        role=UserRole.ADMIN,
    )
    async with AsyncSessionLocal() as session:
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id
        admin_token = create_access_token(admin)

    professional_id: uuid.UUID | None = None
    citizen_id: uuid.UUID | None = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            citizen_registration = await client.post(
                "/auth/register",
                json={
                    "name": "Denied Citizen",
                    "email": f"admin-denied-{suffix}@example.com",
                    "password": password,
                    "role": "citizen",
                },
            )
            assert citizen_registration.status_code == 201
            citizen = citizen_registration.json()
            citizen_id = uuid.UUID(citizen["user"]["id"])
            denied = await client.get(
                "/admin/users",
                headers={"Authorization": f"Bearer {citizen['access_token']}"},
            )
            assert denied.status_code == 403

            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            created = await client.post(
                "/admin/users",
                headers=admin_headers,
                json={
                    "name": "Managed Police Officer",
                    "email": f"managed-police-{suffix}@example.com",
                    "password": password,
                    "role": "police",
                },
            )
            assert created.status_code == 201, created.text
            assert created.json()["is_active"] is True
            professional_id = uuid.UUID(created.json()["id"])

            listed = await client.get("/admin/users", headers=admin_headers)
            assert listed.status_code == 200
            assert any(item["id"] == str(professional_id) for item in listed.json()["users"])

            login = await client.post(
                "/auth/login",
                json={"email": f"managed-police-{suffix}@example.com", "password": password},
            )
            assert login.status_code == 200
            professional_token = login.json()["access_token"]

            suspended = await client.patch(
                f"/admin/users/{professional_id}",
                headers=admin_headers,
                json={"is_active": False},
            )
            assert suspended.status_code == 200, suspended.text
            assert suspended.json()["is_active"] is False

            old_session = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {professional_token}"},
            )
            assert old_session.status_code == 401
            blocked_login = await client.post(
                "/auth/login",
                json={"email": f"managed-police-{suffix}@example.com", "password": password},
            )
            assert blocked_login.status_code == 401

            reactivated = await client.patch(
                f"/admin/users/{professional_id}",
                headers=admin_headers,
                json={"is_active": True, "role": "advocate"},
            )
            assert reactivated.status_code == 200
            assert reactivated.json()["role"] == "advocate"
            assert reactivated.json()["is_active"] is True

            invalid_pdf = await client.post(
                "/admin/corpus/intakes",
                headers=admin_headers,
                data={
                    "title": "Invalid Source",
                    "source_type": "act",
                    "jurisdiction": "India",
                    "source_url": "https://example.gov/source.pdf",
                },
                files={"file": ("source.pdf", b"not a pdf", "application/pdf")},
            )
            assert invalid_pdf.status_code == 422

            overview = await client.get("/admin/overview", headers=admin_headers)
            assert overview.status_code == 200
            assert overview.json()["users_total"] >= 3
        finally:
            async with AsyncSessionLocal() as session:
                ids = [item for item in (admin_id, professional_id, citizen_id) if item]
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(ids)))
                await session.execute(delete(AuditLog).where(AuditLog.resource_id.in_(ids)))
                await session.execute(delete(User).where(User.id.in_(ids)))
                await session.commit()


@pytest.mark.asyncio
async def test_validated_corpus_intake_publishes_only_to_extended_tier(monkeypatch) -> None:
    admin = User(
        name="Corpus Admin",
        email=f"corpus-admin-{uuid.uuid4().hex}@example.com",
        hashed_password=hash_password("CorrectHorseBattery99!"),
        role=UserRole.ADMIN,
    )
    source_id = None
    storage_id = None
    intake_id = None
    async with AsyncSessionLocal() as session:
        try:
            session.add(admin)
            await session.flush()
            stored = StorageObject(
                bucket="legal-rag-corpus",
                object_key=f"tests/{uuid.uuid4()}/source.pdf",
                namespace=StorageNamespace.LEGAL_CORPUS,
                owner_id=admin.id,
                case_id=None,
                original_filename="official-source.pdf",
                content_type="application/pdf",
                file_size=200,
                sha256="a" * 64,
            )
            session.add(stored)
            await session.flush()
            intake = CorpusIntake(
                storage_object_id=stored.id,
                uploaded_by=admin.id,
                title="Official Test Act",
                source_type=CorpusSourceType.ACT,
                jurisdiction="India",
                authority="Test Legislature",
                source_url="https://example.gov/official-source.pdf",
                status="validated",
                validation_summary={"quality_gate": "pass"},
            )
            session.add(intake)
            await session.commit()
            storage_id, intake_id = stored.id, intake.id

            async def fake_download(self, object_id, user):
                del self, object_id, user
                return b"%PDF-test"

            async def fake_extract(stored_object, content):
                del stored_object, content
                return [
                    ExtractedPage(
                        page_number=1,
                        text="A verified legal provision " * 60,
                        original_page_text="A verified legal provision " * 60,
                        extraction_method="text",
                        ocr_used=False,
                    )
                ]

            monkeypatch.setattr(DocumentStorageService, "download_case_document", fake_download)
            monkeypatch.setattr("app.services.admin._extract_pages", fake_extract)
            retrieval = _FakeRetrieval()
            result, _, indexed = await publish_corpus_intake(
                session,
                intake=intake,
                admin=admin,
                retrieval=retrieval,  # type: ignore[arg-type]
            )
            source_id = result.corpus_source_id
            assert result.status == "published"
            assert indexed > 0
            assert all(point.payload["corpus_tier"] == "extended" for point in retrieval.client.points)
            assert all(point.payload["verified_official"] is True for point in retrieval.client.points)
        finally:
            await session.execute(delete(AuditLog).where(AuditLog.user_id == admin.id))
            if intake_id:
                await session.execute(delete(CorpusIntake).where(CorpusIntake.id == intake_id))
            if storage_id:
                await session.execute(delete(StorageObject).where(StorageObject.id == storage_id))
            if source_id:
                await session.execute(delete(CorpusSource).where(CorpusSource.id == source_id))
            await session.execute(delete(User).where(User.id == admin.id))
            await session.commit()
