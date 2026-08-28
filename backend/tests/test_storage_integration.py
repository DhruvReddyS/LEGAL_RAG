from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, Case, StorageObject, User
from app.models.enums import CaseRoleType
from app.services.storage import create_s3_client, ensure_storage_buckets
from main import app
from tests.helpers import provision_test_user


@pytest.mark.asyncio
async def test_storage_round_trip_presign_and_cross_case_denial() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    payload = b"verified private legal case document\n"
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []
    stored_bucket: str | None = None
    stored_key: str | None = None

    assert len(await ensure_storage_buckets()) == 4

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            tokens: list[str] = []
            for index in range(2):
                body = await provision_test_user(
                    name=f"Storage Officer {index}",
                    email=f"storage-officer-{index}-{suffix}@example.com",
                    password=password,
                    role="police",
                )
                user_ids.append(uuid.UUID(body["user"]["id"]))
                tokens.append(body["access_token"])

            async with AsyncSessionLocal() as session:
                cases = [
                    Case(
                        owner_id=user_id,
                        role_type=CaseRoleType.POLICE,
                        title=f"Storage case {index}",
                        status="open",
                    )
                    for index, user_id in enumerate(user_ids)
                ]
                session.add_all(cases)
                await session.commit()
                case_ids.extend(case.id for case in cases)

            owner_headers = {"Authorization": f"Bearer {tokens[0]}"}
            other_headers = {"Authorization": f"Bearer {tokens[1]}"}
            upload = await client.post(
                f"/cases/{case_ids[0]}/storage/objects",
                headers=owner_headers,
                files={"file": ("evidence.txt", payload, "text/plain")},
            )
            assert upload.status_code == 201, upload.text
            stored = upload.json()
            stored_id = stored["id"]
            stored_bucket = stored["bucket"]
            stored_key = stored["object_key"]
            assert stored["file_size"] == len(payload)
            assert stored["sha256"]

            download = await client.get(
                f"/cases/{case_ids[0]}/storage/objects/{stored_id}",
                headers=owner_headers,
            )
            assert download.status_code == 200, download.text
            assert download.content == payload

            presign = await client.post(
                f"/cases/{case_ids[0]}/storage/objects/{stored_id}/presign",
                headers=owner_headers,
            )
            assert presign.status_code == 200, presign.text
            async with httpx.AsyncClient() as s3_client:
                presigned_download = await s3_client.get(presign.json()["url"])
            assert presigned_download.status_code == 200
            assert presigned_download.content == payload

            cross_case_download = await client.get(
                f"/cases/{case_ids[0]}/storage/objects/{stored_id}",
                headers=other_headers,
            )
            assert cross_case_download.status_code == 403

            wrong_path_case = await client.get(
                f"/cases/{case_ids[1]}/storage/objects/{stored_id}",
                headers=other_headers,
            )
            assert wrong_path_case.status_code == 403

            cross_case_presign = await client.post(
                f"/cases/{case_ids[0]}/storage/objects/{stored_id}/presign",
                headers=other_headers,
            )
            assert cross_case_presign.status_code == 403
        finally:
            if stored_bucket and stored_key:
                await asyncio.to_thread(
                    create_s3_client().delete_object,
                    Bucket=stored_bucket,
                    Key=stored_key,
                )
            async with AsyncSessionLocal() as session:
                if case_ids:
                    await session.execute(
                        delete(StorageObject).where(StorageObject.case_id.in_(case_ids))
                    )
                    await session.execute(delete(Case).where(Case.id.in_(case_ids)))
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
