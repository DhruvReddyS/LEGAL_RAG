"""The advocate's tools. Every case route binds the case to its owner.

Routes under `/cases/{case_id}` go through `require_permission(ADVOCATE_STRATEGY_OWN)`,
which infers the ownership check from the path. The two prefixes are kept apart
so a tool reading only the public corpus is never handed a case it doesn't need.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from qdrant_client import models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.advocate_agents import build_verified_brief, compare_on_facts, with_user_facts
from app.core.database import get_db_session
from app.core.permissions import ADVOCATE_DEBATE_OWN, ADVOCATE_STRATEGY_OWN
from app.core.rbac import require_permission
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, GLOBAL_LEGAL_CORPUS
from app.models import AdvocateWorkProduct, AuditLog, Case, CaseDocument, Job, JobEvent, MatterCalendarEvent, User
from app.models.enums import JobStatus, JobType
from app.routers.jobs import _idempotent_job, _persist_job, _request_fingerprint, _validate_idempotency_key, _admit_job_enqueue
from app.schemas.advocate import (
    BailAssessmentRequest,
    BriefRequest,
    CalendarEventCreate,
    CalendarEventUpdate,
    ComparisonRequest,
    DebateRequest,
    DraftRequest,
    LimitationRequest,
    OpponentCheckRequest,
    PrecedentRequest,
    TreatmentRequest,
)
from app.schemas.jobs import JobResponse
from app.services.advocate_drafting import TEMPLATES, create_draft, template_catalogue
from app.services.advocate_sources import Evidence, source_from_payload
from app.services.advocate_work import save_work_product, work_detail, work_summary
from app.services.authority_check import check_authorities
from app.services.bail import BailFacts, BailRoute, assess_bail, retrieval_query
from app.services.citation_status import citation_labels_for
from app.services.debate_room import assemble_debate, turn_plan
from app.services.held_material import (
    best_passages,
    check_opponent_authorities,
    check_treatment,
    holding_sentences,
    judgment_catalogue,
    search_precedents,
)
from app.services.judgment_index import (
    JUDGMENT_SOURCE_TYPES,
    CorpusUnavailable,
    JudgmentIndex,
    coverage_statement,
)
from app.services.llm import OllamaClient
from app.services.matter_calendar import (
    article_catalogue,
    compute_limitation,
    event_state,
)
from app.services.retrieval import HybridRetrievalService, RetrievalFilters

router = APIRouter(tags=["advocate-tools"])

MAX_BRIEF_PASSAGES = 24
MAX_COMPARISON_PASSAGES = 8
_FACT_SIGNALS = "facts prosecution case allegation fir complaint incident appellant accused respondent evidence witness"


@dataclass(frozen=True)
class AdvocateRuntime:
    retrieval: HybridRetrievalService
    llm: OllamaClient
    judgments: JudgmentIndex


def get_advocate_runtime(request: Request) -> AdvocateRuntime:
    workflow = request.app.state.legal_rag_workflow
    index = getattr(request.app.state, "advocate_judgment_index", None)
    if index is None:
        index = JudgmentIndex(workflow.retrieval.client, GLOBAL_LEGAL_CORPUS)
        request.app.state.advocate_judgment_index = index
    return AdvocateRuntime(workflow.retrieval, workflow.llm, index)


CaseOwner = Annotated[User, Depends(require_permission(ADVOCATE_STRATEGY_OWN))]
Advocate = Annotated[User, Depends(require_permission(ADVOCATE_STRATEGY_OWN, infer_case_id=False))]
Session = Annotated[AsyncSession, Depends(get_db_session)]
Runtime = Annotated[AdvocateRuntime, Depends(get_advocate_runtime)]


def _audit(session: AsyncSession, user: User, action: str, case_id: uuid.UUID | None, **metadata: Any) -> None:
    # Metadata only: privileged text never goes in the audit log.
    session.add(
        AuditLog(
            user_id=user.id,
            action=f"advocate.{action}",
            resource_type="case" if case_id else "corpus",
            resource_id=case_id,
            metadata_=metadata,
        )
    )


def _corpus_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The judgment corpus could not be read, so this could not be checked. Nothing has been assumed.",
    )


# ----------------------------------------------------------------- A-02: bail


@router.post("/cases/{case_id}/advocate/bail/assess")
async def assess_bail_routes(
    case_id: uuid.UUID, body: BailAssessmentRequest, user: CaseOwner, session: Session, runtime: Runtime
) -> dict[str, Any]:
    routes = body.routes or list(BailRoute)
    facts = BailFacts(
        as_of=body.as_of or datetime.now(timezone.utc).date(),
        **body.model_dump(
            exclude={"routes", "as_of", "offence_description", "include_authorities", "save"}
        ),
    )
    result = assess_bail(facts, routes)
    result["authorities"] = []
    result["authorities_note"] = ""
    result["coverage"] = coverage_statement(await runtime.judgments.coverage())
    if body.include_authorities:
        try:
            hits = await runtime.retrieval.search(
                retrieval_query(body.offence_description, routes),
                filters=RetrievalFilters(source_types=list(JUDGMENT_SOURCE_TYPES)),
                candidate_limit=20,
                result_limit=6,
            )
            result["authorities"] = [
                {
                    "source": source_from_payload(dict(hit.payload), score=float(hit.reranker_score)),
                    "holding_language": holding_sentences(str(hit.payload.get("text") or "")),
                }
                for hit in hits
            ]
            if not hits:
                result["authorities_note"] = "No passage on this was found in the judgments held."
        except Exception:
            result["authorities_note"] = "The judgments held could not be searched just now."
    if body.save:
        statuses = ", ".join(sorted({row["status"].replace("_", " ") for row in result["routes"]}))
        product = await save_work_product(
            session, case_id=case_id, user_id=user.id, kind="bail_assessment",
            title=f"Bail assessment as of {facts.as_of.isoformat()}: {statuses}"[:255], status="draft",
            content={**result, "inputs": body.model_dump(mode="json", exclude={"save"})},
        )
        result["work_product_id"] = str(product.id)
    _audit(session, user, "bail.assess", case_id, routes=[route.value for route in routes], saved=body.save)
    await session.commit()
    return result


# ------------------------------------------------------------- A-03: drafting


@router.get("/advocate/draft-templates")
async def draft_templates(_: Advocate) -> dict[str, Any]:
    return {"templates": template_catalogue()}


@router.post("/cases/{case_id}/advocate/drafts", status_code=status.HTTP_201_CREATED)
async def create_advocate_draft(
    case_id: uuid.UUID, body: DraftRequest, user: CaseOwner, session: Session, runtime: Runtime
) -> dict[str, Any]:
    template = TEMPLATES.get(body.draft_type)
    if template is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown draft type")
    if template.uses_grounds and len(body.facts.strip()) < 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter the facts as instructed, so authority can be found for them.",
        )
    content = await create_draft(
        retrieval=runtime.retrieval, llm=runtime.llm, case_id=str(case_id), draft_type=body.draft_type,
        fields=body.fields, facts=body.facts, instructions=body.instructions,
    )
    product = await save_work_product(
        session, case_id=case_id, user_id=user.id, kind=f"draft:{body.draft_type}", title=template.title,
        status="incomplete" if content["missing_fields"] else "draft", content=content,
    )
    _audit(
        session, user, "draft.create", case_id, work_product_id=str(product.id), draft_type=body.draft_type,
        grounds=len(content["grounds"]), rejected=content["rejected_ground_count"],
        authority_chunk_ids=[item["chunk_id"] for item in content["authorities"]],
    )
    await session.commit()
    await session.refresh(product)
    return work_detail(product)


# ------------------------------------------------------------- A-04: calendar


def _event_row(event: MatterCalendarEvent, today: date, case_title: str | None = None) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "case_id": str(event.case_id),
        **({"case_title": case_title} if case_title is not None else {}),
        "kind": event.kind,
        "title": event.title,
        "due_on": event.due_on.isoformat(),
        "notes": event.notes,
        "basis": event.basis,
        "completed": event.completed_at is not None,
        "state": event_state(event.due_on, completed=event.completed_at is not None, today=today).value,
        "days_from_today": (event.due_on - today).days,
    }


@router.get("/advocate/calendar")
async def calendar_across_cases(user: Advocate, session: Session) -> dict[str, Any]:
    """Every date in this advocate's own cases. Filtered by owner, not by role."""
    today = datetime.now(timezone.utc).date()
    rows = (
        await session.execute(
            select(MatterCalendarEvent, Case.title)
            .join(Case, Case.id == MatterCalendarEvent.case_id)
            .where(Case.owner_id == user.id, MatterCalendarEvent.completed_at.is_(None))
            .order_by(MatterCalendarEvent.due_on)
            .limit(200)
        )
    ).all()
    return {"today": today.isoformat(), "events": [_event_row(event, today, title) for event, title in rows]}


