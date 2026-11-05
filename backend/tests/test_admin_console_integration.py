"""The administration console, through its routes, against a real database."""

from __future__ import annotations

import importlib.util
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import (
    AccountFlag,
    AuditLog,
    Case,
    ChatMessage,
    ChatSession,
    CorpusWorkItem,
    DocumentQuarantine,
    Feedback,
    FeedbackTriage,
    GateRun,
    Job,
    ReleaseDecision,
    RetentionPolicy,
    RetentionRun,
    StorageObject,
    User,
    UserSecurity,
)
from app.models.enums import (
    CaseRoleType,
    ChatMessageRole,
    FeedbackRating,
    JobStatus,
    JobType,
    UserRole,
)
from app.models.storage import StorageNamespace
from app.routers.admin_tools import get_corpus_client
from app.services import admin_release, quarantine
from app.services.account_gate import PASSWORD_CHANGE_REQUIRED, assert_account_may_proceed
from app.services.admin_incidents import point_id_for_chunk
from main import app
from tests.helpers import provision_test_user, unique_email

PASSWORD = "CorrectHorseBattery99!"
USER_TEXT = "my landlord locked me out and I am frightened"
EVIDENCE_TEXT = "the private witness statement says the accused fled"
PUBLIC_TEXT = "Bail may be granted under section 480 of the BNSS"


def _bearer(account: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['access_token']}"}


class FakeCorpus:
    """The vector store as the console uses it."""

    def __init__(self) -> None:
        self.payloads: dict[str, dict] = {}
        self.deleted: list[dict] = []
        self.broken = False
        self.collections = [("global_legal_corpus_v4", 100), ("global_legal_corpus_v5", 200)]

    async def retrieve(self, collection_name, ids, **_):
        if self.broken:
            raise RuntimeError("down")
        return [
            SimpleNamespace(id=point, payload=self.payloads[point])
            for point in ids
            if point in self.payloads
        ]

    async def count(self, **_):
        if self.broken:
            raise RuntimeError("down")
        return SimpleNamespace(count=42)

    async def scroll(self, **_):
        return [SimpleNamespace(payload={"corpus_tier": "gold"})], None

    async def get_collections(self):
        if self.broken:
            raise RuntimeError("down")
        return SimpleNamespace(
            collections=[SimpleNamespace(name=name) for name, _ in self.collections]
        )

    async def get_collection(self, name):
        points = dict(self.collections)[name]
        return SimpleNamespace(points_count=points, status="green")

    async def delete(self, **kwargs):
        if self.broken:
            raise RuntimeError("down")
        self.deleted.append(kwargs)


@pytest_asyncio.fixture(loop_scope="session")
async def console(tmp_path, monkeypatch):
    fake = FakeCorpus()
    app.dependency_overrides[get_corpus_client] = lambda: fake
    monkeypatch.setattr(settings, "gate_evidence_root", str(tmp_path / "gates"))
    monkeypatch.setattr(admin_release, "rebuild_is_running", lambda: False)
    monkeypatch.setattr(settings, "legal_kb_root", str(tmp_path / "kb"))

    admin = await provision_test_user(
        name="Console Admin", email=unique_email("console-admin"), password=PASSWORD, role="admin"
    )
    other_admin = await provision_test_user(
        name="Second Admin", email=unique_email("console-admin2"), password=PASSWORD, role="admin"
    )
    citizen = await provision_test_user(
        name="Console Citizen", email=unique_email("console-citizen"), password=PASSWORD, role="citizen"
    )
    officer = await provision_test_user(
        name="Console Officer", email=unique_email("console-officer"), password=PASSWORD, role="police"
    )
    async with AsyncSessionLocal() as session:
        await session.execute(delete(GateRun))
        await session.execute(delete(RetentionPolicy))
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            fake=fake,
            admin=admin,
            other_admin=other_admin,
            citizen=citizen,
            officer=officer,
            root=tmp_path,
        )
    app.dependency_overrides.pop(get_corpus_client, None)
    quarantine.replace_active(frozenset())
    ids = [uuid.UUID(item["user"]["id"]) for item in (admin, other_admin, citizen, officer)]
    async with AsyncSessionLocal() as session:
        await session.execute(delete(GateRun))
        await session.execute(delete(ReleaseDecision).where(ReleaseDecision.decided_by.in_(ids)))
        await session.execute(delete(DocumentQuarantine).where(DocumentQuarantine.quarantined_by.in_(ids)))
        await session.execute(delete(CorpusWorkItem).where(CorpusWorkItem.updated_by.in_(ids)))
        await session.execute(delete(RetentionPolicy))
        await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(ids)))
        await session.execute(delete(Job).where(Job.user_id.in_(ids)))
        await session.execute(delete(ChatSession).where(ChatSession.user_id.in_(ids)))
        await session.execute(delete(Case).where(Case.owner_id.in_(ids)))
        await session.execute(delete(User).where(User.id.in_(ids)))
        await session.commit()


async def _audit(actor: dict, action: str) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.user_id == uuid.UUID(actor["user"]["id"]),
                        AuditLog.action == action,
                    )
                )
            ).all()
        )


# ------------------------------------------------------------ every route


def _console_routes() -> list[APIRoute]:
    def walk(container) -> list[APIRoute]:
        found: list[APIRoute] = []
        for route in getattr(container, "routes", []):
            if isinstance(route, APIRoute):
                found.append(route)
                continue
            nested = getattr(route, "original_router", None) or route
            if nested is not route or hasattr(nested, "routes"):
                found.extend(walk(nested))
        return found

    # The older /admin routes too: the same rule applies to everything under it.
    return [route for route in walk(app) if route.path.startswith("/admin/")]


def test_the_route_walk_finds_the_console() -> None:
    assert len(_console_routes()) >= 30


def _fill(path: str) -> str:
    def value(match: re.Match) -> str:
        name = match.group(1)
        if name.endswith("_id"):
            return str(uuid.uuid4())
        return "placeholder"

    return re.sub(r"\{(\w+)\}", value, path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route", _console_routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}"
)
async def test_every_console_route_refuses_everyone_but_an_administrator(console, route) -> None:
    method = sorted(route.methods)[0]
    path = _fill(route.path)
    anonymous = await console.client.request(method, path, json={})
    assert anonymous.status_code == 401, f"{method} {route.path} answered anonymously"
    for account in (console.citizen, console.officer):
        refused = await console.client.request(method, path, json={}, headers=_bearer(account))
        assert refused.status_code == 403, f"{method} {route.path} answered a non-admin"


