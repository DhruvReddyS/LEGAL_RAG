from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS, POLICE_CASE_DATA
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
async def test_scoped_search_resolves_only_authorized_cases_before_qdrant() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []
    fake = CapturingRetrievalService()
    app.dependency_overrides[get_retrieval_service] = lambda: fake

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            tokens = []
            for index in range(2):
                body = await provision_test_user(
                    name=f"Scoped Officer {index}",
                    email=f"scoped-officer-{index}-{suffix}@example.com",
                    password=password,
                    role="police",
                )
                tokens.append(body["access_token"])
                user_ids.append(uuid.UUID(body["user"]["id"]))

            for index, token in enumerate(tokens):
                created = await client.post(
                    "/cases",
                    json={"title": f"Private scope {index}"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert created.status_code == 201, created.text
                case_ids.append(uuid.UUID(created.json()["id"]))

            owner_headers = {"Authorization": f"Bearer {tokens[0]}"}
            own = await client.post(
                f"/retrieval/scoped-search?mode=case_specific&case_id={case_ids[0]}",
                json={"query": "missing dog FIR", "candidate_limit": 5, "result_limit": 2},
                headers=owner_headers,
            )
            assert own.status_code == 200, own.text
            assert own.json()["authorized_case_ids"] == [str(case_ids[0])]
            targets = fake.calls[-1][1]["targets"]
            assert [target.collection_name for target in targets] == [
                GLOBAL_LEGAL_CORPUS,
                POLICE_CASE_DATA,
            ]
            assert targets[1].filters.case_ids == [str(case_ids[0])]

            denied = await client.post(
                f"/retrieval/scoped-search?mode=case_specific&case_id={case_ids[1]}",
                json={"query": "private evidence", "candidate_limit": 5, "result_limit": 2},
                headers=owner_headers,
            )
            assert denied.status_code == 404
            assert len(fake.calls) == 1

            general = await client.post(
                "/retrieval/scoped-search?mode=general",
                json={"query": "all my cases", "candidate_limit": 5, "result_limit": 2},
                headers=owner_headers,
            )
            assert general.status_code == 200, general.text
            assert general.json()["authorized_case_ids"] == [str(case_ids[0])]
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
