from __future__ import annotations

import asyncio
import hashlib
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, status
from qdrant_client import models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion.extract import ExtractedPage, extract_pdf
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, POLICE_CASE_DATA
from app.ingestion.sparse import to_sparse_vector
from app.models import Case, CaseDocument, StorageObject, User
from app.models.enums import CaseRoleType
from app.services.retrieval import HybridRetrievalService
from app.services.storage import DocumentStorageService


MAX_INDEXABLE_BYTES = 25 * 1024 * 1024
MAX_CHUNK_WORDS = 700
CHUNK_OVERLAP_WORDS = 80


@dataclass(frozen=True)
class PrivateChunk:
    chunk_id: str
    text: str
    page_start: int
    page_end: int


def _chunk_pages(document_id: uuid.UUID, pages: list[ExtractedPage]) -> list[PrivateChunk]:
    chunks: list[PrivateChunk] = []
    for page in pages:
        words = page.text.split()
        start = 0
        while start < len(words):
            end = min(start + MAX_CHUNK_WORDS, len(words))
            text = " ".join(words[start:end]).strip()
            if text:
                digest = hashlib.sha256(
                    f"{document_id}|{page.page_number}|{start}|{text}".encode("utf-8")
                ).hexdigest()[:32]
                chunks.append(
                    PrivateChunk(
                        chunk_id=f"case-chunk-{digest}",
                        text=text,
                        page_start=page.page_number,
                        page_end=page.page_number,
                    )
                )
            if end == len(words):
                break
            start = end - CHUNK_OVERLAP_WORDS
    return chunks


def _plain_text_pages(content: bytes, document_id: str) -> list[ExtractedPage]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Text evidence must be UTF-8 encoded",
        ) from exc
    return [
        ExtractedPage(
            page_number=1,
            text=text,
            original_page_text=text,
            extraction_method="utf8",
            ocr_used=False,
        )
    ]


async def _extract_pages(stored: StorageObject, content: bytes) -> list[ExtractedPage]:
    if len(content) > MAX_INDEXABLE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Case evidence exceeds the 25 MiB indexing limit",
        )
    is_pdf = stored.content_type == "application/pdf" or stored.original_filename.lower().endswith(
        ".pdf"
    )
    if not is_pdf:
        if not stored.content_type.startswith("text/"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Indexing currently supports PDF and UTF-8 text evidence",
            )
        return _plain_text_pages(content, str(stored.id))

    def extract() -> list[ExtractedPage]:
        with tempfile.TemporaryDirectory(prefix="legal-rag-case-") as directory:
            path = Path(directory) / "evidence.pdf"
            path.write_bytes(content)
            return extract_pdf(path, document_id=str(stored.id), ocr_workers=2).pages

    try:
        return await asyncio.to_thread(extract)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unable to extract PDF evidence: {type(exc).__name__}",
        ) from exc


def _collection(case: Case) -> str:
    return POLICE_CASE_DATA if case.role_type is CaseRoleType.POLICE else ADVOCATE_CASE_DATA


class CaseDocumentIndexingService:
    def __init__(
        self,
        session: AsyncSession,
        retrieval: HybridRetrievalService,
    ) -> None:
        self.session = session
        self.retrieval = retrieval

    async def index_storage_object(
        self,
        *,
        case: Case,
        stored: StorageObject,
        user: User,
        doc_type: str,
    ) -> tuple[CaseDocument, int, int]:
        content = await DocumentStorageService(self.session).download_case_document(
            stored.id, user
        )
        pages = await _extract_pages(stored, content)
        extracted_text = "\n\n".join(page.text for page in pages if page.text.strip()).strip()
        if not extracted_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Evidence contains no extractable text",
            )

        file_url = f"s3://{stored.bucket}/{stored.object_key}"
        document = await self.session.scalar(
            select(CaseDocument).where(
                CaseDocument.case_id == case.id,
                CaseDocument.file_url == file_url,
            )
        )
        if document is None:
            document = CaseDocument(
                case_id=case.id,
                file_url=file_url,
                doc_type=doc_type,
                ocr_text=extracted_text,
            )
            self.session.add(document)
            await self.session.flush()
        else:
            document.doc_type = doc_type
            document.ocr_text = extracted_text

        chunks = _chunk_pages(document.id, pages)
        embeddings = await self.retrieval.embed_documents(
            [chunk.text for chunk in chunks], batch_size=8
        )
        collection_name = _collection(case)
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                vector={
                    settings.qdrant_dense_vector_name: embedding.dense,
                    settings.qdrant_sparse_vector_name: to_sparse_vector(embedding.sparse),
                },
                payload={
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "title": stored.original_filename,
                    "case_id": str(case.id),
                    "document_id": str(document.id),
                    "storage_object_id": str(stored.id),
                    "doc_type": doc_type,
                    "uploaded_by": str(user.id),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "corpus_scope": "private_case",
                },
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        for offset in range(0, len(points), 64):
            await self.retrieval.client.upsert(
                collection_name=collection_name,
                points=points[offset : offset + 64],
                wait=True,
            )

        current_ids = {str(point.id) for point in points}
        existing, next_offset = await self.retrieval.client.scroll(
            collection_name=collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=str(document.id))
                    )
                ]
            ),
            limit=256,
            with_payload=False,
            with_vectors=False,
        )
        stale_ids = [str(point.id) for point in existing if str(point.id) not in current_ids]
        while next_offset is not None:
            batch, next_offset = await self.retrieval.client.scroll(
                collection_name=collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document.id)),
                        )
                    ]
                ),
                limit=256,
                offset=next_offset,
                with_payload=False,
                with_vectors=False,
            )
            stale_ids.extend(
                str(point.id) for point in batch if str(point.id) not in current_ids
            )
        if stale_ids:
            await self.retrieval.client.delete(
                collection_name=collection_name,
                points_selector=models.PointIdsList(points=stale_ids),
                wait=True,
            )
        return document, len(pages), len(points)
