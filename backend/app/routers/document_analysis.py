from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.case_scope import collection_for_case_role
from app.core.database import get_db_session
from app.core.permissions import CASE_DOCUMENT_MANAGE_OWN, CASE_READ_OWN, CORPUS_READ
from app.core.rbac import require_permission
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.models import AuditLog, Case, CaseDocument, GeneratedDocument, StorageObject, User
from app.schemas.document_analysis import (
    CaseDocumentListResponse,
    CaseDocumentSummary,
    DocumentAnalyzeRequest,
    DocumentAnalysisResponse,
    SourceInspectorResponse,
)
from app.services.document_analysis import DISCLAIMER, DocumentAnalysisService
from app.services.llm import OllamaClient
from app.services.retrieval import HybridRetrievalService


router = APIRouter(tags=["document-analysis"])


@dataclass(frozen=True)
class AnalyzerRuntime:
    retrieval: HybridRetrievalService
    llm: OllamaClient


def get_analyzer_runtime(request: Request) -> AnalyzerRuntime:
    workflow = request.app.state.legal_rag_workflow
    return AnalyzerRuntime(retrieval=workflow.retrieval, llm=workflow.llm)


@router.post(
    "/documents/analyze",
    response_model=DocumentAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_document(
    case_id: Annotated[uuid.UUID, Query()],
    payload: DocumentAnalyzeRequest,
    current_user: Annotated[
        User, Depends(require_permission(CASE_DOCUMENT_MANAGE_OWN))
    ],
    runtime: AnalyzerRuntime = Depends(get_analyzer_runtime),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentAnalysisResponse:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    document = await session.get(CaseDocument, payload.document_id)
    if document is None or document.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        return await DocumentAnalysisService(
            session=session,
            retrieval=runtime.retrieval,
            llm=runtime.llm,
        ).analyze(
            case=case,
            document=document,
            user=current_user,
            focus=payload.focus,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The local analysis model could not complete this review",
        ) from exc


@router.get(
    "/documents/analyses/latest",
    response_model=DocumentAnalysisResponse,
)
async def get_latest_document_analysis(
    case_id: Annotated[uuid.UUID, Query()],
    document_id: Annotated[uuid.UUID, Query()],
    _: Annotated[User, Depends(require_permission(CASE_READ_OWN))],
    session: AsyncSession = Depends(get_db_session),
) -> DocumentAnalysisResponse:
    document = await session.get(CaseDocument, document_id)
    if document is None or document.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    doc_type = f"document_analysis:{document_id}"
    generated = await session.scalar(
        select(GeneratedDocument)
        .where(
            GeneratedDocument.case_id == case_id,
            GeneratedDocument.doc_type == doc_type,
        )
        .order_by(GeneratedDocument.version.desc())
        .limit(1)
    )
    if generated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    content = generated.content
    return DocumentAnalysisResponse(
        id=generated.id,
        case_id=case_id,
        document_id=document_id,
        version=generated.version,
        summary=str(content.get("summary") or ""),
        key_clauses=content.get("key_clauses") or [],
        risks=content.get("risks") or [],
        applicable_sections=content.get("applicable_sections") or [],
        rejected_section_count=int(content.get("rejected_section_count") or 0),
        analyzed_chunk_count=int(content.get("analyzed_chunk_count") or 0),
        total_chunk_count=int(content.get("total_chunk_count") or 0),
        partial_review=bool(content.get("partial_review")),
        disclaimer=DISCLAIMER,
        created_at=generated.created_at,
    )
@router.get(
    "/cases/{case_id}/documents/indexed",
    response_model=CaseDocumentListResponse,
)
async def list_indexed_documents(
    case_id: uuid.UUID,
    _: Annotated[User, Depends(require_permission(CASE_READ_OWN))],
    runtime: AnalyzerRuntime = Depends(get_analyzer_runtime),
    session: AsyncSession = Depends(get_db_session),
) -> CaseDocumentListResponse:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    documents = list(
        (
            await session.scalars(
                select(CaseDocument)
                .where(CaseDocument.case_id == case_id)
                .order_by(CaseDocument.uploaded_at.desc())
            )
        ).all()
    )
    stored_objects = list(
        (await session.scalars(select(StorageObject).where(StorageObject.case_id == case_id))).all()
    )
    by_url = {f"s3://{item.bucket}/{item.object_key}": item for item in stored_objects}
    service = DocumentAnalysisService(session, runtime.retrieval, runtime.llm)
    summaries: list[CaseDocumentSummary] = []
    for document in documents:
        points = await service._document_points(case, document)
        stored = by_url.get(document.file_url)
        pages = {
            int(point.payload.get("page_start") or 1)
            for point in points
        }
        summaries.append(
            CaseDocumentSummary(
                document_id=document.id,
                storage_object_id=stored.id if stored else None,
                filename=stored.original_filename if stored else "Indexed evidence",
                doc_type=document.doc_type,
                uploaded_at=document.uploaded_at,
                sha256=stored.sha256 if stored else None,
                page_count=len(pages),
                chunk_count=len(points),
            )
        )
    return CaseDocumentListResponse(documents=summaries, total=len(summaries))


def _status(payload: dict[str, Any], *, private: bool) -> tuple[str, str]:
    if private:
        return "verified", "not_applicable"
    verification = (
        "verified"
        if payload.get("corpus_tier") in {"gold", "extended"}
        and payload.get("quality_status") not in {"rejected", "failed"}
        else "unverified"
    )
    if payload.get("is_current") is True:
        current = "current"
    elif payload.get("is_superseded") is True:
        current = "superseded"
    else:
        current = "status_unverified"
    return verification, current


def _source_response(point: Any, *, private: bool) -> SourceInspectorResponse:
    payload = dict(point.payload or {})
    verification, current = _status(payload, private=private)
    return SourceInspectorResponse(
        point_id=str(point.id),
        chunk_id=str(payload.get("chunk_id") or point.id),
        scope="private_case" if private else "global",
        source_title=str(payload.get("title") or payload.get("act_name") or "Untitled source"),
        source_type=str(payload.get("source_type") or payload.get("doc_type") or "document"),
        act_or_judgment=str(payload.get("act_name") or payload.get("title") or "").strip() or None,
        section=str(payload.get("section") or "").strip() or None,
        page_start=max(1, int(payload.get("page_start") or 1)),
        page_end=max(1, int(payload.get("page_end") or payload.get("page_start") or 1)),
        retrieved_passage=str(payload.get("text") or ""),
        retrieval_score=None,
        verification_status=verification,
        current_status=current,
        case_id=uuid.UUID(str(payload["case_id"])) if private else None,
        document_id=uuid.UUID(str(payload["document_id"])) if private else None,
        storage_object_id=(
            uuid.UUID(str(payload["storage_object_id"]))
            if private and payload.get("storage_object_id")
            else None
        ),
        corpus_tier=str(payload.get("corpus_tier") or "").strip() or None,
        verified_official=(
            bool(payload.get("verified_official")) if not private else None
        ),
    )


@router.get("/sources/{point_id}", response_model=SourceInspectorResponse)
async def inspect_global_source(
    point_id: uuid.UUID,
    _: Annotated[User | None, Depends(require_permission(CORPUS_READ, allow_anonymous=True))],
    runtime: AnalyzerRuntime = Depends(get_analyzer_runtime),
) -> SourceInspectorResponse:
    points = await runtime.retrieval.client.retrieve(
        collection_name=GLOBAL_LEGAL_CORPUS,
        ids=[str(point_id)],
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return _source_response(points[0], private=False)


@router.get(
    "/cases/{case_id}/sources/{point_id}",
    response_model=SourceInspectorResponse,
)
async def inspect_private_source(
    case_id: uuid.UUID,
    point_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_permission(CASE_READ_OWN))],
    runtime: AnalyzerRuntime = Depends(get_analyzer_runtime),
    session: AsyncSession = Depends(get_db_session),
) -> SourceInspectorResponse:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    points = await runtime.retrieval.client.retrieve(
        collection_name=collection_for_case_role(case.role_type),
        ids=[str(point_id)],
        with_payload=True,
        with_vectors=False,
    )
    if not points or str((points[0].payload or {}).get("case_id")) != str(case_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    response = _source_response(points[0], private=True)
    session.add(
        AuditLog(
            user_id=current_user.id,
            action="source.inspect",
            resource_type="case_document_chunk",
            resource_id=response.document_id,
            metadata_={"case_id": str(case_id), "chunk_id": response.chunk_id},
        )
    )
    await session.commit()
    return response