@router.get("/advocate/limitation-articles")
async def limitation_articles(_: Advocate) -> dict[str, Any]:
    return {
        "articles": article_catalogue(),
        "scope_note": (
            "Only articles checked against the Limitation Act text in the corpus are listed. If none "
            "fits, no date is offered: compute it from the Act, and from any special law that applies."
        ),
    }


@router.get("/cases/{case_id}/advocate/calendar")
async def list_case_calendar(case_id: uuid.UUID, _: CaseOwner, session: Session) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    events = (
        await session.scalars(
            select(MatterCalendarEvent)
            .where(MatterCalendarEvent.case_id == case_id)
            .order_by(MatterCalendarEvent.due_on)
        )
    ).all()
    return {"today": today.isoformat(), "events": [_event_row(event, today) for event in events]}


@router.post("/cases/{case_id}/advocate/calendar", status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    case_id: uuid.UUID, body: CalendarEventCreate, user: CaseOwner, session: Session
) -> dict[str, Any]:
    event = MatterCalendarEvent(case_id=case_id, **body.model_dump())
    session.add(event)
    await session.flush()
    _audit(session, user, "calendar.create", case_id, event_id=str(event.id), kind=event.kind)
    await session.commit()
    return _event_row(event, datetime.now(timezone.utc).date())