# ---------------------------------------------------------------- release


def _write_gates(root: Path, label: str, *, all_pass: bool) -> None:
    directory = root / "gates" / label
    directory.mkdir(parents=True)
    (directory / "payload.txt").write_text("Currency payload gate passed.")
    (directory / "retrieval-gate.txt").write_text(
        "quality gate passed" if all_pass else "quality gate FAILED:\n  recall"
    )
    (directory / "answer-gate.txt").write_text("answer gate passed")
    (directory / "provision.txt").write_text("no provision became unreachable")
    (directory / "health.txt").write_text("9 passed, 0 failed, 0 blocked")
    (directory / "latency-gate.txt").write_text("Latency gate passed.")
    (directory / "provision-drift.txt").write_text("Provision drift gate passed.")
    (directory / "HANDOFF.md").write_text("# notes")


def _decision(label: str, decision: str, **extra) -> dict:
    return {
        "label": label,
        "collection": "global_legal_corpus_v5",
        "decision": decision,
        "reason": "Reviewed the evidence for this release.",
        **extra,
    }


@pytest.mark.asyncio
async def test_the_console_shows_gates_and_what_is_serving(console, monkeypatch) -> None:
    _write_gates(console.root, "rel-a", all_pass=False)
    response = await console.client.get("/admin/console/release", headers=_bearer(console.admin))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["serving_collection"] == settings.qdrant_global_collection
    assert body["live_switch_supported"] is False
    assert [row["name"] for row in body["collections"]["collections"]] == [
        "global_legal_corpus_v4",
        "global_legal_corpus_v5",
    ]
    evidence = body["evidence"][0]
    assert evidence["label"] == "rel-a"
    assert evidence["counts"]["failed"] == 1
    assert evidence["counts"]["passed"] == 6


@pytest.mark.asyncio
async def test_the_console_still_renders_when_the_vector_store_is_down(console) -> None:
    console.fake.broken = True
    response = await console.client.get("/admin/console/release", headers=_bearer(console.admin))
    assert response.status_code == 200
    assert response.json()["collections"]["reachable"] is False


@pytest.mark.asyncio
async def test_approval_over_a_failed_gate_needs_an_override_and_is_recorded(console) -> None:
    _write_gates(console.root, "rel-b", all_pass=False)
    headers = _bearer(console.admin)
    plain = await console.client.post(
        "/admin/console/release/decisions", json=_decision("rel-b", "approve"), headers=headers
    )
    assert plain.status_code == 409
    assert await _audit(console.admin, "admin.release.approve") == []

    overridden = await console.client.post(
        "/admin/console/release/decisions",
        json=_decision("rel-b", "approve", override_failed_gates=True),
        headers=headers,
    )
    assert overridden.status_code == 201, overridden.text
    body = overridden.json()
    assert body["override_failed_gates"] is True
    assert body["gate_snapshot"]["gates"]["retrieval"] == "failed"
    rows = await _audit(console.admin, "admin.release.approve")
    assert rows[0].metadata_["override_failed_gates"] is True


@pytest.mark.asyncio
async def test_a_clean_approval_and_a_refusal_need_no_override(console) -> None:
    _write_gates(console.root, "rel-c", all_pass=True)
    headers = _bearer(console.admin)
    approved = await console.client.post(
        "/admin/console/release/decisions", json=_decision("rel-c", "approve"), headers=headers
    )
    assert approved.status_code == 201
    assert approved.json()["override_failed_gates"] is False
    refused = await console.client.post(
        "/admin/console/release/decisions", json=_decision("rel-c", "refuse"), headers=headers
    )
    assert refused.status_code == 201
    assert len(await _audit(console.admin, "admin.release.refuse")) == 1


