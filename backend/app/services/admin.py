from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException, status
from qdrant_client import models
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.ingestion.sparse import to_sparse_vector
from app.models import AuditLog, Case, CorpusIntake, CorpusSource, StorageObject, User
from app.models.enums import CorpusSourceType, UserRole
from app.models.storage import StorageNamespace
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminUserCreate,
    AdminUserResponse,
    AuditEventResponse,
    CorpusIntakeResponse,
)
from app.schemas.auth import RegisterRequest
from app.services.auth import create_user, get_user_by_email
from app.services.case_documents import _extract_pages
from app.services.retrieval import HybridRetrievalService
from app.services.storage import DocumentStorageService


MAX_CORPUS_UPLOAD_BYTES = 30 * 1024 * 1024
MIN_EXTRACTED_CHARACTERS = 100


def intake_response(intake: CorpusIntake, stored: StorageObject) -> CorpusIntakeResponse:
    return CorpusIntakeResponse(
        id=intake.id,
        storage_object_id=stored.id,
        corpus_source_id=intake.corpus_source_id,
        title=intake.title,
        source_type=intake.source_type,
        jurisdiction=intake.jurisdiction,
        authority=intake.authority,
        source_url=intake.source_url,
        status=intake.status,
        filename=stored.original_filename,
        file_size=stored.file_size,
        sha256=stored.sha256,
        validation_summary=intake.validation_summary,
        created_at=intake.created_at,
        updated_at=intake.updated_at,
    )


async def list_professional_users(session: AsyncSession) -> list[AdminUserResponse]:
    case_counts = (
        select(Case.owner_id, func.count(Case.id).label("case_count"))
        .group_by(Case.owner_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(User, func.coalesce(case_counts.c.case_count, 0))
            .outerjoin(case_counts, case_counts.c.owner_id == User.id)
            .where(User.role.in_([UserRole.POLICE, UserRole.ADVOCATE]))
            .order_by(User.created_at.desc())
        )
    ).all()
    return [
        AdminUserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            case_count=int(case_count),
        )
        for user, case_count in rows
    ]


async def create_professional_user(
    session: AsyncSession,
    payload: AdminUserCreate,
    admin: User,
) -> User:
    if await get_user_by_email(session, str(payload.email)) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = await create_user(
        session,
        RegisterRequest(
            name=payload.name,
            email=payload.email,
            password=payload.password,
            role=UserRole(payload.role),
        ),
    )
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.user.create",
            resource_type="user",
            resource_id=user.id,
            metadata_={"role": user.role.value, "email": user.email},
        )
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_professional_user(
    session: AsyncSession,
    target: User,
    *,
    role: UserRole | None,
    is_active: bool | None,
    admin: User,
) -> User:
    if target.role not in {UserRole.POLICE, UserRole.ADVOCATE}:
        raise HTTPException(status_code=403, detail="Only police and advocate accounts are managed here")
    previous = {"role": target.role.value, "is_active": target.is_active}
    if role is not None and role != target.role:
        case_count = await session.scalar(select(func.count(Case.id)).where(Case.owner_id == target.id))
        if case_count:
            raise HTTPException(status_code=409, detail="Role cannot change while the account owns cases")
        target.role = role
    if is_active is not None:
        target.is_active = is_active
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.user.update",
            resource_type="user",
            resource_id=target.id,
            metadata_={
                "before": previous,
                "after": {"role": target.role.value, "is_active": target.is_active},
            },
        )
    )
    await session.commit()
    await session.refresh(target)
    return target


async def stage_corpus_intake(
    session: AsyncSession,
    *,
    admin: User,
    filename: str,
    content_type: str,
    content: bytes,
    title: str,
    source_type: CorpusSourceType,
    jurisdiction: str,
    authority: str | None,
    source_url: str,
) -> tuple[CorpusIntake, StorageObject]:
    if not content or len(content) > MAX_CORPUS_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Corpus documents must be between 1 byte and 30 MiB")
    if content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Global corpus intake currently accepts PDF only")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="File content is not a valid PDF header")
    if not source_url.startswith("https://"):
        raise HTTPException(status_code=422, detail="An HTTPS official source URL is required")
    digest = hashlib.sha256(content).hexdigest()
    duplicate = await session.scalar(
        select(StorageObject).where(
            StorageObject.namespace == StorageNamespace.LEGAL_CORPUS,
            StorageObject.sha256 == digest,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="This exact document is already staged or indexed")

    stored = await DocumentStorageService(session).upload_corpus_document(
        user=admin,
        filename=filename,
        content=content,
        content_type="application/pdf",
    )
    intake = CorpusIntake(
        storage_object_id=stored.id,
        uploaded_by=admin.id,
        title=" ".join(title.split()),
        source_type=source_type,
        jurisdiction=" ".join(jurisdiction.split()),
        authority=" ".join(authority.split()) if authority else None,
        source_url=source_url,
        status="staged",
        validation_summary={"sha256_verified": True, "pdf_header_verified": True},
    )
    session.add(intake)
    await session.flush()
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.corpus.stage",
            resource_type="corpus_intake",
            resource_id=intake.id,
            metadata_={"sha256": stored.sha256, "filename": stored.original_filename},
        )
    )
    await session.commit()
    await session.refresh(intake)
    return intake, stored


