"""A file indexing refused stayed in the bucket, listed nowhere, after a reload.

The officer saw "damaged" once. From then on the object sat in private storage
with no screen that could show it, retry it or remove it. A file the server will
never index is now removed, every version of it. A file an outage stopped from
indexing is kept and listed with that failure, because a second attempt can work.
"""

from __future__ import annotations

import io
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.ingestion.embedder import EmbeddedText
from app.models import AuditLog, Case, CaseDocument, StorageObject, User
from app.routers.document_analysis import AnalyzerRuntime, get_analyzer_runtime
from app.routers.storage import get_retrieval_service
from app.services.case_documents import OCR_UNAVAILABLE
from app.services.storage import content_matches_declared_type, create_s3_client
from main import app
from tests.helpers import provision_test_user


class _FakeQdrant:
    def __init__(self) -> None:
        self.upserts: list[dict] = []

    async def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    async def scroll(self, **kwargs):
        return [], None

    async def delete(self, **kwargs):
        return None


class _FakeRetrieval:
    def __init__(self, *, down: bool = False) -> None:
        self.client = _FakeQdrant()
        self.down = down

    async def embed_documents(self, texts, *, batch_size):
        if self.down:
            raise RuntimeError("embedder is down")
        return [EmbeddedText(dense=[0.1], sparse={3: 0.8}) for _ in texts]


def _image_of_text(kind: str) -> bytes:
    image = Image.new("RGB", (1400, 240), "white")
    font = ImageFont.load_default(size=64)
    ImageDraw.Draw(image).text((30, 70), "Seizure memo PET 204", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format=kind)
    return buffer.getvalue()


def _versions(bucket: str, key: str) -> list[dict]:
    listing = create_s3_client().list_object_versions(Bucket=bucket, Prefix=key)
    return listing.get("Versions", []) + listing.get("DeleteMarkers", [])