@pytest.mark.asyncio
async def test_a_decision_needs_a_real_reason_and_real_evidence(console) -> None:
    headers = _bearer(console.admin)
    short = await console.client.post(
        "/admin/console/release/decisions",
        json={**_decision("rel-x", "refuse"), "reason": "no"},
        headers=headers,
    )
    assert short.status_code == 422
    unknown = await console.client.post(
        "/admin/console/release/decisions", json=_decision("rel-x", "refuse"), headers=headers
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_the_cutover_plan_needs_approval_and_a_typed_confirmation(console) -> None:
    _write_gates(console.root, "rel-d", all_pass=True)
    headers = _bearer(console.admin)
    target = {"collection": "global_legal_corpus_v5", "confirm_collection": "global_legal_corpus_v5"}

    unapproved = await console.client.post(
        "/admin/console/release/cutover-plan", json=target, headers=headers
    )
    assert unapproved.status_code == 409

    await console.client.post(
        "/admin/console/release/decisions", json=_decision("rel-d", "approve"), headers=headers
    )
    mistyped = await console.client.post(
        "/admin/console/release/cutover-plan",
        json={**target, "confirm_collection": "global_legal_corpus_v4"},
        headers=headers,
    )
    assert mistyped.status_code == 422

    plan = await console.client.post(
        "/admin/console/release/cutover-plan", json=target, headers=headers
    )
    assert plan.status_code == 200
    body = plan.json()
    assert body["live_switch_supported"] is False
    assert "QDRANT_GLOBAL_COLLECTION=global_legal_corpus_v5" in body["steps"][0]["command"]
    assert body["rollback_steps"][0]["command"].endswith(settings.qdrant_global_collection)
    assert settings.qdrant_global_collection != "global_legal_corpus_v5", "must not have switched"
    assert len(await _audit(console.admin, "admin.release.cutover_plan")) == 1


@pytest.mark.asyncio
async def test_a_refusal_after_an_approval_withdraws_the_plan(console) -> None:
    _write_gates(console.root, "rel-e", all_pass=True)
    headers = _bearer(console.admin)
    await console.client.post(
        "/admin/console/release/decisions", json=_decision("rel-e", "approve"), headers=headers
    )
    await console.client.post(
        "/admin/console/release/decisions", json=_decision("rel-e", "refuse"), headers=headers
    )
    plan = await console.client.post(
        "/admin/console/release/cutover-plan",
        json={"collection": "global_legal_corpus_v5", "confirm_collection": "global_legal_corpus_v5"},
        headers=headers,
    )
    assert plan.status_code == 409


@pytest.mark.asyncio
async def test_queuing_gates_needs_confirmation_and_one_at_a_time(console) -> None:
    headers = _bearer(console.admin)
    body = {"label": "rel-q", "collection": "global_legal_corpus_v5"}
    unconfirmed = await console.client.post("/admin/console/release/gate-runs", json=body, headers=headers)
    assert unconfirmed.status_code == 422
    unknown_collection = await console.client.post(
        "/admin/console/release/gate-runs",
        json={**body, "collection": "global_legal_corpus_v9", "confirm": True},
        headers=headers,
    )
    assert unknown_collection.status_code == 409
    hostile = await console.client.post(
        "/admin/console/release/gate-runs",
        json={"label": "x; rm -rf /", "collection": "global_legal_corpus_v5", "confirm": True},
        headers=headers,
    )
    assert hostile.status_code == 422

    first = await console.client.post(
        "/admin/console/release/gate-runs", json={**body, "confirm": True}, headers=headers
    )
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "queued"
    second = await console.client.post(
        "/admin/console/release/gate-runs", json={**body, "confirm": True}, headers=headers
    )
    assert second.status_code == 409
    assert "already queued" in second.json()["detail"]

    cancelled = await console.client.post(
        f"/admin/console/release/gate-runs/{first.json()['id']}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    again = await console.client.post(
        "/admin/console/release/gate-runs", json={**body, "confirm": True}, headers=headers
    )
    assert again.status_code == 202


@pytest.mark.asyncio
async def test_a_running_rebuild_blocks_the_queue(console, monkeypatch) -> None:
    monkeypatch.setattr(admin_release, "rebuild_is_running", lambda: True)
    state = await console.client.get("/admin/console/release", headers=_bearer(console.admin))
    assert any("rebuild" in item for item in state.json()["queue_blockers"])
    refused = await console.client.post(
        "/admin/console/release/gate-runs",
        json={"label": "rel-r", "collection": "global_legal_corpus_v5", "confirm": True},
        headers=_bearer(console.admin),
    )
    assert refused.status_code == 409
    assert "rebuild" in refused.json()["detail"]


def _load_runner():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_queued_gates.py"
    spec = importlib.util.spec_from_file_location("run_queued_gates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_the_runner_takes_the_queued_run_and_records_the_exit(console, tmp_path) -> None:
    runner = _load_runner()
    assert await runner.run_next(script=tmp_path / "missing.sh") is None

    await console.client.post(
        "/admin/console/release/gate-runs",
        json={"label": "rel-run", "collection": "global_legal_corpus_v5", "confirm": True},
        headers=_bearer(console.admin),
    )
    received = tmp_path / "args.txt"
    script = tmp_path / "fake_gates.sh"
    script.write_text(f'#!/bin/sh\necho "$1 $2" > "{received}"\nexit 1\n')
    script.chmod(0o755)

    outcome = await runner.run_next(script=script)
    assert outcome == ("rel-run", 1)
    assert received.read_text().strip() == "global_legal_corpus_v5 rel-run"
    state = await console.client.get("/admin/console/release", headers=_bearer(console.admin))
    latest = state.json()["gate_runs"][0]
    assert latest["status"] == "failed"
    assert latest["exit_code"] == 1


# ----------------------------------------------------------------- corpus


def _manifest(root: Path) -> None:
    directory = root / "kb" / "metadata"
    directory.mkdir(parents=True, exist_ok=True)
    base = {
        "source_id": "s",
        "original_filename": "a.pdf",
        "local_path": "a.pdf",
        "sha256": "0" * 64,
        "file_size": 1,
        "page_count": 3,
        "quality_status": "verified",
        "verified_official": True,
    }
    rows = [
        {"document_id": "1", "canonical_document_id": "doc-bns", "title": "Bharatiya Nyaya Sanhita",
         "source_type": "act", "category": "primary_law/bns", "current_status": "current"},
        {"document_id": "2", "canonical_document_id": "doc-ipc", "title": "Indian Penal Code",
         "source_type": "act", "category": "primary_law/ipc", "current_status": "repealed"},
        {"document_id": "3", "canonical_document_id": "doc-scan", "title": "A scanned judgment",
         "source_type": "judgment", "category": "case_law/sc", "current_status": "current/verify",
         "ocr_required": True, "verified_official": False},
    ]
    (directory / "canonical_documents.jsonl").write_text(
        "\n".join(json.dumps({**base, **row}) for row in rows)
    )


@pytest.mark.asyncio
async def test_the_browser_searches_filters_and_counts(console) -> None:
    _manifest(console.root)
    headers = _bearer(console.admin)
    everything = (await console.client.get("/admin/console/corpus", headers=headers)).json()
    assert everything["total_documents"] == 3
    assert everything["facets"]["queue"] == {"ocr": 1, "verification": 1, "currency": 1}
    assert everything["facets"]["currency"]["repealed_or_superseded"] == 1

    searched = (await console.client.get("/admin/console/corpus?q=penal", headers=headers)).json()
    assert [row["canonical_document_id"] for row in searched["documents"]] == ["doc-ipc"]
    assert searched["documents"][0]["currency_flag"] == "repealed_or_superseded"

    domain = (await console.client.get("/admin/console/corpus?domain=case_law", headers=headers)).json()
    assert domain["total"] == 1

    paged = (await console.client.get("/admin/console/corpus?page=2&page_size=2", headers=headers)).json()
    assert len(paged["documents"]) == 1
    assert paged["total"] == 3


@pytest.mark.asyncio
async def test_a_work_list_tracks_progress_on_the_record(console) -> None:
    _manifest(console.root)
    headers = _bearer(console.admin)
    queue = (await console.client.get("/admin/console/corpus?queue=ocr", headers=headers)).json()
    assert [row["canonical_document_id"] for row in queue["documents"]] == ["doc-scan"]
    assert queue["documents"][0]["work_status"] == "open"

    updated = await console.client.put(
        "/admin/console/corpus/work-items",
        json={"canonical_document_id": "doc-scan", "queue": "ocr", "status": "done", "note": "ran OCR"},
        headers=headers,
    )
    assert updated.status_code == 200

    done = (await console.client.get("/admin/console/corpus?queue=ocr&work_status=done", headers=headers)).json()
    assert done["documents"][0]["work_note"] == "ran OCR"
    still_open = (await console.client.get("/admin/console/corpus?queue=ocr&work_status=open", headers=headers)).json()
    assert still_open["total"] == 0

    rows = await _audit(console.admin, "admin.corpus.work_item")
    assert rows[0].metadata_["status"] == "done"
    assert "ran OCR" not in json.dumps(rows[0].metadata_)


@pytest.mark.asyncio
async def test_a_work_item_needs_a_document_on_that_list(console) -> None:
    _manifest(console.root)
    headers = _bearer(console.admin)
    missing = await console.client.put(
        "/admin/console/corpus/work-items",
        json={"canonical_document_id": "nope", "queue": "ocr", "status": "done"},
        headers=headers,
    )
    assert missing.status_code == 404
    wrong = await console.client.put(
        "/admin/console/corpus/work-items",
        json={"canonical_document_id": "doc-bns", "queue": "ocr", "status": "done"},
        headers=headers,
    )
    assert wrong.status_code == 409


@pytest.mark.asyncio
async def test_a_missing_manifest_is_an_empty_browser_not_an_error(console) -> None:
    response = await console.client.get("/admin/console/corpus", headers=_bearer(console.admin))
    assert response.status_code == 200
    assert response.json()["total_documents"] == 0


# ---------------------------------------------------------------- answers


async def _answer(
    owner: dict,
    *,
    case_id: uuid.UUID | None = None,
    citations: list[dict] | None = None,
    rating: FeedbackRating = FeedbackRating.DOWN,
    correction: str | None = USER_TEXT,
) -> SimpleNamespace:
    owner_id = uuid.UUID(owner["user"]["id"])
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=owner_id, case_id=case_id, title="a title")
        session.add(chat)
        await session.flush()
        session.add(ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content=USER_TEXT, citations=[]))
        message = ChatMessage(
            session_id=chat.id,
            role=ChatMessageRole.ASSISTANT,
            content=f"Answer. {EVIDENCE_TEXT}",
            citations=citations or [],
            confidence_score=0.4,
        )
        session.add(message)
        await session.flush()
        feedback = Feedback(message_id=message.id, user_id=owner_id, rating=rating, correction_text=correction)
        session.add(feedback)
        await session.commit()
        return SimpleNamespace(session_id=chat.id, message_id=message.id, feedback_id=feedback.id)