async def validate_corpus_intake(
    session: AsyncSession,
    *,
    intake: CorpusIntake,
    admin: User,
) -> tuple[CorpusIntake, StorageObject]:
    if intake.status == "published":
        raise HTTPException(status_code=409, detail="Published corpus intake cannot be revalidated")
    stored = await session.get(StorageObject, intake.storage_object_id)
    if stored is None:
        raise HTTPException(status_code=409, detail="Corpus object is missing")
    content = await DocumentStorageService(session).download_case_document(stored.id, admin)
    pages = await _extract_pages(stored, content)
    extracted_characters = sum(len(page.text.strip()) for page in pages)
    if extracted_characters < MIN_EXTRACTED_CHARACTERS:
        intake.status = "rejected"
        intake.validation_summary = {
            **intake.validation_summary,
            "pages": len(pages),
            "extracted_characters": extracted_characters,
            "reason": "Insufficient extractable legal text",
        }
    else:
        intake.status = "validated"
        intake.validation_summary = {
            **intake.validation_summary,
            "pages": len(pages),
            "extracted_characters": extracted_characters,
            "ocr_pages": sum(1 for page in pages if page.ocr_used),
            "quality_gate": "pass",
        }
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.corpus.validate",
            resource_type="corpus_intake",
            resource_id=intake.id,
            metadata_={"status": intake.status, **intake.validation_summary},
        )
    )
    await session.commit()
    await session.refresh(intake)
    return intake, stored


async def publish_corpus_intake(
    session: AsyncSession,
    *,
    intake: CorpusIntake,
    admin: User,
    retrieval: HybridRetrievalService,
) -> tuple[CorpusIntake, StorageObject, int]:
    if intake.status != "validated":
        raise HTTPException(status_code=409, detail="Only a validated intake can be published")
    stored = await session.get(StorageObject, intake.storage_object_id)
    if stored is None:
        raise HTTPException(status_code=409, detail="Corpus object is missing")
    content = await DocumentStorageService(session).download_case_document(stored.id, admin)
    pages = await _extract_pages(stored, content)
    chunks: list[tuple[str, str, int]] = []
    for page in pages:
        words = page.text.split()
        start = 0
        while start < len(words):
            end = min(start + 700, len(words))
            text = " ".join(words[start:end]).strip()
            if text:
                stable = hashlib.sha256(f"{stored.sha256}|{page.page_number}|{start}|{text}".encode()).hexdigest()[:32]
                chunks.append((f"extended-chunk-{stable}", text, page.page_number))
            if end == len(words):
                break
            start = end - 80
    if not chunks:
        raise HTTPException(status_code=422, detail="Validated document produced no indexable chunks")
    embeddings = await retrieval.embed_documents([text for _, text, _ in chunks], batch_size=8)
    canonical_id = f"admin-extended-{stored.sha256[:24]}"
    points = [
        models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id)),
            vector={
                settings.qdrant_dense_vector_name: embedding.dense,
                settings.qdrant_sparse_vector_name: to_sparse_vector(embedding.sparse),
            },
            payload={
                "chunk_id": chunk_id,
                "text": text,
                "source_type": intake.source_type.value,
                "title": intake.title,
                "jurisdiction": intake.jurisdiction,
                "court": intake.authority or "",
                "source_url": intake.source_url,
                "document_id": canonical_id,
                "canonical_document_id": canonical_id,
                "source_id": str(intake.id),
                "page_start": page,
                "page_end": page,
                "verified_official": True,
                "quality_status": "admin_validated",
                "is_current": True,
                "corpus_tier": "extended",
            },
        )
        for (chunk_id, text, page), embedding in zip(chunks, embeddings, strict=True)
    ]
    for offset in range(0, len(points), 64):
        await retrieval.client.upsert(
            collection_name=GLOBAL_LEGAL_CORPUS,
            points=points[offset : offset + 64],
            wait=True,
        )
    source = CorpusSource(
        title=intake.title,
        type=intake.source_type,
        jurisdiction=intake.jurisdiction,
        court=intake.authority if intake.source_type is CorpusSourceType.JUDGMENT else None,
        is_current=True,
    )
    session.add(source)
    await session.flush()
    intake.corpus_source_id = source.id
    intake.status = "published"
    intake.validation_summary = {**intake.validation_summary, "indexed_chunks": len(points), "corpus_tier": "extended"}
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.corpus.publish",
            resource_type="corpus_intake",
            resource_id=intake.id,
            metadata_={"indexed_chunks": len(points), "corpus_tier": "extended"},
        )
    )
    await session.commit()
    await session.refresh(intake)
    return intake, stored, len(points)


async def admin_overview(session: AsyncSession) -> AdminOverviewResponse:
    async def count_where(model, *conditions) -> int:
        return int(await session.scalar(select(func.count(model.id)).where(*conditions)) or 0)
    return AdminOverviewResponse(
        users_total=await count_where(User),
        police_active=await count_where(User, User.role == UserRole.POLICE, User.is_active.is_(True)),
        advocates_active=await count_where(User, User.role == UserRole.ADVOCATE, User.is_active.is_(True)),
        staged_intakes=await count_where(CorpusIntake, CorpusIntake.status == "staged"),
        validated_intakes=await count_where(CorpusIntake, CorpusIntake.status == "validated"),
        published_intakes=await count_where(CorpusIntake, CorpusIntake.status == "published"),
        audit_events=await count_where(AuditLog),
    )
