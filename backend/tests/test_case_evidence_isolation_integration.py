"""Evidence from one investigation must not surface in another's search.

Every other test of this boundary uses a fake retrieval service, so they prove
the *authorisation* is right -- a request for another user's case is refused --
without ever proving the *filter* is. Those are different failures: one is a
routing decision in Python, the other is whether Qdrant actually narrows the
result set. A wrong filter returns another investigation's evidence to a
correctly authorised user, and no amount of authorisation testing sees it.

This test therefore uses the real retrieval service and a real collection.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client import models
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.ingestion.init_qdrant import POLICE_CASE_DATA
from app.models import AuditLog, Case, CaseDocument, StorageObject, User
from app.routers.storage import get_retrieval_service
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalTarget,
)
from main import app
from tests.helpers import provision_test_user

pytestmark = pytest.mark.object_storage


@pytest.mark.asyncio
async def test_one_case_never_retrieves_another_cases_evidence() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []
    service = HybridRetrievalService()
    # The real service, not a fake. The lifespan that normally provides it does
    # not run under the test transport, and a fake here would defeat the point:
    # this test exists to check that Qdrant narrows the result set.
    app.dependency_overrides[get_retrieval_service] = lambda: service

    # Deliberately similar text. Two investigations about a missing vehicle
    # near the same park will embed close together, so only the case filter
    # can separate them -- which is the thing under test.
    evidence = {
        0: b"Witness saw a red hatchback leaving Cubbon Park at 18:30. "
           b"Registration partially noted as KA-01-HH-1234. Case marker ALPHA-77.",
        1: b"Witness saw a red hatchback leaving Cubbon Park at 18:45. "
           b"Registration partially noted as KA-01-HH-5678. Case marker BRAVO-99.",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            headers = []
            for index in range(2):
                body = await provision_test_user(
                    name=f"Isolation Officer {index}",
                    email=f"isolation-{index}-{suffix}@example.com",
                    password=password,
                    role="police",
                )
                user_ids.append(uuid.UUID(body["user"]["id"]))
                headers.append({"Authorization": f"Bearer {body['access_token']}"})

            for index in range(2):
                created = await client.post(
                    "/cases",
                    json={"title": f"Isolation matter {index}"},
                    headers=headers[index],
                )
                assert created.status_code == 201, created.text
                case_id = uuid.UUID(created.json()["id"])
                case_ids.append(case_id)

                uploaded = await client.post(
                    f"/cases/{case_id}/storage/objects",
                    headers=headers[index],
                    files={"file": (f"statement-{index}.txt", evidence[index], "text/plain")},
                )
                assert uploaded.status_code == 201, uploaded.text
                object_id = uuid.UUID(uploaded.json()["id"])

                indexed = await client.post(
                    f"/cases/{case_id}/storage/objects/{object_id}/index",
                    json={"doc_type": "witness_statement"},
                    headers=headers[index],
                )
                assert indexed.status_code == 201, indexed.text

            await service.warmup()

            # Both investigations must actually be in the collection at once,
            # or isolation is satisfied trivially and this test proves nothing.
            present = {
                str(case_id): (
                    await service.client.count(
                        collection_name=POLICE_CASE_DATA,
                        count_filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="case_id",
                                    match=models.MatchValue(value=str(case_id)),
                                )
                            ]
                        ),
                        exact=True,
                    )
                ).count
                for case_id in case_ids
            }
            assert all(count > 0 for count in present.values()), (
                f"both cases must hold evidence for this test to mean anything: {present}"
            )

            query = "red hatchback seen leaving the park"

            for index, marker, foreign_marker in (
                (0, "ALPHA-77", "BRAVO-99"),
                (1, "BRAVO-99", "ALPHA-77"),
            ):
                hits, _ = await service.search_across_collections_with_timings(
                    query,
                    targets=[
                        RetrievalTarget(
                            POLICE_CASE_DATA,
                            RetrievalFilters(
                                corpus_tiers=[], case_ids=[str(case_ids[index])]
                            ),
                        )
                    ],
                    candidate_limit=20,
                    result_limit=10,
                    rerank=False,
                )
                texts = " ".join(str(hit.payload.get("text") or "") for hit in hits)
                seen_cases = {str(hit.payload.get("case_id")) for hit in hits}

                assert hits, f"case {index} retrieved none of its own evidence"
                assert marker in texts, f"case {index} did not retrieve its own statement"
                assert foreign_marker not in texts, (
                    f"case {index} retrieved the other investigation's evidence"
                )
                assert seen_cases == {str(case_ids[index])}, (
                    f"case {index} saw foreign case ids: {seen_cases}"
                )
        finally:
            app.dependency_overrides.pop(get_retrieval_service, None)
            await service.close()
            # Remove the vectors this test wrote, so a private collection is not
            # left carrying test evidence.
            cleanup = HybridRetrievalService()
            try:
                for case_id in case_ids:
                    await cleanup.client.delete(
                        collection_name=POLICE_CASE_DATA,
                        points_selector=models.FilterSelector(
                            filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="case_id",
                                        match=models.MatchValue(value=str(case_id)),
                                    )
                                ]
                            )
                        ),
                        wait=True,
                    )
            finally:
                await cleanup.close()
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
