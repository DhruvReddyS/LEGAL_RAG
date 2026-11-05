from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import StorageNamespace


class StorageObjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bucket: str
    object_key: str
    namespace: StorageNamespace
    owner_id: uuid.UUID | None
    case_id: uuid.UUID | None
    original_filename: str
    content_type: str
    file_size: int
    sha256: str
    created_at: datetime


class PresignedDownloadResponse(BaseModel):
    url: str
    expires_seconds: int


class CaseDocumentIndexRequest(BaseModel):
    doc_type: str = Field(min_length=2, max_length=100)


class CaseDocumentIndexResponse(BaseModel):
    document_id: uuid.UUID
    storage_object_id: uuid.UUID
    case_id: uuid.UUID
    doc_type: str
    pages: int
    chunks: int
    extraction_method: str = "native_or_ocr"
