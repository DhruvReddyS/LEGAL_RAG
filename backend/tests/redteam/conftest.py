"""Shared fixtures for the cross-tenant suite.

Everything here uses real infrastructure. A fake retrieval service would prove
the authorisation decision is right while leaving a wrong Qdrant filter
completely undetected, and those are different bugs: the second one hands
another investigation's evidence to a correctly authorised caller.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from qdrant_client import models
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, POLICE_CASE_DATA
from app.models import AuditLog, Case, CaseDocument, StorageObject, User
from app.services.retrieval import HybridRetrievalService
from main import app
from tests.helpers import provision_test_user

PASSWORD = "CorrectHorseBattery99!"

# Deliberately near-identical statements. Two investigations into a red
# hatchback leaving the same park minutes apart embed close together, so only
# the tenant filter can separate them -- which is the property under test. A
# marker unique to each case is the tripwire.
EVIDENCE = {
    "police": (
        b"Witness statement: a red hatchback left Cubbon Park at 18:30. "
        b"Registration partially noted KA-01-HH-1234. Marker POLICEALPHA77."
    ),
    # A second matter of the same role, so it lands in the *same* collection.
    # This is the cell that matters most: between two police investigations
    # nothing separates the evidence except the case filter itself. With only
    # one case per collection, deleting that filter changed no test result,
    # because the collection boundary was silently doing the work.
    "police_two": (
        b"Witness statement: a red hatchback left Cubbon Park at 18:35. "
        b"Registration partially noted KA-01-HH-9012. Marker POLICEGAMMA55."
    ),
    "advocate": (
        b"Attendance note: a red hatchback left Cubbon Park at 18:45. "
        b"Registration partially noted KA-01-HH-5678. Marker ADVOCATEBRAVO99."
    ),
    "advocate_two": (
        b"Attendance note: a red hatchback left Cubbon Park at 18:50. "
        b"Registration partially noted KA-01-HH-3456. Marker ADVOCATEDELTA33."
    ),
}
MARKERS = {
    "police": "POLICEALPHA77",
    "police_two": "POLICEGAMMA55",
    "advocate": "ADVOCATEBRAVO99",
    "advocate_two": "ADVOCATEDELTA33",
}
COLLECTION_FOR = {
    "police": POLICE_CASE_DATA,
    "police_two": POLICE_CASE_DATA,
    "advocate": ADVOCATE_CASE_DATA,
    "advocate_two": ADVOCATE_CASE_DATA,
}
# The user role each tenant signs in as. Two of them share a role deliberately.
USER_ROLE_FOR = {
    "citizen": "citizen",
    "police": "police",
    "police_two": "police",
    "advocate": "advocate",
    "advocate_two": "advocate",
    "admin": "admin",
}
CASE_OWNERS = ("police", "police_two", "advocate", "advocate_two")

# A query that matches both statements, so any leak is a retrieval leak rather
# than a relevance accident.
SHARED_QUERY = "red hatchback seen leaving the park"


@dataclass
class RecordingRetrieval:
    """Delegates to the real service and records what was asked of it.

    Not a fake. The results come from Qdrant, so a broken filter shows up in
    the hits; the recorded targets additionally let a test assert that a
    private collection was never even queried, which is the stronger claim.
    """

    inner: HybridRetrievalService
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def search_across_collections_with_timings(self, query, **kwargs):
        self.calls.append(kwargs)
        return await self.inner.search_across_collections_with_timings(query, **kwargs)

    @property
    def client(self):
        return self.inner.client

    def __getattr__(self, name: str):
        """Forward everything not recorded to the real service.

        The indexing path calls `embed_documents` on this object. Enumerating
        the methods it happens to need today would mean this delegate silently
        stops being a real service the next time one is added, and the suite
        would quietly go back to testing a fake.
        """
        return getattr(self.inner, name)

    def targets_of_last_call(self) -> list[Any]:
        return list(self.calls[-1]["targets"]) if self.calls else []

    def private_collections_queried(self) -> set[str]:
        queried: set[str] = set()
        for call in self.calls:
            for target in call.get("targets", []):
                if target.collection_name in COLLECTION_FOR.values():
                    queried.add(target.collection_name)
        return queried

    def case_ids_queried(self) -> set[str]:
        seen: set[str] = set()
        for call in self.calls:
            for target in call.get("targets", []):
                if target.collection_name in COLLECTION_FOR.values():
                    seen.update(target.filters.case_ids or [])
        return seen


@dataclass
class Tenant:
    role: str
    user_id: uuid.UUID
    headers: dict[str, str]
    case_id: uuid.UUID | None = None
    marker: str | None = None


@dataclass
class RedTeamWorld:
    client: AsyncClient
    retrieval: RecordingRetrieval
    tenants: dict[str, Tenant]

    def actor(self, role: str) -> Tenant:
        return self.tenants[role]

    def foreign_markers(self, role: str) -> list[str]:
        return [
            tenant.marker
            for name, tenant in self.tenants.items()
            if name != role and tenant.marker
        ]


# The suite runs in the session loop (see pytest.ini). A fixture left on the
# default function loop opens its database connections on a different loop from
# the test that uses them, and asyncpg fails with "attached to a different
# loop" rather than anything about tenancy.
@pytest_asyncio.fixture(loop_scope="session")
async def world():
    """Two owned cases with indexed evidence, plus a citizen and an admin.

    Built once per test so a leak in one test cannot be masked by state another
    test left behind.
    """
    from app.routers.retrieval import get_retrieval_service as retrieval_dependency
    from app.routers.storage import get_retrieval_service as storage_dependency

    suffix = uuid.uuid4().hex[:12]
    service = HybridRetrievalService()
    recorder = RecordingRetrieval(inner=service)
    app.dependency_overrides[retrieval_dependency] = lambda: recorder
    app.dependency_overrides[storage_dependency] = lambda: recorder

    tenants: dict[str, Tenant] = {}
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            for role in USER_ROLE_FOR:
                body = await provision_test_user(
                    name=f"RedTeam {role} {suffix}",
                    email=f"redteam-{role}-{suffix}@example.com",
                    password=PASSWORD,
                    role=USER_ROLE_FOR[role],
                )
                user_id = uuid.UUID(body["user"]["id"])
                user_ids.append(user_id)
                tenants[role] = Tenant(
                    role=role,
                    user_id=user_id,
                    headers={"Authorization": f"Bearer {body['access_token']}"},
                )

            for role in CASE_OWNERS:
                tenant = tenants[role]
                created = await client.post(
                    "/cases",
                    json={"title": f"RedTeam {role} matter {suffix}"},
                    headers=tenant.headers,
                )
                assert created.status_code == 201, created.text
                tenant.case_id = uuid.UUID(created.json()["id"])
                tenant.marker = MARKERS[role]
                case_ids.append(tenant.case_id)

                uploaded = await client.post(
                    f"/cases/{tenant.case_id}/storage/objects",
                    headers=tenant.headers,
                    files={"file": (f"{role}.txt", EVIDENCE[role], "text/plain")},
                )
                assert uploaded.status_code == 201, uploaded.text
                object_id = uuid.UUID(uploaded.json()["id"])

                indexed = await client.post(
                    f"/cases/{tenant.case_id}/storage/objects/{object_id}/index",
                    json={"doc_type": "witness_statement"},
                    headers=tenant.headers,
                )
                assert indexed.status_code == 201, indexed.text

            await service.warmup()

            # Vacuity guard. If either case holds nothing, isolation is
            # satisfied by an empty index and every assertion below is
            # meaningless. This runs before any test body.
            for role in CASE_OWNERS:
                count = (
                    await service.client.count(
                        collection_name=COLLECTION_FOR[role],
                        count_filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="case_id",
                                    match=models.MatchValue(
                                        value=str(tenants[role].case_id)
                                    ),
                                )
                            ]
                        ),
                        exact=True,
                    )
                ).count
                assert count > 0, (
                    f"{role} case holds no indexed evidence, so isolation would "
                    "pass trivially and this suite would prove nothing"
                )

            recorder.calls.clear()
            yield RedTeamWorld(client=client, retrieval=recorder, tenants=tenants)
        finally:
            app.dependency_overrides.pop(retrieval_dependency, None)
            app.dependency_overrides.pop(storage_dependency, None)
            cleanup = HybridRetrievalService()
            try:
                for role in CASE_OWNERS:
                    tenant = tenants.get(role)
                    if tenant is None or tenant.case_id is None:
                        continue
                    await cleanup.client.delete(
                        collection_name=COLLECTION_FOR[role],
                        points_selector=models.FilterSelector(
                            filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="case_id",
                                        match=models.MatchValue(value=str(tenant.case_id)),
                                    )
                                ]
                            )
                        ),
                        wait=True,
                    )
            finally:
                await cleanup.close()
                await service.close()
            async with AsyncSessionLocal() as session:
                if case_ids:
                    await session.execute(
                        delete(CaseDocument).where(CaseDocument.case_id.in_(case_ids))
                    )
                    await session.execute(
                        delete(StorageObject).where(StorageObject.case_id.in_(case_ids))
                    )
                    await session.execute(
                        delete(AuditLog).where(AuditLog.resource_id.in_(case_ids))
                    )
                    await session.execute(delete(Case).where(Case.id.in_(case_ids)))
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
