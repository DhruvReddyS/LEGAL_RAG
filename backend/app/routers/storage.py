from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import CASE_DOCUMENT_MANAGE_OWN, CASE_READ_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, Case, User
from app.schemas.storage import (
    PresignedDownloadResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    StorageObjectResponse,
    CaseDocumentIndexRequest,
    CaseDocumentIndexResponse,
)
from app.services.case_documents import CaseDocumentIndexingService
from app.services.retrieval import HybridRetrievalService
from app.services.storage import DocumentStorageService


router = APIRouter(prefix="/cases/{case_id}/storage", tags=["case-storage"])


def get_retrieval_service(request: Request) -> HybridRetrievalService:
    return request.app.state.retrieval_service


@router.post("/objects", response_model=StorageObjectResponse, status_code=status.HTTP_201_CREATED)
async def upload_case_object(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(CASE_DOCUMENT_MANAGE_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> StorageObjectResponse:
    service = DocumentStorageService(session)
    stored = await service.upload_case_document(
        case_id=case_id,
        user=current_user,
        filename=file.filename or "document.bin",
        content=await file.read(),
        content_type=file.content_type or "application/octet-stream",
    )
    await session.commit()
    await session.refresh(stored)
    return StorageObjectResponse.model_validate(stored)


@router.post(
    "/objects/{object_id}/index",
    response_model=CaseDocumentIndexResponse,
    status_code=status.HTTP_201_CREATED,
)
async def index_case_object(
    case_id: uuid.UUID,
    object_id: uuid.UUID,
    request: CaseDocumentIndexRequest,
    current_user: User = Depends(require_permission(CASE_DOCUMENT_MANAGE_OWN)),
    session: AsyncSession = Depends(get_db_session),
    retrieval: HybridRetrievalService = Depends(get_retrieval_service),
) -> CaseDocumentIndexResponse:
    case = await session.get(Case, case_id)
    service = DocumentStorageService(session)
    stored = await service._authorized_object(object_id, current_user)
    if stored.case_id != case_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found")
    document, pages, chunks = await CaseDocumentIndexingService(
        session, retrieval
    ).index_storage_object(
        case=case,
        stored=stored,
        user=current_user,
        doc_type=request.doc_type.strip().lower(),
    )
    session.add(
        AuditLog(
            user_id=current_user.id,
            action="case.document.index",
            resource_type="case_document",
            resource_id=document.id,
            metadata_={
                "case_id": str(case_id),
                "storage_object_id": str(object_id),
                "pages": pages,
                "chunks": chunks,
            },
        )
    )
    await session.commit()
    return CaseDocumentIndexResponse(
        document_id=document.id,
        storage_object_id=stored.id,
        case_id=case.id,
        doc_type=document.doc_type,
        pages=pages,
        chunks=chunks,
    )


@router.get("/objects/{object_id}")
async def download_case_object(
    case_id: uuid.UUID,
    object_id: uuid.UUID,
    current_user: User = Depends(require_permission(CASE_READ_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    service = DocumentStorageService(session)
    stored = await service._authorized_object(object_id, current_user)
    if stored.case_id != case_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found")
    content = await service.download_case_document(object_id, current_user)
    return Response(
        content=content,
        media_type=stored.content_type,
        headers={"Content-Disposition": f'attachment; filename="{stored.original_filename}"'},
    )


@router.post("/objects/{object_id}/presign", response_model=PresignedDownloadResponse)
async def presign_case_object_download(
    case_id: uuid.UUID,
    object_id: uuid.UUID,
    expires_seconds: int = Query(default=900, ge=60, le=3600),
    current_user: User = Depends(require_permission(CASE_READ_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> PresignedDownloadResponse:
    service = DocumentStorageService(session)
    stored = await service._authorized_object(object_id, current_user)
    if stored.case_id != case_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found")
    url = await service.create_presigned_download_url(
        object_id,
        current_user,
        expires_seconds=expires_seconds,
    )
    return PresignedDownloadResponse(url=url, expires_seconds=expires_seconds)


@router.post("/presign-upload", response_model=PresignedUploadResponse)
async def presign_case_object_upload(
    case_id: uuid.UUID,
    request: PresignedUploadRequest,
    current_user: User = Depends(require_permission(CASE_DOCUMENT_MANAGE_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> PresignedUploadResponse:
    service = DocumentStorageService(session)
    url, bucket, object_key = await service.create_presigned_upload_url(
        case_id=case_id,
        user=current_user,
        filename=request.filename,
        content_type=request.content_type,
        expires_seconds=request.expires_seconds,
    )
    return PresignedUploadResponse(
        url=url,
        bucket=bucket,
        object_key=object_key,
        expires_seconds=request.expires_seconds,
    )
