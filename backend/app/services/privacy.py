"""Consent, data export, erasure and retention.

Erasure is ordered so a failure can be retried. Everything outside PostgreSQL
goes first: if Qdrant or object storage is down, the account still exists, the
person can try again, and nothing has been half-forgotten in a way that leaves
vectors behind with no row left to find them by. PostgreSQL commits last, in one
transaction.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from qdrant_client import models
from sqlalchemy import cast, delete, func, or_, select, String, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, POLICE_CASE_DATA
from app.models import (
    AuditLog,
    Case,
    CaseDocument,
    CaseNote,
    ChatMessage,
    ChatSession,
    ChatSessionMeta,
    ConsentRecord,
    ErasureReceipt,
    Feedback,
    GeneratedDocument,
    InvestigationFacts,
    Job,
    StorageNamespace,
    StorageObject,
    User,
    UserSession,
)
from app.models.advocate import AdvocateWorkProduct, MatterCalendarEvent
from app.models.citizen import CitizenDeadline
from app.models.corpus_lifecycle import LawChangeNotice
from app.models.enums import UserRole
from app.models.police import (
    PoliceComplianceRecord,
    PoliceCustodyEvent,
    PoliceDeadlineCompletion,
    PoliceDiaryEntry,
    PoliceEvidenceItem,
    PoliceOffenceAssessment,
    PoliceRemandPeriod,
    PoliceSearch,
    PoliceWitness,
)
from app.services.privacy_notice import PRIVACY_NOTICE_VERSION, notice_document
from app.services.storage import create_s3_client


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return value.value
    return value


def _row_dict(row: Any, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Every column of a row.

    From the table rather than a list written here, so a column added next year
    reaches the person's export without anyone remembering to add it.
    """
    return {
        column.name: _plain(getattr(row, column.key))
        for column in row.__table__.columns
        if column.name not in exclude
    }


# ------------------------------------------------------------------ the notice


def grievance_contact() -> dict[str, Any]:
    name = settings.grievance_officer_name.strip()
    email = settings.grievance_officer_email.strip()
    phone = settings.grievance_officer_phone.strip()
    address = settings.grievance_officer_address.strip()
    return {
        "configured": bool(name and (email or phone or address)),
        "name": name or None,
        "email": email or None,
        "phone": phone or None,
        "address": address or None,
    }


def retention_policy() -> dict[str, Any]:
    """The retention rule in force, for the notice and the admin console."""
    days = settings.chat_retention_days
    return {
        "chat_retention_days": days,
        "chats_kept_until_deleted": days == 0,
    }


def privacy_configuration() -> dict[str, Any]:
    return {
        "notice": notice_document(),
        "data_fiduciary": settings.data_fiduciary_name.strip() or None,
        "grievance": grievance_contact(),
        "retention": retention_policy(),
        "self_service_reset": settings.self_service_reset_available,
    }


# --------------------------------------------------------------------- consent


async def consent_state(session: AsyncSession, user: User) -> dict[str, Any]:
    latest = await session.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user.id)
        .order_by(ConsentRecord.accepted_at.desc())
        .limit(1)
    )
    current = (
        latest is not None
        and latest.notice_version == PRIVACY_NOTICE_VERSION
        and latest.withdrawn_at is None
    )
    return {
        "current_version": PRIVACY_NOTICE_VERSION,
        "accepted_version": latest.notice_version if latest else None,
        "accepted_at": latest.accepted_at if latest else None,
        "withdrawn_at": latest.withdrawn_at if latest else None,
        "required": not current,
    }


async def record_consent(
    session: AsyncSession, user_id: uuid.UUID, notice_version: str, *, source: str
) -> None:
    """Consent to anything but the current text is not consent to the current text."""
    if notice_version != PRIVACY_NOTICE_VERSION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The privacy notice has changed. Read the current version.",
        )
    session.add(ConsentRecord(user_id=user_id, notice_version=notice_version, source=source))
    session.add(
        AuditLog(
            user_id=user_id,
            action="privacy.consent_given",
            resource_type="user",
            resource_id=user_id,
            metadata_={"notice_version": notice_version, "source": source},
        )
    )


async def withdraw_consent(session: AsyncSession, user: User) -> None:
    await session.execute(
        update(ConsentRecord)
        .where(ConsentRecord.user_id == user.id, ConsentRecord.withdrawn_at.is_(None))
        .values(withdrawn_at=_utcnow())
    )
    session.add(
        AuditLog(
            user_id=user.id,
            action="privacy.consent_withdrawn",
            resource_type="user",
            resource_id=user.id,
            metadata_={},
        )
    )


