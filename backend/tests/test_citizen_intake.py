import io
import json
import uuid
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.security import get_current_user
from app.routers.citizen_intake import extract_upload, router
from app.schemas.chat import ChatQueryRequest, CitizenDocumentContext
from app.services.citizen_context import select_document_context


def pdf_bytes(pages=1):
    with pymupdf.open() as pdf:
        for _ in range(pages):
            page = pdf.new_page()
            page.insert_text((72, 72), "Rental agreement: the tenant must receive written notice before termination.")
        return pdf.tobytes()


def test_pdf_extraction_and_page_limit():
    pages, truncated = extract_upload(pdf_bytes(), "application/pdf")
    assert "tenant" in pages[0]["text"]
    assert pages[0]["page"] == 1
    assert not truncated
    with pytest.raises(ValueError, match="20 pages"):
        extract_upload(pdf_bytes(21), "application/pdf")


def test_context_is_bounded_and_document_ids_separate():
    documents = [CitizenDocumentContext(filename="notice.pdf", pages=[{"page": 1, "text": "rent notice " * 900}])]
    context = json.loads(select_document_context("rent", documents))
    assert context[0]["document"] == "D1"
    assert context[0]["filename"] == "notice.pdf"
    assert sum(len(item["text"]) for item in context) <= 9000
    assert select_document_context("rent", []) == ""
    assert "chunk_id" not in context[0]


def test_context_request_limits():
    assert ChatQueryRequest(query="hello").documents == []
    with pytest.raises(ValidationError):
        ChatQueryRequest(query="hello", documents=[{"filename": "a", "pages": [{"page": 1, "text": "x" * 12001}]}])
    with pytest.raises(ValidationError):
        ChatQueryRequest(query="hello", documents=[{"filename": "a", "pages": [{"page": 21, "text": "x"}]}])


@pytest.mark.asyncio
async def test_extraction_auth_and_validation():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post("/citizen/documents/extract", files={"file": ("test.pdf", pdf_bytes(), "application/pdf")})
        assert denied.status_code in (401, 403)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
        valid = await client.post("/citizen/documents/extract", files={"file": ("test.pdf", pdf_bytes(), "application/pdf")})
        assert valid.status_code == 200, valid.text
        assert "tenant" in valid.json()["pages"][0]["text"]
        unsupported = await client.post("/citizen/documents/extract", files={"file": ("file.txt", b"text", "text/plain")})
        assert unsupported.status_code == 415
        corrupt = await client.post("/citizen/documents/extract", files={"file": ("file.pdf", b"broken", "application/pdf")})
        assert corrupt.status_code == 422
        oversized = await client.post("/citizen/documents/extract", files={"file": ("file.png", b"a" * (10 * 1024 * 1024 + 1), "image/png")})
        assert oversized.status_code == 413


def test_real_image_ocr():
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1200, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 65), "RENTAL NOTICE: Please reply in writing.", font=ImageFont.load_default(size=32), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    pages, _ = extract_upload(buffer.getvalue(), "image/png")
    assert "RENTAL NOTICE" in pages[0]["text"]


@pytest.mark.asyncio
async def test_document_context_reaches_deep_workflow_without_persisting_raw_upload():
    from sqlalchemy import delete
    from app.core.database import AsyncSessionLocal
    from app.models import AuditLog, User
    from app.routers.chat import get_workflow
    from app.schemas.agents import AgentTraceEvent, QueryIntent
    from main import app

    calls = []
    class Workflow:
        async def run(self, **kwargs):
            calls.append(kwargs)
            return {"final_answer": "Review the notice against the relevant authority.", "citations": [],
                    "confidence_score": 0.8, "evidence_strength": "strong",
                    "intent": QueryIntent(retrieval_query="rent notice"),
                    "agent_trace": [AgentTraceEvent(node="verification", details={"score": 0.8})]}
    app.dependency_overrides[get_workflow] = lambda: Workflow()
    user_id = None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            registered = await client.post("/auth/register", json={"name": "Intake test", "email": f"intake-{uuid.uuid4().hex}@example.com", "password": "CorrectHorseBattery99!", "role": "citizen"})
            assert registered.status_code == 201, registered.text
            user_id = uuid.UUID(registered.json()["user"]["id"])
            headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
            response = await client.post("/chat/query", headers=headers, json={"query": "Explain this notice", "response_mode": "fast", "documents": [{"filename": "notice.pdf", "pages": [{"page": 1, "text": "PRIVATE-CONTEXT-ONLY rental notice"}]}]})
            assert response.status_code == 200, response.text
            assert response.json()["response_mode"] == "deep"
            assert "PRIVATE-CONTEXT-ONLY" in calls[0]["document_context"]
            assert calls[0]["query"] == "Explain this notice"
            saved = await client.get(f"/chat/sessions/{response.json()['session_id']}", headers=headers)
            assert "PRIVATE-CONTEXT-ONLY" not in saved.text
            assert calls[0]["case_id"] is None
            branch = await client.post("/chat/query", headers=headers, json={"query": "My edited question", "response_mode": "deep", "prior_messages": [{"role": "user", "content": "Earlier context"}]})
            assert branch.status_code == 200, branch.text
            assert branch.json()["session_id"] != response.json()["session_id"]
            assert calls[1]["history"] == [{"role": "user", "content": "Earlier context"}]
            assert "document_context" not in calls[1]
            original = await client.get(f"/chat/sessions/{response.json()['session_id']}", headers=headers)
            assert "My edited question" not in original.text
    finally:
        app.dependency_overrides.pop(get_workflow, None)
        if user_id:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()


@pytest.mark.asyncio
async def test_stop_cancels_workflow_on_client_disconnect():
    import asyncio
    from fastapi import HTTPException
    from app.routers.chat import run_while_connected
    cancelled = asyncio.Event()
    class DisconnectedRequest:
        async def is_disconnected(self):
            return True
    async def work():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    with pytest.raises(HTTPException) as error:
        await run_while_connected(DisconnectedRequest(), work())
    assert error.value.status_code == 499
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_completed_workflow_result_is_returned():
    from app.routers.chat import run_while_connected
    async def work():
        return {"answer": "completed"}
    assert await run_while_connected(None, work()) == {"answer": "completed"}
