from __future__ import annotations

import uuid
import asyncio
from time import perf_counter

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models import (
    AuditLog,
    Case,
    CaseDocument,
    ChatMessage,
    ChatSession,
    Job,
    StorageNamespace,
    StorageObject,
    User,
)
from app.models.enums import CaseRoleType, ChatMessageRole, JobStatus
from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent
from app.services.job_worker import DurableJobWorker
from main import app
from tests.helpers import provision_test_user


class FakeDeepWorkflow:
    async def run(self, **_: object) -> dict:
        return {
            "final_answer": "Grounded Deep answer [SRC:job-chunk].",
            "citations": [
                AgentCitation(
                    number=1,
                    chunk_id="job-chunk",
                    title="Job Test Authority",
                    source_type="act",
                    page_start=1,
                    page_end=1,
                    excerpt="Grounded authority.",
                )
            ],
            "confidence_score": 0.8,
            "evidence_strength": "moderate",
            "intent": QueryIntent(retrieval_query="deep job test"),
            "agent_trace": [AgentTraceEvent(node="verification", details={"score": 0.8})],
            "timings": {"workflow_total_ms": 12.5},
            "stage_metrics": [{"stage": "workflow_total", "duration_ms": 12.5}],
        }


async def _register(client: AsyncClient, suffix: str, index: int) -> tuple[uuid.UUID, str]:
    response = await client.post(
        "/auth/register",
        json={
            "name": f"Job User {index}",
            "email": f"job-{index}-{suffix}@example.com",
            "password": "CorrectHorseBattery99!",
            "role": "citizen",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), body["access_token"]


@pytest.mark.asyncio
async def test_deep_job_idempotency_ownership_cancellation_and_worker_success() -> None:
    suffix = uuid.uuid4().hex
    user_ids: list[uuid.UUID] = []
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first_id, first_token = await _register(client, suffix, 1)
            second_id, second_token = await _register(client, suffix, 2)
            user_ids.extend([first_id, second_id])
            first_headers = {
                "Authorization": f"Bearer {first_token}",
                "Idempotency-Key": f"deep-{suffix}",
            }
            request = {"query": "Compare the supplied legal authorities carefully."}

            created = await client.post("/jobs/deep-review", headers=first_headers, json=request)
            assert created.status_code == 202, created.text
            created_body = created.json()
            job_id = uuid.UUID(created_body["id"])
            assert created_body["status"] == "queued"
            assert created_body["progress"] == 0
            assert created_body["attempt_count"] == 0
            assert created_body["max_attempts"] == 3

            repeated = await client.post("/jobs/deep-review", headers=first_headers, json=request)
            assert repeated.status_code == 202, repeated.text
            assert repeated.json()["id"] == str(job_id)

            conflicting = await client.post(
                "/jobs/deep-review",
                headers=first_headers,
                json={"query": "A different request using the same key."},
            )
            assert conflicting.status_code == 409

            denied = await client.get(
                f"/jobs/{job_id}",
                headers={"Authorization": f"Bearer {second_token}"},
            )
            assert denied.status_code == 403

            listed = await client.get(
                "/jobs",
                headers={"Authorization": f"Bearer {first_token}"},
            )
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["items"]] == [str(job_id)]

            async with AsyncSessionLocal() as session:
                message_count = await session.scalar(
                    select(func.count(ChatMessage.id))
                    .join(ChatSession)
                    .where(ChatSession.user_id == first_id)
                )
                assert message_count == 1

            worker = DurableJobWorker(FakeDeepWorkflow())  # type: ignore[arg-type]
            claimed = await worker._claim()
            assert claimed == job_id
            await worker._execute(job_id)

            completed = await client.get(
                f"/jobs/{job_id}",
                headers={"Authorization": f"Bearer {first_token}"},
            )
            assert completed.status_code == 200
            completed_body = completed.json()
            assert completed_body["status"] == "succeeded"
            assert completed_body["progress"] == 100
            assert completed_body["attempt_count"] == 1
            assert completed_body["result"]["answer"].startswith("Grounded Deep answer")
            assert completed_body["result"]["message_id"] is not None

            event_stream = await client.get(
                f"/jobs/{job_id}/events",
                headers={"Authorization": f"Bearer {first_token}"},
            )
            assert event_stream.status_code == 200
            assert event_stream.headers["content-type"].startswith("text/event-stream")
            assert "event: citation" in event_stream.text
            assert "event: answer_chunk" in event_stream.text
            assert '"stage":"succeeded"' in event_stream.text

            denied_events = await client.get(
                f"/jobs/{job_id}/events",
                headers={"Authorization": f"Bearer {second_token}"},
            )
            assert denied_events.status_code == 403

            cancel_terminal = await client.post(
                f"/jobs/{job_id}/cancel",
                headers={"Authorization": f"Bearer {first_token}"},
            )
            assert cancel_terminal.status_code == 409

            queued = await client.post(
                "/jobs/deep-review",
                headers={
                    "Authorization": f"Bearer {first_token}",
                    "Idempotency-Key": f"cancel-{suffix}",
                },
                json={"query": "This queued Deep job will be cancelled."},
            )
            assert queued.status_code == 202
            cancel_id = queued.json()["id"]
            cancelled = await client.post(
                f"/jobs/{cancel_id}/cancel",
                headers={"Authorization": f"Bearer {first_token}"},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            assert cancelled.json()["cancel_requested"] is True
    finally:
        async with AsyncSessionLocal() as session:
            if user_ids:
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


class AlwaysFailWorkflow:
    async def run(self, **_: object) -> dict:
        raise RuntimeError("synthetic worker failure with private text")


class SlowWorkflow:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self, **_: object) -> dict:
        self.started.set()
        await asyncio.sleep(30)
        raise AssertionError("cancelled workflow should not finish")