# ---------------------------------------------------------------------- export


async def build_export(session: AsyncSession, user: User) -> dict[str, Any]:
    """Everything held about one person, in a form they can read and keep.

    Credentials are the one thing left out: hashes and an encrypted secret are
    of no use to the person and of real use to whoever gets hold of the file.
    """
    chats = list(
        (
            await session.scalars(
                select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.created_at)
            )
        ).all()
    )
    chat_ids = [chat.id for chat in chats]
    messages: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if chat_ids:
        for message in (
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id.in_(chat_ids))
                .order_by(ChatMessage.sequence)
            )
        ).all():
            messages.setdefault(message.session_id, []).append(_row_dict(message))
    meta = {
        row.session_id: row
        for row in (
            await session.scalars(select(ChatSessionMeta).where(ChatSessionMeta.user_id == user.id))
        ).all()
    }

    cases = list((await session.scalars(select(Case).where(Case.owner_id == user.id))).all())
    case_ids = [case.id for case in cases]

    async def rows_for_cases(model: Any) -> list[dict[str, Any]]:
        if not case_ids:
            return []
        rows = await session.scalars(select(model).where(model.case_id.in_(case_ids)))
        return [_row_dict(row) for row in rows.all()]

    storage = (
        await session.scalars(
            select(StorageObject).where(
                or_(
                    StorageObject.owner_id == user.id,
                    StorageObject.case_id.in_(case_ids) if case_ids else False,
                )
            )
        )
    ).all()
    audit = (
        await session.scalars(
            select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.timestamp)
        )
    ).all()

    return {
        "format": "corpusil-data-export",
        "format_version": 1,
        "generated_at": _utcnow().isoformat(),
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        "not_included": (
            "Your password hash, authenticator secret and recovery code hashes, which only "
            "exist to verify you. Uploaded files themselves: each is listed with its metadata "
            "and can be downloaded from the case it belongs to."
        ),
        "account": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role.value,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        },
        "consent": [
            _row_dict(row)
            for row in (
                await session.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id))
            ).all()
        ],
        "devices": [
            _row_dict(row)
            for row in (
                await session.scalars(select(UserSession).where(UserSession.user_id == user.id))
            ).all()
        ],
        "conversations": [
            {
                **_row_dict(chat),
                "pinned": bool(meta.get(chat.id) and meta[chat.id].pinned_at),
                "matter": meta[chat.id].matter if chat.id in meta else None,
                "messages": messages.get(chat.id, []),
            }
            for chat in chats
        ],
        "feedback": [
            _row_dict(row)
            for row in (await session.scalars(select(Feedback).where(Feedback.user_id == user.id))).all()
        ],
        "cases": [_row_dict(case) for case in cases],
        "case_documents": await rows_for_cases(CaseDocument),
        "case_notes": await rows_for_cases(CaseNote),
        "generated_documents": await rows_for_cases(GeneratedDocument),
        "investigation_facts": await rows_for_cases(InvestigationFacts),
        "police_searches": await rows_for_cases(PoliceSearch),
        "police_evidence": await rows_for_cases(PoliceEvidenceItem),
        "police_custody_events": await rows_for_cases(PoliceCustodyEvent),
        "police_witnesses": await rows_for_cases(PoliceWitness),
        "police_deadline_completions": await rows_for_cases(PoliceDeadlineCompletion),
        "police_compliance_records": await rows_for_cases(PoliceComplianceRecord),
        "police_offence_assessments": await rows_for_cases(PoliceOffenceAssessment),
        "police_remand_periods": await rows_for_cases(PoliceRemandPeriod),
        "police_diary": await rows_for_cases(PoliceDiaryEntry),
        "advocate_work": await rows_for_cases(AdvocateWorkProduct),
        "matter_calendar": await rows_for_cases(MatterCalendarEvent),
        "my_matter_deadlines": [
            _row_dict(row)
            for row in (
                await session.scalars(select(CitizenDeadline).where(CitizenDeadline.user_id == user.id))
            ).all()
        ],
        "law_change_notices": [
            _row_dict(row)
            for row in (
                await session.scalars(select(LawChangeNotice).where(LawChangeNotice.user_id == user.id))
            ).all()
        ],
        "stored_files": [_row_dict(row) for row in storage],
        "activity": [
            {
                "action": row.action,
                "resource_type": row.resource_type,
                "timestamp": row.timestamp.isoformat(),
            }
            for row in audit
        ],
    }


