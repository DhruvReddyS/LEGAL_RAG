from contextlib import asynccontextmanager
import json
import logging
import re
import uuid
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

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
from app.services.retrieval import HybridRetrievalService
from app.services.fast_research import FastLegalResearchService
from app.core.config import settings


logger = logging.getLogger("legal_rag.http")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    retrieval_service = HybridRetrievalService()
    app.state.retrieval_service = retrieval_service
    app.state.legal_rag_workflow = LegalRAGWorkflow(retrieval_service)
    app.state.fast_research_service = FastLegalResearchService(retrieval_service)
    if settings.warm_query_models_on_startup:
        await retrieval_service.warmup()
    try:
        yield
    finally:
        await retrieval_service.close()


app = FastAPI(
    title="Multi-Agent Legal RAG Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Server-Timing"],
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


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Report whether the API process is healthy."""
    return {"status": "healthy"}
