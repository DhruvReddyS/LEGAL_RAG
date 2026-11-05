"""CORP-08: sampled answers, reviewed claim by claim, with a figure and its sample size."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update

from app.core.database import AsyncSessionLocal
from app.models import (
    AuditLog,
    Case,
    ChatMessage,
    ChatMessageAnnotation,
    ChatSession,
    ChatSessionMeta,
    User,
)
from app.models.corpus_lifecycle import ExpertReviewClaim, ExpertReviewItem
from app.models.enums import CaseRoleType, ChatMessageRole
from app.services import expert_review
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "Original-Password-1234"
SECRET_QUESTION = "my employer Meenakshi Sundaram owes me wages"
GOOD_ANSWER = (
    "Direct answer\n"
    "An employer must pay wages on the date the statute fixes [Source 1]. "
    "The officer may direct payment of what is owed [Source 2].\n"
    "This is general information, not advice."
)
CITATIONS = [
    {
        "number": 1,
        "chunk_id": "gold-chunk-1",
        "title": "The Invented Wages Act, 2001",
        "act_name": "The Invented Wages Act, 2001",
        "section": "5",
        "page_start": 1,
        "page_end": 2,
        "source_url": "https://example.gov.in/a.pdf",
        "excerpt": "Wages shall be paid.",
        "retrieval_score": 0.9,
        "verification_status": "verified",
    }
]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def console():
    # Other suites leave old answers behind, and these tests count what is sampled.
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ExpertReviewItem))
        await session.execute(
            update(ChatMessage)
            .where(ChatMessage.created_at >= datetime.now(timezone.utc) - timedelta(days=400))
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=500))
        )
        await session.commit()
    admin = await provision_test_user(
        name="Review Admin", email=unique_email("review-admin"), password=PASSWORD, role="admin"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update(_bearer(admin["access_token"]))
        yield client


async def _asker(name: str = "Meenakshi Sundaram") -> tuple[uuid.UUID, str]:
    email = unique_email("asker")
    body = await provision_test_user(name=name, email=email, password=PASSWORD, role="citizen")
    return uuid.UUID(body["user"]["id"]), email


async def _answer(
    user_id: uuid.UUID,
    *,
    content: str = GOOD_ANSWER,
    citations: list[dict] | None = None,
    case_id: uuid.UUID | None = None,
    matter: str | None = None,
    safety_kind: str | None = None,
    age_days: int = 0,
) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=user_id, title=SECRET_QUESTION, case_id=case_id)
        session.add(chat)
        await session.flush()
        session.add(ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content=SECRET_QUESTION, citations=[]))
        message = ChatMessage(
            session_id=chat.id,
            role=ChatMessageRole.ASSISTANT,
            content=content,
            citations=CITATIONS if citations is None else citations,
        )
        session.add(message)
        await session.flush()
        if matter:
            session.add(ChatSessionMeta(session_id=chat.id, user_id=user_id, matter=matter))
        if safety_kind:
            session.add(ChatMessageAnnotation(message_id=message.id, safety_kind=safety_kind))
        if age_days:
            message.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
        await session.commit()
        return message.id


async def _sampled_message_ids() -> set[uuid.UUID]:
    async with AsyncSessionLocal() as session:
        return set((await session.scalars(select(ExpertReviewItem.message_id))).all())


async def _sample(client: AsyncClient, count: int = 10, days: int = 30) -> dict:
    response = await client.post("/admin/console/quality/review/sample", json={"count": count, "days": days})
    assert response.status_code == 201, response.text
    return response.json()


async def _queue(client: AsyncClient, status: str = "open") -> dict:
    response = await client.get("/admin/console/quality/review", params={"status": status, "page_size": 50})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------- what is sampled


async def test_only_ordinary_recent_answers_are_sampled(console) -> None:
    user, _ = await _asker()
    async with AsyncSessionLocal() as session:
        case = Case(owner_id=user, title="A private case", role_type=CaseRoleType.ADVOCATE, status="open")
        session.add(case)
        await session.commit()
        case_id = case.id

    eligible = await _answer(user)
    excluded = [
        await _answer(user, case_id=case_id),
        await _answer(user, matter="My named matter"),
        await _answer(user, safety_kind="refusal"),
        await _answer(user, citations=[]),
        await _answer(user, citations=[{**CITATIONS[0], "chunk_id": "case-chunk-1"}]),
        await _answer(user, citations=[CITATIONS[0], {**CITATIONS[0], "chunk_id": "case-chunk-2"}]),
        await _answer(user, age_days=90),
        await _answer(user, content="Nothing here cites anything at all."),
    ]

    result = await _sample(console, count=20, days=30)

    assert result["sampled"] == 1
    assert await _sampled_message_ids() == {eligible}
    assert not set(excluded) & await _sampled_message_ids()


async def test_a_case_erased_since_leaves_no_way_in(console) -> None:
    """Deleting a case clears case_id, so the citation is what still shows where it came from."""
    user, _ = await _asker()
    orphan = await _answer(user, citations=[{**CITATIONS[0], "chunk_id": "case-chunk-9"}])
    await _sample(console, count=50, days=30)
    assert orphan not in await _sampled_message_ids()


async def test_an_answer_is_not_sampled_twice(console) -> None:
    user, _ = await _asker()
    message = await _answer(user)
    first = await _sample(console, count=50)
    second = await _sample(console, count=50)
    assert first["sampled"] >= 1 and second["sampled"] == 0
    assert message in await _sampled_message_ids()


async def test_the_sample_is_bounded_by_what_was_asked_for(console) -> None:
    user, _ = await _asker()
    for _ in range(5):
        await _answer(user)
    assert (await _sample(console, count=2))["sampled"] == 2


# ---------------------------------------------------------------- what is shown


async def test_no_identifier_reaches_the_reviewer(console) -> None:
    name = f"Zarina{uuid.uuid4().hex[:6]} Qureshi"
    user, email = await _asker(name)
    content = (
        f"{name} must be paid under the statute [Source 1]. "
        f"Write to {email} or call +91 98765 43210 about this [Source 1]. "
        "The Aadhaar 1234 5678 9012 and PAN ABCDE1234F are not needed for this step [Source 1]. "
        "FIR No. 123/2026 is recorded at the station for the complaint [Source 1]. "
        "Vehicle TS 09 AB 1234 is the one in the record of the case [Source 1]."
    )
    await _answer(user, content=content)
    await _sample(console)

    body = await _queue(console)
    dumped = json.dumps(body)
    for leaked in (
        name,
        name.split()[0],
        email,
        "98765",
        "1234 5678 9012",
        "ABCDE1234F",
        "123/2026",
        "TS 09",
        SECRET_QUESTION,
    ):
        assert leaked not in dumped, leaked
    for internal in ("message_id", "user_id", "session_id", "chunk_id", "retrieval_score"):
        assert internal not in dumped, internal
    assert "[name removed]" in dumped and "[phone removed]" in dumped


async def test_a_claim_is_a_sentence_that_cites_something(console) -> None:
    user, _ = await _asker()
    await _answer(user)
    await _sample(console)
    item = (await _queue(console))["items"][0]
    assert [claim["text"] for claim in item["claims"]] == [
        "An employer must pay wages on the date the statute fixes [Source 1].",
        "The officer may direct payment of what is owed [Source 2].",
    ]
    assert item["citations"][0]["title"] == "The Invented Wages Act, 2001"
    assert len(item["answered_month"]) == 7, "the month, not a moment that identifies a conversation"


def test_splitting_handles_an_abbreviation_and_a_bare_marker() -> None:
    claims = expert_review.split_claims(
        "- Hon. Court held that bail is the rule here [Source 1]\n"
        "**Application**\n"
        "1. The section applies to every officer [Source 2]; the duty is absolute in this case [Source 3].\n"
        "A long sentence with no source at all and plenty of words in it.\n"
        "Short [Source 4]."
    )
    # The heading, the uncited sentence and the too-short fragment are all left out,
    # and a list prefix does not survive into the claim.
    assert claims == [
        "Hon. Court held that bail is the rule here [Source 1]",
        "The section applies to every officer [Source 2]; the duty is absolute in this case [Source 3].",
    ]


# ----------------------------------------------------------- the measured figure


async def test_no_verdicts_means_not_measured_rather_than_zero(console) -> None:
    measure = (await _queue(console))["measure"]
    assert measure["claim_accuracy"] is None
    assert measure["sample_size"] == 0
    assert measure["interval_95"] is None


async def test_verdicts_become_a_figure_with_its_sample_size(console) -> None:
    user, _ = await _asker()
    await _answer(user)
    await _answer(user)
    await _sample(console)
    claims = [claim for item in (await _queue(console))["items"] for claim in item["claims"]]
    assert len(claims) == 4
    verdicts = ["correct", "correct", "incorrect", "unsure"]
    for claim, verdict in zip(claims, verdicts):
        response = await console.put(
            f"/admin/console/quality/review/claims/{claim['id']}", json={"verdict": verdict, "note": "Checked."}
        )
        assert response.status_code == 200

    measure = (await _queue(console))["measure"]
    assert measure["correct"] == 2 and measure["incorrect"] == 1 and measure["unsure"] == 1
    # Unsure is reported beside the figure, not counted either way.
    assert measure["sample_size"] == 3
    assert measure["claim_accuracy"] == pytest.approx(2 / 3, abs=0.001)
    low, high = measure["interval_95"]
    assert low < 2 / 3 < high
    assert measure["answers_reviewed"] == 2
    assert (await _queue(console))["total"] == 0, "nothing left open"
    assert (await _queue(console, "done"))["total"] == 2


async def test_a_verdict_can_be_withdrawn(console) -> None:
    user, _ = await _asker()
    await _answer(user)
    await _sample(console)
    claim = (await _queue(console))["items"][0]["claims"][0]
    url = f"/admin/console/quality/review/claims/{claim['id']}"
    await console.put(url, json={"verdict": "incorrect", "note": "Oops"})
    assert (await _queue(console))["measure"]["sample_size"] == 1
    cleared = await console.put(url, json={"verdict": None})
    assert cleared.json() == {"id": claim["id"], "verdict": None, "note": None}
    assert (await _queue(console))["measure"]["sample_size"] == 0


async def test_the_audit_row_says_a_note_exists_without_holding_it(console) -> None:
    user, _ = await _asker()
    await _answer(user)
    await _sample(console)
    claim = (await _queue(console))["items"][0]["claims"][0]
    await console.put(
        f"/admin/console/quality/review/claims/{claim['id']}",
        json={"verdict": "correct", "note": "Private reviewer remark"},
    )
    async with AsyncSessionLocal() as session:
        row = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.expert_review.verdict", AuditLog.resource_id == uuid.UUID(claim["id"])
            )
        )
    assert row.metadata_ == {"verdict": "correct", "has_note": True}


@pytest.mark.parametrize(
    "successes,total",
    [(0, 1), (1, 1), (5, 10), (10, 10), (0, 10), (99, 100)],
)
def test_the_interval_stays_a_valid_range(successes, total) -> None:
    low, high = expert_review.wilson_interval(successes, total)
    assert 0 <= low <= successes / total <= high <= 1


def test_an_empty_sample_has_no_interval() -> None:
    assert expert_review.wilson_interval(0, 0) is None


# -------------------------------------------------------------------- the edges


async def test_erasing_a_conversation_erases_its_review(console) -> None:
    user, _ = await _asker()
    message = await _answer(user)
    await _sample(console)
    assert message in await _sampled_message_ids()
    async with AsyncSessionLocal() as session:
        stored = await session.get(ChatMessage, message)
        await session.execute(delete(ChatSession).where(ChatSession.id == stored.session_id))
        await session.commit()
        left = await session.scalar(select(func.count()).select_from(ExpertReviewClaim))
    assert left == 0
    assert message not in await _sampled_message_ids()


async def test_erasing_an_account_erases_its_reviews(console) -> None:
    user, _ = await _asker()
    await _answer(user)
    await _sample(console)
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.id == user))
        await session.commit()
        left = await session.scalar(select(func.count()).select_from(ExpertReviewItem))
    assert left == 0


async def test_a_citizen_cannot_reach_the_queue(console) -> None:
    citizen = await provision_test_user(
        name="Not Admin", email=unique_email("review-citizen"), password=PASSWORD, role="citizen"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = _bearer(citizen["access_token"])
        assert (await client.get("/admin/console/quality/review", headers=headers)).status_code == 403
        assert (
            await client.post("/admin/console/quality/review/sample", json={"count": 1}, headers=headers)
        ).status_code == 403
        assert (
            await client.put(f"/admin/console/quality/review/claims/{uuid.uuid4()}", json={"verdict": "correct"}, headers=headers)
        ).status_code == 403


async def test_an_unknown_claim_is_not_found(console) -> None:
    response = await console.put(f"/admin/console/quality/review/claims/{uuid.uuid4()}", json={"verdict": "correct"})
    assert response.status_code == 404
