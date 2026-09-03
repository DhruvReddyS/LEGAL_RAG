from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.agents.orchestrator import LegalRAGWorkflow
from app.core.database import AsyncSessionLocal
from app.models import AuditLog, Case, CaseDocument, ChatMessage, Job, StorageObject, User
from app.models.enums import ChatMessageRole, JobStatus, JobType
from app.services.case_documents import CaseDocumentIndexingService
from app.services.document_analysis import DocumentAnalysisService
from app.services.jobs import (
    append_job_event,
    claim_next_job,
    mark_job_cancelled,
    mark_job_succeeded,
    record_job_failure,
    recover_interrupted_jobs,
    update_job_progress,
)


logger = logging.getLogger("legal_rag.jobs")


class JobCancellationRequested(Exception):
    pass


DEEP_STAGE_PROGRESS = {
    "role_context": 5,
    "query_understanding": 10,
    "retrieval": 25,
    "reasoning": 50,
    "verification": 75,
    "retry": 80,
    "response_generation": 90,
    "document_extraction": 10,
    "document_analysis": 10,
}


class DurableJobWorker:
    def __init__(
        self,
        workflow: LegalRAGWorkflow,
        *,
        poll_interval_ms: int = 500,
    ) -> None:
        self.workflow = workflow
        self.poll_interval_seconds = poll_interval_ms / 1000
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        async with AsyncSessionLocal() as session:
            async with session.begin():
                recovered = await recover_interrupted_jobs(session)
        if recovered:
            logger.warning("recovered %s interrupted durable jobs", recovered)
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="durable-job-worker")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await recover_interrupted_jobs(session)

    async def _run(self) -> None:
        while not self._stop.is_set():
            job_id = await self._claim()
            if job_id is None:
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=self.poll_interval_seconds,
                    )
                except TimeoutError:
                    continue
                continue
            await self._execute(job_id)

    async def _claim(self) -> uuid.UUID | None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = await claim_next_job(
                    session,
                    supported_types=(
                        JobType.DEEP_REVIEW,
                        JobType.OCR_INGESTION,
                        JobType.DOCUMENT_ANALYSIS,
                    ),
                )
                if job is None or job.status is JobStatus.CANCELLED:
                    return None
                job.progress = 1
                append_job_event(
                    session,
                    job,
                    event_type="status",
                    stage="running",
                    data={"status": JobStatus.RUNNING.value, "attempt": job.attempt_count},
                )
                return job.id

    async def _execute(self, job_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status is not JobStatus.RUNNING:
                return
            payload = dict(job.payload)
        try:
            if job.type is JobType.DEEP_REVIEW:
                await self._execute_deep_review(job_id, payload)
            elif job.type is JobType.OCR_INGESTION:
                await self._record_progress(job_id, "document_extraction", "started", {})
                await self._execute_ocr_ingestion(job_id, payload)
            elif job.type is JobType.DOCUMENT_ANALYSIS:
                await self._record_progress(job_id, "document_analysis", "started", {})
                await self._execute_document_analysis(job_id, payload)
            else:
                raise ValueError("Unsupported durable job type")
        except asyncio.CancelledError:
            raise
        except JobCancellationRequested:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    job = await session.scalar(
                        select(Job).where(Job.id == job_id).with_for_update()
                    )
                    if job is not None and job.status in {
                        JobStatus.QUEUED,
                        JobStatus.RUNNING,
                    }:
                        mark_job_cancelled(job)
                        append_job_event(
                            session,
                            job,
                            event_type="status",
                            stage="cancelled",
                            data={"status": JobStatus.CANCELLED.value},
                        )
        except Exception as exc:
            logger.warning(
                "durable job %s attempt failed error_type=%s",
                job_id,
                type(exc).__name__,
            )
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    job = await session.scalar(
                        select(Job).where(Job.id == job_id).with_for_update()
                    )
                    if job is None or job.status is not JobStatus.RUNNING:
                        return
                    will_retry = record_job_failure(
                        job,
                        code=type(exc).__name__,
                        message=f"{self._safe_job_label(job.type)} execution failed",
                    )
                    append_job_event(
                        session,
                        job,
                        event_type="status",
                        stage="retry_queued" if will_retry else "failed",
                        data={
                            "status": job.status.value,
                            "attempt": job.attempt_count,
                            "max_attempts": job.max_attempts,
                            "error_code": job.error_code,
                        },
                    )
                    session.add(
                        AuditLog(
                            user_id=job.user_id,
                            action="job.retry_scheduled" if will_retry else "job.failed",
                            resource_type="job",
                            resource_id=job.id,
                            metadata_={
                                "job_type": job.type.value,
                                "attempt_count": job.attempt_count,
                                "max_attempts": job.max_attempts,
                                "error_code": job.error_code,
                            },
                        )
                    )

    async def _execute_deep_review(
        self,
        job_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        result = await self._run_deep_with_cancellation(
            job_id,
            self.workflow.run(
                query=str(payload["query"]),
                role=str(payload["role"]),
                case_id=payload.get("case_id"),
                history=list(payload.get("history", [])),
                progress_callback=lambda stage, transition, data: self._record_progress(
                    job_id, stage, transition, data
                ),
            ),
        )
        serialized = self._serialize_result(result, payload)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = await self._running_job_for_update(session, job_id)
                if job is None:
                    return
                if job.cancel_requested:
                    mark_job_cancelled(job)
                    return
                assistant = ChatMessage(
                    session_id=uuid.UUID(str(payload["chat_session_id"])),
                    role=ChatMessageRole.ASSISTANT,
                    content=result["final_answer"],
                    citations=serialized["citations"],
                    confidence_score=Decimal(str(round(result["confidence_score"], 4))),
                )
                session.add(assistant)
                await session.flush()
                serialized["message_id"] = str(assistant.id)
                for citation in serialized["citations"]:
                    append_job_event(
                        session,
                        job,
                        event_type="citation",
                        stage="response_generation",
                        data=citation,
                    )
                answer = str(serialized["answer"])
                for offset in range(0, len(answer), 240):
                    append_job_event(
                        session,
                        job,
                        event_type="answer_chunk",
                        stage="response_generation",
                        data={"text": answer[offset : offset + 240], "offset": offset},
                    )
                self._complete_job(
                    session,
                    job,
                    serialized,
                    {"chat_session_id": payload["chat_session_id"], "message_id": str(assistant.id)},
                )

    async def _run_deep_with_cancellation(
        self,
        job_id: uuid.UUID,
        operation: Any,
    ) -> Any:
        task = asyncio.create_task(operation, name=f"deep-job-{job_id}")
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=0.5)
                if done:
                    return await task
                async with AsyncSessionLocal() as session:
                    cancel_requested = await session.scalar(
                        select(Job.cancel_requested).where(Job.id == job_id)
                    )
                if cancel_requested:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    raise JobCancellationRequested
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise

    async def _execute_ocr_ingestion(
        self,
        job_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                initial_job = await session.get(Job, job_id)
                if initial_job is None or initial_job.status is not JobStatus.RUNNING:
                    return
                if initial_job.cancel_requested:
                    mark_job_cancelled(initial_job)
                    return
                case = await session.get(Case, uuid.UUID(str(payload["case_id"])))
                stored = await session.get(StorageObject, uuid.UUID(str(payload["object_id"])))
                user = await session.get(User, initial_job.user_id)
                if case is None or stored is None or user is None or stored.case_id != case.id:
                    raise ValueError("Queued OCR ingestion resources no longer exist")
                document, pages, chunks = await CaseDocumentIndexingService(
                    session, self.workflow.retrieval
                ).index_storage_object(
                    case=case,
                    stored=stored,
                    user=user,
                    doc_type=str(payload["doc_type"]),
                )
                job = await self._running_job_for_update(session, job_id)
                if job is None:
                    return
                if job.cancel_requested:
                    mark_job_cancelled(job)
                    return
                update_job_progress(job, 90)
                append_job_event(
                    session,
                    job,
                    event_type="stage",
                    stage="vector_indexing",
                    data={"transition": "completed", "pages": pages, "chunks": chunks},
                )
                result = {
                    "document_id": str(document.id),
                    "storage_object_id": str(stored.id),
                    "case_id": str(case.id),
                    "doc_type": document.doc_type,
                    "pages": pages,
                    "chunks": chunks,
                    "extraction_method": "native_or_ocr",
                }
                session.add(
                    AuditLog(
                        user_id=user.id,
                        action="case.document.index",
                        resource_type="case_document",
                        resource_id=document.id,
                        metadata_={
                            "case_id": str(case.id),
                            "storage_object_id": str(stored.id),
                            "pages": pages,
                            "chunks": chunks,
                            "job_id": str(job.id),
                        },
                    )
                )
                self._complete_job(session, job, result, {"case_id": str(case.id)})

    async def _execute_document_analysis(
        self,
        job_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                initial_job = await session.get(Job, job_id)
                if initial_job is None or initial_job.status is not JobStatus.RUNNING:
                    return
                if initial_job.cancel_requested:
                    mark_job_cancelled(initial_job)
                    return
                case = await session.get(Case, uuid.UUID(str(payload["case_id"])))
                document = await session.get(
                    CaseDocument, uuid.UUID(str(payload["document_id"]))
                )
                user = await session.get(User, initial_job.user_id)
                if case is None or document is None or user is None or document.case_id != case.id:
                    raise ValueError("Queued document-analysis resources no longer exist")
                analysis = await DocumentAnalysisService(
                    session=session,
                    retrieval=self.workflow.retrieval,
                    llm=self.workflow.llm,
                ).analyze(
                    case=case,
                    document=document,
                    user=user,
                    focus=payload.get("focus"),
                    commit=False,
                )
                job = await self._running_job_for_update(session, job_id)
                if job is None:
                    return
                if job.cancel_requested:
                    mark_job_cancelled(job)
                    return
                update_job_progress(job, 90)
                append_job_event(
                    session,
                    job,
                    event_type="stage",
                    stage="document_analysis",
                    data={"transition": "completed"},
                )
                self._complete_job(
                    session,
                    job,
                    analysis.model_dump(mode="json"),
                    {"case_id": str(case.id), "document_id": str(document.id)},
                )

    @staticmethod
    async def _running_job_for_update(session: Any, job_id: uuid.UUID) -> Job | None:
        job = await session.scalar(
            select(Job)
            .where(Job.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None or job.status is not JobStatus.RUNNING:
            return None
        return job

    async def _record_progress(
        self,
        job_id: uuid.UUID,
        stage: str,
        transition: str,
        data: dict[str, Any],
    ) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = await session.scalar(
                    select(Job).where(Job.id == job_id).with_for_update()
                )
                if job is None or job.status is not JobStatus.RUNNING:
                    raise JobCancellationRequested
                if job.cancel_requested:
                    raise JobCancellationRequested
                target = DEEP_STAGE_PROGRESS.get(stage, job.progress)
                if transition == "completed":
                    target = min(99, target + 5)
                update_job_progress(job, max(job.progress, target))
                append_job_event(
                    session,
                    job,
                    event_type="stage",
                    stage=stage,
                    data={"transition": transition, **data},
                )

    @staticmethod
    def _complete_job(
        session: Any,
        job: Job,
        result: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        mark_job_succeeded(job, result)
        append_job_event(
            session,
            job,
            event_type="status",
            stage="succeeded",
            data={"status": JobStatus.SUCCEEDED.value},
        )
        session.add(
            AuditLog(
                user_id=job.user_id,
                action="job.succeeded",
                resource_type="job",
                resource_id=job.id,
                metadata_={
                    "job_type": job.type.value,
                    "attempt_count": job.attempt_count,
                    **metadata,
                },
            )
        )

    @staticmethod
    def _safe_job_label(job_type: JobType) -> str:
        return {
            JobType.DEEP_REVIEW: "Deep Review",
            JobType.OCR_INGESTION: "OCR ingestion",
            JobType.DOCUMENT_ANALYSIS: "Document analysis",
            JobType.EXPORT: "Export",
        }[job_type]

    @staticmethod
    def _serialize_result(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": payload["chat_session_id"],
            "message_id": None,
            "answer": result["final_answer"],
            "citations": [citation.model_dump(mode="json") for citation in result["citations"]],
            "confidence_score": result["confidence_score"],
            "evidence_strength": result["evidence_strength"],
            "intent": result["intent"].model_dump(mode="json"),
            "agent_trace": [event.model_dump(mode="json") for event in result["agent_trace"]],
            "timings_ms": result.get("timings", {}),
            "pipeline_metrics": result.get("stage_metrics", []),
            "response_mode": "deep",
            "requested_mode": "deep",
        }