def _citation(chunk_id: str, excerpt: str) -> dict:
    return {
        "number": 1,
        "chunk_id": chunk_id,
        "title": "A source",
        "source_type": "act",
        "page_start": 1,
        "page_end": 2,
        "excerpt": excerpt,
        "verification_status": "verified",
        "current_status": "current",
    }


async def _police_case(owner: dict) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        case = Case(
            owner_id=uuid.UUID(owner["user"]["id"]),
            title="private",
            role_type=CaseRoleType.POLICE,
            status="open",
        )
        session.add(case)
        await session.commit()
        return case.id


@pytest.mark.asyncio
async def test_the_triage_list_holds_no_conversation_text(console) -> None:
    await _answer(console.citizen, citations=[_citation("c1", PUBLIC_TEXT)])
    response = await console.client.get("/admin/console/feedback?rating=down", headers=_bearer(console.admin))
    assert response.status_code == 200
    assert USER_TEXT not in response.text and EVIDENCE_TEXT not in response.text
    assert response.json()["items"][0]["has_correction"] is True


@pytest.mark.asyncio
async def test_a_trace_reaches_the_chunks_and_leaves_a_row_without_text(console) -> None:
    point = point_id_for_chunk("chunk-public")
    console.fake.payloads[point] = {"canonical_document_id": "doc-bns", "corpus_tier": "gold"}
    answer = await _answer(console.citizen, citations=[_citation("chunk-public", PUBLIC_TEXT)])
    response = await console.client.get(
        f"/admin/console/feedback/{answer.feedback_id}/trace", headers=_bearer(console.admin)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["citations"][0]["canonical_document_id"] == "doc-bns"
    assert body["citations"][0]["excerpt"] == PUBLIC_TEXT
    assert body["correction"] == USER_TEXT

    rows = await _audit(console.admin, "admin.feedback.trace")
    assert len(rows) == 1
    stored = json.dumps(rows[0].metadata_)
    for forbidden in (USER_TEXT, EVIDENCE_TEXT, PUBLIC_TEXT):
        assert forbidden not in stored


@pytest.mark.asyncio
async def test_a_case_linked_trace_shows_only_what_is_proved_public(console) -> None:
    """A thumbs-down is not an authorised matter."""
    case_id = await _police_case(console.officer)
    public_point = point_id_for_chunk("chunk-public-2")
    console.fake.payloads[public_point] = {"canonical_document_id": "doc-bns", "corpus_tier": "gold"}
    answer = await _answer(
        console.officer,
        case_id=case_id,
        citations=[
            _citation("chunk-public-2", PUBLIC_TEXT),
            _citation("chunk-private", EVIDENCE_TEXT),
        ],
    )
    response = await console.client.get(
        f"/admin/console/feedback/{answer.feedback_id}/trace", headers=_bearer(console.admin)
    )
    assert response.status_code == 200
    body = response.json()
    assert EVIDENCE_TEXT not in response.text
    assert USER_TEXT not in response.text
    assert body["answer"] is None and body["correction"] is None
    assert body["citations_withheld"] == 1
    assert [row["chunk_id"] for row in body["citations"]] == ["chunk-public-2"]


@pytest.mark.asyncio
async def test_a_case_linked_trace_fails_closed_when_the_corpus_is_unreachable(console) -> None:
    case_id = await _police_case(console.officer)
    answer = await _answer(
        console.officer, case_id=case_id, citations=[_citation("chunk-private-3", EVIDENCE_TEXT)]
    )
    console.fake.broken = True
    response = await console.client.get(
        f"/admin/console/feedback/{answer.feedback_id}/trace", headers=_bearer(console.admin)
    )
    assert response.status_code == 200
    assert EVIDENCE_TEXT not in response.text
    assert response.json()["corpus_checked"] is False
    assert response.json()["citations"] == []


@pytest.mark.asyncio
async def test_triage_moves_on_the_record_without_copying_the_note(console) -> None:
    answer = await _answer(console.citizen)
    headers = _bearer(console.admin)
    response = await console.client.put(
        f"/admin/console/feedback/{answer.feedback_id}/triage",
        json={"status": "investigating", "note": "looks like a stale section"},
        headers=headers,
    )
    assert response.status_code == 200
    listed = await console.client.get("/admin/console/feedback?status=investigating", headers=headers)
    assert str(answer.feedback_id) in {item["id"] for item in listed.json()["items"]}
    rows = await _audit(console.admin, "admin.feedback.triage")
    assert rows[0].metadata_ == {"status": "investigating", "has_note": True}


@pytest.mark.asyncio
async def test_quarantine_previews_first_then_takes_effect_at_once(console) -> None:
    _manifest(console.root)
    headers = _bearer(console.admin)
    document = f"doc-{uuid.uuid4().hex[:8]}"

    preview = await console.client.post(
        "/admin/console/quarantine/preview", json={"canonical_document_id": document}, headers=headers
    )
    assert preview.status_code == 200
    assert preview.json()["points_in_serving_collection"] == 42
    assert not quarantine.is_quarantined(document), "a preview must change nothing"

    unconfirmed = await console.client.post(
        "/admin/console/quarantine",
        json={"canonical_document_id": document, "reason": "wrong section text in this file"},
        headers=headers,
    )
    assert unconfirmed.status_code == 422
    assert not quarantine.is_quarantined(document)

    created = await console.client.post(
        "/admin/console/quarantine",
        json={
            "canonical_document_id": document,
            "reason": "wrong section text in this file",
            "confirm": True,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    # No restart, no refresh: the very next query carries the exclusion.
    assert quarantine.is_quarantined(document)

    duplicate = await console.client.post(
        "/admin/console/quarantine",
        json={"canonical_document_id": document, "reason": "wrong section text in this file", "confirm": True},
        headers=headers,
    )
    assert duplicate.status_code == 409

    rows = await _audit(console.admin, "admin.corpus.quarantine")
    assert rows[-1].metadata_["canonical_document_id"] == document

    released = await console.client.post(
        f"/admin/console/quarantine/{created.json()['id']}/release",
        json={"reason": "the file was corrected upstream", "confirm": True},
        headers=headers,
    )
    assert released.status_code == 200
    assert not quarantine.is_quarantined(document)
    assert len(await _audit(console.admin, "admin.corpus.quarantine_release")) >= 1
    again = await console.client.post(
        f"/admin/console/quarantine/{created.json()['id']}/release",
        json={"reason": "the file was corrected upstream", "confirm": True},
        headers=headers,
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_a_process_that_missed_the_change_catches_up_from_the_database(console) -> None:
    document = f"doc-{uuid.uuid4().hex[:8]}"
    await console.client.post(
        "/admin/console/quarantine",
        json={"canonical_document_id": document, "reason": "wrong section text in this file", "confirm": True},
        headers=_bearer(console.admin),
    )
    quarantine.replace_active(frozenset())
    await quarantine.refresh()
    assert quarantine.is_quarantined(document)


@pytest.mark.asyncio
async def test_a_quarantined_source_stops_opening(console, monkeypatch) -> None:
    from app.routers.document_analysis import AnalyzerRuntime, get_analyzer_runtime

    point = str(uuid.uuid4())
    console.fake.payloads[point] = {
        "canonical_document_id": "doc-withdrawn",
        "chunk_id": "c",
        "document_id": str(uuid.uuid4()),
        "title": "A withdrawn source",
        "text": "x",
        "page_start": 1,
        "page_end": 1,
    }
    runtime = AnalyzerRuntime(retrieval=SimpleNamespace(client=console.fake), llm=None)
    app.dependency_overrides[get_analyzer_runtime] = lambda: runtime
    quarantine.replace_active(frozenset({"doc-withdrawn"}))
    try:
        response = await console.client.get(f"/sources/{point}", headers=_bearer(console.citizen))
    finally:
        app.dependency_overrides.pop(get_analyzer_runtime, None)
    assert response.status_code == 404


# ------------------------------------------------------------------ users


@pytest.mark.asyncio
async def test_the_directory_finds_citizens_and_pages(console) -> None:
    headers = _bearer(console.admin)
    found = await console.client.get(
        f"/admin/console/users?q={console.citizen['user']['email']}", headers=headers
    )
    assert found.status_code == 200
    assert found.json()["total"] == 1
    assert found.json()["users"][0]["role"] == "citizen"

    by_role = await console.client.get("/admin/console/users?role=citizen&page_size=1", headers=headers)
    assert len(by_role.json()["users"]) == 1
    assert by_role.json()["by_role"]["citizen"] >= 1

    literal = await console.client.get("/admin/console/users?q=%25", headers=headers)
    assert literal.json()["total"] == 0, "a % in the search is not a wildcard"


@pytest.mark.asyncio
async def test_suspending_ends_access_at_once_and_reactivating_restores_it(console) -> None:
    headers = _bearer(console.admin)
    user_id = console.citizen["user"]["id"]
    unconfirmed = await console.client.post(
        f"/admin/console/users/{user_id}/suspend", json={"reason": "abuse report"}, headers=headers
    )
    assert unconfirmed.status_code == 422

    suspended = await console.client.post(
        f"/admin/console/users/{user_id}/suspend",
        json={"reason": "abuse report", "confirm": True},
        headers=headers,
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["is_active"] is False
    assert suspended.json()["suspended_reason"] == "abuse report"
    me = await console.client.get("/auth/me", headers=_bearer(console.citizen))
    assert me.status_code == 401

    rows = await _audit(console.admin, "admin.user.suspend")
    assert rows[-1].resource_id == uuid.UUID(user_id)
    assert "abuse report" not in json.dumps(rows[-1].metadata_)

    restored = await console.client.post(
        f"/admin/console/users/{user_id}/reactivate", json={"confirm": True}, headers=headers
    )
    assert restored.json()["is_active"] is True


@pytest.mark.asyncio
async def test_a_forced_reset_flags_the_account_and_ends_its_sessions(console) -> None:
    user_id = console.citizen["user"]["id"]
    response = await console.client.post(
        f"/admin/console/users/{user_id}/force-password-reset",
        json={"required": True},
        headers=_bearer(console.admin),
    )
    assert response.status_code == 200
    assert response.json()["force_password_reset"] is True
    assert (await console.client.get("/auth/me", headers=_bearer(console.citizen))).status_code == 401
    async with AsyncSessionLocal() as session:
        flag = await session.get(AccountFlag, uuid.UUID(user_id))
    assert flag.force_password_reset is True


@pytest.mark.asyncio
async def test_clearing_a_reset_shows_the_first_password_change_that_remains(console) -> None:
    """"Clear reset" read as done while the account stayed locked out of the product."""
    created = await console.client.post(
        "/admin/users",
        json={
            "name": "Provisioned Officer",
            "email": unique_email("provisioned"),
            "password": PASSWORD,
            "role": "police",
        },
        headers=_bearer(console.admin),
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    url = f"/admin/console/users/{user_id}/force-password-reset"
    try:
        forced = await console.client.post(url, json={"required": True}, headers=_bearer(console.admin))
        assert forced.json()["force_password_reset"] is True
        assert forced.json()["first_password_change_pending"] is True

        cleared = await console.client.post(url, json={"required": False}, headers=_bearer(console.admin))
        assert cleared.json()["force_password_reset"] is False
        assert cleared.json()["first_password_change_pending"] is True

        listed = await console.client.get(
            "/admin/console/users", params={"q": created.json()["email"]}, headers=_bearer(console.admin)
        )
        row = next(item for item in listed.json()["users"] if item["id"] == user_id)
        assert row["force_password_reset"] is False
        assert row["first_password_change_pending"] is True

        # The screen is telling the truth: this account is still held at the gate.
        async with AsyncSessionLocal() as session:
            user = await session.get(User, uuid.UUID(user_id))
            with pytest.raises(HTTPException) as held:
                await assert_account_may_proceed(session, user)
        assert held.value.detail == PASSWORD_CHANGE_REQUIRED

        # An ordinary account, which never had a first password to replace, shows nothing.
        ordinary = await console.client.post(
            f"/admin/console/users/{console.citizen['user']['id']}/force-password-reset",
            json={"required": False},
            headers=_bearer(console.admin),
        )
        assert ordinary.json()["first_password_change_pending"] is False
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(AccountFlag).where(AccountFlag.user_id == uuid.UUID(user_id)))
            await session.execute(delete(UserSecurity).where(UserSecurity.user_id == uuid.UUID(user_id)))
            await session.execute(delete(AuditLog).where(AuditLog.resource_id == uuid.UUID(user_id)))
            await session.execute(delete(User).where(User.id == uuid.UUID(user_id)))
            await session.commit()


@pytest.mark.asyncio
async def test_mfa_is_a_flag_with_a_record(console) -> None:
    user_id = console.officer["user"]["id"]
    response = await console.client.post(
        f"/admin/console/users/{user_id}/mfa-required", json={"required": True}, headers=_bearer(console.admin)
    )
    assert response.json()["mfa_required"] is True
    rows = await _audit(console.admin, "admin.user.mfa_required")
    assert rows[-1].metadata_ == {"required": True}
    assert (await console.client.get("/auth/me", headers=_bearer(console.officer))).status_code == 200


@pytest.mark.asyncio
async def test_a_role_changes_only_for_an_account_with_no_cases(console) -> None:
    headers = _bearer(console.admin)
    user_id = console.officer["user"]["id"]
    changed = await console.client.post(
        f"/admin/console/users/{user_id}/role",
        json={"role": "advocate", "confirm": True},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "advocate"
    rows = await _audit(console.admin, "admin.user.role_change")
    assert rows[-1].metadata_ == {"before": "police", "after": "advocate"}

    grant = await console.client.post(
        f"/admin/console/users/{user_id}/role", json={"role": "admin", "confirm": True}, headers=headers
    )
    assert grant.status_code == 422

    async with AsyncSessionLocal() as session:
        session.add(
            Case(owner_id=uuid.UUID(user_id), title="held", role_type=CaseRoleType.ADVOCATE, status="open")
        )
        await session.commit()
    blocked = await console.client.post(
        f"/admin/console/users/{user_id}/role",
        json={"role": "citizen", "confirm": True},
        headers=headers,
    )
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_an_administrator_cannot_be_managed_from_here(console) -> None:
    headers = _bearer(console.admin)
    self_id = console.admin["user"]["id"]
    other_id = console.other_admin["user"]["id"]
    themselves = await console.client.post(
        f"/admin/console/users/{self_id}/suspend", json={"reason": "by accident", "confirm": True}, headers=headers
    )
    assert themselves.status_code == 409
    another = await console.client.post(
        f"/admin/console/users/{other_id}/suspend", json={"reason": "a coup attempt", "confirm": True}, headers=headers
    )
    assert another.status_code == 403
    assert (await console.client.get("/auth/me", headers=_bearer(console.other_admin))).status_code == 200
    missing = await console.client.post(
        f"/admin/console/users/{uuid.uuid4()}/revoke-sessions", json={"confirm": True}, headers=headers
    )
    assert missing.status_code == 404


# -------------------------------------------------------------- retention


async def _age(session_id: uuid.UUID, days: int) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE chat_messages SET created_at = :at WHERE session_id = :id"),
            {"at": stamp, "id": session_id},
        )
        await session.execute(
            text("UPDATE chat_sessions SET created_at = :at WHERE id = :id"),
            {"at": stamp, "id": session_id},
        )
        await session.commit()


@pytest.mark.asyncio
async def test_periods_have_floors_and_default_to_keeping_everything(console) -> None:
    headers = _bearer(console.admin)
    state = (await console.client.get("/admin/console/retention", headers=headers)).json()
    assert all(item["days"] is None for item in state["categories"])
    too_short = await console.client.put(
        "/admin/console/retention/audit_logs", json={"days": 30}, headers=headers
    )
    assert too_short.status_code == 422
    unknown = await console.client.put(
        "/admin/console/retention/everything", json={"days": 30}, headers=headers
    )
    assert unknown.status_code == 404
    accepted = await console.client.put(
        "/admin/console/retention/chat_history", json={"days": 30}, headers=headers
    )
    assert accepted.status_code == 200
    rows = await _audit(console.admin, "admin.retention.policy")
    assert rows[-1].metadata_ == {"category": "chat_history", "before": None, "after": 30}


@pytest.mark.asyncio
async def test_a_dry_run_counts_and_deletes_nothing(console) -> None:
    headers = _bearer(console.admin)
    old = await _answer(console.citizen)
    await _age(old.session_id, 90)
    await console.client.put("/admin/console/retention/chat_history", json={"days": 30}, headers=headers)
    run = await console.client.post("/admin/console/retention/dry-run", headers=headers)
    assert run.status_code == 201
    assert run.json()["counts"]["chat_history"] >= 1
    async with AsyncSessionLocal() as session:
        assert await session.get(ChatSession, old.session_id) is not None


@pytest.mark.asyncio
async def test_a_purge_deletes_what_the_dry_run_showed_and_nothing_else(console) -> None:
    headers = _bearer(console.admin)
    old = await _answer(console.citizen)
    await _age(old.session_id, 90)
    recent = await _answer(console.citizen)
    case_id = await _police_case(console.officer)
    attached = await _answer(console.officer, case_id=case_id)
    await _age(attached.session_id, 90)

    await console.client.put("/admin/console/retention/chat_history", json={"days": 30}, headers=headers)
    run = (await console.client.post("/admin/console/retention/dry-run", headers=headers)).json()

    wrong_word = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "yes"},
        headers=headers,
    )
    assert wrong_word.status_code == 422

    done = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["deleted"]["chat_history"] >= 1

    async with AsyncSessionLocal() as session:
        assert await session.get(ChatSession, old.session_id) is None
        assert await session.get(ChatSession, recent.session_id) is not None
        assert await session.get(ChatSession, attached.session_id) is not None, (
            "a conversation attached to a case belongs to the case"
        )
    rows = await _audit(console.admin, "admin.retention.purge")
    assert rows[-1].metadata_["deleted"]["chat_history"] >= 1

    reused = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=headers,
    )
    assert reused.status_code == 409


@pytest.mark.asyncio
async def test_a_purge_refuses_a_changed_policy_a_stale_preview_and_someone_elses(console) -> None:
    headers = _bearer(console.admin)
    await console.client.put("/admin/console/retention/chat_history", json={"days": 30}, headers=headers)

    run = (await console.client.post("/admin/console/retention/dry-run", headers=headers)).json()
    others = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=_bearer(console.other_admin),
    )
    assert others.status_code == 409

    await console.client.put("/admin/console/retention/chat_history", json={"days": 7}, headers=headers)
    changed = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=headers,
    )
    assert changed.status_code == 409
    assert "changed" in changed.json()["detail"]

    run = (await console.client.post("/admin/console/retention/dry-run", headers=headers)).json()
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE retention_runs SET created_at = now() - interval '1 hour' WHERE id = :id"),
            {"id": uuid.UUID(run["id"])},
        )
        await session.commit()
    stale = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=headers,
    )
    assert stale.status_code == 409
    assert "expired" in stale.json()["detail"]


