"""The police working record, over the API.

Three kinds of route, with three different gates.

* /cases/{case_id}/police/...: the owner of that case and nobody else. The shared
  permission checker lets an administrator past its ownership test, which is right for
  some case routes and not for these: custody logs and witness details have no business
  reaching someone who is not party to the matter. The dependency here closes that.

* /police/...: a caller's own material, across their own cases, or reference data.

* /police/supervision/... and /police/units/...: the only routes that look past one
  officer. A supervisor view needs the permission and an explicit supervisor row that
  only an administrator can write; it returns counts and deadline states, never
  evidence, statements or witnesses; it grants nothing on the case routes; and every
  look is audited against each case, where its owner can read it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import (
    ADMIN_USER_MANAGE,
    POLICE_INVESTIGATION_OWN,
    POLICE_UNIT_SUPERVISE,
)
from app.core.rbac import require_permission
from app.models import AuditLog, Case, GeneratedDocument, InvestigationFacts as FactsRow, User
from app.models.enums import CaseRoleType, OffenceGravity, UserRole
from app.models.police import (
    PoliceComplianceRecord,
    PoliceCustodyEvent,
    PoliceDeadlineCompletion,
    PoliceDiaryEntry,
    PoliceEvidenceItem,
    PoliceOffenceAssessment,
    PoliceRemandPeriod,
    PoliceSearch,
    PoliceUnit,
    PoliceUnitMember,
    PoliceWitness,
)
from app.routers.investigation import _FACT_FIELDS as FACT_FIELDS
from app.routers.investigation import COMPLIANCE_FLAGS, effective_flags
from app.schemas.police import (
    AccessEntry,
    AccessLogResponse,
    CaseFileResponse,
    CaseReference,
    ChainResponse,
    CompletionRequest,
    ComplianceRecordItem,
    ComplianceRecordRequest,
    ComplianceRecordResponse,
    CustodyEventCreate,
    CustodyEventResponse,
    DiaryCreate,
    DiaryEntryResponse,
    DiaryResponse,
    DraftCreate,
    DraftListResponse,
    DraftResponse,
    DraftSummary,
    ElementResponse,
    EvidenceCreate,
    EvidenceListResponse,
    EvidenceResponse,
    EvidenceUpdate,
    MyUnitEntry,
    MyUnitsResponse,
    OffenceAssessmentList,
    OffenceAssessmentResponse,
    OffenceAssessmentWrite,
    OffenceCatalogue,
    OffenceCatalogueEntry,
    RegisterResponse,
    RegisterRowResponse,
    RemandCreate,
    RemandPeriodResponse,
    RemandResponse,
    SearchCheckResponse,
    SearchListResponse,
    SearchResponse,
    SearchWrite,
    SupervisedCase,
    SupervisedDeadline,
    SupervisedUnitResponse,
    UnitCreate,
    UnitListResponse,
    UnitMemberResponse,
    UnitMemberWrite,
    UnitResponse,
    WitnessCreate,
    WitnessDuty,
    WitnessListResponse,
    WitnessResponse,
    WitnessUpdate,
)
from app.services.investigation_compliance import (
    ComplianceStatus,
    PoliceAction,
    compliance_checklist,
)
from app.services.investigation_timeline import InvestigationFacts, investigation_deadlines
from app.services.police_case_file import render_case_file
from app.services.police_custody import (
    CustodyHop,
    RemandPeriod,
    analyse_chain,
    diary_gaps,
    remand_summary,
)
from app.services.police_drafting import DRAFT_TYPES, DraftContext, render_draft
from app.services.police_offences import OFFENCES, ElementState, assess, overall_finding
from app.services.police_register import (
    IMMINENT_HOURS,
    RegisterRow,
    RegisterState,
    derived_completions,
    register_rows,
    search_record_deadline,
    sort_rows,
    summarise,
)
from app.services.police_search_check import (
    CHECK_QUESTIONS,
    SearchRecord,
    evaluate_search,
    overall,
)

router = APIRouter(tags=["police-tools"])

_CASE_CHECKER = require_permission(POLICE_INVESTIGATION_OWN, case_id_param="case_id")
# Reaches the caller's own material only; each query filters on owner.
_OWN = require_permission(POLICE_INVESTIGATION_OWN, infer_case_id=False)
_SUPERVISE = require_permission(POLICE_UNIT_SUPERVISE)
_MANAGE_UNITS = require_permission(ADMIN_USER_MANAGE)

_FUTURE_TOLERANCE = timedelta(minutes=5)
DRAFT_DOC_PREFIX = "police_draft:"


async def police_case_owner(
    case_id: uuid.UUID,
    user: Annotated[User, Depends(_CASE_CHECKER)],
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """The checker above, without its administrator exception."""
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    if case.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this case")
    if case.role_type is not CaseRoleType.POLICE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not a police case")
    return user


Owner = Annotated[User, Depends(police_case_owner)]
Session = Annotated[AsyncSession, Depends(get_db_session)]


def _audit(session: AsyncSession, user: User, action: str, case_id: uuid.UUID | None, **metadata) -> None:
    """Names what happened, never the free text. The log is read by administrators,
    who are not party to the matter."""
    session.add(
        AuditLog(
            user_id=user.id,
            action=action,
            resource_type="case" if case_id else "police_unit",
            resource_id=case_id,
            metadata_=metadata,
        )
    )


def _refuse_future(moment: datetime | None, label: str) -> None:
    if moment is not None and moment > datetime.now(timezone.utc) + _FUTURE_TOLERANCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} cannot be in the future")


async def _in_case(session: AsyncSession, model, case_id: uuid.UUID, item_id: uuid.UUID, label: str):
    """Fetch by id through the case. An id from another case is simply not found."""
    row = await session.scalar(select(model).where(model.id == item_id, model.case_id == case_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found in this case")
    return row


def _facts(row: FactsRow | None) -> InvestigationFacts:
    return InvestigationFacts(**{field: getattr(row, field) for field in FACT_FIELDS}) if row else InvestigationFacts()


# ---- The register


async def _register_for(
    session: AsyncSession,
    cases: list[Case],
    now: datetime,
    imminent_hours: int,
) -> tuple[list[RegisterRow], list[Case]]:
    if not cases:
        return [], []
    ids = [case.id for case in cases]
    facts = {row.case_id: row for row in await session.scalars(select(FactsRow).where(FactsRow.case_id.in_(ids)))}
    completions: dict[uuid.UUID, dict] = {}
    for row in await session.scalars(
        select(PoliceDeadlineCompletion).where(PoliceDeadlineCompletion.case_id.in_(ids))
    ):
        completions.setdefault(row.case_id, {})[row.deadline_key] = (row.completed_at, row.note or "")
    searches: dict[uuid.UUID, list[PoliceSearch]] = {}
    for row in await session.scalars(
        select(PoliceSearch).where(PoliceSearch.case_id.in_(ids), PoliceSearch.basis == "section_185")
    ):
        searches.setdefault(row.case_id, []).append(row)

    rows: list[RegisterRow] = []
    without_facts: list[Case] = []
    for case in cases:
        recorded = facts.get(case.id)
        case_searches = searches.get(case.id, [])
        if recorded is None and not case_searches:
            without_facts.append(case)
        as_facts = _facts(recorded)
        derived = derived_completions(as_facts)
        deadlines = investigation_deadlines(as_facts)
        for search in case_searches:
            deadline = search_record_deadline(str(search.id), search.place, search.grounds_recorded_at)
            deadlines.append(deadline)
            if search.record_sent_to_magistrate_at:
                derived[deadline.key] = search.record_sent_to_magistrate_at
        rows.extend(
            register_rows(
                case_id=str(case.id),
                case_title=case.title,
                deadlines=deadlines,
                completions=completions.get(case.id, {}),
                derived=derived,
                now=now,
                imminent_hours=imminent_hours,
            )
        )
    return rows, without_facts


def _row_response(row: RegisterRow) -> RegisterRowResponse:
    return RegisterRowResponse(
        case_id=uuid.UUID(row.case_id),
        case_title=row.case_title,
        key=row.key,
        obligation=row.obligation,
        provision=row.provision,
        actor=row.actor,
        is_officer_duty=row.is_officer_duty,
        consequence=row.consequence,
        computed_from=row.computed_from,
        due_at=row.due_at,
        state=row.state.value,
        state_reason=row.state_reason,
        is_earliest_possible=row.is_earliest_possible,
        is_imminent=row.is_imminent,
        completed_at=row.completed_at,
        completion_note=row.completion_note,
        completion_is_derived=row.completion_is_derived,
        notes=list(row.notes),
    )


def _apply_filters(
    rows: list[RegisterRow],
    states: list[RegisterState] | None,
    provision: str | None,
    imminent_only: bool,
    officer_only: bool,
) -> list[RegisterRow]:
    needle = (provision or "").strip().casefold()
    return [
        row
        for row in rows
        if (not states or row.state in states)
        and (not needle or needle in row.provision.casefold() or needle in row.obligation.casefold())
        and (not imminent_only or row.is_imminent)
        and (not officer_only or row.is_officer_duty)
    ]


@router.get("/police/deadlines", response_model=RegisterResponse)
async def deadline_register(
    user: Annotated[User, Depends(_OWN)],
    session: Session,
    state: Annotated[list[RegisterState] | None, Query()] = None,
    case_id: uuid.UUID | None = None,
    provision: str | None = Query(default=None, max_length=80),
    imminent_only: bool = False,
    officer_only: bool = False,
    include_closed: bool = False,
    imminent_hours: int = Query(default=IMMINENT_HOURS, ge=1, le=24 * 30),
) -> RegisterResponse:
    """Every deadline across the caller's own police cases."""
    query = select(Case).where(Case.owner_id == user.id, Case.role_type == CaseRoleType.POLICE)
    if case_id is not None:
        target = await session.get(Case, case_id)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        if target.owner_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this case")
        query = query.where(Case.id == case_id)
    elif not include_closed:
        query = query.where(Case.status == "open")
    cases = list(await session.scalars(query))
    now = datetime.now(timezone.utc)
    rows, without_facts = await _register_for(session, cases, now, imminent_hours)
    shown = sort_rows(_apply_filters(rows, state, provision, imminent_only, officer_only))
    return RegisterResponse(
        evaluated_at=now,
        imminent_hours=imminent_hours,
        rows=[_row_response(row) for row in shown],
        counts=summarise(shown),
        cases_without_facts=[CaseReference(case_id=c.id, title=c.title) for c in without_facts],
    )