@pytest.mark.asyncio
async def test_worker_retries_twice_then_records_sanitized_failure() -> None:
    suffix = uuid.uuid4().hex
    user_ids: list[uuid.UUID] = []
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_id, token = await _register(client, suffix, 3)
            user_ids.append(user_id)
            created = await client.post(
                "/jobs/deep-review",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": f"retry-{suffix}",
                },
                json={"query": "Synthetic retry scenario."},
            )
            assert created.status_code == 202
            job_id = uuid.UUID(created.json()["id"])

        worker = DurableJobWorker(AlwaysFailWorkflow())  # type: ignore[arg-type]
        for expected_attempt in range(1, 4):
            assert await worker._claim() == job_id
            await worker._execute(job_id)
            async with AsyncSessionLocal() as session:
                job = await session.get(Job, job_id)
                assert job is not None
                assert job.attempt_count == expected_attempt
                expected_status = JobStatus.QUEUED if expected_attempt < 3 else JobStatus.FAILED
                assert job.status is expected_status

        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            assert job is not None
            assert job.error_code == "RuntimeError"
            assert job.error_message == "Deep Review execution failed"
            assert "private text" not in job.error_message
    finally:
        async with AsyncSessionLocal() as session:
            if user_ids:
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


@pytest.mark.asyncio
async def test_running_deep_job_observes_cancellation_without_waiting_for_stage_end() -> None:
    suffix = uuid.uuid4().hex
    user_ids: list[uuid.UUID] = []
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_id, token = await _register(client, suffix, 4)
            user_ids.append(user_id)
            headers = {
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"running-cancel-{suffix}",
            }
            created = await client.post(
                "/jobs/deep-review",
                headers=headers,
                json={"query": "Cancel this deliberately slow Deep review."},
            )
            assert created.status_code == 202
            job_id = uuid.UUID(created.json()["id"])

            workflow = SlowWorkflow()
            worker = DurableJobWorker(workflow)  # type: ignore[arg-type]
            assert await worker._claim() == job_id
            execution = asyncio.create_task(worker._execute(job_id))
            await asyncio.wait_for(workflow.started.wait(), timeout=1)
            started = perf_counter()
            cancelled = await client.post(
                f"/jobs/{job_id}/cancel",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["cancel_requested"] is True
            await asyncio.wait_for(execution, timeout=2)
            observed_seconds = perf_counter() - started

            final = await client.get(
                f"/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert final.status_code == 200
            assert final.json()["status"] == "cancelled"
            assert observed_seconds < 2
    finally:
        async with AsyncSessionLocal() as session:
            if user_ids:
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


@pytest.mark.asyncio
async def test_private_document_jobs_are_idempotent_owner_scoped_and_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []
    transport = ASGITransport(app=app)
    try:
        owner = await provision_test_user(
            name="Queued Document Owner",
            email=f"queued-document-owner-{suffix}@example.com",
            password="CorrectHorseBattery99!",
            role="police",
        )
        other = await provision_test_user(
            name="Queued Document Other",
            email=f"queued-document-other-{suffix}@example.com",
            password="CorrectHorseBattery99!",
            role="police",
        )
        owner_id = uuid.UUID(owner["user"]["id"])
        other_id = uuid.UUID(other["user"]["id"])
        user_ids.extend([owner_id, other_id])
        async with AsyncSessionLocal() as session:
            case = Case(
                owner_id=owner_id,
                role_type=CaseRoleType.POLICE,
                title="Durable private-document case",
                status="open",
            )
            session.add(case)
            await session.flush()
            stored = StorageObject(
                bucket="legal-rag-police",
                object_key=f"tests/{suffix}/evidence.txt",
                namespace=StorageNamespace.POLICE_CASE,
                owner_id=owner_id,
                case_id=case.id,
                original_filename="evidence.txt",
                content_type="text/plain",
                file_size=8,
                sha256="a" * 64,
            )
            document = CaseDocument(
                case_id=case.id,
                file_url=f"s3://legal-rag-police/tests/{suffix}/evidence.txt",
                doc_type="evidence",
                ocr_text="evidence",
            )
            session.add_all([stored, document])
            await session.commit()
            case_ids.append(case.id)
            case_id, object_id, document_id = case.id, stored.id, document.id

        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ocr_headers = {**owner_headers, "Idempotency-Key": f"ocr-{suffix}"}
            ocr_payload = {
                "case_id": str(case_id),
                "object_id": str(object_id),
                "doc_type": "Witness Statement",
            }
            ocr = await client.post("/jobs/ocr-ingestion", headers=ocr_headers, json=ocr_payload)
            assert ocr.status_code == 202, ocr.text
            assert ocr.json()["type"] == "ocr_ingestion"
            repeated = await client.post(
                "/jobs/ocr-ingestion", headers=ocr_headers, json=ocr_payload
            )
            assert repeated.status_code == 202
            assert repeated.json()["id"] == ocr.json()["id"]

            denied = await client.post(
                "/jobs/ocr-ingestion",
                headers={**other_headers, "Idempotency-Key": f"other-{suffix}"},
                json=ocr_payload,
            )
            assert denied.status_code == 403

            analysis = await client.post(
                "/jobs/document-analysis",
                headers={**owner_headers, "Idempotency-Key": f"analysis-{suffix}"},
                json={
                    "case_id": str(case_id),
                    "document_id": str(document_id),
                    "focus": "procedural gaps",
                },
            )
            assert analysis.status_code == 202, analysis.text
            assert analysis.json()["type"] == "document_analysis"

            async def fake_index(*_: object, **__: object) -> tuple[CaseDocument, int, int]:
                async with AsyncSessionLocal() as worker_session:
                    worker_document = await worker_session.get(CaseDocument, document_id)
                    assert worker_document is not None
                    return worker_document, 1, 2

            class FakeAnalysis:
                def model_dump(self, **_: object) -> dict:
                    return {
                        "id": str(uuid.uuid4()),
                        "case_id": str(case_id),
                        "document_id": str(document_id),
                        "summary": "Grounded queued analysis.",
                    }

            async def fake_analyze(*_: object, **__: object) -> FakeAnalysis:
                return FakeAnalysis()

            monkeypatch.setattr(
                "app.services.job_worker.CaseDocumentIndexingService.index_storage_object",
                fake_index,
            )
            monkeypatch.setattr(
                "app.services.job_worker.DocumentAnalysisService.analyze",
                fake_analyze,
            )
            workflow = FakeDeepWorkflow()
            workflow.retrieval = object()  # type: ignore[attr-defined]
            workflow.llm = object()  # type: ignore[attr-defined]
            worker = DurableJobWorker(workflow)  # type: ignore[arg-type]
            claimed_ids: list[uuid.UUID] = []
            for _ in range(2):
                claimed_id = await worker._claim()
                assert claimed_id is not None
                claimed_ids.append(claimed_id)
                await worker._execute(claimed_id)
            assert set(claimed_ids) == {
                uuid.UUID(ocr.json()["id"]),
                uuid.UUID(analysis.json()["id"]),
            }
            for completed_id in claimed_ids:
                response = await client.get(
                    f"/jobs/{completed_id}", headers=owner_headers
                )
                assert response.status_code == 200
                assert response.json()["status"] == "succeeded"
                assert response.json()["progress"] == 100
    finally:
        async with AsyncSessionLocal() as session:
            if user_ids:
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
            if case_ids:
                await session.execute(delete(Case).where(Case.id.in_(case_ids)))
            if user_ids:
                await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.commit()