async def _case_event(session: AsyncSession, case_id: uuid.UUID, event_id: uuid.UUID) -> MatterCalendarEvent:
    event = await session.get(MatterCalendarEvent, event_id)
    if event is None or event.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.patch("/cases/{case_id}/advocate/calendar/{event_id}")
async def update_calendar_event(
    case_id: uuid.UUID, event_id: uuid.UUID, body: CalendarEventUpdate, user: CaseOwner, session: Session
) -> dict[str, Any]:
    event = await _case_event(session, case_id, event_id)
    changes = body.model_dump(exclude_unset=True)
    if "completed" in changes:
        event.completed_at = datetime.now(timezone.utc) if changes.pop("completed") else None
    for name, value in changes.items():
        if value is not None or name == "notes":
            setattr(event, name, value)
    _audit(session, user, "calendar.update", case_id, event_id=str(event.id))
    await session.commit()
    await session.refresh(event)
    return _event_row(event, datetime.now(timezone.utc).date())


@router.delete("/cases/{case_id}/advocate/calendar/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_event(
    case_id: uuid.UUID, event_id: uuid.UUID, user: CaseOwner, session: Session
) -> None:
    event = await _case_event(session, case_id, event_id)
    await session.delete(event)
    _audit(session, user, "calendar.delete", case_id, event_id=str(event_id))
    await session.commit()


@router.post("/cases/{case_id}/advocate/calendar/limitation")
async def calculate_limitation(
    case_id: uuid.UUID, body: LimitationRequest, user: CaseOwner, session: Session
) -> dict[str, Any]:
    try:
        result = compute_limitation(body.article, body.runs_from, excluded_days=body.excluded_days)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That article is not one checked against the corpus. No date can be offered.",
        ) from exc
    event_payload = None
    if body.add_to_calendar:
        event = MatterCalendarEvent(
            case_id=case_id,
            kind="limitation",
            title=(body.title or f"Limitation: {result['description']}")[:255],
            due_on=date.fromisoformat(result["last_day"]),
            basis={
                "provision": result["basis_label"],
                "runs_from": result["runs_from"],
                "excluded_days": result["excluded_days"],
                "period": result["period"],
                "computed": True,
            },
        )
        session.add(event)
        await session.flush()
        event_payload = _event_row(event, datetime.now(timezone.utc).date())
    _audit(session, user, "limitation.compute", case_id, article=body.article, saved=body.add_to_calendar)
    await session.commit()
    return {**result, "event": event_payload}


# ---------------------------------------------------------------- A-05: brief


async def _case_document_passages(
    runtime: AdvocateRuntime, case_id: uuid.UUID, document_id: uuid.UUID
) -> list[dict[str, Any]]:
    records: list[Any] = []
    offset: Any = None
    while True:
        batch, offset = await runtime.retrieval.client.scroll(
            collection_name=ADVOCATE_CASE_DATA,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document_id))),
                    # Both, always: a document id alone is not a case boundary.
                    models.FieldCondition(key="case_id", match=models.MatchValue(value=str(case_id))),
                ]
            ),
            limit=128,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        records.extend(batch)
        if offset is None:
            break
    payloads = [dict(record.payload or {}) for record in records]
    payloads.sort(key=lambda item: (int(item.get("page_start") or 0), str(item.get("chunk_id") or "")))
    return payloads