async def _known_deadline_keys(session: AsyncSession, case: Case) -> set[str]:
    row = await session.scalar(select(FactsRow).where(FactsRow.case_id == case.id))
    keys = {d.key for d in investigation_deadlines(_facts(row))}
    searches = await session.scalars(
        select(PoliceSearch.id).where(PoliceSearch.case_id == case.id, PoliceSearch.basis == "section_185")
    )
    keys |= {f"search_record_to_magistrate:{search_id}" for search_id in searches}
    return keys


@router.put("/cases/{case_id}/police/deadlines/{key}/completion", response_model=RegisterRowResponse)
async def record_completion(
    case_id: uuid.UUID,
    key: str,
    request: CompletionRequest,
    user: Owner,
    session: Session,
) -> RegisterRowResponse:
    """When the step was actually taken."""
    _refuse_future(request.completed_at, "The completion time")
    case = await session.get(Case, case_id)
    if key not in await _known_deadline_keys(session, case):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That deadline does not apply to this case")
    row = await session.scalar(
        select(PoliceDeadlineCompletion).where(
            PoliceDeadlineCompletion.case_id == case_id,
            PoliceDeadlineCompletion.deadline_key == key,
        )
    )
    if row is None:
        row = PoliceDeadlineCompletion(case_id=case_id, deadline_key=key, completed_at=request.completed_at)
        session.add(row)
    row.completed_at = request.completed_at
    row.note = request.note
    row.recorded_by = user.id
    _audit(session, user, "police.deadline_completion_recorded", case_id, deadline=key)
    await session.commit()
    rows, _ = await _register_for(session, [case], datetime.now(timezone.utc), IMMINENT_HOURS)
    return _row_response(next(r for r in rows if r.key == key))


