from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Case, StorageNamespace, StorageObject, User
from app.models.enums import CaseRoleType, UserRole


_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    safe_name = _UNSAFE_FILENAME.sub("_", name).strip("._")
    return safe_name[:240] or "document.bin"


def create_s3_client(*, public: bool = False) -> Any:
    endpoint_url = (
        settings.s3_public_endpoint_url if public else settings.s3_endpoint_url
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def configured_buckets() -> list[str]:
    return list(
        dict.fromkeys(
            [
                settings.s3_corpus_bucket,
                settings.s3_police_bucket,
                settings.s3_advocate_bucket,
                settings.s3_generated_bucket,
            ]
        )
    )


async def ensure_storage_buckets() -> list[str]:
    client = create_s3_client()

    def ensure() -> None:
        existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
        for bucket in configured_buckets():
            if bucket not in existing:
                client.create_bucket(Bucket=bucket)
            client.put_bucket_versioning(
                Bucket=bucket,
                VersioningConfiguration={"Status": "Enabled"},
            )

    await asyncio.to_thread(ensure)
    return configured_buckets()


class DocumentStorageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.client = create_s3_client()
        self.public_client = create_s3_client(public=True)

    async def _authorized_case(self, case_id: uuid.UUID, user: User) -> Case:
        case = await self.session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        if user.role == UserRole.ADMIN:
            return case
        if case.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case access denied")
        if case.role_type.value != user.role.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case role mismatch")
        return case

    @staticmethod
    def _case_location(case: Case) -> tuple[str, StorageNamespace]:
        if case.role_type == CaseRoleType.POLICE:
            return settings.s3_police_bucket, StorageNamespace.POLICE_CASE
        if case.role_type == CaseRoleType.ADVOCATE:
            return settings.s3_advocate_bucket, StorageNamespace.ADVOCATE_CASE
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unsupported case role")

    async def upload_case_document(
        self,
        *,
        case_id: uuid.UUID,
        user: User,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> StorageObject:
        case = await self._authorized_case(case_id, user)
        bucket, namespace = self._case_location(case)
        safe_filename = sanitize_filename(filename)
        object_key = f"cases/{case.id}/documents/{uuid.uuid4()}/{safe_filename}"
        digest = hashlib.sha256(content).hexdigest()

        await asyncio.to_thread(
            self.client.put_object,
            Bucket=bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            Metadata={
                "owner-id": str(user.id),
                "case-id": str(case.id),
                "sha256": digest,
                "original-filename": safe_filename,
            },
        )
        stored = StorageObject(
            bucket=bucket,
            object_key=object_key,
            namespace=namespace,
            owner_id=user.id,
            case_id=case.id,
            original_filename=filename,
            content_type=content_type,
            file_size=len(content),
            sha256=digest,
        )
        self.session.add(stored)
        try:
            await self.session.flush()
        except Exception:
            await asyncio.to_thread(
                self.client.delete_object,
                Bucket=bucket,
                Key=object_key,
            )
            raise
        return stored

    async def upload_corpus_document(
        self,
        *,
        user: User,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> StorageObject:
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
        safe_filename = sanitize_filename(filename)
        digest = hashlib.sha256(content).hexdigest()
        object_key = f"corpus/intake/{digest[:12]}/{uuid.uuid4()}/{safe_filename}"
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=settings.s3_corpus_bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            Metadata={
                "uploaded-by": str(user.id),
                "sha256": digest,
                "original-filename": safe_filename,
                "intake-status": "staged",
            },
        )
        stored = StorageObject(
            bucket=settings.s3_corpus_bucket,
            object_key=object_key,
            namespace=StorageNamespace.LEGAL_CORPUS,
            owner_id=user.id,
            case_id=None,
            original_filename=filename,
            content_type=content_type,
            file_size=len(content),
            sha256=digest,
        )
        self.session.add(stored)
        try:
            await self.session.flush()
        except Exception:
            await asyncio.to_thread(
                self.client.delete_object,
                Bucket=settings.s3_corpus_bucket,
                Key=object_key,
            )
            raise
        return stored

    async def _authorized_object(self, object_id: uuid.UUID, user: User) -> StorageObject:
        stored = await self.session.get(StorageObject, object_id)
        if stored is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found")
        if stored.case_id is not None:
            await self._authorized_case(stored.case_id, user)
        elif user.role != UserRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Object access denied")
        return stored

    async def download_case_document(self, object_id: uuid.UUID, user: User) -> bytes:
        stored = await self._authorized_object(object_id, user)

        def download() -> bytes:
            response = self.client.get_object(Bucket=stored.bucket, Key=stored.object_key)
            try:
                return response["Body"].read()
            finally:
                response["Body"].close()

        return await asyncio.to_thread(download)

    async def create_presigned_download_url(
        self,
        object_id: uuid.UUID,
        user: User,
        *,
        expires_seconds: int = 900,
    ) -> str:
        stored = await self._authorized_object(object_id, user)
        expires = max(60, min(expires_seconds, 3600))
        return await asyncio.to_thread(
            self.public_client.generate_presigned_url,
            "get_object",
            Params={"Bucket": stored.bucket, "Key": stored.object_key},
            ExpiresIn=expires,
        )

    async def create_presigned_upload_url(
        self,
        *,
        case_id: uuid.UUID,
        user: User,
        filename: str,
        content_type: str = "application/octet-stream",
        expires_seconds: int = 900,
    ) -> tuple[str, str, str]:
        case = await self._authorized_case(case_id, user)
        bucket, _ = self._case_location(case)
        object_key = f"cases/{case.id}/pending/{uuid.uuid4()}/{sanitize_filename(filename)}"
        expires = max(60, min(expires_seconds, 3600))
        url = await asyncio.to_thread(
            self.public_client.generate_presigned_url,
            "put_object",
            Params={"Bucket": bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=expires,
        )
        return url, bucket, object_key

    async def delete_object(self, object_id: uuid.UUID, user: User) -> None:
        stored = await self._authorized_object(object_id, user)
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=stored.bucket,
            Key=stored.object_key,
        )
        await self.session.delete(stored)