def _even_sample(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(items) <= limit:
        return items
    picked = sorted({round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)})
    return [items[index] for index in picked]


@router.post("/cases/{case_id}/advocate/briefs", status_code=status.HTTP_201_CREATED)
async def create_brief(
    case_id: uuid.UUID, body: BriefRequest, user: CaseOwner, session: Session, runtime: Runtime
) -> dict[str, Any]:
    query = select(CaseDocument).where(CaseDocument.case_id == case_id)
    if body.document_ids:
        query = query.where(CaseDocument.id.in_(body.document_ids))
    documents = (await session.scalars(query)).all()
    if body.document_ids and len(documents) != len(set(body.document_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found in this case")
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No document has been added to this case yet, so there is nothing to summarise.",
        )
    passages: list[dict[str, Any]] = []
    for document in documents:
        passages.extend(await _case_document_passages(runtime, case_id, document.id))
    if not passages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The documents in this case have not finished indexing.",
        )
    selected = _even_sample(passages, MAX_BRIEF_PASSAGES)
    evidence = Evidence()
    for payload in selected:
        evidence.add(payload)
    try:
        brief = await build_verified_brief(runtime.llm, kind=body.kind, focus=body.focus, evidence=evidence)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The language model is unavailable, so no brief was produced.",
        ) from exc
    # Provisions the record itself cites, checked deterministically: a charge
    # sheet citing the CrPC should be flagged in the brief that summarises it.
    checks = check_authorities("\n".join(str(item.get("text") or "") for item in passages))
    content = {
        **brief,
        "kind": body.kind,
        "focus": body.focus,
        "partial_review": len(selected) < len(passages),
        "passages_read": len(selected),
        "passages_total": len(passages),
        "documents_read": len(documents),
        "provisions_in_record": [
            {
                "citation": check.citation, "finding": check.finding.value, "advice": check.advice,
                "successors": list(check.successors), "needs_attention": check.needs_attention,
            }
            for check in checks
        ],
        "disclaimer": (
            "Prepared from the documents in this case. Each statement passed a check against the "
            "passage cited for it. Whether a document is accurate is not checked. Review against the record."
        ),
    }
    product = await save_work_product(
        session, case_id=case_id, user_id=user.id, kind=body.kind,
        title="Synopsis" if body.kind == "synopsis" else "Brief",
        status="draft", content=content,
    )
    _audit(
        session, user, "brief.create", case_id, work_product_id=str(product.id), kind=body.kind,
        verified=brief["verified_count"], rejected=brief["rejected_count"],
    )
    await session.commit()
    await session.refresh(product)
    return work_detail(product)


# ------------------------------------------------- A-06 / A-07: held judgments


@router.get("/advocate/judgments")
async def held_judgments(_: Advocate, runtime: Runtime) -> dict[str, Any]:
    try:
        judgments = await runtime.judgments.judgments()
    except CorpusUnavailable as exc:
        raise _corpus_unavailable() from exc
    coverage = await runtime.judgments.coverage()
    return {
        "coverage": coverage_statement(coverage, what="Listing"),
        "year_min": coverage.year_min if coverage else None,
        "year_max": coverage.year_max if coverage else None,
        "undated": coverage.undated if coverage else None,
        "judgments": judgment_catalogue(judgments),
    }


@router.post("/advocate/precedents")
async def precedent_research(body: PrecedentRequest, user: Advocate, session: Session, runtime: Runtime) -> dict[str, Any]:
    if body.year_from is not None and body.year_to is not None and body.year_from > body.year_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The year range is reversed")
    try:
        result = await search_precedents(
            retrieval=runtime.retrieval, index=runtime.judgments, query=body.query, holding=body.holding,
            court=body.court, year_from=body.year_from, year_to=body.year_to,
        )
    except CorpusUnavailable as exc:
        raise _corpus_unavailable() from exc
    _audit(session, user, "precedents.search", None, court=body.court, results=len(result["results"]))
    await session.commit()
    return result


@router.post("/advocate/treatment")
async def treatment_check(body: TreatmentRequest, user: Advocate, session: Session, runtime: Runtime) -> dict[str, Any]:
    try:
        result = await check_treatment(index=runtime.judgments, reference_text=body.reference)
    except CorpusUnavailable as exc:
        raise _corpus_unavailable() from exc
    _audit(session, user, "treatment.check", None, held=len(result["held"]), cited_by=len(result["cited_by"]))
    await session.commit()
    return result


