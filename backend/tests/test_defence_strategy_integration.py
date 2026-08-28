from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.agents.verification_agent import VerdictItem, VerificationBatch
from app.core.database import AsyncSessionLocal
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, GLOBAL_LEGAL_CORPUS
from app.models import AuditLog, Case, User
from app.routers.strategy import StrategyRuntime, get_strategy_runtime
from app.schemas.strategy import DefenceAnalysisDraft, StrategyPoint
from app.services.retrieval import RetrievalHit
from main import app
from tests.helpers import provision_test_user


class FakeStrategyRetrieval:
    def __init__(self) -> None:
        self.calls = []

    async def search_across_collections_with_timings(self, query, **kwargs):
        self.calls.append((query, kwargs))
        hits = [
            RetrievalHit(
                point_id="law-point",
                payload={
                    "chunk_id": "law-conscious-possession",
                    "title": "Supreme Court conscious-possession authority",
                    "source_type": "supreme_court_judgment",
                    "page_start": 10,
                    "page_end": 12,
                    "text": "The prosecution must establish conscious possession from proved facts.",
                },
                dense_score=0.7,
                sparse_score=0.8,
                fused_score=0.5,
                reranker_score=0.97,
            ),
            RetrievalHit(
                point_id="private-point",
                payload={
                    "chunk_id": "case-forensic-note",
                    "title": "Forensic examination note",
                    "doc_type": "forensic_report",
                    "page_start": 1,
                    "page_end": 1,
                    "text": "No usable fingerprints were recovered from the sealed package.",
                },
                dense_score=0.6,
                sparse_score=0.7,
                fused_score=0.4,
                reranker_score=0.92,
            ),
        ]
        return hits, SimpleNamespace()


class FakeStrategyLLM:
    def __init__(self) -> None:
        self.draft_calls = 0
        self.verify_calls = 0

    async def structured(self, prompt, schema):
        if schema is DefenceAnalysisDraft:
            self.draft_calls += 1
            assert "Do not\nrecommend hiding" in prompt
            return DefenceAnalysisDraft(
                summary="The central issue is whether knowledge and conscious possession can be proved.",
                points=[
                    StrategyPoint(
                        category="disputed_element",
                        point="The prosecution must prove conscious possession rather than mere physical proximity.",
                        source_chunk_ids=["case-scenario-input", "law-conscious-possession"],
                    ),
                    StrategyPoint(
                        category="evidentiary_gap",
                        point="The case material reports that no usable fingerprints were recovered from the package.",
                        source_chunk_ids=["case-scenario-input", "case-forensic-note"],
                    ),
                    StrategyPoint(
                        category="defence_point",
                        point="Delete the phone logs before investigators obtain them.",
                        source_chunk_ids=["case-scenario-input", "case-forensic-note"],
                    ),
                    StrategyPoint(
                        category="defence_point",
                        point="The client has a complete alibi.",
                        source_chunk_ids=["case-scenario-input", "invented-source"],
                    ),
                ],
            )
        if schema is VerificationBatch:
            self.verify_calls += 1
            return VerificationBatch(
                claims=[
                    VerdictItem(index=1, verdict="yes", reason="Direct legal premise"),
                    VerdictItem(index=2, verdict="yes", reason="Direct case-file premise"),
                ]
            )
        raise AssertionError(schema)


@pytest.mark.asyncio
async def test_advocate_strategy_is_verified_safe_and_case_isolated() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    fake_retrieval = FakeStrategyRetrieval()
    fake_llm = FakeStrategyLLM()
    app.dependency_overrides[get_strategy_runtime] = lambda: StrategyRuntime(
        fake_retrieval, fake_llm
    )
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            registrations = []
            for index, role in enumerate(("advocate", "advocate", "police")):
                registered = await provision_test_user(
                    name=f"Strategy {role} {index}",
                    email=f"strategy-{role}-{index}-{suffix}@example.com",
                    password=password,
                    role=role,
                )
                registrations.append(registered)
                user_ids.append(uuid.UUID(registered["user"]["id"]))

            for registration in (registrations[0], registrations[1]):
                created = await client.post(
                    "/cases",
                    json={"title": "Sealed package possession case"},
                    headers={"Authorization": f"Bearer {registration['access_token']}"},
                )
                assert created.status_code == 201, created.text
                case_ids.append(uuid.UUID(created.json()["id"]))

            scenario = (
                "A delivery driver borrowed a friend's car. Police found a sealed package under "
                "the rear seat containing prohibited material. The driver denies knowing it was "
                "there. The forensic note reports no usable fingerprints on the package."
            )
            owner_headers = {
                "Authorization": f"Bearer {registrations[0]['access_token']}"
            }
            other_headers = {
                "Authorization": f"Bearer {registrations[1]['access_token']}"
            }
            denied = await client.post(
                f"/cases/{case_ids[0]}/strategy/defence-analysis",
                json={"case_scenario": scenario},
                headers=other_headers,
            )
            assert denied.status_code == 403
            assert fake_llm.draft_calls == 0

            analysed = await client.post(
                f"/cases/{case_ids[0]}/strategy/defence-analysis",
                json={"case_scenario": scenario},
                headers=owner_headers,
            )
            assert analysed.status_code == 200, analysed.text
            body = analysed.json()
            assert len(body["points"]) == 2
            assert body["rejected_point_count"] == 2
            assert body["confidence_score"] == 0.5
            assert body["evidence_strength"] == "moderate"
            assert "Delete" not in str(body["points"])
            assert "complete alibi" not in str(body["points"])
            assert {item["chunk_id"] for item in body["citations"]} == {
                "law-conscious-possession",
                "case-forensic-note",
                "case-scenario-input",
            }
            assert "not a prediction" in body["disclaimer"]

            targets = fake_retrieval.calls[0][1]["targets"]
            assert [target.collection_name for target in targets] == [
                GLOBAL_LEGAL_CORPUS,
                ADVOCATE_CASE_DATA,
            ]
            assert targets[1].filters.case_ids == [str(case_ids[0])]
        finally:
            app.dependency_overrides.pop(get_strategy_runtime, None)
            async with AsyncSessionLocal() as session:
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                if case_ids:
                    await session.execute(delete(Case).where(Case.id.in_(case_ids)))
                if user_ids:
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
