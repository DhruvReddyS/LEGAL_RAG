"""PLAT-05: consent, export, erasure and retention.

The erasure test uses the real stores: PostgreSQL, Qdrant and versioned object
storage, each inspected directly afterwards. Being told it is gone by the code
that did the deleting would prove nothing.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client import models
from sqlalchemy import func, select, text, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.qdrant import create_qdrant_client
from app.ingestion.init_qdrant import POLICE_CASE_DATA
from app.models import (
    AuditLog,
    Case,
    CaseDocument,
    ChatMessage,
    ChatSession,
    ChatSessionMeta,
    ConsentRecord,
    ErasureReceipt,
    Feedback,
    GeneratedDocument,
    Job,
    JobEvent,
    RevokedRefreshToken,
    StorageNamespace,
    StorageObject,
    User,
    UserSecurity,
    UserSession,
)
from app.models.enums import CaseRoleType, ChatMessageRole, FeedbackRating, JobStatus, JobType
from app.services import privacy
from app.services.privacy_notice import PRIVACY_NOTICE_VERSION
from app.services.rate_limit import user_rate_limiter
from app.services.storage import create_s3_client, ensure_storage_buckets
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = [pytest.mark.integration, pytest.mark.object_storage]

PASSWORD = "Original-Password-1234"
SENSITIVE_QUESTION = "my husband beats me and I want to leave quietly"


@pytest.fixture(autouse=True)
async def _clean_limiter():
    await user_rate_limiter.clear()
    yield
    await user_rate_limiter.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _account(role: str = "citizen") -> dict:
    email = unique_email(f"privacy-{role}")
    body = await provision_test_user(name="Asha Rao", email=email, password=PASSWORD, role=role)
    return {"email": email, "id": uuid.UUID(body["user"]["id"]), "token": body["access_token"]}


# --------------------------------------------------------------------- the notice


async def test_the_notice_is_public_and_itemises_data_and_purposes() -> None:
    async with _client() as client:
        response = await client.get("/account/privacy")
    assert response.status_code == 200
    body = response.json()
    assert body["notice"]["version"] == PRIVACY_NOTICE_VERSION
    assert body["notice"]["personal_data"] and body["notice"]["purposes"]


async def test_grievance_contact_shows_a_clear_unset_state(monkeypatch) -> None:
    monkeypatch.setattr(settings, "grievance_officer_name", "")
    monkeypatch.setattr(settings, "grievance_officer_email", "")
    async with _client() as client:
        unset = (await client.get("/account/privacy")).json()["grievance"]
    assert unset["configured"] is False and unset["name"] is None

    monkeypatch.setattr(settings, "grievance_officer_name", "R. Iyer")
    monkeypatch.setattr(settings, "grievance_officer_email", "grievance@example.com")
    async with _client() as client:
        configured = (await client.get("/account/privacy")).json()["grievance"]
    assert configured["configured"] is True and configured["email"] == "grievance@example.com"


async def test_a_name_with_no_way_to_reach_them_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "grievance_officer_name", "R. Iyer")
    assert privacy.grievance_contact()["configured"] is False


# ------------------------------------------------------------------------ consent


async def _register(client: AsyncClient, **extra):
    return await client.post(
        "/auth/register",
        json={"name": "Asha Rao", "email": unique_email("consent"), "password": PASSWORD, "role": "citizen", **extra},
    )


async def test_registering_with_consent_records_the_version() -> None:
    async with _client() as client:
        response = await _register(client, consent_notice_version=PRIVACY_NOTICE_VERSION)
        assert response.status_code == 201, response.text
        token = response.json()["access_token"]
        state = (await client.get("/account/consent", headers=_bearer(token))).json()
    assert state["required"] is False
    assert state["accepted_version"] == PRIVACY_NOTICE_VERSION


async def test_consent_to_an_old_version_is_not_consent() -> None:
    async with _client() as client:
        at_registration = await _register(client, consent_notice_version="1999-01-01")
        assert at_registration.status_code == 409
        account = await _account()
        later = await client.post(
            "/account/consent", json={"notice_version": "1999-01-01"}, headers=_bearer(account["token"])
        )
        assert later.status_code == 409
        state = (await client.get("/account/consent", headers=_bearer(account["token"]))).json()
    assert state["required"] is True


async def test_a_changed_notice_asks_everyone_again(monkeypatch) -> None:
    account = await _account()
    async with _client() as client:
        await client.post(
            "/account/consent", json={"notice_version": PRIVACY_NOTICE_VERSION}, headers=_bearer(account["token"])
        )
        monkeypatch.setattr(privacy, "PRIVACY_NOTICE_VERSION", "2099-01-01")
        state = (await client.get("/account/consent", headers=_bearer(account["token"]))).json()
    assert state["required"] is True
    assert state["accepted_version"] == PRIVACY_NOTICE_VERSION


async def test_when_enforced_the_product_waits_for_consent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "consent_enforcement", "on")
    account = await _account()
    headers = _bearer(account["token"])
    async with _client() as client:
        blocked = await client.get("/chat/sessions", headers=headers)
        assert (blocked.status_code, blocked.json()["detail"]) == (403, "consent_required")

        # The way out has to stay open.
        assert (await client.get("/account/status", headers=headers)).status_code == 200
        accepted = await client.post(
            "/account/consent", json={"notice_version": PRIVACY_NOTICE_VERSION}, headers=headers
        )
        assert accepted.status_code == 200
        assert (await client.get("/chat/sessions", headers=headers)).status_code == 200

        withdrawn = await client.post("/account/consent/withdraw", headers=headers)
        assert withdrawn.json()["required"] is True
        assert (await client.get("/chat/sessions", headers=headers)).status_code == 403


def test_enforcement_defaults_on_outside_development() -> None:
    from app.core.config import Settings

    assert Settings(_env_file=None, app_env="production", cookie_secure=True).consent_is_enforced is True
    assert Settings(_env_file=None, app_env="development").consent_is_enforced is False


# ------------------------------------------------------------------------- export


async def _seed_conversation(user_id: uuid.UUID, question: str = SENSITIVE_QUESTION) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=user_id, title=question[:120])
        session.add(chat)
        await session.flush()
        session.add(ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content=question, citations=[]))
        answer = ChatMessage(session_id=chat.id, role=ChatMessageRole.ASSISTANT, content="An answer.", citations=[])
        session.add(answer)
        await session.flush()
        session.add(Feedback(message_id=answer.id, user_id=user_id, rating=FeedbackRating.DOWN, correction_text="wrong"))
        session.add(ChatSessionMeta(session_id=chat.id, user_id=user_id, matter="Separation"))
        await session.commit()
        return chat.id


async def test_export_holds_my_data_and_nobody_elses_and_no_credentials() -> None:
    mine, other = await _account(), await _account()
    await _seed_conversation(mine["id"])
    await _seed_conversation(other["id"], "a question that belongs to someone else")
    async with _client() as client:
        response = await client.post(
            "/account/export", json={"password": PASSWORD}, headers=_bearer(mine["token"])
        )
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    exported = json.loads(response.text)
    assert exported["account"]["email"] == mine["email"]
    assert exported["conversations"][0]["messages"][0]["content"] == SENSITIVE_QUESTION
    assert exported["conversations"][0]["matter"] == "Separation"
    assert exported["feedback"][0]["correction_text"] == "wrong"
    assert "someone else" not in response.text
    assert "hashed_password" not in response.text
    assert "totp_secret" not in response.text


async def test_export_needs_the_password_and_is_not_a_get() -> None:
    account = await _account()
    async with _client() as client:
        wrong = await client.post(
            "/account/export", json={"password": "Not-The-Password-000"}, headers=_bearer(account["token"])
        )
        assert wrong.status_code == 403
        assert (await client.get("/account/export", headers=_bearer(account["token"]))).status_code == 405
        assert (await client.post("/account/export", json={"password": PASSWORD})).status_code == 401


# ------------------------------------------------------------------------ erasure


async def _seed_police_matter(user_id: uuid.UUID, marker: str) -> dict:
    """A case with evidence in every store, including old file versions."""
    await ensure_storage_buckets()
    s3 = create_s3_client()
    case_id = uuid.uuid4()
    bucket = settings.s3_police_bucket
    stored_key = f"cases/{case_id}/documents/{uuid.uuid4()}/statement.txt"
    # A second version, then a delete marker over a third object, and a presigned
    # upload that was never registered in PostgreSQL at all.
    s3.put_object(Bucket=bucket, Key=stored_key, Body=f"first draft {marker}".encode())
    s3.put_object(Bucket=bucket, Key=stored_key, Body=f"second draft {marker}".encode())
    deleted_key = f"cases/{case_id}/documents/{uuid.uuid4()}/removed.txt"
    s3.put_object(Bucket=bucket, Key=deleted_key, Body=f"removed {marker}".encode())
    s3.delete_object(Bucket=bucket, Key=deleted_key)
    orphan_key = f"cases/{case_id}/pending/{uuid.uuid4()}/never-registered.txt"
    s3.put_object(Bucket=bucket, Key=orphan_key, Body=f"orphan {marker}".encode())

    async with AsyncSessionLocal() as session:
        session.add(Case(id=case_id, owner_id=user_id, role_type=CaseRoleType.POLICE, title=f"Matter {marker}", status="open"))
        await session.flush()
        session.add(
            StorageObject(
                bucket=bucket,
                object_key=stored_key,
                namespace=StorageNamespace.POLICE_CASE,
                owner_id=user_id,
                case_id=case_id,
                original_filename="statement.txt",
                content_type="text/plain",
                file_size=10,
                sha256="0" * 64,
            )
        )
        session.add(CaseDocument(case_id=case_id, file_url=stored_key, doc_type="statement", ocr_text=f"ocr {marker}"))
        session.add(GeneratedDocument(case_id=case_id, doc_type="fir", version=1, content={"text": marker}, status="draft"))
        await session.commit()

    qdrant = create_qdrant_client()
    try:
        await qdrant.upsert(
            collection_name=POLICE_CASE_DATA,
            points=[
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector={"dense": [0.1] * settings.embedding_dimension},
                    payload={"case_id": str(case_id), "text": f"private passage {marker}"},
                )
            ],
            wait=True,
        )
    finally:
        await qdrant.close()
    return {"case_id": case_id, "bucket": bucket}


async def _vectors_for(case_id: uuid.UUID) -> int:
    qdrant = create_qdrant_client()
    try:
        result = await qdrant.count(
            POLICE_CASE_DATA,
            count_filter=models.Filter(
                must=[models.FieldCondition(key="case_id", match=models.MatchValue(value=str(case_id)))]
            ),
            exact=True,
        )
        return result.count
    finally:
        await qdrant.close()


def _versions_under(bucket: str, prefix: str) -> list[str]:
    listing = create_s3_client().list_object_versions(Bucket=bucket, Prefix=prefix)
    return [
        item["Key"]
        for group in ("Versions", "DeleteMarkers")
        for item in listing.get(group, [])
    ]


async def _row_count(model, *conditions) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


async def test_erasure_removes_the_person_from_every_store() -> None:
    subject, bystander = await _account("police"), await _account("police")
    marker = f"marker-{uuid.uuid4().hex}"
    # Unique per run: the integration database persists between runs.
    question = f"{SENSITIVE_QUESTION} {marker}"
    matter = await _seed_police_matter(subject["id"], marker)
    theirs = await _seed_police_matter(bystander["id"], f"bystander-{marker}")
    chat_id = await _seed_conversation(subject["id"], question)
    keep_chat = await _seed_conversation(bystander["id"], "the bystander asked this")

    async with AsyncSessionLocal() as session:
        job = Job(
            user_id=subject["id"],
            type=JobType.DEEP_REVIEW,
            status=JobStatus.SUCCEEDED,
            progress=100,
            idempotency_key=f"erasure-{uuid.uuid4().hex}",
            payload={"query": question, "chat_session_id": str(chat_id)},
            result={"answer": question},
            max_attempts=3,
        )
        session.add(job)
        await session.flush()
        job_id = job.id
        session.add(JobEvent(job_id=job.id, event_type="stage", stage="x", progress=10, data={"query": question}))
        session.add(
            AuditLog(
                user_id=subject["id"],
                action="chat.query",
                resource_type="chat_session",
                resource_id=chat_id,
                metadata_={"agent_trace": [{"query": question}], "email": subject["email"]},
            )
        )
        session.add(
            AuditLog(
                user_id=None,
                action="admin.user_created",
                resource_type="user",
                resource_id=subject["id"],
                metadata_={"email": subject["email"]},
            )
        )
        await session.commit()

    assert await _vectors_for(matter["case_id"]) == 1
    prefix = f"cases/{matter['case_id']}/"
    assert len(_versions_under(matter["bucket"], prefix)) == 5

    async with _client() as client:
        erased = await client.post(
            "/account/erase",
            json={"password": PASSWORD, "confirm": "ERASE MY ACCOUNT"},
            headers=_bearer(subject["token"]),
        )
        assert erased.status_code == 200, erased.text
        body = erased.json()

        # The credential is dead.
        assert (await client.get("/auth/me", headers=_bearer(subject["token"]))).status_code == 401
        relogin = await client.post("/auth/login", json={"email": subject["email"], "password": PASSWORD})
        assert relogin.status_code == 401

    # Qdrant, directly.
    assert await _vectors_for(matter["case_id"]) == 0
    # Object storage, directly, including old versions and delete markers.
    assert _versions_under(matter["bucket"], prefix) == []

    # PostgreSQL, table by table.
    uid = subject["id"]
    case_id = matter["case_id"]
    assert await _row_count(User, User.id == uid) == 0
    assert await _row_count(Case, Case.owner_id == uid) == 0
    assert await _row_count(CaseDocument, CaseDocument.case_id == case_id) == 0
    assert await _row_count(GeneratedDocument, GeneratedDocument.case_id == case_id) == 0
    assert await _row_count(StorageObject, StorageObject.case_id == case_id) == 0
    assert await _row_count(ChatSession, ChatSession.user_id == uid) == 0
    assert await _row_count(ChatMessage, ChatMessage.session_id == chat_id) == 0
    assert await _row_count(Feedback, Feedback.user_id == uid) == 0
    assert await _row_count(ChatSessionMeta, ChatSessionMeta.user_id == uid) == 0
    assert await _row_count(Job, Job.user_id == uid) == 0
    assert await _row_count(JobEvent, JobEvent.job_id == job_id) == 0
    assert await _row_count(ConsentRecord, ConsentRecord.user_id == uid) == 0
    assert await _row_count(UserSession, UserSession.user_id == uid) == 0
    assert await _row_count(UserSecurity, UserSecurity.user_id == uid) == 0
    assert await _row_count(RevokedRefreshToken, RevokedRefreshToken.user_id == uid) == 0
    assert await _row_count(AuditLog, AuditLog.user_id == uid) == 0
    assert await _row_count(AuditLog, AuditLog.resource_id.in_([uid, chat_id, job_id, case_id])) == 0

    # Nothing anywhere in the audit log still says who it was or what they asked.
    async with AsyncSessionLocal() as session:
        for needle in (subject["email"], question, str(uid)):
            hits = await session.scalar(
                text("select count(*) from audit_logs where metadata::text like :needle"),
                {"needle": f"%{needle}%"},
            )
            assert hits == 0, needle
        receipt = await session.get(ErasureReceipt, uuid.UUID(body["receipt_id"]))
    assert receipt is not None
    assert subject["email"] not in json.dumps(receipt.counts)
    assert body["counts"]["vectors"] == 1
    assert body["counts"]["file_versions"] == 5
    assert body["counts"]["messages"] == 2

    # The bystander lost nothing.
    assert await _vectors_for(theirs["case_id"]) == 1
    assert len(_versions_under(theirs["bucket"], f"cases/{theirs['case_id']}/")) == 5
    assert await _row_count(ChatMessage, ChatMessage.session_id == keep_chat) == 2
    async with _client() as client:
        assert (await client.get("/auth/me", headers=_bearer(bystander["token"]))).status_code == 200


async def test_erasure_needs_password_and_the_exact_phrase() -> None:
    account = await _account()
    async with _client() as client:
        no_phrase = await client.post(
            "/account/erase", json={"password": PASSWORD, "confirm": "yes"}, headers=_bearer(account["token"])
        )
        wrong_password = await client.post(
            "/account/erase",
            json={"password": "Not-The-Password-000", "confirm": "ERASE MY ACCOUNT"},
            headers=_bearer(account["token"]),
        )
        anonymous = await client.post(
            "/account/erase", json={"password": PASSWORD, "confirm": "ERASE MY ACCOUNT"}
        )
    assert (no_phrase.status_code, wrong_password.status_code, anonymous.status_code) == (422, 403, 401)
    assert await _row_count(User, User.id == account["id"]) == 1


async def test_a_store_being_down_keeps_the_account_so_it_can_be_retried(monkeypatch) -> None:
    subject = await _account("police")
    matter = await _seed_police_matter(subject["id"], f"marker-{uuid.uuid4().hex}")

    def unreachable():
        raise ConnectionError("vector store at 10.0.0.3 is down")

    monkeypatch.setattr(privacy, "create_qdrant_client", unreachable)
    async with _client() as client:
        failed = await client.post(
            "/account/erase",
            json={"password": PASSWORD, "confirm": "ERASE MY ACCOUNT"},
            headers=_bearer(subject["token"]),
        )
        assert failed.status_code == 503
        assert "10.0.0.3" not in failed.text
        assert (await client.get("/auth/me", headers=_bearer(subject["token"]))).status_code == 200
        assert await _row_count(Case, Case.id == matter["case_id"]) == 1

        monkeypatch.undo()
        retried = await client.post(
            "/account/erase",
            json={"password": PASSWORD, "confirm": "ERASE MY ACCOUNT"},
            headers=_bearer(subject["token"]),
        )
        assert retried.status_code == 200, retried.text
    assert await _vectors_for(matter["case_id"]) == 0
    assert _versions_under(matter["bucket"], f"cases/{matter['case_id']}/") == []


async def test_the_only_administrator_cannot_erase_themselves() -> None:
    admin = await _account("admin")
    async with AsyncSessionLocal() as session:
        # Every other administrator left behind by other tests stands aside.
        others = (
            await session.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True), User.id != admin["id"]))
        ).all()
        await session.execute(update(User).where(User.id.in_(others)).values(is_active=False))
        await session.commit()
    try:
        async with _client() as client:
            refused = await client.post(
                "/account/erase",
                json={"password": PASSWORD, "confirm": "ERASE MY ACCOUNT"},
                headers=_bearer(admin["token"]),
            )
        assert refused.status_code == 409
        assert await _row_count(User, User.id == admin["id"]) == 1
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(update(User).where(User.id.in_(others)).values(is_active=True))
            await session.commit()


async def test_an_administrator_can_erase_for_someone_locked_out_without_reading_it() -> None:
    admin, subject, citizen = await _account("admin"), await _account(), await _account()
    await _seed_conversation(subject["id"])
    async with _client() as client:
        body = {
            "email": subject["email"],
            "admin_password": PASSWORD,
            "confirm": "ERASE THIS ACCOUNT",
        }
        assert (await client.post("/account/admin/erase", json=body, headers=_bearer(citizen["token"]))).status_code == 403
        wrong = await client.post(
            "/account/admin/erase", json={**body, "admin_password": "Not-The-Password-000"}, headers=_bearer(admin["token"])
        )
        assert wrong.status_code == 403
        done = await client.post("/account/admin/erase", json=body, headers=_bearer(admin["token"]))
        assert done.status_code == 200, done.text
    assert SENSITIVE_QUESTION not in done.text
    assert await _row_count(User, User.id == subject["id"]) == 0


# ------------------------------------------------------- deleting one conversation


async def test_deleting_a_conversation_takes_its_traces_with_it() -> None:
    account = await _account()
    chat_id = await _seed_conversation(account["id"])
    async with AsyncSessionLocal() as session:
        job = Job(
            user_id=account["id"],
            type=JobType.DEEP_REVIEW,
            status=JobStatus.SUCCEEDED,
            progress=100,
            idempotency_key=f"delete-{uuid.uuid4().hex}",
            payload={"query": SENSITIVE_QUESTION, "chat_session_id": str(chat_id)},
            result={"answer": "x"},
            max_attempts=3,
        )
        session.add(job)
        await session.flush()
        job_id = job.id
        session.add(
            AuditLog(
                user_id=account["id"],
                action="chat.query",
                resource_type="chat_session",
                resource_id=chat_id,
                metadata_={"agent_trace": [{"query": SENSITIVE_QUESTION}]},
            )
        )
        await session.commit()
    async with _client() as client:
        deleted = await client.delete(f"/chat/sessions/{chat_id}", headers=_bearer(account["token"]))
    assert deleted.status_code == 204
    assert await _row_count(Job, Job.id == job_id) == 0
    async with AsyncSessionLocal() as session:
        hits = await session.scalar(
            text("select count(*) from audit_logs where metadata::text like :needle"),
            {"needle": f"%{chat_id}%"},
        )
        rows = await session.scalars(select(AuditLog).where(AuditLog.resource_id == chat_id))
        assert all(SENSITIVE_QUESTION not in str(row.metadata_) for row in rows.all())
    assert hits == 0


# ---------------------------------------------------------------------- retention


async def _age_conversation(chat_id: uuid.UUID, days: int) -> None:
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        await session.execute(update(ChatSession).where(ChatSession.id == chat_id).values(created_at=moment))
        await session.execute(update(ChatMessage).where(ChatMessage.session_id == chat_id).values(created_at=moment))
        await session.commit()


async def test_retention_erases_only_what_is_past_its_period() -> None:
    account = await _account()
    old, recent = await _seed_conversation(account["id"]), await _seed_conversation(account["id"])
    await _age_conversation(old, 40)
    await _age_conversation(recent, 5)
    async with AsyncSessionLocal() as session:
        erased = await privacy.apply_retention(session, days=30)
        await session.commit()
    assert erased >= 1
    assert await _row_count(ChatSession, ChatSession.id == old) == 0
    assert await _row_count(ChatSession, ChatSession.id == recent) == 1


async def test_a_retention_period_of_zero_keeps_everything() -> None:
    account = await _account()
    old = await _seed_conversation(account["id"])
    await _age_conversation(old, 4000)
    async with AsyncSessionLocal() as session:
        assert await privacy.apply_retention(session, days=0) == 0
        await session.commit()
    assert await _row_count(ChatSession, ChatSession.id == old) == 1


async def test_the_retention_setting_is_readable_by_administrators_and_nobody_else(monkeypatch) -> None:
    monkeypatch.setattr(settings, "chat_retention_days", 365)
    admin, citizen = await _account("admin"), await _account()
    async with _client() as client:
        forbidden = await client.get("/account/admin/retention", headers=_bearer(citizen["token"]))
        allowed = await client.get("/account/admin/retention", headers=_bearer(admin["token"]))
        public = await client.get("/account/privacy")
    assert forbidden.status_code == 403
    assert allowed.json()["chat_retention_days"] == 365
    assert public.json()["retention"]["chat_retention_days"] == 365
    assert privacy.retention_policy()["chats_kept_until_deleted"] is False