@pytest_asyncio.fixture(loop_scope="session")
async def officer():
    suffix = uuid.uuid4().hex
    body = await provision_test_user(
        name="Refused Evidence Officer",
        email=f"refused-evidence-{suffix}@example.com",
        password="CorrectHorseBattery99!",
        role="police",
    )
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    user_id = uuid.UUID(body["user"]["id"])
    app.dependency_overrides[get_analyzer_runtime] = lambda: AnalyzerRuntime(
        retrieval=_FakeRetrieval(), llm=None
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/cases", json={"title": "Refused"}, headers=headers)
        assert created.status_code == 201, created.text
        case_id = uuid.UUID(created.json()["id"])
        yield client, headers, case_id
    app.dependency_overrides.pop(get_retrieval_service, None)
    app.dependency_overrides.pop(get_analyzer_runtime, None)
    async with AsyncSessionLocal() as session:
        await session.execute(delete(CaseDocument).where(CaseDocument.case_id == case_id))
        await session.execute(delete(StorageObject).where(StorageObject.case_id == case_id))
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _upload(client, headers, case_id, name, content, kind) -> dict:
    uploaded = await client.post(
        f"/cases/{case_id}/storage/objects", headers=headers, files={"file": (name, content, kind)}
    )
    assert uploaded.status_code == 201, uploaded.text
    return uploaded.json()


async def _index(client, headers, case_id, object_id):
    return await client.post(
        f"/cases/{case_id}/storage/objects/{object_id}/index",
        json={"doc_type": "other"},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_a_damaged_pdf_leaves_no_object_no_row_and_says_so(officer) -> None:
    client, headers, case_id = officer
    app.dependency_overrides[get_retrieval_service] = lambda: _FakeRetrieval()
    stored = await _upload(client, headers, case_id, "damaged.pdf", b"%PDF-1.4\nnot a pdf\x00\xff" * 40, "application/pdf")

    refused = await _index(client, headers, case_id, stored["id"])

    assert refused.status_code == 422
    assert "could not be read" in refused.json()["detail"]
    assert "not kept" in refused.json()["detail"]
    assert _versions(stored["bucket"], stored["object_key"]) == []
    async with AsyncSessionLocal() as session:
        assert await session.get(StorageObject, uuid.UUID(stored["id"])) is None
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "case.document.refused",
                AuditLog.resource_id == uuid.UUID(stored["id"]),
            )
        )
        assert audit is not None
        assert "damaged" not in str(audit.metadata_)
    listed = await client.get(f"/cases/{case_id}/documents/indexed", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["documents"] == [] and listed.json()["not_indexed"] == []


@pytest.mark.asyncio
async def test_an_outage_keeps_the_file_and_lists_it_with_its_failure(officer) -> None:
    client, headers, case_id = officer
    app.dependency_overrides[get_retrieval_service] = lambda: _FakeRetrieval(down=True)
    stored = await _upload(client, headers, case_id, "statement.txt", b"The witness saw a red car.", "text/plain")

    with pytest.raises(RuntimeError):
        await _index(client, headers, case_id, stored["id"])

    assert len(_versions(stored["bucket"], stored["object_key"])) == 1
    listed = (await client.get(f"/cases/{case_id}/documents/indexed", headers=headers)).json()
    assert [row["storage_object_id"] for row in listed["not_indexed"]] == [stored["id"]]
    assert listed["not_indexed"][0]["filename"] == "statement.txt"

    app.dependency_overrides[get_retrieval_service] = lambda: _FakeRetrieval()
    retried = await _index(client, headers, case_id, stored["id"])
    assert retried.status_code == 201, retried.text
    listed = (await client.get(f"/cases/{case_id}/documents/indexed", headers=headers)).json()
    assert listed["not_indexed"] == []
    assert listed["total"] == 1


@pytest.mark.asyncio
async def test_every_image_type_the_upload_admits_is_read_by_ocr_and_indexed(officer) -> None:
    client, headers, case_id = officer
    fake = _FakeRetrieval()
    app.dependency_overrides[get_retrieval_service] = lambda: fake

    for kind, pil_format in (("image/png", "PNG"), ("image/jpeg", "JPEG"), ("image/webp", "WEBP")):
        stored = await _upload(client, headers, case_id, f"memo.{pil_format.lower()}", _image_of_text(pil_format), kind)
        indexed = await _index(client, headers, case_id, stored["id"])
        assert indexed.status_code == 201, indexed.text
        assert indexed.json()["pages"] == 1 and indexed.json()["chunks"] == 1
        text = fake.client.upserts[-1]["points"][0].payload["text"]
        assert "Seizure" in text, f"{kind}: {text!r}"


@pytest.mark.asyncio
async def test_a_damaged_or_blank_image_is_refused_and_not_kept(officer) -> None:
    client, headers, case_id = officer
    app.dependency_overrides[get_retrieval_service] = lambda: _FakeRetrieval()
    blank = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(blank, format="PNG")

    for name, content, phrase in (
        ("damaged.png", b"\x89PNG\r\n\x1a\n" + b"not a real image" * 40, "could not be read"),
        ("blank.png", blank.getvalue(), "no extractable text"),
    ):
        stored = await _upload(client, headers, case_id, name, content, "image/png")
        refused = await _index(client, headers, case_id, stored["id"])
        assert refused.status_code == 422, refused.text
        assert phrase in refused.json()["detail"]
        assert "not kept" in refused.json()["detail"]
        assert _versions(stored["bucket"], stored["object_key"]) == []


@pytest.mark.asyncio
async def test_an_image_with_no_ocr_engine_is_an_outage_not_a_refusal(officer, monkeypatch) -> None:
    import pytesseract

    client, headers, case_id = officer
    app.dependency_overrides[get_retrieval_service] = lambda: _FakeRetrieval()
    stored = await _upload(client, headers, case_id, "memo.png", _image_of_text("PNG"), "image/png")

    def no_engine(*_args, **_kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr("app.services.case_documents.ocr_png", no_engine)
    outage = await _index(client, headers, case_id, stored["id"])

    assert outage.status_code == 503
    assert outage.json()["detail"] == OCR_UNAVAILABLE
    assert len(_versions(stored["bucket"], stored["object_key"])) == 1


def test_a_wav_labelled_webp_is_not_an_image() -> None:
    assert content_matches_declared_type(b"RIFF\x24\x00\x00\x00WEBPVP8 ", "image/webp")
    assert not content_matches_declared_type(b"RIFF\x24\x00\x00\x00WAVEfmt ", "image/webp")
