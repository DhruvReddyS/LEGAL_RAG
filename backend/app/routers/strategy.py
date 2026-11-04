from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.defence_strategy_agent import DefenceStrategyAgent
from app.core.database import get_db_session
from app.core.permissions import ADVOCATE_STRATEGY_OWN
from app.core.rbac import require_permission
from app.models import AdvocateWorkProduct, AuditLog, User
from app.schemas.strategy import DefenceAnalysisRequest, DefenceAnalysisResponse
from app.services.advocate_work import save_work_product, work_summary
from app.services.llm import OllamaClient
from app.services.rate_limit import enforce_llm_sync_limit
from app.services.retrieval import HybridRetrievalService


router = APIRouter(prefix="/cases/{case_id}/strategy", tags=["advocate-strategy"])
DEFENCE_ANALYSIS_KIND = "defence_analysis"


@dataclass(frozen=True)
class StrategyRuntime:
    retrieval: HybridRetrievalService
    llm: OllamaClient


def get_strategy_runtime(request: Request) -> StrategyRuntime:
    workflow = request.app.state.legal_rag_workflow
    return StrategyRuntime(workflow.retrieval, workflow.llm)


@router.post("/defence-analysis", response_model=DefenceAnalysisResponse)
async def analyse_defence(
    case_id: uuid.UUID,
    request: DefenceAnalysisRequest,
    current_user: Annotated[User, Depends(require_permission(ADVOCATE_STRATEGY_OWN))],
    runtime: StrategyRuntime = Depends(get_strategy_runtime),
    session: AsyncSession = Depends(get_db_session),
) -> DefenceAnalysisResponse:
    await enforce_llm_sync_limit(current_user.id)
    result = await DefenceStrategyAgent(runtime.retrieval, runtime.llm).run(
        case_id=str(case_id),
        case_scenario=request.case_scenario,
        advocate_position=request.advocate_position,
    )
    content = result.model_dump(mode="json") | {
        "case_scenario": request.case_scenario,
        "advocate_position": request.advocate_position,
    }
    # Kept whatever it found: minutes of model time lost on "Back to chat" was
    # the defect, and an honest "insufficient" is still a record of the attempt.
    product = await save_work_product(
        session,
        case_id=case_id,
        user_id=current_user.id,
        kind=DEFENCE_ANALYSIS_KIND,
        title=f"Defence analysis, {result.evidence_strength} evidence",
        status="draft",
        content=content,
    )
    session.add(
        AuditLog(
            user_id=current_user.id,
            action="advocate.defence_analysis",
            resource_type="case",
            resource_id=case_id,
            metadata_={
                "work_product_id": str(product.id),
                "confidence_score": result.confidence_score,
                "evidence_strength": result.evidence_strength,
                "accepted_points": len(result.points),
                "rejected_points": result.rejected_point_count,
                "source_chunk_ids": [item.chunk_id for item in result.citations],
            },
        )
    )
    await session.commit()
    await session.refresh(product)
    return _saved_analysis(product)


def _saved_analysis(product: AdvocateWorkProduct) -> DefenceAnalysisResponse:
    return DefenceAnalysisResponse.model_validate(
        {
            **product.content,
            "id": product.id,
            "version": product.version,
            "created_at": product.created_at,
        }
    )


@router.get("/defence-analyses")
async def list_defence_analyses(
    case_id: uuid.UUID,
    _: Annotated[User, Depends(require_permission(ADVOCATE_STRATEGY_OWN))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, list[dict]]:
    rows = (
        await session.scalars(
            select(AdvocateWorkProduct)
            .where(
                AdvocateWorkProduct.case_id == case_id,
                AdvocateWorkProduct.kind == DEFENCE_ANALYSIS_KIND,
            )
            .order_by(AdvocateWorkProduct.version.desc())
        )
    ).all()
    return {"analyses": [work_summary(row) for row in rows]}


@router.get("/defence-analyses/{analysis_id}", response_model=DefenceAnalysisResponse)
async def read_defence_analysis(
    case_id: uuid.UUID,
    analysis_id: uuid.UUID,
    _: Annotated[User, Depends(require_permission(ADVOCATE_STRATEGY_OWN))],
    session: AsyncSession = Depends(get_db_session),
) -> DefenceAnalysisResponse:
    """A saved analysis, exactly as it was written. Nothing is rerun."""
    product = await session.get(AdvocateWorkProduct, analysis_id)
    if (
        product is None
        or product.case_id != case_id
        or product.kind != DEFENCE_ANALYSIS_KIND
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return _saved_analysis(product)