@router.delete("/cases/{case_id}/police/deadlines/{key}/completion", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_completion(case_id: uuid.UUID, key: str, user: Owner, session: Session) -> Response:
    row = await session.scalar(
        select(PoliceDeadlineCompletion).where(
            PoliceDeadlineCompletion.case_id == case_id,
            PoliceDeadlineCompletion.deadline_key == key,
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No completion is recorded for that deadline")
    await session.delete(row)
    _audit(session, user, "police.deadline_completion_withdrawn", case_id, deadline=key)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Compliance as a record


async def _compliance_items(
    session: AsyncSession, case_id: uuid.UUID, action: PoliceAction
) -> ComplianceRecordResponse:
    facts = await session.scalar(select(FactsRow).where(FactsRow.case_id == case_id))
    flags = effective_flags(facts.compliance_flags if facts else None, {})
    stored = ((facts.compliance_status if facts else None) or {}).get(str(action)) or {}
    recorded = {k: ComplianceStatus(v) for k, v in stored.items() if v in set(ComplianceStatus)}
    records = {
        row.requirement_key: row
        for row in await session.scalars(
            select(PoliceComplianceRecord).where(
                PoliceComplianceRecord.case_id == case_id,
                PoliceComplianceRecord.action == str(action),
            )
        )
    }
    labels = {
        row.id: row.exhibit_label
        for row in await session.scalars(select(PoliceEvidenceItem).where(PoliceEvidenceItem.case_id == case_id))
    }
    items = []
    for item in compliance_checklist(action, status=recorded, **flags):
        record = records.get(item.key)
        has_record = bool(record and (record.occurred_at or record.evidence_note or record.evidence_item_id))
        items.append(
            ComplianceRecordItem(
                key=item.key,
                requirement=item.requirement,
                provision=item.provision,
                consequence=item.consequence,
                applies_because=item.applies_because,
                status=item.status,
                occurred_at=record.occurred_at if record else None,
                evidence_note=record.evidence_note if record else None,
                evidence_item_id=record.evidence_item_id if record else None,
                evidence_label=labels.get(record.evidence_item_id) if record else None,
                needs_record=item.status is ComplianceStatus.SATISFIED and not has_record,
            )
        )
    return ComplianceRecordResponse(action=action, items=items, flags=flags)


@router.get("/cases/{case_id}/police/compliance-records", response_model=ComplianceRecordResponse)
async def read_compliance_records(
    case_id: uuid.UUID,
    _: Owner,
    session: Session,
    action: PoliceAction = PoliceAction.ARREST,
) -> ComplianceRecordResponse:
    return await _compliance_items(session, case_id, action)


@router.put("/cases/{case_id}/police/compliance-records/{action}/{key}", response_model=ComplianceRecordResponse)
async def write_compliance_record(
    case_id: uuid.UUID,
    action: PoliceAction,
    key: str,
    request: ComplianceRecordRequest,
    user: Owner,
    session: Session,
) -> ComplianceRecordResponse:
    """Attach the date and the evidence to one duty, and optionally set its status."""
    every_row = compliance_checklist(
        action, **{flag: flag != "memorandum_attested_by_family" for flag in COMPLIANCE_FLAGS}
    )
    if key not in {item.key for item in every_row}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That requirement is not part of this action")
    _refuse_future(request.occurred_at, "The date of the duty")
    if request.evidence_item_id is not None:
        await _in_case(session, PoliceEvidenceItem, case_id, request.evidence_item_id, "Evidence item")

    facts = await session.scalar(select(FactsRow).where(FactsRow.case_id == case_id))
    if facts is None:
        facts = FactsRow(case_id=case_id)
        session.add(facts)
    if request.status is not None:
        stored = dict(facts.compliance_status or {})
        current = dict(stored.get(str(action)) or {})
        if request.status is ComplianceStatus.NOT_RECORDED:
            current.pop(key, None)
        else:
            current[key] = str(request.status)
        stored[str(action)] = current
        facts.compliance_status = stored

    record = await session.scalar(
        select(PoliceComplianceRecord).where(
            PoliceComplianceRecord.case_id == case_id,
            PoliceComplianceRecord.action == str(action),
            PoliceComplianceRecord.requirement_key == key,
        )
    )
    if record is None:
        record = PoliceComplianceRecord(case_id=case_id, action=str(action), requirement_key=key)
        session.add(record)
    record.occurred_at = request.occurred_at
    record.evidence_note = request.evidence_note
    record.evidence_item_id = request.evidence_item_id
    record.recorded_by = user.id
    _audit(
        session, user, "police.compliance_record_written", case_id,
        police_action=str(action), requirement=key,
        status=str(request.status) if request.status else None,
    )
    await session.commit()
    return await _compliance_items(session, case_id, action)


# ---- Evidence and custody


def _evidence_response(item: PoliceEvidenceItem, events: list[PoliceCustodyEvent]) -> EvidenceResponse:
    ordered = sorted(events, key=lambda e: e.occurred_at)
    finding = analyse_chain(
        seized_by=item.seized_by,
        seized_at=item.seized_at,
        hops=[
            CustodyHop(
                id=str(e.id), occurred_at=e.occurred_at, from_person=e.from_person, to_person=e.to_person,
                corrects_event_id=str(e.corrects_event_id) if e.corrects_event_id else None,
            )
            for e in ordered
        ],
    )
    response = EvidenceResponse.model_validate(item, from_attributes=True)
    response.custody_events = [CustodyEventResponse.model_validate(e) for e in ordered]
    response.chain = ChainResponse(
        state=finding.state.value, current_holder=finding.current_holder, issues=list(finding.issues)
    )
    return response


async def _events_by_item(session: AsyncSession, case_id: uuid.UUID) -> dict[uuid.UUID, list[PoliceCustodyEvent]]:
    grouped: dict[uuid.UUID, list[PoliceCustodyEvent]] = {}
    for event in await session.scalars(select(PoliceCustodyEvent).where(PoliceCustodyEvent.case_id == case_id)):
        grouped.setdefault(event.evidence_item_id, []).append(event)
    return grouped


@router.get("/cases/{case_id}/police/evidence", response_model=EvidenceListResponse)
async def list_evidence(case_id: uuid.UUID, _: Owner, session: Session) -> EvidenceListResponse:
    events = await _events_by_item(session, case_id)
    rows = await session.scalars(
        select(PoliceEvidenceItem).where(PoliceEvidenceItem.case_id == case_id).order_by(PoliceEvidenceItem.created_at)
    )
    return EvidenceListResponse(items=[_evidence_response(row, events.get(row.id, [])) for row in rows])


@router.post("/cases/{case_id}/police/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def add_evidence(case_id: uuid.UUID, request: EvidenceCreate, user: Owner, session: Session) -> EvidenceResponse:
    _refuse_future(request.seized_at, "The seizure time")
    if request.search_id is not None:
        await _in_case(session, PoliceSearch, case_id, request.search_id, "Search")
    item = PoliceEvidenceItem(case_id=case_id, recorded_by=user.id, **request.model_dump())
    session.add(item)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That exhibit label is already used in this case") from exc
    _audit(session, user, "police.evidence_added", case_id, evidence_item=str(item.id), category=item.category)
    await session.commit()
    await session.refresh(item)
    return _evidence_response(item, [])


@router.patch("/cases/{case_id}/police/evidence/{item_id}", response_model=EvidenceResponse)
async def update_evidence(
    case_id: uuid.UUID, item_id: uuid.UUID, request: EvidenceUpdate, user: Owner, session: Session
) -> EvidenceResponse:
    item = await _in_case(session, PoliceEvidenceItem, case_id, item_id, "Evidence item")
    changes = request.model_dump(exclude_unset=True)
    _refuse_future(changes.get("seized_at"), "The seizure time")
    if changes.get("search_id") is not None:
        await _in_case(session, PoliceSearch, case_id, changes["search_id"], "Search")
    for field, value in changes.items():
        setattr(item, field, value)
    _audit(session, user, "police.evidence_updated", case_id, evidence_item=str(item.id), fields=sorted(changes))
    await session.commit()
    await session.refresh(item)
    events = await _events_by_item(session, case_id)
    return _evidence_response(item, events.get(item.id, []))


@router.post(
    "/cases/{case_id}/police/evidence/{item_id}/custody",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_custody_event(
    case_id: uuid.UUID, item_id: uuid.UUID, request: CustodyEventCreate, user: Owner, session: Session
) -> EvidenceResponse:
    """Append a hand-over. There is no route to edit or remove one."""
    item = await _in_case(session, PoliceEvidenceItem, case_id, item_id, "Evidence item")
    _refuse_future(request.occurred_at, "The hand-over time")
    if request.corrects_event_id is not None:
        corrected = await _in_case(session, PoliceCustodyEvent, case_id, request.corrects_event_id, "Custody entry")
        if corrected.evidence_item_id != item_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That entry belongs to a different item")
    session.add(PoliceCustodyEvent(case_id=case_id, evidence_item_id=item_id, recorded_by=user.id, **request.model_dump()))
    _audit(
        session, user, "police.custody_event_added", case_id,
        evidence_item=str(item_id), corrects=str(request.corrects_event_id) if request.corrects_event_id else None,
    )
    await session.commit()
    await session.refresh(item)
    events = await _events_by_item(session, case_id)
    return _evidence_response(item, events.get(item.id, []))


# ---- Witnesses


def _witness_duties(witness: PoliceWitness) -> list[WitnessDuty]:
    def tri(value: str) -> str:
        return {"yes": "done", "no": "not_done"}.get(value, "cannot_be_determined")

    duties: list[WitnessDuty] = []
    if witness.statement_recorded_at:
        duties.append(
            WitnessDuty(
                key="separate_true_record",
                duty="A separate and true record of the statement was made.",
                provision="BNSS s.180(3)",
                state="done" if witness.statement_mode else "cannot_be_determined",
            )
        )
        duties.append(
            WitnessDuty(
                key="inserted_in_diary",
                duty="The statement is inserted in the case diary.",
                provision="BNSS s.192(2)",
                state=tri(witness.inserted_in_diary),
            )
        )
        if witness.needs_woman_officer:
            duties.append(
                WitnessDuty(
                    key="woman_officer",
                    duty="The statement was recorded by a woman police officer or any woman officer.",
                    provision="BNSS s.180(3)",
                    state=tri(witness.recorded_by_woman_officer),
                )
            )
    if witness.attends_only_at_residence:
        duties.append(
            WitnessDuty(
                key="attendance_at_residence",
                duty="May not be required to attend anywhere but where this person resides, unless willing.",
                provision="BNSS s.179(1)",
                state="cannot_be_determined",
            )
        )
    return duties


def _witness_response(witness: PoliceWitness) -> WitnessResponse:
    response = WitnessResponse.model_validate(witness)
    response.duties = _witness_duties(witness)
    return response


@router.get("/cases/{case_id}/police/witnesses", response_model=WitnessListResponse)
async def list_witnesses(case_id: uuid.UUID, _: Owner, session: Session) -> WitnessListResponse:
    rows = await session.scalars(
        select(PoliceWitness).where(PoliceWitness.case_id == case_id).order_by(PoliceWitness.created_at)
    )
    return WitnessListResponse(witnesses=[_witness_response(row) for row in rows])


@router.post("/cases/{case_id}/police/witnesses", response_model=WitnessResponse, status_code=status.HTTP_201_CREATED)
async def add_witness(case_id: uuid.UUID, request: WitnessCreate, user: Owner, session: Session) -> WitnessResponse:
    witness = PoliceWitness(case_id=case_id, recorded_by=user.id, **request.model_dump())
    session.add(witness)
    await session.flush()
    _audit(session, user, "police.witness_added", case_id, witness=str(witness.id), category=witness.category)
    await session.commit()
    await session.refresh(witness)
    return _witness_response(witness)


@router.patch("/cases/{case_id}/police/witnesses/{witness_id}", response_model=WitnessResponse)
async def update_witness(
    case_id: uuid.UUID, witness_id: uuid.UUID, request: WitnessUpdate, user: Owner, session: Session
) -> WitnessResponse:
    witness = await _in_case(session, PoliceWitness, case_id, witness_id, "Witness")
    changes = request.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(witness, field, value)
    _audit(session, user, "police.witness_updated", case_id, witness=str(witness.id), fields=sorted(changes))
    await session.commit()
    await session.refresh(witness)
    return _witness_response(witness)


# ---- Search and seizure


def _search_response(search: PoliceSearch, now: datetime) -> SearchResponse:
    checks = evaluate_search(
        SearchRecord(
            basis=search.basis,
            searched_at=search.searched_at,
            grounds_recorded_at=search.grounds_recorded_at,
            record_sent_to_magistrate_at=search.record_sent_to_magistrate_at,
            recording_forwarded_at=search.recording_forwarded_at,
            witness_count=search.witness_count,
            answers=search.answers or {},
        ),
        now,
    )
    summary = overall(checks)
    response = SearchResponse.model_validate(search)
    response.finding = str(summary["finding"])
    response.counts = dict(summary["counts"])
    response.checks = [
        SearchCheckResponse(
            key=c.key, requirement=c.requirement, provision=c.provision, verdict=c.verdict.value, detail=c.detail
        )
        for c in checks
    ]
    return response


@router.get("/police/search-questions")
async def search_questions(_: Annotated[User, Depends(_OWN)]) -> dict:
    return CHECK_QUESTIONS


@router.get("/cases/{case_id}/police/searches", response_model=SearchListResponse)
async def list_searches(case_id: uuid.UUID, _: Owner, session: Session) -> SearchListResponse:
    now = datetime.now(timezone.utc)
    rows = await session.scalars(
        select(PoliceSearch).where(PoliceSearch.case_id == case_id).order_by(PoliceSearch.created_at)
    )
    return SearchListResponse(searches=[_search_response(row, now) for row in rows])


@router.post("/cases/{case_id}/police/searches", response_model=SearchResponse, status_code=status.HTTP_201_CREATED)
async def add_search(case_id: uuid.UUID, request: SearchWrite, user: Owner, session: Session) -> SearchResponse:
    _refuse_future(request.searched_at, "The search time")
    search = PoliceSearch(case_id=case_id, recorded_by=user.id, **request.model_dump())
    session.add(search)
    await session.flush()
    _audit(session, user, "police.search_recorded", case_id, search=str(search.id), basis=search.basis)
    await session.commit()
    await session.refresh(search)
    return _search_response(search, datetime.now(timezone.utc))


@router.put("/cases/{case_id}/police/searches/{search_id}", response_model=SearchResponse)
async def update_search(
    case_id: uuid.UUID, search_id: uuid.UUID, request: SearchWrite, user: Owner, session: Session
) -> SearchResponse:
    search = await _in_case(session, PoliceSearch, case_id, search_id, "Search")
    _refuse_future(request.searched_at, "The search time")
    for field, value in request.model_dump().items():
        setattr(search, field, value)
    _audit(session, user, "police.search_updated", case_id, search=str(search.id), basis=search.basis)
    await session.commit()
    await session.refresh(search)
    return _search_response(search, datetime.now(timezone.utc))


# ---- Offence elements


@router.get("/police/offences", response_model=OffenceCatalogue)
async def offence_catalogue(_: Annotated[User, Depends(_OWN)]) -> OffenceCatalogue:
    return OffenceCatalogue(
        offences=[
            OffenceCatalogueEntry(
                key=o.key, title=o.title, provision=o.provision, limits=o.limits, element_count=len(o.elements)
            )
            for o in OFFENCES.values()
        ]
    )


def _assessment_response(key: str, stored: dict | None) -> OffenceAssessmentResponse:
    offence = OFFENCES[key]
    elements = assess(offence, stored)
    return OffenceAssessmentResponse(
        offence_key=key,
        title=offence.title,
        provision=offence.provision,
        limits=offence.limits,
        finding=overall_finding(elements).value,
        elements=[ElementResponse(**element) for element in elements],
    )


@router.get("/cases/{case_id}/police/offences", response_model=OffenceAssessmentList)
async def list_assessments(case_id: uuid.UUID, _: Owner, session: Session) -> OffenceAssessmentList:
    rows = await session.scalars(
        select(PoliceOffenceAssessment).where(PoliceOffenceAssessment.case_id == case_id)
        .order_by(PoliceOffenceAssessment.updated_at.desc())
    )
    return OffenceAssessmentList(
        assessments=[_assessment_response(r.offence_key, r.elements) for r in rows if r.offence_key in OFFENCES]
    )


@router.put("/cases/{case_id}/police/offences/{offence_key}", response_model=OffenceAssessmentResponse)
async def write_assessment(
    case_id: uuid.UUID, offence_key: str, request: OffenceAssessmentWrite, user: Owner, session: Session
) -> OffenceAssessmentResponse:
    """Replaces the assessment. An element left out goes back to cannot be determined."""
    offence = OFFENCES.get(offence_key)
    if offence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That offence is not in the catalogue")
    known = {element.key for element in offence.elements}
    unknown = set(request.elements) - known
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Not an element of this offence: {sorted(unknown)}")

    evidence_ids = set(
        await session.scalars(
            select(PoliceEvidenceItem.id).where(
                PoliceEvidenceItem.case_id == case_id, PoliceEvidenceItem.status != "entered_in_error"
            )
        )
    )
    witness_ids = set(
        await session.scalars(
            select(PoliceWitness.id).where(
                PoliceWitness.case_id == case_id, PoliceWitness.status != "entered_in_error"
            )
        )
    )
    stored: dict[str, dict] = {}
    for key, element in request.elements.items():
        if set(element.evidence_item_ids) - evidence_ids or set(element.witness_ids) - witness_ids:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "A linked item or witness is not on record in this case"
            )
        if element.state is ElementState.ESTABLISHED and not (element.evidence_item_ids or element.witness_ids):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "An element can be marked established only with an exhibit or witness linked to it.",
            )
        stored[key] = {
            "state": element.state.value,
            "evidence_item_ids": [str(i) for i in element.evidence_item_ids],
            "witness_ids": [str(i) for i in element.witness_ids],
            "note": element.note or "",
        }

    row = await session.scalar(
        select(PoliceOffenceAssessment).where(
            PoliceOffenceAssessment.case_id == case_id, PoliceOffenceAssessment.offence_key == offence_key
        )
    )
    if row is None:
        row = PoliceOffenceAssessment(case_id=case_id, offence_key=offence_key)
        session.add(row)
    row.elements = stored
    row.recorded_by = user.id
    _audit(
        session, user, "police.offence_assessed", case_id, offence=offence_key,
        states={key: value["state"] for key, value in stored.items()},
    )
    await session.commit()
    return _assessment_response(offence_key, stored)


@router.delete("/cases/{case_id}/police/offences/{offence_key}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_assessment(case_id: uuid.UUID, offence_key: str, user: Owner, session: Session) -> Response:
    row = await session.scalar(
        select(PoliceOffenceAssessment).where(
            PoliceOffenceAssessment.case_id == case_id, PoliceOffenceAssessment.offence_key == offence_key
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That offence has not been assessed in this case")
    await session.delete(row)
    _audit(session, user, "police.offence_assessment_removed", case_id, offence=offence_key)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Remand


async def _remand(session: AsyncSession, case_id: uuid.UUID) -> RemandResponse:
    rows = list(
        await session.scalars(
            select(PoliceRemandPeriod).where(PoliceRemandPeriod.case_id == case_id).order_by(PoliceRemandPeriod.from_date)
        )
    )
    facts = await session.scalar(select(FactsRow).where(FactsRow.case_id == case_id))
    summary = remand_summary(
        [RemandPeriod(r.custody_type, r.from_date, r.to_date) for r in rows],
        first_remand_at=facts.first_remand_at if facts else None,
        gravity=facts.gravity if facts else OffenceGravity.UNKNOWN,
        today=datetime.now(timezone.utc).date(),
    )
    return RemandResponse(
        periods=[RemandPeriodResponse.model_validate(r) for r in rows],
        police_days_used=summary.police_days_used,
        police_days_left=summary.police_days_left,
        judicial_days=summary.judicial_days,
        first_remand_date=summary.first_remand_date,
        police_custody_window_ends=summary.police_custody_window_ends,
        window_days=summary.window_days,
        undetermined_because=summary.undetermined_because,
        findings=list(summary.findings),
    )


@router.get("/cases/{case_id}/police/remand", response_model=RemandResponse)
async def read_remand(case_id: uuid.UUID, _: Owner, session: Session) -> RemandResponse:
    return await _remand(session, case_id)


@router.post("/cases/{case_id}/police/remand", response_model=RemandResponse, status_code=status.HTTP_201_CREATED)
async def add_remand(case_id: uuid.UUID, request: RemandCreate, user: Owner, session: Session) -> RemandResponse:
    session.add(PoliceRemandPeriod(case_id=case_id, recorded_by=user.id, **request.model_dump()))
    _audit(session, user, "police.remand_recorded", case_id, custody_type=request.custody_type)
    await session.commit()
    return await _remand(session, case_id)


@router.delete("/cases/{case_id}/police/remand/{period_id}", response_model=RemandResponse)
async def remove_remand(case_id: uuid.UUID, period_id: uuid.UUID, user: Owner, session: Session) -> RemandResponse:
    row = await _in_case(session, PoliceRemandPeriod, case_id, period_id, "Remand period")
    await session.delete(row)
    _audit(session, user, "police.remand_removed", case_id, period=str(period_id))
    await session.commit()
    return await _remand(session, case_id)


# ---- Case diary


async def _diary(session: AsyncSession, case_id: uuid.UUID) -> DiaryResponse:
    rows = list(
        await session.scalars(
            select(PoliceDiaryEntry).where(PoliceDiaryEntry.case_id == case_id).order_by(PoliceDiaryEntry.page_no)
        )
    )
    return DiaryResponse(
        entries=[DiaryEntryResponse.model_validate(r) for r in rows],
        days_without_entry=diary_gaps([r.entry_date for r in rows], until=datetime.now(timezone.utc).date()),
    )


@router.get("/cases/{case_id}/police/diary", response_model=DiaryResponse)
async def read_diary(case_id: uuid.UUID, _: Owner, session: Session) -> DiaryResponse:
    return await _diary(session, case_id)


@router.post("/cases/{case_id}/police/diary", response_model=DiaryResponse, status_code=status.HTTP_201_CREATED)
async def add_diary_entry(case_id: uuid.UUID, request: DiaryCreate, user: Owner, session: Session) -> DiaryResponse:
    """Appended, and numbered here. s.192(3) pagination is what makes a later insertion
    visible, so a caller does not get to choose the page."""
    if request.entry_date > datetime.now(timezone.utc).date() + timedelta(days=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A diary entry cannot be dated in the future")
    last = await session.scalar(select(func.max(PoliceDiaryEntry.page_no)).where(PoliceDiaryEntry.case_id == case_id))
    if request.corrects_page is not None and request.corrects_page > (last or 0):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That page does not exist yet")
    entry = PoliceDiaryEntry(case_id=case_id, page_no=(last or 0) + 1, recorded_by=user.id, **request.model_dump())
    session.add(entry)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Another entry was added first. Try again.") from exc
    _audit(session, user, "police.diary_entry_added", case_id, page=entry.page_no, corrects=request.corrects_page)
    await session.commit()
    return await _diary(session, case_id)


# ---- Drafts


def _plain(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def _case_material(session: AsyncSession, case_id: uuid.UUID) -> dict:
    """Everything a draft or the case file may read, for this case only."""
    facts = await session.scalar(select(FactsRow).where(FactsRow.case_id == case_id))
    events = await _events_by_item(session, case_id)
    evidence = []
    for item in await session.scalars(
        select(PoliceEvidenceItem).where(PoliceEvidenceItem.case_id == case_id).order_by(PoliceEvidenceItem.created_at)
    ):
        response = _evidence_response(item, events.get(item.id, []))
        evidence.append(response.model_dump())
    witnesses = [
        _plain(row)
        for row in await session.scalars(
            select(PoliceWitness).where(PoliceWitness.case_id == case_id).order_by(PoliceWitness.created_at)
        )
    ]
    now = datetime.now(timezone.utc)
    searches = [
        _search_response(row, now).model_dump()
        for row in await session.scalars(
            select(PoliceSearch).where(PoliceSearch.case_id == case_id).order_by(PoliceSearch.created_at)
        )
    ]
    diary = (await _diary(session, case_id)).model_dump()
    remand = (await _remand(session, case_id)).model_dump()
    assessments = [
        _assessment_response(r.offence_key, r.elements).model_dump()
        for r in await session.scalars(
            select(PoliceOffenceAssessment).where(PoliceOffenceAssessment.case_id == case_id)
        )
        if r.offence_key in OFFENCES
    ]
    flags = effective_flags(facts.compliance_flags if facts else None, {})
    fact_values = {field: getattr(facts, field) for field in FACT_FIELDS} if facts else {}
    fact_values["clause_h_applies"] = flags["is_listed_sexual_offence"]
    return {
        "facts_row": facts,
        "facts": fact_values,
        "flags": flags,
        "evidence": evidence,
        "witnesses": witnesses,
        "searches": searches,
        "diary": diary["entries"],
        "remand": remand,
        "assessments": assessments,
    }


def _draft_type_of(row: GeneratedDocument) -> str:
    return row.doc_type.removeprefix(DRAFT_DOC_PREFIX)


def _draft_response(row: GeneratedDocument) -> DraftResponse:
    content = row.content or {}
    return DraftResponse(
        id=row.id,
        case_id=row.case_id,
        draft_type=_draft_type_of(row),
        title=str(content.get("title") or ""),
        version=row.version,
        status=row.status,
        rendered_text=str(content.get("rendered_text") or ""),
        missing_fields=list(content.get("missing_fields") or []),
        provisions=list(content.get("provisions") or []),
        disclaimer=str(content.get("disclaimer") or ""),
        inputs=dict(content.get("inputs") or {}),
        created_at=row.created_at,
    )


@router.get("/police/draft-types")
async def draft_types(_: Annotated[User, Depends(_OWN)]) -> dict:
    return {"draft_types": [{"key": key, "title": value[0]} for key, value in DRAFT_TYPES.items()]}


@router.get("/cases/{case_id}/police/drafts", response_model=DraftListResponse)
async def list_drafts(case_id: uuid.UUID, _: Owner, session: Session) -> DraftListResponse:
    rows = await session.scalars(
        select(GeneratedDocument)
        .where(GeneratedDocument.case_id == case_id, GeneratedDocument.doc_type.startswith(DRAFT_DOC_PREFIX))
        .order_by(GeneratedDocument.created_at.desc())
    )
    return DraftListResponse(
        drafts=[
            DraftSummary(
                id=row.id,
                draft_type=_draft_type_of(row),
                title=str((row.content or {}).get("title") or ""),
                version=row.version,
                status=row.status,
                missing_field_count=len((row.content or {}).get("missing_fields") or []),
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.post("/cases/{case_id}/police/drafts", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(case_id: uuid.UUID, request: DraftCreate, user: Owner, session: Session) -> DraftResponse:
    """Each generation is a new immutable version, with status "draft"."""
    case = await session.get(Case, case_id)
    material = await _case_material(session, case_id)
    context = DraftContext(
        case_title=case.title,
        officer_name=user.name,
        facts=material["facts"],
        evidence=[e for e in material["evidence"] if e["status"] != "entered_in_error"],
        witnesses=[w for w in material["witnesses"] if w["status"] != "entered_in_error"],
        searches=material["searches"],
        remand=material["remand"],
        diary=material["diary"],
        offences=[a["provision"] for a in material["assessments"]],
        now=datetime.now(timezone.utc),
    )
    rendered = render_draft(request.draft_type, context, request.inputs)
    doc_type = f"{DRAFT_DOC_PREFIX}{request.draft_type}"
    version = (
        await session.scalar(
            select(func.max(GeneratedDocument.version)).where(
                GeneratedDocument.case_id == case_id, GeneratedDocument.doc_type == doc_type
            )
        )
        or 0
    ) + 1
    row = GeneratedDocument(
        case_id=case_id,
        doc_type=doc_type,
        version=version,
        status="draft",
        content={
            "title": rendered.title,
            "rendered_text": rendered.rendered_text,
            "missing_fields": rendered.missing_fields,
            "provisions": rendered.provisions,
            "disclaimer": rendered.disclaimer,
            "inputs": request.inputs,
        },
    )
    session.add(row)
    await session.flush()
    _audit(
        session, user, "police.draft_generated", case_id,
        draft=str(row.id), draft_type=request.draft_type, version=version,
        missing=len(rendered.missing_fields),
    )
    await session.commit()
    await session.refresh(row)
    return _draft_response(row)


@router.get("/cases/{case_id}/police/drafts/{draft_id}", response_model=DraftResponse)
async def read_draft(case_id: uuid.UUID, draft_id: uuid.UUID, _: Owner, session: Session) -> DraftResponse:
    row = await session.scalar(
        select(GeneratedDocument).where(
            GeneratedDocument.id == draft_id,
            GeneratedDocument.case_id == case_id,
            GeneratedDocument.doc_type.startswith(DRAFT_DOC_PREFIX),
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found in this case")
    return _draft_response(row)


# ---- The case file


@router.get("/cases/{case_id}/police/case-file", response_model=CaseFileResponse)
async def export_case_file(
    case_id: uuid.UUID,
    user: Owner,
    session: Session,
    include_witness_contact: bool = False,
    include_drafts: bool = True,
) -> CaseFileResponse:
    """A printable compilation. Witness contact details stay out unless asked for: this
    is the copy most likely to leave the building."""
    case = await session.get(Case, case_id)
    material = await _case_material(session, case_id)
    now = datetime.now(timezone.utc)
    rows, _ = await _register_for(session, [case], now, IMMINENT_HOURS)
    facts_row = material["facts_row"]

    labels = {e["id"]: e["exhibit_label"] for e in material["evidence"]}
    compliance = []
    for action in PoliceAction:
        response = await _compliance_items(session, case_id, action)
        compliance.append(
            {
                "action": str(action),
                "items": [
                    {
                        "requirement": item.requirement,
                        "provision": item.provision,
                        "status": item.status.value,
                        "occurred_at": item.occurred_at,
                        "evidence": " / ".join(
                            part
                            for part in (labels.get(item.evidence_item_id), item.evidence_note)
                            if part
                        ) or None,
                    }
                    for item in response.items
                ],
            }
        )

    drafts: list[dict] = []
    if include_drafts:
        generated = await session.scalars(
            select(GeneratedDocument)
            .where(GeneratedDocument.case_id == case_id, GeneratedDocument.doc_type.startswith(DRAFT_DOC_PREFIX))
            .order_by(GeneratedDocument.doc_type, GeneratedDocument.version.desc())
        )
        seen: set[str] = set()
        for row in generated:
            if row.doc_type in seen:
                continue
            seen.add(row.doc_type)
            content = row.content or {}
            drafts.append(
                {
                    "title": str(content.get("title") or row.doc_type),
                    "version": row.version,
                    "rendered_text": str(content.get("rendered_text") or ""),
                }
            )

    html = render_case_file(
        {
            "case": {"title": case.title, "status": case.status, "created_at": case.created_at},
            "generated_at": now,
            "officer_name": user.name,
            "include_witness_contact": include_witness_contact,
            "facts": material["facts"] if facts_row else {},
            "deadlines": [
                {
                    "obligation": row.obligation,
                    "provision": row.provision,
                    "due_at": row.due_at,
                    "state": row.state.value,
                    "state_reason": row.state_reason,
                }
                for row in sort_rows(rows)
            ],
            "compliance": compliance,
            "evidence": material["evidence"],
            "witnesses": [w for w in material["witnesses"] if w["status"] != "entered_in_error"],
            "searches": material["searches"],
            "offences": material["assessments"],
            "remand": material["remand"],
            "diary": material["diary"],
            "drafts": drafts,
        }
    )
    missing = [
        label
        for label, present in (
            ("dates", bool(facts_row)),
            ("evidence", bool(material["evidence"])),
            ("witnesses", bool(material["witnesses"])),
            ("searches", bool(material["searches"])),
            ("offence assessment", bool(material["assessments"])),
            ("case diary", bool(material["diary"])),
            ("drafts", bool(drafts)),
        )
        if not present
    ]
    _audit(
        session, user, "police.case_file_exported", case_id,
        include_witness_contact=include_witness_contact, include_drafts=include_drafts,
    )
    await session.commit()
    return CaseFileResponse(
        case_id=case_id,
        generated_at=now,
        included_witness_contact=include_witness_contact,
        html=html,
        missing_sections=missing,
    )


# ---- Who has looked


_SUPERVISOR_CASE_VIEW = "police.supervisor_case_view"


@router.get("/cases/{case_id}/police/access-log", response_model=AccessLogResponse)
async def access_log(case_id: uuid.UUID, _: Owner, session: Session) -> AccessLogResponse:
    """Who else has looked at this case's summary. An officer can always see it."""
    rows = await session.execute(
        select(AuditLog, User.name)
        .join(User, User.id == AuditLog.user_id, isouter=True)
        .where(AuditLog.resource_id == case_id, AuditLog.action == _SUPERVISOR_CASE_VIEW)
        .order_by(AuditLog.timestamp.desc())
        .limit(200)
    )
    return AccessLogResponse(
        entries=[
            AccessEntry(at=log.timestamp, who=name or "Former user", what="Viewed this case in the supervisor summary")
            for log, name in rows
        ]
    )


# ---- Units


async def _unit_response(session: AsyncSession, unit: PoliceUnit) -> UnitResponse:
    rows = await session.execute(
        select(PoliceUnitMember, User)
        .join(User, User.id == PoliceUnitMember.user_id)
        .where(PoliceUnitMember.unit_id == unit.id)
        .order_by(User.name)
    )
    return UnitResponse(
        id=unit.id,
        name=unit.name,
        members=[
            UnitMemberResponse(user_id=user.id, name=user.name, email=user.email, role=member.role)
            for member, user in rows
        ],
    )


@router.get("/police/units", response_model=UnitListResponse)
async def list_units(_: Annotated[User, Depends(_MANAGE_UNITS)], session: Session) -> UnitListResponse:
    units = await session.scalars(select(PoliceUnit).order_by(PoliceUnit.name))
    return UnitListResponse(units=[await _unit_response(session, unit) for unit in units])


@router.post("/police/units", response_model=UnitResponse, status_code=status.HTTP_201_CREATED)
async def create_unit(request: UnitCreate, admin: Annotated[User, Depends(_MANAGE_UNITS)], session: Session) -> UnitResponse:
    unit = PoliceUnit(name=request.name.strip(), created_by=admin.id)
    session.add(unit)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A unit with that name already exists") from exc
    _audit(session, admin, "police.unit_created", None, unit=str(unit.id))
    await session.commit()
    return await _unit_response(session, unit)


@router.put("/police/units/{unit_id}/members", response_model=UnitResponse)
async def set_unit_member(
    unit_id: uuid.UUID, request: UnitMemberWrite, admin: Annotated[User, Depends(_MANAGE_UNITS)], session: Session
) -> UnitResponse:
    """The explicit grant. Only an administrator writes this, and it is always audited."""
    unit = await session.get(PoliceUnit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unit not found")
    target = await session.scalar(select(User).where(User.email == request.email.strip().lower()))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that email")
    if target.role is not UserRole.POLICE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only a police account can join a unit")
    member = await session.scalar(
        select(PoliceUnitMember).where(PoliceUnitMember.unit_id == unit_id, PoliceUnitMember.user_id == target.id)
    )
    previous = member.role if member else None
    if member is None:
        member = PoliceUnitMember(unit_id=unit_id, user_id=target.id, added_by=admin.id)
        session.add(member)
    member.role = request.role
    _audit(
        session, admin, "police.unit_member_set", None,
        unit=str(unit_id), member=str(target.id), role=request.role, previous_role=previous,
    )
    await session.commit()
    return await _unit_response(session, unit)


@router.delete("/police/units/{unit_id}/members/{user_id}", response_model=UnitResponse)
async def remove_unit_member(
    unit_id: uuid.UUID, user_id: uuid.UUID, admin: Annotated[User, Depends(_MANAGE_UNITS)], session: Session
) -> UnitResponse:
    unit = await session.get(PoliceUnit, unit_id)
    member = await session.scalar(
        select(PoliceUnitMember).where(PoliceUnitMember.unit_id == unit_id, PoliceUnitMember.user_id == user_id)
    )
    if unit is None or member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person is not in this unit")
    await session.delete(member)
    _audit(session, admin, "police.unit_member_removed", None, unit=str(unit_id), member=str(user_id))
    await session.commit()
    return await _unit_response(session, unit)


@router.get("/police/my-units", response_model=MyUnitsResponse)
async def my_units(user: Annotated[User, Depends(_OWN)], session: Session) -> MyUnitsResponse:
    """Which units I am in and who can see my summaries. The officer is entitled to know."""
    mine = await session.execute(
        select(PoliceUnitMember, PoliceUnit)
        .join(PoliceUnit, PoliceUnit.id == PoliceUnitMember.unit_id)
        .where(PoliceUnitMember.user_id == user.id)
        .order_by(PoliceUnit.name)
    )
    units = []
    for member, unit in mine:
        supervisors = await session.scalars(
            select(User.name)
            .join(PoliceUnitMember, PoliceUnitMember.user_id == User.id)
            .where(PoliceUnitMember.unit_id == unit.id, PoliceUnitMember.role == "supervisor")
            .order_by(User.name)
        )
        units.append(
            MyUnitEntry(unit_id=unit.id, unit_name=unit.name, my_role=member.role, supervisors=list(supervisors))
        )
    return MyUnitsResponse(units=units)


# ---- The supervisor's view


def _compliance_counts(facts: FactsRow | None) -> dict[str, int]:
    """Across all four actions, in the same three states as the checklist."""
    counts = {status_.value: 0 for status_ in ComplianceStatus}
    flags = effective_flags(facts.compliance_flags if facts else None, {})
    stored = (facts.compliance_status if facts else None) or {}
    for action in PoliceAction:
        recorded = {
            key: ComplianceStatus(value)
            for key, value in (stored.get(str(action)) or {}).items()
            if value in set(ComplianceStatus)
        }
        for item in compliance_checklist(action, status=recorded, **flags):
            counts[item.status.value] += 1
    return counts


@router.get("/police/supervision/units/{unit_id}", response_model=SupervisedUnitResponse)
async def supervised_unit(
    unit_id: uuid.UUID,
    supervisor: Annotated[User, Depends(_SUPERVISE)],
    session: Session,
    imminent_hours: int = Query(default=IMMINENT_HOURS, ge=1, le=24 * 30),
) -> SupervisedUnitResponse:
    """Compliance and imminent breaches across one unit.

    Counts and deadline states only. No facts, evidence, witnesses, statements, drafts
    or files appear here, and none of those routes open for a supervisor.
    """
    grant = await session.scalar(
        select(PoliceUnitMember).where(
            PoliceUnitMember.unit_id == unit_id,
            PoliceUnitMember.user_id == supervisor.id,
            PoliceUnitMember.role == "supervisor",
        )
    )
    if grant is None:
        _audit(session, supervisor, "police.supervisor_view_refused", None, unit=str(unit_id))
        await session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not supervise this unit")
    unit = await session.get(PoliceUnit, unit_id)

    officers = {
        user.id: user
        for user in await session.scalars(
            select(User)
            .join(PoliceUnitMember, PoliceUnitMember.user_id == User.id)
            .where(
                PoliceUnitMember.unit_id == unit_id,
                User.role == UserRole.POLICE,
                User.is_active.is_(True),
            )
        )
    }
    cases = list(
        await session.scalars(
            select(Case).where(
                Case.owner_id.in_(list(officers)) if officers else Case.id.is_(None),
                Case.role_type == CaseRoleType.POLICE,
                Case.status == "open",
            )
        )
    )
    now = datetime.now(timezone.utc)
    rows, _ = await _register_for(session, cases, now, imminent_hours)
    by_case: dict[str, list[RegisterRow]] = {}
    for row in rows:
        by_case.setdefault(row.case_id, []).append(row)
    facts_rows = {}
    if cases:
        facts_rows = {
            row.case_id: row
            for row in await session.scalars(select(FactsRow).where(FactsRow.case_id.in_([c.id for c in cases])))
        }

    total_compliance = {status_.value: 0 for status_ in ComplianceStatus}
    entries: list[SupervisedCase] = []
    for case in cases:
        case_rows = sort_rows(by_case.get(str(case.id), []))
        compliance = _compliance_counts(facts_rows.get(case.id))
        for key, value in compliance.items():
            total_compliance[key] += value
        entries.append(
            SupervisedCase(
                case_id=case.id,
                title=case.title,
                officer_name=officers[case.owner_id].name,
                has_facts=case.id in facts_rows,
                counts=summarise(case_rows),
                compliance=compliance,
                attention=[
                    SupervisedDeadline(
                        key=row.key,
                        obligation=row.obligation,
                        provision=row.provision,
                        actor=row.actor,
                        due_at=row.due_at,
                        state=row.state.value,
                        state_reason=row.state_reason,
                        is_imminent=row.is_imminent,
                    )
                    for row in case_rows
                    if row.state in (RegisterState.OVERDUE, RegisterState.BREACHED)
                    or row.is_imminent
                ],
            )
        )
        # One row per case, so the owner's access log can show it.
        _audit(session, supervisor, _SUPERVISOR_CASE_VIEW, case.id, unit=str(unit_id))
    _audit(session, supervisor, "police.supervisor_unit_view", None, unit=str(unit_id), cases=len(cases))
    await session.commit()

    entries.sort(
        key=lambda e: (
            -(e.counts.get("overdue", 0) + e.counts.get("imminent", 0)),
            -e.counts.get("breached", 0),
            e.title,
        )
    )
    return SupervisedUnitResponse(
        unit_id=unit_id,
        unit_name=unit.name,
        evaluated_at=now,
        imminent_hours=imminent_hours,
        officer_count=len(officers),
        counts=summarise(rows),
        compliance=total_compliance,
        cases=entries,
    )
