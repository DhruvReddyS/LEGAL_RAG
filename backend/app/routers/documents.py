from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.drafting_agent import LegalDraftingAgent, PROFESSIONAL_REVIEW_DISCLAIMER
from app.core.database import get_db_session
from app.core.permissions import CASE_READ_OWN, POLICE_INVESTIGATION_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, Case, GeneratedDocument, User
from app.schemas.documents import (
    DocumentDraftRequest,
    DocumentDraftResponse,
    GeneratedDocumentListResponse,
    GeneratedDocumentSummary,
)
from app.services.llm import OllamaClient
from app.services.retrieval import HybridRetrievalService


router = APIRouter(prefix="/cases/{case_id}/documents", tags=["legal-documents"])


@dataclass(frozen=True)
class DraftingRuntime:
    retrieval: HybridRetrievalService
    llm: OllamaClient


def get_drafting_runtime(request: Request) -> DraftingRuntime:
    workflow = request.app.state.legal_rag_workflow
    return DraftingRuntime(retrieval=workflow.retrieval, llm=workflow.llm)


@router.post("/draft", response_model=DocumentDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_document_draft(
    case_id: uuid.UUID,
    request: DocumentDraftRequest,
    current_user: Annotated[
        User, Depends(require_permission(POLICE_INVESTIGATION_OWN))
    ],
    runtime: DraftingRuntime = Depends(get_drafting_runtime),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentDraftResponse:
    case = await session.get(Case, case_id)
    generated, facts, missing, authorities, rendered = await LegalDraftingAgent(
        session=session,
        retrieval=runtime.retrieval,
        llm=runtime.llm,
    ).create_fir_draft(case=case, description=request.case_description)
    session.add(
        AuditLog(
            user_id=current_user.id,
            action="document.draft.create",
            resource_type="generated_document",
            resource_id=generated.id,
            metadata_={
                "case_id": str(case_id),
                "doc_type": generated.doc_type,
                "version": generated.version,
                "status": generated.status,
                "authority_chunk_ids": [item.chunk_id for item in authorities],
                "missing_fields": missing,
            },
        )
    )
    await session.commit()
    await session.refresh(generated)
    return DocumentDraftResponse(
        id=generated.id,
        case_id=generated.case_id,
        doc_type=generated.doc_type,
        version=generated.version,
        status=generated.status,
        facts=facts,
        missing_fields=missing,
        authorities=authorities,
        rendered_text=rendered,
        disclaimer=PROFESSIONAL_REVIEW_DISCLAIMER,
        created_at=generated.created_at,
    )


@router.get("/generated", response_model=GeneratedDocumentListResponse)
async def list_generated_documents(
    case_id: uuid.UUID,
    _: Annotated[User, Depends(require_permission(CASE_READ_OWN))],
    session: AsyncSession = Depends(get_db_session),
) -> GeneratedDocumentListResponse:
    """Everything drafted in this case, newest first."""
    rows = (
        await session.scalars(
            select(GeneratedDocument)
            .where(GeneratedDocument.case_id == case_id)
            .order_by(GeneratedDocument.created_at.desc())
        )
    ).all()
    return GeneratedDocumentListResponse(
        documents=[
            GeneratedDocumentSummary(
                id=row.id,
                case_id=row.case_id,
                doc_type=row.doc_type,
                version=row.version,
                status=row.status,
                created_at=row.created_at,
                # Counted from what was stored with the draft, so the case
                # file reports the draft as it was made, not as the current
                # code would make it.
                missing_field_count=len(row.content.get("missing_fields") or []),
                authority_count=len(row.content.get("authorities") or []),
            )
            for row in rows
        ]
    )


@router.get("/generated/{document_id}", response_model=DocumentDraftResponse)
async def read_generated_document(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    _: Annotated[User, Depends(require_permission(CASE_READ_OWN))],
    session: AsyncSession = Depends(get_db_session),
) -> DocumentDraftResponse:
    """A stored draft, exactly as it was written.

    Nothing is regenerated: a draft that has been reviewed must read the
    same on every later visit, so this returns the recorded content.
    """
    document = await session.get(GeneratedDocument, document_id)
    if document is None or document.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    content = document.content or {}
    return DocumentDraftResponse(
        id=document.id,
        case_id=document.case_id,
        doc_type=document.doc_type,
        version=document.version,
        status=document.status,
        facts=content.get("facts") or {},
        missing_fields=list(content.get("missing_fields") or []),
        authorities=list(content.get("authorities") or []),
        rendered_text=str(content.get("rendered_text") or ""),
        disclaimer=str(content.get("disclaimer") or PROFESSIONAL_REVIEW_DISCLAIMER),
        created_at=document.created_at,
    )
