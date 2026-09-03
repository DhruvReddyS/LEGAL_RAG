from contextlib import asynccontextmanager
import json
import logging
import re
import uuid
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import ResponseHandlingException

from app.services.llm import LLMUnavailableError

from app.agents.orchestrator import LegalRAGWorkflow
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.cases import router as cases_router
from app.routers.documents import router as documents_router
from app.routers.strategy import router as strategy_router
from app.routers.ingestion import router as ingestion_router
from app.routers.storage import router as storage_router
from app.routers.retrieval import router as retrieval_router
from app.routers.admin import router as admin_router
from app.routers.document_analysis import router as document_analysis_router
from app.routers.jobs import router as jobs_router
from app.routers.citizen_intake import router as citizen_intake_router
from app.routers.feedback import router as feedback_router
from app.services.retrieval import HybridRetrievalService
from app.services.fast_research import FastLegalResearchService
from app.services.job_worker import DurableJobWorker
from app.core.config import settings
from app.core.http_security import DesktopOriginSecurityMiddleware
from app.services.health import (
    assert_accelerated_inference,
    log_runtime_profile,
    readiness_report,
)


logger = logging.getLogger("legal_rag.http")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast rather than serving a silently degraded deployment.
    assert_accelerated_inference()
    log_runtime_profile(logger)
    retrieval_service = HybridRetrievalService()
    app.state.retrieval_service = retrieval_service
    app.state.legal_rag_workflow = LegalRAGWorkflow(retrieval_service)
    app.state.fast_research_service = FastLegalResearchService(retrieval_service)
    app.state.job_worker = DurableJobWorker(
        app.state.legal_rag_workflow,
        poll_interval_ms=settings.job_poll_interval_ms,
    )
    if settings.warm_query_models_on_startup:
        await retrieval_service.warmup()
    if settings.job_worker_enabled:
        await app.state.job_worker.start()
    try:
        yield
    finally:
        if settings.job_worker_enabled:
            await app.state.job_worker.stop()
        await app.state.legal_rag_workflow.llm.close()
        await retrieval_service.close()


app = FastAPI(
    title="Multi-Agent Legal RAG Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Server-Timing"],
)
app.add_middleware(
    DesktopOriginSecurityMiddleware,
    allowed_origins=settings.cors_origin_list,
    allow_private_network=settings.cors_allow_private_network,
)


@app.exception_handler(ResponseHandlingException)
async def vector_store_unavailable(request: Request, exc: ResponseHandlingException) -> JSONResponse:
    """A dependency being down is 503, not 500.

    Losing Qdrant surfaced as Internal Server Error, which reads as a defect in
    this service and tells a caller nothing about whether retrying helps. The
    exception message can carry a host and port, so only the fact of the outage
    is returned.
    """
    logger.error(
        json.dumps(
            {
                "event": "vector_store_unavailable",
                "request_id": getattr(request.state, "request_id", None),
                "path": request.url.path,
                "error_type": type(exc).__name__,
            },
            separators=(",", ":"),
        )
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The legal corpus is temporarily unavailable. Please try again shortly."
        },
        headers={"Retry-After": "15", "Cache-Control": "no-store"},
    )


@app.exception_handler(LLMUnavailableError)
async def model_host_unavailable(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    """Reasoning has no fallback, by design: there is no safe way to invent a
    legal answer. Losing the model host is therefore an outage, not a defect."""
    logger.error(
        json.dumps(
            {
                "event": "model_host_unavailable",
                "request_id": getattr(request.state, "request_id", None),
                "path": request.url.path,
                "error_type": type(exc).__name__,
            },
            separators=(",", ":"),
        )
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Deep review is temporarily unavailable. "
            "Fast evidence search still works, or try again shortly."
        },
        headers={"Retry-After": "30", "Cache-Control": "no-store"},
    )


@app.middleware("http")
async def request_telemetry(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex
    request.state.request_id = request_id
    started = perf_counter()
    response = await call_next(request)
    duration_ms = round((perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["Server-Timing"] = f"app;dur={duration_ms}"
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
            separators=(",", ":"),
        )
    )
    return response

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(cases_router)
app.include_router(documents_router)
app.include_router(strategy_router)
app.include_router(ingestion_router)
app.include_router(storage_router)
app.include_router(retrieval_router)
app.include_router(admin_router)
app.include_router(document_analysis_router)
app.include_router(jobs_router)
app.include_router(citizen_intake_router)
app.include_router(feedback_router)


@app.get("/health/live", tags=["system"])
async def liveness_check() -> JSONResponse:
    """Report whether the API process is running. Never touches a dependency."""
    return JSONResponse(
        content={"status": "alive", "api_compatibility": "1"},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health/ready", tags=["system"])
async def readiness_check() -> JSONResponse:
    """Report whether every dependency needed to serve a request is reachable."""
    ready, payload = await readiness_report()
    return JSONResponse(
        content=payload,
        status_code=200 if ready else 503,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health", tags=["system"])
async def health_check() -> JSONResponse:
    """Liveness alias retained for the packaged desktop client's probe."""
    return JSONResponse(
        content={"status": "healthy", "api_compatibility": "1"},
        headers={"Cache-Control": "no-store"},
    )
