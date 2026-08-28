from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.drafting_agent import LegalDraftingAgent, PROFESSIONAL_REVIEW_DISCLAIMER
from app.core.database import get_db_session
from app.core.permissions import POLICE_INVESTIGATION_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, Case, User
from app.schemas.documents import DocumentDraftRequest, DocumentDraftResponse
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
