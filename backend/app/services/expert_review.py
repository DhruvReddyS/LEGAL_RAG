"""CORP-08: a person checks sampled answers, and the result is a measured figure.

The golden set measures the system on a fixed test. This measures what users were
actually given, one claim at a time.

Privacy is by construction, in three layers:

* What is never sampled: anything attached to a case or a named matter, anything
  citing case evidence, and anything the safety screen answered.
* What is never stored: the question, the conversation, the user. A claim is a
  sentence of the answer that cites a source, which is all a reviewer needs.
* What is removed from the claim: the asker's own name and email, and anything shaped
  like an identifier.

Pattern matching cannot find every name in free text, so the last layer is a
reduction and not a guarantee. That is why the first two exist, and the panel says so.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Text, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, ChatMessage, ChatMessageAnnotation, ChatSession, ChatSessionMeta, User
from app.models.corpus_lifecycle import ExpertReviewClaim, ExpertReviewItem
from app.models.enums import ChatMessageRole

MAX_CLAIMS_PER_ANSWER = 12
_MIN_CLAIM_WORDS = 4
_EXCERPT_LIMIT = 1500
_CASE_CHUNK_PREFIX = "case-chunk-"
_SOURCE_MARKER = re.compile(r"\[Source\s+\d+\]")
_SENTENCE_BREAK = re.compile(r"(?<=[.;?!\]])\s+(?=[A-Z(])")
_LIST_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email removed]"),
    # Sixteen grouped digits first: the first twelve of a card also look like Aadhaar.
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[account removed]"),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[id number removed]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN removed]"),
    (re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"), "[bank code removed]"),
    (re.compile(r"(?:\+91[ -]?|\b0)?\b[6-9]\d{4}[ -]?\d{5}\b"), "[phone removed]"),
    (re.compile(r"\b[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{4}\b"), "[vehicle removed]"),
    (
        re.compile(
            r"\b(?:FIR|Crime|Cr\.?|C\.?C\.?|Case|Account|A/c)\s*(?:No\.?|Number|#)\s*:?\s*[\w/-]*\d[\w/-]*",
            re.I,
        ),
        "[reference removed]",
    ),
    (re.compile(r"\b(?:address|residing at|resident of)\s*:?\s*[^.;\n]+", re.I), "[address removed]"),
)


def redact(text: str, *, known_names: tuple[str, ...] = ()) -> str:
    cleaned = text
    for pattern, replacement in _REDACTIONS:
        cleaned = pattern.sub(replacement, cleaned)
    # Longest first, so the full name is replaced whole before any part of it.
    for name in sorted({item for item in known_names if len(item) >= 3}, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(name)}\b", "[name removed]", cleaned, flags=re.I)
    return cleaned


def identifiers_of(name: str | None, email: str | None) -> tuple[str, ...]:
    parts = [part for part in re.split(r"\s+", (name or "").strip()) if part]
    local = (email or "").split("@")[0]
    return tuple(filter(None, [(name or "").strip(), *parts, email or "", local]))


def split_claims(answer: str) -> list[str]:
    """The sentences of an answer that cite a source, each with its marker.

    Uncited lines are headings, framing or limits rather than propositions of law a
    reviewer can check against a source. A sentence broken by an abbreviation ("Hon.
    Court held") is joined back to the fragment before it.
    """
    claims: list[str] = []
    for line in answer.splitlines():
        line = _LIST_PREFIX.sub("", line).strip().replace("**", "")
        if not line:
            continue
        pending = ""
        for piece in _SENTENCE_BREAK.split(line):
            # A marker standing alone belongs to the sentence before it.
            if _SOURCE_MARKER.fullmatch(piece.strip().rstrip(".")) and claims:
                claims[-1] = f"{claims[-1]} {piece.strip()}"
                continue
            candidate = f"{pending} {piece}".strip()
            if _SOURCE_MARKER.search(candidate):
                if len(_SOURCE_MARKER.sub("", candidate).split()) >= _MIN_CLAIM_WORDS:
                    claims.append(candidate)
                pending = ""
            else:
                pending = candidate if len(candidate.split()) < _MIN_CLAIM_WORDS else ""
    return claims[:MAX_CLAIMS_PER_ANSWER]


def _public_citation(citation: dict[str, Any]) -> dict[str, Any]:
    """Allowlisted fields of public law, so a field added later stays out by default."""
    return {
        "number": citation.get("number"),
        "title": citation.get("title"),
        "act_name": citation.get("act_name"),
        "section": citation.get("section"),
        "page_start": citation.get("page_start"),
        "page_end": citation.get("page_end"),
        "source_url": citation.get("source_url"),
        "excerpt": str(citation.get("excerpt") or "")[:_EXCERPT_LIMIT],
    }


def _is_public(citations: list[dict[str, Any]]) -> bool:
    return bool(citations) and not any(
        str(item.get("chunk_id") or "").startswith(_CASE_CHUNK_PREFIX) for item in citations
    )


async def sample_answers(
    session: AsyncSession, *, admin: User, count: int, days: int
) -> dict[str, Any]:
    """Draw up to `count` eligible recent answers at random into the queue."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sampled_already = select(ExpertReviewItem.message_id)
    rows = (
        await session.execute(
            select(
                ChatMessage.id,
                ChatMessage.content,
                ChatMessage.citations,
                ChatMessage.created_at,
                User.name,
                User.email,
            )
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .join(User, User.id == ChatSession.user_id)
            .outerjoin(ChatSessionMeta, ChatSessionMeta.session_id == ChatSession.id)
            .outerjoin(ChatMessageAnnotation, ChatMessageAnnotation.message_id == ChatMessage.id)
            .where(
                ChatMessage.role == ChatMessageRole.ASSISTANT,
                ChatMessage.created_at >= cutoff,
                ChatSession.case_id.is_(None),
                ChatSessionMeta.matter.is_(None),
                ChatMessageAnnotation.safety_kind.is_(None),
                func.jsonb_array_length(cast(ChatMessage.citations, JSONB)) > 0,
                ChatMessage.id.not_in(sampled_already),
                # A case-evidence citation can outlive its case: deleting a case
                # leaves the conversation behind with case_id cleared.
                cast(ChatMessage.citations, Text).not_like(f'%"chunk_id": "{_CASE_CHUNK_PREFIX}%'),
            )
            .order_by(func.random())
            # More than asked for, because some have no citing sentence to review.
            .limit(count * 4)
        )
    ).all()

    sampled = 0
    for message_id, content, citations, created_at, name, email in rows:
        if sampled >= count:
            break
        if not _is_public(citations):
            continue
        known = identifiers_of(name, email)
        claims = [redact(claim, known_names=known) for claim in split_claims(content)]
        if not claims:
            continue
        item = ExpertReviewItem(
            message_id=message_id,
            answered_month=created_at.strftime("%Y-%m"),
            citations=[_public_citation(citation) for citation in citations],
            sampled_by=admin.id,
        )
        session.add(item)
        await session.flush()
        session.add_all(
            ExpertReviewClaim(item_id=item.id, ordinal=ordinal, text=text)
            for ordinal, text in enumerate(claims)
        )
        sampled += 1
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.expert_review.sampled",
            resource_type="expert_review_item",
            metadata_={"requested": count, "sampled": sampled, "days": days},
        )
    )
    await session.commit()
    return {"requested": count, "sampled": sampled, "days": days}


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """A 95% interval that stays meaningful for the small samples this will have."""
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