# ----------------------------------------------------------------- conversation


async def purge_conversation_traces(session: AsyncSession, session_ids: list[uuid.UUID]) -> None:
    """Remove what a conversation left behind outside its own tables.

    A Deep job's payload holds the question and its history, its events hold
    located sources, and audit rows hold agent traces. Deleting only the chat
    session left all of that in place while telling the person it was gone.
    """
    if not session_ids:
        return
    as_text = [str(item) for item in session_ids]
    jobs = await session.scalars(
        select(Job.id).where(Job.payload["chat_session_id"].astext.in_(as_text))
    )
    job_ids = list(jobs.all())
    if job_ids:
        await session.execute(delete(Job).where(Job.id.in_(job_ids)))
    await session.execute(
        update(AuditLog)
        .where(
            or_(
                AuditLog.resource_id.in_([*session_ids, *job_ids]),
                AuditLog.metadata_["chat_session_id"].astext.in_(as_text),
            )
        )
        .values(metadata_={})
    )


# ------------------------------------------------------------------- retention


async def expired_conversation_ids(
    session: AsyncSession, *, days: int, now: datetime | None = None
) -> list[uuid.UUID]:
    if days <= 0:
        return []
    cutoff = (now or _utcnow()) - timedelta(days=days)
    last_activity = func.coalesce(func.max(ChatMessage.created_at), ChatSession.created_at)
    rows = await session.execute(
        select(ChatSession.id)
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        # Case work can carry legal holds this system cannot judge, and a period
        # set for general chats says nothing about it. Its owner still can erase it.
        .where(ChatSession.case_id.is_(None))
        .group_by(ChatSession.id)
        .having(last_activity < cutoff)
    )
    return [row[0] for row in rows.all()]


async def apply_retention(session: AsyncSession, *, days: int | None = None) -> int:
    """Erase conversations past the configured period. Commits nothing itself."""
    effective = settings.chat_retention_days if days is None else days
    ids = await expired_conversation_ids(session, days=effective)
    if not ids:
        return 0
    await purge_conversation_traces(session, ids)
    await session.execute(delete(ChatSession).where(ChatSession.id.in_(ids)))
    session.add(
        AuditLog(
            user_id=None,
            action="privacy.retention_applied",
            resource_type="chat_session",
            resource_id=None,
            metadata_={"erased": len(ids), "days": effective},
        )
    )
    return len(ids)


# --------------------------------------------------------------------- erasure


class ErasureIncomplete(RuntimeError):
    """A store outside PostgreSQL could not confirm deletion. Safe to retry."""


@dataclass(frozen=True)
class ErasureResult:
    receipt_id: uuid.UUID
    counts: dict[str, int]


PRIVATE_COLLECTIONS = (POLICE_CASE_DATA, ADVOCATE_CASE_DATA)


async def _erase_private_vectors(case_ids: list[uuid.UUID]) -> int:
    if not case_ids:
        return 0
    client = create_qdrant_client()
    selector = models.Filter(
        must=[
            models.FieldCondition(
                key="case_id",
                match=models.MatchAny(any=[str(case_id) for case_id in case_ids]),
            )
        ]
    )
    erased = 0
    try:
        for collection in PRIVATE_COLLECTIONS:
            if not await client.collection_exists(collection):
                continue
            before = await client.count(collection, count_filter=selector, exact=True)
            await client.delete(
                collection_name=collection,
                points_selector=models.FilterSelector(filter=selector),
                wait=True,
            )
            after = await client.count(collection, count_filter=selector, exact=True)
            if after.count:
                raise ErasureIncomplete(f"{after.count} points remain in {collection}")
            erased += before.count
    except ErasureIncomplete:
        raise
    except Exception as exc:
        # The type only: the message can carry a host.
        raise ErasureIncomplete(f"vector store: {type(exc).__name__}") from exc
    finally:
        await client.close()
    return erased


def _delete_every_version(client: Any, bucket: str, prefix: str) -> int:
    """Delete an object and all its history.

    The buckets are versioned, so a plain delete only adds a delete marker and
    leaves every byte recoverable. Erasure has to remove the versions themselves.
    """
    removed = 0
    paginator = client.get_paginator("list_object_versions")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            targets = [
                {"Key": item["Key"], "VersionId": item["VersionId"]}
                for group in ("Versions", "DeleteMarkers")
                for item in page.get(group, [])
            ]
            for start in range(0, len(targets), 1000):
                batch = targets[start : start + 1000]
                client.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})
                removed += len(batch)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "NoSuchBucket":
            return 0
        raise
    return removed