# ------------------------------------------------------------ A-08: opponent


@router.post("/cases/{case_id}/advocate/opponent-check")
async def opponent_check(
    case_id: uuid.UUID, body: OpponentCheckRequest, user: CaseOwner, session: Session, runtime: Runtime
) -> dict[str, Any]:
    text = (body.text or "").strip()
    if body.document_id is not None:
        document = await session.get(CaseDocument, body.document_id)
        if document is None or document.case_id != case_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found in this case")
        text = "\n".join(filter(None, [text, document.ocr_text or ""]))
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="That document has no readable text.")
    try:
        result = await check_opponent_authorities(index=runtime.judgments, text=text)
    except CorpusUnavailable as exc:
        raise _corpus_unavailable() from exc
    if body.save:
        product = await save_work_product(
            session, case_id=case_id, user_id=user.id, kind="opponent_check",
            title=f"Opponent's authorities: {len(result['cases'])} cases, {len(result['provisions'])} provisions",
            status="draft", content=result,
        )
        result = {**result, "work_product_id": str(product.id)}
    _audit(
        session, user, "opponent.check", case_id, cases=len(result["cases"]),
        provisions=len(result["provisions"]), needs_attention=result["needs_attention"],
    )
    await session.commit()
    return result


# ---------------------------------------------------------- A-09: comparison


def _judgment_evidence(chunks: list[dict[str, Any]], focus: str | None) -> Evidence:
    """The passages most likely to state the facts, plus the opening pages."""
    evidence = Evidence()
    wanted = best_passages(chunks, f"{_FACT_SIGNALS} {focus or ''}", limit=MAX_COMPARISON_PASSAGES - 2)
    for chunk in [*chunks[:2], *wanted]:
        evidence.add(chunk)
    return evidence


@router.post("/cases/{case_id}/advocate/compare", status_code=status.HTTP_201_CREATED)
async def compare_judgments(
    case_id: uuid.UUID, body: ComparisonRequest, user: CaseOwner, session: Session, runtime: Runtime
) -> dict[str, Any]:
    try:
        judgments = await runtime.judgments.judgments()
        first_held = judgments.get(body.first_judgment_id)
        second_held = judgments.get(body.second_judgment_id or "")
        if first_held is None or (body.second_judgment_id and second_held is None):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That judgment is not held in this corpus")
        if body.second_judgment_id == body.first_judgment_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Choose two different judgments")
        first = _judgment_evidence(await runtime.judgments.document_chunks(first_held.document_id), body.focus)
        if second_held is not None:
            second = _judgment_evidence(await runtime.judgments.document_chunks(second_held.document_id), body.focus)
            second_title = second_held.title
        else:
            second = Evidence()
            second_title = "This matter's facts, as you entered them (unverified)"
            with_user_facts(second, (body.matter_facts or "").strip(), label=second_title)
    except CorpusUnavailable as exc:
        raise _corpus_unavailable() from exc
    try:
        comparison = await compare_on_facts(
            runtime.llm, focus=body.focus, first_title=first_held.title, first=first,
            second_title=second_title, second=second, second_is_user_account=second_held is None,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The language model is unavailable, so no comparison was produced.",
        ) from exc
    coverage = await runtime.judgments.coverage()
    content = {
        **comparison,
        "first": first_held.summary(),
        "second": second_held.summary() if second_held else None,
        "second_title": second_title,
        "focus": body.focus,
        "coverage": coverage_statement(
            coverage, judgments_searched=2 if second_held else 1, what="Compared"
        ),
        "limit_note": (
            "This compares only what is stated here, on passages selected from each judgment. It does "
            "not find the closest case, and it does not say which position is stronger."
        ),
        "first_labels": _judgment_labels(first_held.document_id, first),
    }
    product = await save_work_product(
        session, case_id=case_id, user_id=user.id, kind="case_comparison",
        title=f"Comparison: {first_held.title[:90]} / {second_title[:90]}", status="draft", content=content,
    )
    _audit(session, user, "compare.create", case_id, work_product_id=str(product.id), verified=comparison["verified_count"])
    await session.commit()
    await session.refresh(product)
    return work_detail(product)


def _judgment_labels(document_id: str, evidence: Evidence) -> dict[str, Any]:
    payload = next(iter(evidence.payloads.values()), {"canonical_document_id": document_id})
    labels = citation_labels_for(payload)
    return {"current_status": labels["current_status"], "repeal_label": labels["repeal_label"]}


