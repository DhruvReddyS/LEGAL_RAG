"""An administrator is not a party to every matter.

The admin role profile states that administrative access "does not authorise
... disclosure of private case material outside an explicitly authorised
matter". A general search is precisely not an authorised matter, so it must
not sweep the private corpora.

The existing scope test covers a case owner. Nothing covered an admin, and the
owner filter in `resolve_authorized_case_scope` is skipped for them.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.models import AuditLog, Case, User
from app.routers.retrieval import get_retrieval_service
from main import app
from tests.helpers import provision_test_user


class CapturingRetrievalService:
    def __init__(self) -> None:
        self.calls = []

    async def search_across_collections_with_timings(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return [], SimpleNamespace()


@pytest.mark.asyncio
async def test_an_admin_general_search_does_not_reach_private_case_corpora() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []
    fake = CapturingRetrievalService()
    app.dependency_overrides[get_retrieval_service] = lambda: fake

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            officer = await provision_test_user(
                name="Case Owning Officer",
                email=f"owner-{suffix}@example.com",
                password=password,
                role="police",
            )
            user_ids.append(uuid.UUID(officer["user"]["id"]))
            created = await client.post(
                "/cases",
                json={"title": "Someone else's investigation"},
                headers={"Authorization": f"Bearer {officer['access_token']}"},
            )
            assert created.status_code == 201, created.text
            case_ids.append(uuid.UUID(created.json()["id"]))

            administrator = await provision_test_user(
                name="System Administrator",
                email=f"admin-{suffix}@example.com",
                password=password,
                role="admin",
            )
            user_ids.append(uuid.UUID(administrator["user"]["id"]))

            general = await client.post(
                "/retrieval/scoped-search?mode=general",
                json={"query": "what does the evidence show", "candidate_limit": 5, "result_limit": 2},
                headers={"Authorization": f"Bearer {administrator['access_token']}"},
            )
            assert general.status_code == 200, general.text

            body = general.json()
            assert body["authorized_case_ids"] == [], (
                "an admin general search enumerated other users' cases: "
                f"{body['authorized_case_ids']}"
            )

            targets = fake.calls[-1][1]["targets"]
            collections = [target.collection_name for target in targets]
            assert collections == [GLOBAL_LEGAL_CORPUS], (
                "an admin general search queried a private case corpus: "
                f"{collections}"
            )
        finally:
            app.dependency_overrides.pop(get_retrieval_service, None)
            async with AsyncSessionLocal() as session:
                if case_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.resource_id.in_(case_ids)))
                    await session.execute(delete(Case).where(Case.id.in_(case_ids)))
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


@pytest.mark.asyncio
async def test_an_admin_may_still_reach_an_explicitly_named_matter() -> None:
    """The other direction, so the narrowing does not break support and audit.

    Naming the case is what makes it an authorised matter, and what leaves a
    record of which matter was opened.
    """
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []
    fake = CapturingRetrievalService()
    app.dependency_overrides[get_retrieval_service] = lambda: fake

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            officer = await provision_test_user(
                name="Investigating Officer",
                email=f"named-owner-{suffix}@example.com",
                password=password,
                role="police",
            )
            user_ids.append(uuid.UUID(officer["user"]["id"]))
            created = await client.post(
                "/cases",
                json={"title": "Matter under review"},
                headers={"Authorization": f"Bearer {officer['access_token']}"},
            )
            assert created.status_code == 201, created.text
            case_id = uuid.UUID(created.json()["id"])
            case_ids.append(case_id)

            administrator = await provision_test_user(
                name="Reviewing Administrator",
                email=f"named-admin-{suffix}@example.com",
                password=password,
                role="admin",
            )
            user_ids.append(uuid.UUID(administrator["user"]["id"]))

            named = await client.post(
                f"/retrieval/scoped-search?mode=case_specific&case_id={case_id}",
                json={"query": "evidence review", "candidate_limit": 5, "result_limit": 2},
                headers={"Authorization": f"Bearer {administrator['access_token']}"},
            )
            assert named.status_code == 200, named.text
            assert named.json()["authorized_case_ids"] == [str(case_id)]
        finally:
            app.dependency_overrides.pop(get_retrieval_service, None)
            async with AsyncSessionLocal() as session:
                if case_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.resource_id.in_(case_ids)))
                    await session.execute(delete(Case).where(Case.id.in_(case_ids)))
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