@pytest.mark.asyncio
async def test_a_job_still_running_is_never_purged(console) -> None:
    headers = _bearer(console.admin)
    owner = uuid.UUID(console.citizen["user"]["id"])
    async with AsyncSessionLocal() as session:
        finished = Job(user_id=owner, type=JobType.DEEP_REVIEW, status=JobStatus.SUCCEEDED, progress=100,
                       idempotency_key=uuid.uuid4().hex, payload={})
        running = Job(user_id=owner, type=JobType.DEEP_REVIEW, status=JobStatus.RUNNING, progress=10,
                      idempotency_key=uuid.uuid4().hex, payload={})
        session.add_all([finished, running])
        await session.commit()
        await session.execute(
            text("UPDATE jobs SET updated_at = now() - interval '90 days' WHERE id IN (:a, :b)"),
            {"a": finished.id, "b": running.id},
        )
        await session.commit()
        finished_id, running_id = finished.id, running.id
    await console.client.put("/admin/console/retention/job_records", json={"days": 30}, headers=headers)
    run = (await console.client.post("/admin/console/retention/dry-run", headers=headers)).json()
    await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=headers,
    )
    async with AsyncSessionLocal() as session:
        assert await session.get(Job, finished_id) is None
        assert await session.get(Job, running_id) is not None


