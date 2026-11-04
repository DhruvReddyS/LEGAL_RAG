"""Saving and listing an advocate's work products, always within one case."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdvocateWorkProduct, Case


async def save_work_product(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    user_id: uuid.UUID | None,
    kind: str,
    title: str,
    status: str,
    content: dict[str, Any],
) -> AdvocateWorkProduct:
    """Write the next version. The case row lock keeps version numbers unique."""
    await session.scalar(select(Case.id).where(Case.id == case_id).with_for_update())
    latest = await session.scalar(
        select(func.max(AdvocateWorkProduct.version)).where(
            AdvocateWorkProduct.case_id == case_id, AdvocateWorkProduct.kind == kind
        )
    )
    product = AdvocateWorkProduct(
        case_id=case_id,
        created_by=user_id,
        kind=kind,
        version=int(latest or 0) + 1,
        status=status,
        title=title[:255],
        content=content,
    )
    session.add(product)
    await session.flush()
    return product


def work_summary(product: AdvocateWorkProduct) -> dict[str, Any]:
    return {
        "id": str(product.id),
        "case_id": str(product.case_id),
        "kind": product.kind,
        "version": product.version,
        "status": product.status,
        "title": product.title,
        "created_at": product.created_at.isoformat(),
    }


def work_detail(product: AdvocateWorkProduct) -> dict[str, Any]:
    return {**work_summary(product), "content": product.content}
