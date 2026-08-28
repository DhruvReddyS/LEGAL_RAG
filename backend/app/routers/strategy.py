from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.defence_strategy_agent import DefenceStrategyAgent
from app.core.database import get_db_session
from app.core.permissions import ADVOCATE_STRATEGY_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, User
from app.schemas.strategy import DefenceAnalysisRequest, DefenceAnalysisResponse
from app.services.llm import OllamaClient
from app.services.retrieval import HybridRetrievalService


router = APIRouter(prefix="/cases/{case_id}/strategy", tags=["advocate-strategy"])


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
    result = await DefenceStrategyAgent(runtime.retrieval, runtime.llm).run(
        case_id=str(case_id),
        case_scenario=request.case_scenario,
        advocate_position=request.advocate_position,
    )
    session.add(
        AuditLog(
            user_id=current_user.id,
            action="advocate.defence_analysis",
            resource_type="case",
            resource_id=case_id,
            metadata_={
                "confidence_score": result.confidence_score,
                "evidence_strength": result.evidence_strength,
                "accepted_points": len(result.points),
                "rejected_points": result.rejected_point_count,
                "source_chunk_ids": [item.chunk_id for item in result.citations],
            },
        )
    )
    await session.commit()
    return result