async def _old_closed_case(owner: dict) -> SimpleNamespace:
    async with AsyncSessionLocal() as session:
        case = Case(
            owner_id=uuid.UUID(owner["user"]["id"]),
            title="closed",
            role_type=CaseRoleType.POLICE,
            status="closed",
        )
        session.add(case)
        await session.flush()
        stored = StorageObject(
            bucket="legal-rag-police",
            object_key=f"cases/{case.id}/documents/{uuid.uuid4()}/a.txt",
            namespace=StorageNamespace.POLICE_CASE,
            owner_id=uuid.UUID(owner["user"]["id"]),
            case_id=case.id,
            original_filename="a.txt",
            content_type="text/plain",
            file_size=1,
            sha256="a" * 64,
        )
        session.add(stored)
        await session.flush()
        chat = ChatSession(user_id=uuid.UUID(owner["user"]["id"]), case_id=case.id, title="t")
        session.add(chat)
        await session.commit()
        await session.execute(
            text("UPDATE cases SET created_at = now() - interval '800 days' WHERE id = :id"),
            {"id": case.id},
        )
        await session.commit()
        return SimpleNamespace(case=case.id, stored=stored.id, key=stored.object_key, chat=chat.id)


class _FakeS3:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_object(self, Bucket: str, Key: str) -> None:
        self.deleted.append(Key)