async def measured_accuracy(session: AsyncSession) -> dict[str, Any]:
    """Correct out of those a reviewer could decide.

    `unsure` is reported beside the figure and not in it. Counting it as wrong would
    punish a careful reviewer, and counting it as right would flatter the system.
    """
    counts = {
        verdict: int(number)
        for verdict, number in (
            await session.execute(
                select(ExpertReviewClaim.verdict, func.count()).group_by(ExpertReviewClaim.verdict)
            )
        ).all()
    }
    correct = counts.get("correct", 0)
    incorrect = counts.get("incorrect", 0)
    decided = correct + incorrect
    answers = await session.scalar(
        select(func.count(func.distinct(ExpertReviewClaim.item_id))).where(
            ExpertReviewClaim.verdict.is_not(None)
        )
    )
    interval = wilson_interval(correct, decided)
    return {
        "claim_accuracy": round(correct / decided, 4) if decided else None,
        "interval_95": list(interval) if interval else None,
        "sample_size": decided,
        "correct": correct,
        "incorrect": incorrect,
        "unsure": counts.get("unsure", 0),
        "unreviewed": counts.get(None, 0),
        "answers_reviewed": int(answers or 0),
    }


async def review_queue(
    session: AsyncSession, *, status: str, page: int, page_size: int
) -> dict[str, Any]:
    has_open_claim = (
        select(ExpertReviewClaim.id)
        .where(ExpertReviewClaim.item_id == ExpertReviewItem.id, ExpertReviewClaim.verdict.is_(None))
        .exists()
    )
    condition = has_open_claim if status == "open" else ~has_open_claim
    total = await session.scalar(select(func.count()).select_from(ExpertReviewItem).where(condition))
    items = (
        await session.scalars(
            select(ExpertReviewItem)
            .where(condition)
            .order_by(ExpertReviewItem.sampled_at.desc(), ExpertReviewItem.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    claims: dict[uuid.UUID, list[ExpertReviewClaim]] = {}
    if items:
        for claim in (
            await session.scalars(
                select(ExpertReviewClaim)
                .where(ExpertReviewClaim.item_id.in_([item.id for item in items]))
                .order_by(ExpertReviewClaim.ordinal)
            )
        ).all():
            claims.setdefault(claim.item_id, []).append(claim)
    return {
        "measure": await measured_accuracy(session),
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(item.id),
                "answered_month": item.answered_month,
                "citations": item.citations,
                "claims": [
                    {
                        "id": str(claim.id),
                        "text": claim.text,
                        "verdict": claim.verdict,
                        "note": claim.note,
                    }
                    for claim in claims.get(item.id, [])
                ],
            }
            for item in items
        ],
    }


async def record_verdict(
    session: AsyncSession, *, admin: User, claim_id: uuid.UUID, verdict: str | None, note: str | None
) -> dict[str, Any]:
    claim = await session.get(ExpertReviewClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.verdict = verdict
    claim.note = note.strip() or None if note else None
    claim.reviewed_by = admin.id if verdict else None
    claim.reviewed_at = datetime.now(timezone.utc) if verdict else None
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.expert_review.verdict",
            resource_type="expert_review_claim",
            resource_id=claim.id,
            metadata_={"verdict": verdict, "has_note": bool(claim.note)},
        )
    )
    await session.commit()
    return {"id": str(claim.id), "verdict": claim.verdict, "note": claim.note}
