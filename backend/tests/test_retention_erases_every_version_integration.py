"""A retention purge left every byte of a purged case's files behind a delete marker.

The buckets are versioned, so a plain delete_object hides an object and keeps it.
A purge that claims to have removed a privileged file has to remove the versions.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models.enums import CaseRoleType
from app.services.admin_retention import _erase_case_from_stores
from app.services.storage import create_s3_client, ensure_storage_buckets


class _FakeQdrant:
    async def delete(self, **kwargs):
        return None


@pytest.mark.asyncio
async def test_a_purged_case_file_has_no_version_left() -> None:
    await ensure_storage_buckets()
    client = create_s3_client()
    bucket = settings.s3_police_bucket
    key = f"cases/{uuid.uuid4()}/documents/{uuid.uuid4()}/statement.txt"
    client.put_object(Bucket=bucket, Key=key, Body=b"first")
    client.put_object(Bucket=bucket, Key=key, Body=b"second")

    await _erase_case_from_stores(
        SimpleNamespace(id=uuid.uuid4(), role_type=CaseRoleType.POLICE),
        _FakeQdrant(),
        [SimpleNamespace(bucket=bucket, object_key=key)],
    )

    listing = client.list_object_versions(Bucket=bucket, Prefix=key)
    assert not listing.get("Versions")
    assert not listing.get("DeleteMarkers")