@pytest.mark.asyncio
async def test_a_closed_case_goes_from_every_store(console, monkeypatch) -> None:
    headers = _bearer(console.admin)
    old = await _old_closed_case(console.officer)
    s3 = _FakeS3()
    monkeypatch.setattr("app.services.admin_retention.create_s3_client", lambda: s3)
    await console.client.put("/admin/console/retention/closed_cases", json={"days": 365}, headers=headers)
    run = (await console.client.post("/admin/console/retention/dry-run", headers=headers)).json()
    assert run["counts"]["closed_cases"] >= 1
    assert await _case_exists(old.case), "a dry run deletes nothing"

    done = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert old.key in s3.deleted
    assert console.fake.deleted, "indexed passages must go from the vector store"
    assert not await _case_exists(old.case)
    async with AsyncSessionLocal() as session:
        assert await session.get(StorageObject, old.stored) is None
        assert await session.get(ChatSession, old.chat) is None


async def _case_exists(case_id: uuid.UUID) -> bool:
    async with AsyncSessionLocal() as session:
        return await session.get(Case, case_id) is not None


@pytest.mark.asyncio
async def test_a_case_that_cannot_be_erased_everywhere_stays_for_the_next_run(console, monkeypatch) -> None:
    """Deleting the row first would orphan privileged files with nothing pointing at them."""
    headers = _bearer(console.admin)
    old = await _old_closed_case(console.officer)
    monkeypatch.setattr("app.services.admin_retention.create_s3_client", lambda: _FakeS3())
    await console.client.put("/admin/console/retention/closed_cases", json={"days": 365}, headers=headers)
    run = (await console.client.post("/admin/console/retention/dry-run", headers=headers)).json()
    console.fake.broken = True
    done = await console.client.post(
        "/admin/console/retention/purge",
        json={"dry_run_id": run["id"], "confirmation": "PURGE"},
        headers=headers,
    )
    assert done.status_code == 200
    assert done.json()["deleted"]["closed_cases_failed"] >= 1
    assert await _case_exists(old.case)


# ----------------------------------------------------------------- models