def _erase_objects(
    prefixes: list[tuple[str, str]],
) -> int:
    client = create_s3_client()
    removed = 0
    for bucket, prefix in prefixes:
        removed += _delete_every_version(client, bucket, prefix)
        try:
            leftover = client.list_object_versions(Bucket=bucket, Prefix=prefix)
        except ClientError as exc:
            # A configured bucket this install never created holds nothing.
            if exc.response.get("Error", {}).get("Code") == "NoSuchBucket":
                continue
            raise
        if leftover.get("Versions") or leftover.get("DeleteMarkers"):
            raise ErasureIncomplete(f"objects remain in {bucket}")
    return removed


async def erase_account(
    session: AsyncSession, user: User, *, initiated_by: str
) -> ErasureResult:
    """Remove a person from every store, or raise having removed nothing from this one."""
    if user.role is UserRole.ADMIN:
        others = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != user.id)
        )
        if not others:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This is the only active administrator. Appoint another first.",
            )

    user_id = user.id
    case_ids = list((await session.scalars(select(Case.id).where(Case.owner_id == user_id))).all())
    chat_ids = list(
        (await session.scalars(select(ChatSession.id).where(ChatSession.user_id == user_id))).all()
    )
    job_ids = list((await session.scalars(select(Job.id).where(Job.user_id == user_id))).all())

    objects = (
        await session.execute(
            select(StorageObject.bucket, StorageObject.object_key).where(
                StorageObject.namespace != StorageNamespace.LEGAL_CORPUS,
                or_(
                    StorageObject.owner_id == user_id,
                    StorageObject.case_id.in_(case_ids) if case_ids else False,
                ),
            )
        )
    ).all()
    # Each case's whole prefix, not just the rows above: a presigned upload that
    # never completed registration has bytes in the bucket and no row at all.
    case_buckets = dict.fromkeys(
        (
            settings.s3_police_bucket,
            settings.s3_advocate_bucket,
            settings.s3_generated_bucket,
            settings.s3_bucket_name,
        )
    )
    prefixes: list[tuple[str, str]] = [
        (bucket, f"cases/{case_id}/") for case_id in case_ids for bucket in case_buckets
    ]
    prefixes.extend((bucket, key) for bucket, key in objects)

    message_count = 0
    if chat_ids:
        message_count = int(
            await session.scalar(
                select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id.in_(chat_ids))
            )
            or 0
        )
    # End this read transaction before talking to other services, so a slow
    # store does not hold a connection idle in transaction.
    await session.commit()

    try:
        vectors = await _erase_private_vectors(case_ids)
        removed_objects = await asyncio.to_thread(_erase_objects, prefixes)
    except ErasureIncomplete:
        raise
    except Exception as exc:
        raise ErasureIncomplete(f"object storage: {type(exc).__name__}") from exc

    identifying_ids = [user_id, *case_ids, *chat_ids, *job_ids]
    # The action and time of each event survive as a security record. Who it was
    # and anything said in it do not: traces can carry question text, and rows
    # about this account can carry its address.
    await session.execute(
        update(AuditLog)
        .where(
            or_(
                AuditLog.user_id == user_id,
                AuditLog.resource_id.in_(identifying_ids),
                cast(AuditLog.metadata_, String).contains(str(user_id)),
            )
        )
        .values(metadata_={}, user_id=None, resource_id=None)
    )
    if case_ids:
        await session.execute(delete(Case).where(Case.id.in_(case_ids)))
    await session.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    await session.execute(delete(Job).where(Job.user_id == user_id))
    await session.execute(delete(User).where(User.id == user_id))

    counts = {
        "cases": len(case_ids),
        "conversations": len(chat_ids),
        "messages": message_count,
        "jobs": len(job_ids),
        "file_versions": removed_objects,
        "vectors": vectors,
    }
    receipt = ErasureReceipt(initiated_by=initiated_by, counts=counts)
    session.add(receipt)
    await session.flush()
    session.add(
        AuditLog(
            user_id=None,
            action="privacy.account_erased",
            resource_type="erasure_receipt",
            resource_id=receipt.id,
            metadata_={"initiated_by": initiated_by},
        )
    )
    await session.commit()
    return ErasureResult(receipt_id=receipt.id, counts=counts)