# -------------------------------------------------------------- A-10: debate


@router.post("/cases/{case_id}/advocate/debates", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse)
async def start_debate(
    case_id: uuid.UUID,
    body: DebateRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    user: Annotated[User, Depends(require_permission(ADVOCATE_DEBATE_OWN))],
    session: Session,
) -> Job:
    _validate_idempotency_key(idempotency_key)
    fingerprint = hashlib.sha256(
        json.dumps({"case_id": str(case_id), "fingerprint": _request_fingerprint(body)}).encode()
    ).hexdigest()
    existing = await _idempotent_job(
        session, user_id=user.id, job_type=JobType.DEBATE_ROOM,
        idempotency_key=idempotency_key, fingerprint=fingerprint,
    )
    if existing is not None:
        return existing
    await _admit_job_enqueue(user)
    return await _persist_job(
        session,
        user=user,
        job_type=JobType.DEBATE_ROOM,
        idempotency_key=idempotency_key,
        payload={
            "request_fingerprint": fingerprint,
            "case_id": str(case_id),
            "proposition": body.proposition.strip(),
            "facts": (body.facts or "").strip() or None,
            "rounds": body.rounds,
        },
        audit_metadata={"case_id": str(case_id), "rounds": body.rounds},
    )


def _debate_row(job: Job) -> dict[str, Any]:
    turns = list(job.payload.get("checkpoint") or [])
    return {
        "id": str(job.id),
        "status": job.status.value,
        "progress": job.progress,
        "proposition": job.payload.get("proposition"),
        "rounds": job.payload.get("rounds"),
        "turns_total": len(turn_plan(int(job.payload.get("rounds") or 1))),
        "turns_done": len(turns),
        "attempt_count": job.attempt_count,
        "error_message": job.error_message,
        "work_product_id": (job.result or {}).get("work_product_id"),
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def _case_debates(session: AsyncSession, case_id: uuid.UUID, user: User) -> list[Job]:
    rows = await session.scalars(
        select(Job)
        .where(
            Job.type == JobType.DEBATE_ROOM,
            Job.user_id == user.id,
            Job.payload["case_id"].astext == str(case_id),
        )
        .order_by(Job.created_at.desc())
        .limit(20)
    )
    return list(rows.all())


@router.get("/cases/{case_id}/advocate/debates")
async def list_debates(
    case_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission(ADVOCATE_DEBATE_OWN))],
    session: Session,
) -> dict[str, Any]:
    return {"debates": [_debate_row(job) for job in await _case_debates(session, case_id, user)]}


@router.get("/cases/{case_id}/advocate/debates/{job_id}")
async def read_debate(
    case_id: uuid.UUID,
    job_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission(ADVOCATE_DEBATE_OWN))],
    session: Session,
) -> dict[str, Any]:
    """Progress, and the turns verified so far. A partial run is still readable."""
    job = await session.get(Job, job_id)
    if (
        job is None
        or job.type is not JobType.DEBATE_ROOM
        or job.user_id != user.id
        or job.payload.get("case_id") != str(case_id)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debate not found")
    latest = await session.scalar(
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.event_type == "stage")
        .order_by(JobEvent.id.desc())
        .limit(1)
    )
    turns = list(job.payload.get("checkpoint") or [])
    return {
        **_debate_row(job),
        "stage_label": latest.data.get("label") if latest is not None and job.status is JobStatus.RUNNING else None,
        "debate": assemble_debate(job.payload, turns) if turns else None,
    }


# ---------------------------------------------------- saved work, in one place


@router.get("/cases/{case_id}/advocate/work")
async def list_work(case_id: uuid.UUID, _: CaseOwner, session: Session) -> dict[str, Any]:
    rows = (
        await session.scalars(
            select(AdvocateWorkProduct)
            .where(AdvocateWorkProduct.case_id == case_id)
            .order_by(AdvocateWorkProduct.created_at.desc())
        )
    ).all()
    return {"work": [work_summary(row) for row in rows]}


@router.get("/cases/{case_id}/advocate/work/{work_id}")
async def read_work(case_id: uuid.UUID, work_id: uuid.UUID, _: CaseOwner, session: Session) -> dict[str, Any]:
    """Exactly as it was written. Nothing is regenerated on reading."""
    product = await session.get(AdvocateWorkProduct, work_id)
    if product is None or product.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found in this case")
    return work_detail(product)