@pytest.mark.asyncio
async def test_prompts_are_fingerprinted_and_the_configuration_is_shown(console) -> None:
    from app.agents.prompt_registry import registered_prompt_names

    response = await console.client.get("/admin/console/models", headers=_bearer(console.admin))
    assert response.status_code == 200
    body = response.json()
    assert {row["name"] for row in body["prompts"]} == set(registered_prompt_names())
    assert all(re.fullmatch(r"[0-9a-f]{12}", row["fingerprint"]) for row in body["prompts"])
    assert body["generation"]["model"] == settings.ollama_model


@pytest.mark.asyncio
async def test_two_stored_runs_compare_side_by_side(console, tmp_path, monkeypatch) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    for name, value, prompt in (("answers-a", 0.8, "aaa"), ("answers-b", 0.9, "bbb")):
        (root / f"{name}.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-09-01T00:00:00+00:00",
                    "golden_set": "golden_set_v3.json",
                    "measurement_config": {
                        "collection": "global_legal_corpus_v4",
                        "generation_model": "m",
                        "prompt_versions": {"reasoning": prompt},
                    },
                    "metrics": {"overall": {"abstention_correct": value}},
                    "rows": [{"answer": USER_TEXT, "citations": 1, "abstained": False}],
                }
            )
        )
    monkeypatch.setattr(settings, "evaluation_evidence_root", str(root))
    headers = _bearer(console.admin)
    listed = await console.client.get("/admin/console/evaluations", headers=headers)
    assert {run["id"] for run in listed.json()["runs"]} == {"answers-a", "answers-b"}
    assert USER_TEXT not in listed.text

    compared = await console.client.get(
        "/admin/console/evaluations/compare?a=answers-a&b=answers-b", headers=headers
    )
    assert compared.status_code == 200
    body = compared.json()
    row = next(item for item in body["metrics"] if item["metric"] == "abstention_correct")
    assert row["better"] == "b"
    assert body["prompts"][0]["changed"] is True
    assert USER_TEXT not in compared.text

    traversal = await console.client.get(
        "/admin/console/evaluations/compare?a=../../etc/passwd&b=answers-b", headers=headers
    )
    assert traversal.status_code == 404


# ---------------------------------------------------------- quality, audit


@pytest.mark.asyncio
async def test_the_dashboard_aggregates_live_numbers_without_text(console) -> None:
    owner = uuid.UUID(console.citizen["user"]["id"])
    answer = await _answer(console.citizen, citations=[_citation("c9", PUBLIC_TEXT)])
    async with AsyncSessionLocal() as session:
        session.add(
            AuditLog(
                user_id=owner,
                action="chat.query",
                resource_type="chat_session",
                resource_id=answer.session_id,
                metadata_={
                    "evidence_strength": "insufficient",
                    "timings_ms": {"api_total_ms": 1234.0},
                    "pipeline_metrics": [
                        {"stage": "verification", "outputs": {"unsupported_claim_count": 2}}
                    ],
                    "query": USER_TEXT,
                },
            )
        )
        session.add(
            Job(
                user_id=owner,
                type=JobType.DEEP_REVIEW,
                status=JobStatus.SUCCEEDED,
                progress=100,
                idempotency_key=uuid.uuid4().hex,
                payload={"query": USER_TEXT},
                result={"answer": EVIDENCE_TEXT, "evidence_strength": "strong", "pipeline_metrics": []},
                started_at=datetime.now(timezone.utc) - timedelta(seconds=60),
                completed_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    response = await console.client.get("/admin/console/quality?days=7", headers=_bearer(console.admin))
    assert response.status_code == 200, response.text
    assert USER_TEXT not in response.text and EVIDENCE_TEXT not in response.text
    live = response.json()["live"]
    assert live["totals"]["answers"] >= 2
    assert live["totals"]["unsupported_claims"] >= 2
    assert live["totals"]["citation_coverage"] > 0
    assert live["totals"]["feedback_down"] >= 1
    assert live["series"], "at least today"
    assert response.json()["stored"]["answers"], "the repository holds recorded runs"


@pytest.mark.asyncio
async def test_the_audit_log_filters_pages_and_shows_no_user_text(console) -> None:
    headers = _bearer(console.admin)
    actor = uuid.UUID(console.citizen["user"]["id"])
    resource = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        for _ in range(3):
            session.add(
                AuditLog(
                    user_id=actor,
                    action="chat.query",
                    resource_type="chat_session",
                    resource_id=resource,
                    metadata_={"agent_trace": [{"details": {"query": USER_TEXT}}], "kept": 1},
                )
            )
        await session.commit()

    by_resource = await console.client.get(
        f"/admin/console/audit?resource_id={resource}&page_size=2", headers=headers
    )
    assert by_resource.status_code == 200
    body = by_resource.json()
    assert body["total"] == 3 and len(body["events"]) == 2
    assert body["events"][0]["metadata"] == {"kept": 1}
    assert USER_TEXT not in by_resource.text

    second_page = await console.client.get(
        f"/admin/console/audit?resource_id={resource}&page_size=2&page=2", headers=headers
    )
    assert len(second_page.json()["events"]) == 1

    by_actor = await console.client.get(
        f"/admin/console/audit?actor={console.citizen['user']['email']}&action=chat.", headers=headers
    )
    assert by_actor.json()["total"] >= 3
    none = await console.client.get(
        f"/admin/console/audit?resource_id={resource}&action=admin.", headers=headers
    )
    assert none.json()["total"] == 0
    window = await console.client.get(
        f"/admin/console/audit?resource_id={resource}&until=2000-01-01T00:00:00Z", headers=headers
    )
    assert window.json()["total"] == 0
    assert "chat.query" in body["actions"]


@pytest.mark.asyncio
async def test_health_reports_the_queue_as_metadata_only(console, monkeypatch) -> None:
    async def report():
        return True, {"status": "ready", "dependencies": {}, "inference": {}}

    monkeypatch.setattr("app.routers.admin_tools.readiness_report", report)
    owner = uuid.UUID(console.citizen["user"]["id"])
    async with AsyncSessionLocal() as session:
        session.add(
            Job(user_id=owner, type=JobType.DEEP_REVIEW, status=JobStatus.QUEUED, progress=0,
                idempotency_key=uuid.uuid4().hex, payload={"query": USER_TEXT})
        )
        await session.commit()
    response = await console.client.get("/admin/console/health", headers=_bearer(console.admin))
    assert response.status_code == 200, response.text
    assert USER_TEXT not in response.text
    body = response.json()
    assert body["jobs"]["by_status"]["queued"] >= 1
    assert body["jobs"]["oldest_queued_at"]
    assert body["schema_revision"]
