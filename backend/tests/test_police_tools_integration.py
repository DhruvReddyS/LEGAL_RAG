"""The police tools against a real database: isolation first, then behaviour.

test_case_scoped_routes_are_owner_checked proves a checker is wired on every case
route. This proves what happens when a stranger, a foreign case id, an administrator
or a supervisor actually arrives. The route list is read from the app, so a new route
under /police cannot escape it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, GeneratedDocument
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "RedTeam-Password-9142"
NOW = datetime.now(timezone.utc)


def _iso(delta: timedelta = timedelta()) -> str:
    return (NOW + delta).isoformat()


async def _client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _user(role: str = "police", label: str = "officer") -> tuple[dict[str, str], dict]:
    body = await provision_test_user(
        name=f"{label.title()} {uuid.uuid4().hex[:6]}",
        email=unique_email(label),
        password=PASSWORD,
        role=role,
    )
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


async def _case(headers: dict[str, str], title: str = "FIR 12 of 2026") -> uuid.UUID:
    async with await _client() as client:
        created = await client.post("/cases", json={"title": title}, headers=headers)
    assert created.status_code == 201, created.text
    return uuid.UUID(created.json()["id"])


async def _audit_rows(action: str, resource_id: uuid.UUID | None = None) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        query = select(AuditLog).where(AuditLog.action == action)
        if resource_id is not None:
            query = query.where(AuditLog.resource_id == resource_id)
        return list(await session.scalars(query))


def _flatten(container) -> list[APIRoute]:
    found: list[APIRoute] = []
    for route in getattr(container, "routes", []):
        if isinstance(route, APIRoute):
            found.append(route)
            continue
        nested = getattr(route, "original_router", None) or route
        if nested is not route or hasattr(nested, "routes"):
            found.extend(_flatten(nested))
    return found


def _police_case_routes() -> list[tuple[str, str]]:
    from main import app

    routes = []
    for route in _flatten(app):
        if "/police/" in route.path and "{case_id}" in route.path:
            for method in route.methods:
                routes.append((method, route.path))
    return sorted(set(routes))


def _fill(path: str, case_id: uuid.UUID) -> str:
    filled = path.replace("{case_id}", str(case_id))
    for name in ("item_id", "witness_id", "search_id", "draft_id", "period_id"):
        filled = filled.replace("{" + name + "}", str(uuid.uuid4()))
    return filled.replace("{key}", "production_before_magistrate").replace("{action}", "arrest").replace("{offence_key}", "theft")


CASE_ROUTES = _police_case_routes()


def test_the_isolation_list_is_not_empty() -> None:
    assert len(CASE_ROUTES) >= 25


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), CASE_ROUTES, ids=[f"{m} {p}" for m, p in CASE_ROUTES])
async def test_a_stranger_is_refused_on_every_case_route(method: str, path: str) -> None:
    owner, _ = await _user()
    stranger, _ = await _user(label="stranger")
    case_id = await _case(owner)

    async with await _client() as client:
        response = await client.request(method, _fill(path, case_id), json={}, headers=stranger)

    assert response.status_code == 404, f"{method} {path}: {response.status_code} {response.text}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), CASE_ROUTES, ids=[f"{m} {p}" for m, p in CASE_ROUTES])
async def test_an_administrator_is_refused_on_every_case_route(method: str, path: str) -> None:
    """The shared checker exempts administrators. Custody logs and witness details are
    not administrative material."""
    owner, _ = await _user()
    admin, _ = await _user(role="admin", label="admin")
    case_id = await _case(owner)

    async with await _client() as client:
        response = await client.request(method, _fill(path, case_id), json={}, headers=admin)

    assert response.status_code == 403, f"{method} {path}: {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), CASE_ROUTES[:6], ids=[f"{m} {p}" for m, p in CASE_ROUTES[:6]])
async def test_a_citizen_and_an_advocate_are_refused(method: str, path: str) -> None:
    owner, _ = await _user()
    case_id = await _case(owner)
    citizen, _ = await _user(role="citizen", label="citizen")
    advocate, _ = await _user(role="advocate", label="advocate")

    async with await _client() as client:
        for headers in (citizen, advocate):
            response = await client.request(method, _fill(path, case_id), json={}, headers=headers)
            assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_nobody_gets_in_without_signing_in() -> None:
    owner, _ = await _user()
    case_id = await _case(owner)
    async with await _client() as client:
        for path in (f"/cases/{case_id}/police/evidence", "/police/deadlines", "/police/my-units"):
            assert (await client.get(path)).status_code == 401


@pytest.mark.asyncio
async def test_an_object_from_another_case_is_not_found_through_my_case() -> None:
    """A foreign id reached through a case I own. The path check passes, so the object
    lookup has to hold on its own."""
    owner, _ = await _user()
    other, _ = await _user(label="other")
    mine = await _case(owner)
    theirs = await _case(other)

    async with await _client() as client:
        item = (await client.post(f"/cases/{theirs}/police/evidence", json={"exhibit_label": "T-1", "description": "Their item"}, headers=other)).json()
        witness = (await client.post(f"/cases/{theirs}/police/witnesses", json={"name": "Their witness"}, headers=other)).json()
        search = (await client.post(f"/cases/{theirs}/police/searches", json={"place": "Their place"}, headers=other)).json()
        draft = (await client.post(f"/cases/{theirs}/police/drafts", json={"draft_type": "s35_3_notice"}, headers=other)).json()
        remand = (await client.post(f"/cases/{theirs}/police/remand", json={"custody_type": "police", "from_date": "2026-01-01", "to_date": "2026-01-02"}, headers=other)).json()

        base = f"/cases/{mine}/police"
        attempts = [
            await client.patch(f"{base}/evidence/{item['id']}", json={"description": "Hijacked"}, headers=owner),
            await client.post(f"{base}/evidence/{item['id']}/custody", json={"occurred_at": _iso(), "from_person": "Me", "to_person": "Me2"}, headers=owner),
            await client.patch(f"{base}/witnesses/{witness['id']}", json={"name": "Hijacked"}, headers=owner),
            await client.put(f"{base}/searches/{search['id']}", json={"place": "Hijacked"}, headers=owner),
            await client.get(f"{base}/drafts/{draft['id']}", headers=owner),
            await client.delete(f"{base}/remand/{remand['periods'][0]['id']}", headers=owner),
            await client.post(f"{base}/evidence", json={"exhibit_label": "M-1", "description": "Mine", "search_id": search["id"]}, headers=owner),
            await client.put(f"{base}/compliance-records/arrest/memorandum_of_arrest", json={"evidence_item_id": item["id"]}, headers=owner),
            await client.put(f"{base}/offences/theft", json={"elements": {"moved": {"state": "established", "evidence_item_ids": [item["id"]]}}}, headers=owner),
            await client.put(f"{base}/offences/theft", json={"elements": {"moved": {"state": "established", "witness_ids": [witness["id"]]}}}, headers=owner),
        ]
        untouched = await client.get(f"/cases/{theirs}/police/evidence", headers=other)

    assert [a.status_code for a in attempts] == [404] * len(attempts), [a.text for a in attempts]
    assert untouched.json()["items"][0]["description"] == "Their item"


@pytest.mark.asyncio
async def test_the_register_shows_only_my_cases_and_refuses_a_foreign_filter() -> None:
    mine, _ = await _user()
    other, _ = await _user(label="other")
    my_case = await _case(mine, "Mine")
    their_case = await _case(other, "Theirs")

    async with await _client() as client:
        for case_id, headers in ((my_case, mine), (their_case, other)):
            await client.put(f"/cases/{case_id}/investigation/facts", json={"arrested_at": _iso(-timedelta(hours=1))}, headers=headers)
        register = await client.get("/police/deadlines", headers=mine)
        foreign = await client.get(f"/police/deadlines?case_id={their_case}", headers=mine)
        missing = await client.get(f"/police/deadlines?case_id={uuid.uuid4()}", headers=mine)

    assert {row["case_id"] for row in register.json()["rows"]} == {str(my_case)}
    assert foreign.status_code == 403
    assert missing.status_code == 404


class TestTheRegister:
    @pytest.mark.asyncio
    async def test_each_state_comes_back_with_its_provision(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        facts = {
            "arrested_at": _iso(-timedelta(hours=30)),
            "information_recorded_at": _iso(-timedelta(days=1)),
            "first_remand_at": None,
        }
        async with await _client() as client:
            await client.put(f"/cases/{case_id}/investigation/facts", json=facts, headers=headers)
            body = (await client.get("/police/deadlines", headers=headers)).json()

        by_key = {row["key"]: row for row in body["rows"]}
        production = by_key["production_before_magistrate"]
        assert production["state"] == "overdue"
        assert production["provision"].startswith("BNSS s.")
        assert by_key["default_bail_entitlement"]["state"] == "unknown"
        assert by_key["default_bail_entitlement"]["due_at"] is None
        assert by_key["victim_progress_update"]["state"] == "due"
        assert body["counts"]["overdue"] == 1
        assert body["counts"]["unknown"] == 1

    @pytest.mark.asyncio
    async def test_a_late_completion_turns_overdue_into_breached(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/police/deadlines/victim_progress_update/completion"
        async with await _client() as client:
            await client.put(
                f"/cases/{case_id}/investigation/facts",
                json={"information_recorded_at": _iso(-timedelta(days=100))},
                headers=headers,
            )
            before = (await client.get("/police/deadlines", headers=headers)).json()["rows"][0]
            late = await client.put(url, json={"completed_at": _iso(-timedelta(days=1)), "note": "Called the informant"}, headers=headers)
            on_time = await client.put(url, json={"completed_at": _iso(-timedelta(days=50))}, headers=headers)
            removed = await client.delete(url, headers=headers)
            after = (await client.get("/police/deadlines", headers=headers)).json()["rows"][0]

        assert before["state"] == "overdue"
        assert late.json()["state"] == "breached"
        assert on_time.json()["state"] == "met"
        assert removed.status_code == 204
        assert after["state"] == "overdue"

    @pytest.mark.asyncio
    async def test_a_completion_cannot_be_recorded_for_a_deadline_that_does_not_apply(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            response = await client.put(
                f"/cases/{case_id}/police/deadlines/production_before_magistrate/completion",
                json={"completed_at": _iso()},
                headers=headers,
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_a_completion_in_the_future_is_refused(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            await client.put(f"/cases/{case_id}/investigation/facts", json={"arrested_at": _iso()}, headers=headers)
            response = await client.put(
                f"/cases/{case_id}/police/deadlines/production_before_magistrate/completion",
                json={"completed_at": _iso(timedelta(days=3))},
                headers=headers,
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_a_naive_time_is_refused(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            response = await client.post(
                f"/cases/{case_id}/police/evidence",
                json={"exhibit_label": "N-1", "description": "Naive", "seized_at": "2026-01-01T10:00:00"},
                headers=headers,
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_filters_narrow_the_rows_and_the_counts(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            await client.put(
                f"/cases/{case_id}/investigation/facts",
                json={"arrested_at": _iso(-timedelta(hours=30)), "information_recorded_at": _iso()},
                headers=headers,
            )
            overdue = (await client.get("/police/deadlines?state=overdue", headers=headers)).json()
            by_provision = (await client.get("/police/deadlines?provision=193", headers=headers)).json()
            imminent = (await client.get(f"/police/deadlines?imminent_only=true&case_id={case_id}", headers=headers)).json()

        assert {row["state"] for row in overdue["rows"]} == {"overdue"}
        assert all("193" in row["provision"] for row in by_provision["rows"])
        assert imminent["rows"] == []

    @pytest.mark.asyncio
    async def test_a_case_with_nothing_recorded_stays_visible(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers, "Nothing yet")
        async with await _client() as client:
            body = (await client.get("/police/deadlines", headers=headers)).json()

        assert [c["case_id"] for c in body["cases_without_facts"]] == [str(case_id)]

    @pytest.mark.asyncio
    async def test_a_section_185_search_puts_its_48_hours_on_the_register(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            search = (await client.post(
                f"/cases/{case_id}/police/searches",
                json={"place": "Godown", "basis": "section_185", "grounds_recorded_at": _iso(-timedelta(hours=50))},
                headers=headers,
            )).json()
            before = (await client.get("/police/deadlines", headers=headers)).json()
            await client.put(
                f"/cases/{case_id}/police/searches/{search['id']}",
                json={"place": "Godown", "basis": "section_185", "grounds_recorded_at": _iso(-timedelta(hours=50)), "record_sent_to_magistrate_at": _iso(-timedelta(hours=10))},
                headers=headers,
            )
            after = (await client.get("/police/deadlines", headers=headers)).json()

        row = next(r for r in before["rows"] if r["provision"] == "BNSS s.185(5)")
        assert row["state"] == "overdue"
        assert next(r for r in after["rows"] if r["provision"] == "BNSS s.185(5)")["state"] == "met"
        assert any("Godown" in note for note in row["notes"])


class TestFlagsAreOnTheRecord:
    """F14: a reload must show the same list, and must not cost a record."""

    @pytest.mark.asyncio
    async def test_flags_and_their_rows_survive_a_reload(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/investigation/compliance"
        async with await _client() as client:
            await client.put(
                url,
                json={"action": "arrest", "status": {"handcuff_ground_within_s43_3": "satisfied"}, "handcuffs_used": True},
                headers=headers,
            )
            reload = (await client.get(f"{url}?action=arrest", headers=headers)).json()

        assert reload["flags"]["handcuffs_used"] is True
        status = {item["key"]: item["status"] for item in reload["items"]}
        assert status["handcuff_ground_within_s43_3"] == "satisfied"

    @pytest.mark.asyncio
    async def test_a_flag_can_be_switched_off_without_losing_the_record(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/investigation/compliance"
        async with await _client() as client:
            await client.put(url, json={"action": "arrest", "status": {"handcuff_ground_within_s43_3": "satisfied"}, "handcuffs_used": True}, headers=headers)
            off = (await client.put(url, json={"action": "arrest", "status": {}, "handcuffs_used": False}, headers=headers)).json()
            on = (await client.put(url, json={"action": "arrest", "status": {"handcuff_ground_within_s43_3": "satisfied"}, "handcuffs_used": True}, headers=headers)).json()

        assert "handcuff_ground_within_s43_3" not in {item["key"] for item in off["items"]}
        assert off["flags"]["handcuffs_used"] is False
        assert {i["key"]: i["status"] for i in on["items"]}["handcuff_ground_within_s43_3"] == "satisfied"

    @pytest.mark.asyncio
    async def test_a_query_flag_overrides_for_that_read_only(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/investigation/compliance"
        async with await _client() as client:
            what_if = (await client.get(f"{url}?action=arrest&arrested_person_is_woman=true", headers=headers)).json()
            read = (await client.get(f"{url}?action=arrest", headers=headers)).json()

        assert "woman_not_arrested_after_sunset" in {i["key"] for i in what_if["items"]}
        assert "woman_not_arrested_after_sunset" not in {i["key"] for i in read["items"]}


class TestPolFactsRoundTrip:
    @pytest.mark.asyncio
    async def test_the_new_facts_survive_the_round_trip(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            await client.put(
                f"/cases/{case_id}/investigation/facts",
                json={
                    "arrested_at": _iso(),
                    "arrested_under_warrant": True,
                    "is_rape_or_attempt": True,
                    "first_remand_at": _iso(),
                    "gravity": "other",
                    "special_statute": "ndps_s36a",
                },
                headers=headers,
            )
            timeline = (await client.get(f"/cases/{case_id}/investigation/timeline", headers=headers)).json()

        rows = {row["key"]: row for row in timeline["deadlines"]}
        assert rows["production_before_magistrate"]["provision"] == "BNSS s.78"
        assert rows["default_bail_entitlement"]["due_at"] is None
        assert any("36A" in note for note in rows["default_bail_entitlement"]["notes"])
        assert rows["medical_report_to_officer"]["actor"] == "medical_practitioner"

    @pytest.mark.asyncio
    async def test_an_unrecognised_statute_is_refused(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            response = await client.put(f"/cases/{case_id}/investigation/facts", json={"special_statute": "uapa"}, headers=headers)
        assert response.status_code == 422


class TestComplianceAsARecord:
    @pytest.mark.asyncio
    async def test_a_date_and_evidence_attach_to_one_duty(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        base = f"/cases/{case_id}/police"
        async with await _client() as client:
            item = (await client.post(f"{base}/evidence", json={"exhibit_label": "D-1", "description": "Memo of arrest"}, headers=headers)).json()
            written = await client.put(
                f"{base}/compliance-records/arrest/memorandum_of_arrest",
                json={"status": "satisfied", "occurred_at": _iso(-timedelta(hours=2)), "evidence_note": "Countersigned", "evidence_item_id": item["id"]},
                headers=headers,
            )
            read = (await client.get(f"{base}/compliance-records?action=arrest", headers=headers)).json()
            checklist = (await client.get(f"/cases/{case_id}/investigation/compliance?action=arrest", headers=headers)).json()

        assert written.status_code == 200, written.text
        row = next(i for i in read["items"] if i["key"] == "memorandum_of_arrest")
        assert row["evidence_label"] == "D-1" and row["evidence_note"] == "Countersigned"
        assert row["needs_record"] is False
        # One status, not two: the old checklist reads the same answer.
        assert {i["key"]: i["status"] for i in checklist["items"]}["memorandum_of_arrest"] == "satisfied"

    @pytest.mark.asyncio
    async def test_done_with_nothing_to_show_is_flagged(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            read = (await client.put(
                f"/cases/{case_id}/police/compliance-records/arrest/memorandum_of_arrest",
                json={"status": "satisfied"},
                headers=headers,
            )).json()

        assert next(i for i in read["items"] if i["key"] == "memorandum_of_arrest")["needs_record"] is True
        assert next(i for i in read["items"] if i["key"] == "medical_examination")["needs_record"] is False

    @pytest.mark.asyncio
    async def test_a_requirement_from_another_action_is_refused(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            response = await client.put(
                f"/cases/{case_id}/police/compliance-records/arrest/seizure_list", json={}, headers=headers
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_it_is_audited_without_the_free_text(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            await client.put(
                f"/cases/{case_id}/police/compliance-records/arrest/medical_examination",
                json={"evidence_note": "SECRET-NOTE"},
                headers=headers,
            )
        rows = await _audit_rows("police.compliance_record_written", case_id)
        assert len(rows) == 1
        assert "SECRET-NOTE" not in str(rows[0].metadata_)


class TestEvidenceAndCustody:
    @pytest.mark.asyncio
    async def test_a_chain_is_built_append_only_and_read_back(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        base = f"/cases/{case_id}/police/evidence"
        async with await _client() as client:
            item = (await client.post(base, json={
                "exhibit_label": "E-1", "description": "Phone", "category": "electronic",
                "seized_by": "SI Rao", "seized_at": _iso(-timedelta(days=3)),
            }, headers=headers)).json()
            assert item["chain"]["state"] == "continuous"
            assert item["certificate_s63"] == "unknown"

            ok = (await client.post(f"{base}/{item['id']}/custody", json={
                "occurred_at": _iso(-timedelta(days=2)), "from_person": "SI Rao", "to_person": "HC Das",
            }, headers=headers)).json()
            broken = (await client.post(f"{base}/{item['id']}/custody", json={
                "occurred_at": _iso(-timedelta(days=1)), "from_person": "Somebody", "to_person": "FSL",
            }, headers=headers)).json()
            fixed = (await client.post(f"{base}/{item['id']}/custody", json={
                "occurred_at": _iso(-timedelta(days=1)), "from_person": "HC Das", "to_person": "FSL",
                "corrects_event_id": broken["custody_events"][-1]["id"],
            }, headers=headers)).json()
            routes = {m for m, p in _police_case_routes() if p.endswith("/custody")}

        assert ok["chain"]["current_holder"] == "HC Das"
        assert broken["chain"]["state"] == "broken"
        assert fixed["chain"]["state"] == "continuous"
        assert fixed["chain"]["current_holder"] == "FSL"
        assert len(fixed["custody_events"]) == 3, "the corrected entry stays visible"
        assert routes == {"POST"}, "there is no route to change a custody entry"

    @pytest.mark.asyncio
    async def test_exhibit_labels_are_unique_per_case_not_globally(self) -> None:
        headers, _ = await _user()
        first = await _case(headers)
        second = await _case(headers)
        body = {"exhibit_label": "A-1", "description": "Item"}
        async with await _client() as client:
            assert (await client.post(f"/cases/{first}/police/evidence", json=body, headers=headers)).status_code == 201
            assert (await client.post(f"/cases/{first}/police/evidence", json=body, headers=headers)).status_code == 409
            assert (await client.post(f"/cases/{second}/police/evidence", json=body, headers=headers)).status_code == 201


class TestWitnesses:
    @pytest.mark.asyncio
    async def test_duties_follow_the_record(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        base = f"/cases/{case_id}/police/witnesses"
        async with await _client() as client:
            witness = (await client.post(base, json={"name": "Lata", "category": "victim", "needs_woman_officer": True, "attends_only_at_residence": True}, headers=headers)).json()
            updated = (await client.patch(f"{base}/{witness['id']}", json={
                "statement_recorded_at": _iso(-timedelta(days=1)), "statement_mode": "written", "recorded_by_woman_officer": "no",
            }, headers=headers)).json()

        assert {d["key"] for d in witness["duties"]} == {"attendance_at_residence"}
        duties = {d["key"]: d for d in updated["duties"]}
        assert duties["woman_officer"]["state"] == "not_done"
        assert duties["woman_officer"]["provision"] == "BNSS s.180(3)"
        assert duties["inserted_in_diary"]["state"] == "cannot_be_determined"


class TestSearchCheckRoutes:
    @pytest.mark.asyncio
    async def test_the_check_comes_back_with_the_record(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            body = (await client.post(f"/cases/{case_id}/police/searches", json={
                "place": "Shop", "basis": "section_185", "witness_count": 1,
                "answers": {"audio_video_recorded": "no"},
            }, headers=headers)).json()
            questions = (await client.get("/police/search-questions", headers=headers)).json()
            refused = await client.post(f"/cases/{case_id}/police/searches", json={"place": "Shop", "answers": {"x": "maybe"}}, headers=headers)

        assert body["finding"] == "defect_on_record"
        by_key = {c["key"]: c["verdict"] for c in body["checks"]}
        assert by_key["two_or_more_witnesses"] == "not_met"
        assert by_key["audio_video_recorded"] == "not_met"
        assert by_key["seizure_list_signed"] == "cannot_be_determined"
        assert questions["conditions"] and questions["questions"]
        assert refused.status_code == 422


class TestOffenceElements:
    @pytest.mark.asyncio
    async def test_established_requires_something_on_record(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/police/offences/theft"
        async with await _client() as client:
            bare = await client.put(url, json={"elements": {"moved": {"state": "established"}}}, headers=headers)
            witness = (await client.post(f"/cases/{case_id}/police/witnesses", json={"name": "Lata"}, headers=headers)).json()
            linked = await client.put(url, json={"elements": {"moved": {"state": "established", "witness_ids": [witness["id"]]}}}, headers=headers)
            listed = (await client.get(f"/cases/{case_id}/police/offences", headers=headers)).json()

        assert bare.status_code == 422
        assert linked.status_code == 200
        assert linked.json()["finding"] == "cannot_be_determined", "other elements are still open"
        assert listed["assessments"][0]["offence_key"] == "theft"
        row = next(e for e in listed["assessments"][0]["elements"] if e["key"] == "moved")
        assert row["state"] == "established"
        assert row["provision"] == "BNS s.303(1)"
        assert row["source_quote"]

    @pytest.mark.asyncio
    async def test_unknown_offences_and_elements_are_refused(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            no_offence = await client.put(f"/cases/{case_id}/police/offences/treason", json={}, headers=headers)
            no_element = await client.put(f"/cases/{case_id}/police/offences/theft", json={"elements": {"nope": {}}}, headers=headers)
            catalogue = (await client.get("/police/offences", headers=headers)).json()

        assert no_offence.status_code == 404
        assert no_element.status_code == 422
        assert len(catalogue["offences"]) >= 20

    @pytest.mark.asyncio
    async def test_an_assessment_can_be_removed(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/police/offences/theft"
        async with await _client() as client:
            await client.put(url, json={}, headers=headers)
            assert (await client.delete(url, headers=headers)).status_code == 204
            assert (await client.delete(url, headers=headers)).status_code == 404


class TestRemandAndDiary:
    @pytest.mark.asyncio
    async def test_remand_days_are_summed_and_removable(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/police/remand"
        async with await _client() as client:
            backwards = await client.post(url, json={"custody_type": "police", "from_date": "2026-01-05", "to_date": "2026-01-01"}, headers=headers)
            body = (await client.post(url, json={"custody_type": "police", "from_date": "2026-01-01", "to_date": "2026-01-16"}, headers=headers)).json()
            cleared = (await client.delete(f"{url}/{body['periods'][0]['id']}", headers=headers)).json()

        assert backwards.status_code == 422
        assert body["police_days_used"] == 16
        assert body["findings"]
        assert body["provision"] == "BNSS s.187(2)"
        assert cleared["periods"] == []

    @pytest.mark.asyncio
    async def test_the_server_numbers_the_pages(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        url = f"/cases/{case_id}/police/diary"
        async with await _client() as client:
            await client.post(url, json={"entry_date": "2026-01-01", "circumstances": "Visited the scene"}, headers=headers)
            second = (await client.post(url, json={"entry_date": "2026-01-03", "circumstances": "Recorded statements", "corrects_page": 1}, headers=headers)).json()
            bad = await client.post(url, json={"entry_date": "2026-01-03", "circumstances": "Later", "corrects_page": 99}, headers=headers)

        assert [e["page_no"] for e in second["entries"]] == [1, 2]
        assert second["entries"][1]["corrects_page"] == 1
        assert "2026-01-02" in second["days_without_entry"]
        assert bad.status_code == 422
        assert {m for m, p in _police_case_routes() if p.endswith("/police/diary")} == {"GET", "POST"}


class TestDraftRoutes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "draft_type",
        ["s35_3_notice", "s94_production_order", "seizure_memo", "case_diary_entry", "remand_application", "chargesheet_skeleton"],
    )
    async def test_each_draft_is_generated_from_the_case_as_a_draft(self, draft_type: str) -> None:
        headers, _ = await _user()
        case_id = await _case(headers, "FIR 99")
        base = f"/cases/{case_id}/police/drafts"
        async with await _client() as client:
            created = await client.post(base, json={"draft_type": draft_type}, headers=headers)
            second = await client.post(base, json={"draft_type": draft_type}, headers=headers)
            read = await client.get(f"{base}/{created.json()['id']}", headers=headers)
            listed = (await client.get(base, headers=headers)).json()

        body = created.json()
        assert created.status_code == 201, created.text
        assert body["status"] == "draft"
        assert "FIR 99" in body["rendered_text"]
        assert "NOT FILED" in body["rendered_text"]
        assert body["provisions"]
        assert second.json()["version"] == body["version"] + 1
        assert read.json()["rendered_text"] == body["rendered_text"], "a reviewed draft does not change"
        assert len(listed["drafts"]) == 2

    @pytest.mark.asyncio
    async def test_a_draft_reads_this_case_and_no_other(self) -> None:
        headers, _ = await _user()
        mine = await _case(headers)
        other = await _case(headers)
        async with await _client() as client:
            await client.post(f"/cases/{other}/police/witnesses", json={"name": "Elsewhere Witness"}, headers=headers)
            draft = (await client.post(f"/cases/{mine}/police/drafts", json={"draft_type": "chargesheet_skeleton"}, headers=headers)).json()

        assert "Elsewhere Witness" not in draft["rendered_text"]

    @pytest.mark.asyncio
    async def test_the_seizure_memo_uses_the_inventory(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        base = f"/cases/{case_id}/police"
        async with await _client() as client:
            search = (await client.post(f"{base}/searches", json={"place": "Godown 4", "basis": "warrant"}, headers=headers)).json()
            await client.post(f"{base}/evidence", json={"exhibit_label": "M-1", "description": "Knife", "seized_from": "Shelf", "search_id": search["id"]}, headers=headers)
            await client.post(f"{base}/evidence", json={"exhibit_label": "M-2", "description": "Unrelated"}, headers=headers)
            await client.post(f"{base}/witnesses", json={"name": "Panch One", "category": "search_witness"}, headers=headers)
            draft = (await client.post(f"{base}/drafts", json={"draft_type": "seizure_memo", "inputs": {"search_id": search["id"]}}, headers=headers)).json()

        text = draft["rendered_text"]
        assert "Godown 4" in text and "M-1: Knife" in text and "Panch One" in text
        assert "Unrelated" not in text

    @pytest.mark.asyncio
    async def test_an_unknown_type_is_refused(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with await _client() as client:
            response = await client.post(f"/cases/{case_id}/police/drafts", json={"draft_type": "arrest_warrant"}, headers=headers)
        assert response.status_code == 422


class TestGeneratedListIsDraftsOnly:
    """F23."""

    @pytest.mark.asyncio
    async def test_a_document_analysis_is_not_listed_as_a_draft(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers)
        async with AsyncSessionLocal() as session:
            session.add(GeneratedDocument(case_id=case_id, doc_type=f"document_analysis:{uuid.uuid4()}", version=1, content={"a": 1}, status="complete"))
            session.add(GeneratedDocument(case_id=case_id, doc_type="fir", version=1, content={"rendered_text": "x", "missing_fields": ["place"]}, status="draft"))
            await session.commit()
        async with await _client() as client:
            await client.post(f"/cases/{case_id}/police/drafts", json={"draft_type": "s35_3_notice"}, headers=headers)
            listed = (await client.get(f"/cases/{case_id}/documents/generated", headers=headers)).json()
            named = (await client.get(f"/cases/{case_id}/documents/generated?doc_type=police_draft:s35_3_notice", headers=headers)).json()

        assert [d["doc_type"] for d in listed["documents"]] == ["fir"]
        assert [d["doc_type"] for d in named["documents"]] == ["police_draft:s35_3_notice"]


class TestCaseFileRoute:
    @pytest.mark.asyncio
    async def test_it_compiles_the_record_escaped_and_audited(self) -> None:
        headers, _ = await _user()
        case_id = await _case(headers, "<b>FIR</b> 7")
        base = f"/cases/{case_id}/police"
        async with await _client() as client:
            await client.put(f"/cases/{case_id}/investigation/facts", json={"arrested_at": _iso(-timedelta(hours=2))}, headers=headers)
            await client.post(f"{base}/evidence", json={"exhibit_label": "E-1", "description": "<script>x</script>", "seized_by": "SI Rao", "seized_at": _iso(-timedelta(hours=1))}, headers=headers)
            await client.post(f"{base}/witnesses", json={"name": "Lata", "contact": "98765-CONTACT"}, headers=headers)
            await client.post(f"{base}/drafts", json={"draft_type": "s35_3_notice"}, headers=headers)
            body = (await client.get(f"{base}/case-file", headers=headers)).json()
            with_contact = (await client.get(f"{base}/case-file?include_witness_contact=true", headers=headers)).json()

        html = body["html"]
        assert "&lt;b&gt;FIR&lt;/b&gt;" in html and "<script>x" not in html
        assert "E-1" in html and "Lata" in html and "BNSS s.58" in html
        assert "DRAFT: Notice of appearance" in html
        assert "98765-CONTACT" not in html
        assert "98765-CONTACT" in with_contact["html"]
        assert "searches" in body["missing_sections"]
        assert "dates" not in body["missing_sections"]
        rows = await _audit_rows("police.case_file_exported", case_id)
        assert {r.metadata_["include_witness_contact"] for r in rows} == {False, True}

    @pytest.mark.asyncio
    async def test_it_holds_only_this_case(self) -> None:
        headers, _ = await _user()
        mine = await _case(headers, "Mine")
        other = await _case(headers, "Other")
        async with await _client() as client:
            await client.post(f"/cases/{other}/police/evidence", json={"exhibit_label": "OTHER-EXHIBIT", "description": "Other"}, headers=headers)
            body = (await client.get(f"/cases/{mine}/police/case-file", headers=headers)).json()

        assert "OTHER-EXHIBIT" not in body["html"]


async def _unit_with_supervisor() -> dict:
    admin, _ = await _user(role="admin", label="admin")
    supervisor, supervisor_user = await _user(label="supervisor")
    officer, officer_user = await _user(label="unit-officer")
    async with await _client() as client:
        unit = (await client.post("/police/units", json={"name": f"Unit {uuid.uuid4().hex[:8]}"}, headers=admin)).json()
        url = f"/police/units/{unit['id']}/members"
        await client.put(url, json={"email": supervisor_user["email"], "role": "supervisor"}, headers=admin)
        await client.put(url, json={"email": officer_user["email"], "role": "member"}, headers=admin)
    return {
        "admin": admin, "supervisor": supervisor, "supervisor_user": supervisor_user,
        "officer": officer, "officer_user": officer_user, "unit": unit,
    }


class TestSupervision:
    @pytest.mark.asyncio
    async def test_an_explicit_supervisor_sees_counts_and_imminent_breaches(self) -> None:
        ctx = await _unit_with_supervisor()
        case_id = await _case(ctx["officer"], "Unit case")
        base = f"/cases/{case_id}/police"
        async with await _client() as client:
            await client.put(
                f"/cases/{case_id}/investigation/facts",
                json={"arrested_at": _iso(-timedelta(hours=30)), "information_recorded_at": _iso(-timedelta(hours=1))},
                headers=ctx["officer"],
            )
            await client.put(f"/cases/{case_id}/investigation/compliance", json={"action": "arrest", "status": {"medical_examination": "not_satisfied"}}, headers=ctx["officer"])
            await client.post(f"{base}/witnesses", json={"name": "WITNESS-NAME-SECRET", "contact": "CONTACT-SECRET"}, headers=ctx["officer"])
            await client.post(f"{base}/evidence", json={"exhibit_label": "EXHIBIT-SECRET", "description": "DESC-SECRET"}, headers=ctx["officer"])
            await client.post(f"{base}/searches", json={"place": "PLACE-SECRET", "basis": "section_185"}, headers=ctx["officer"])
            view = await client.get(f"/police/supervision/units/{ctx['unit']['id']}", headers=ctx["supervisor"])

        assert view.status_code == 200, view.text
        body = view.json()
        case = next(c for c in body["cases"] if c["case_id"] == str(case_id))
        assert case["counts"]["overdue"] == 1
        assert case["compliance"]["not_satisfied"] == 1
        assert [row["key"] for row in case["attention"]] == ["production_before_magistrate"]
        assert body["counts"]["overdue"] >= 1
        assert case["officer_name"]
        for secret in ("WITNESS-NAME-SECRET", "CONTACT-SECRET", "EXHIBIT-SECRET", "DESC-SECRET", "PLACE-SECRET"):
            assert secret not in view.text, secret

    @pytest.mark.asyncio
    async def test_the_grant_opens_no_case_route(self) -> None:
        ctx = await _unit_with_supervisor()
        case_id = await _case(ctx["officer"])
        async with await _client() as client:
            responses = [
                await client.request(method, _fill(path, case_id), json={}, headers=ctx["supervisor"])
                for method, path in CASE_ROUTES
            ]
            old = await client.get(f"/cases/{case_id}/investigation/timeline", headers=ctx["supervisor"])
            documents = await client.get(f"/cases/{case_id}/documents/generated", headers=ctx["supervisor"])
            case = await client.get(f"/cases/{case_id}", headers=ctx["supervisor"])
            register = (await client.get(f"/police/deadlines", headers=ctx["supervisor"])).json()

        assert {r.status_code for r in responses} == {404}
        assert old.status_code == 404
        assert documents.status_code == 404
        assert case.status_code in (403, 404)
        assert str(case_id) not in str(register)

    @pytest.mark.asyncio
    async def test_a_plain_officer_and_a_member_are_refused(self) -> None:
        ctx = await _unit_with_supervisor()
        plain, _ = await _user(label="plain")
        async with await _client() as client:
            for headers in (plain, ctx["officer"]):
                response = await client.get(f"/police/supervision/units/{ctx['unit']['id']}", headers=headers)
                assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_a_refused_attempt_is_audited(self) -> None:
        ctx = await _unit_with_supervisor()
        async with await _client() as client:
            await client.get(f"/police/supervision/units/{ctx['unit']['id']}", headers=ctx["officer"])
        rows = await _audit_rows("police.supervisor_view_refused")
        assert any(r.metadata_.get("unit") == ctx["unit"]["id"] for r in rows)

    @pytest.mark.asyncio
    async def test_supervising_one_unit_gives_nothing_on_another(self) -> None:
        first = await _unit_with_supervisor()
        second = await _unit_with_supervisor()
        case_id = await _case(second["officer"], "Second unit case")
        async with await _client() as client:
            response = await client.get(f"/police/supervision/units/{second['unit']['id']}", headers=first["supervisor"])
            own = await client.get(f"/police/supervision/units/{first['unit']['id']}", headers=first["supervisor"])

        assert response.status_code == 403
        assert str(case_id) not in own.text

    @pytest.mark.asyncio
    async def test_other_roles_lack_the_permission_outright(self) -> None:
        ctx = await _unit_with_supervisor()
        citizen, _ = await _user(role="citizen", label="citizen")
        advocate, _ = await _user(role="advocate", label="advocate")
        async with await _client() as client:
            for headers in (citizen, advocate, ctx["admin"]):
                response = await client.get(f"/police/supervision/units/{ctx['unit']['id']}", headers=headers)
                assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_removal_ends_access_immediately(self) -> None:
        ctx = await _unit_with_supervisor()
        url = f"/police/units/{ctx['unit']['id']}/members/{ctx['supervisor_user']['id']}"
        async with await _client() as client:
            view = f"/police/supervision/units/{ctx['unit']['id']}"
            assert (await client.get(view, headers=ctx["supervisor"])).status_code == 200
            assert (await client.delete(url, headers=ctx["admin"])).status_code == 200
            assert (await client.get(view, headers=ctx["supervisor"])).status_code == 403

    @pytest.mark.asyncio
    async def test_demotion_ends_access_too(self) -> None:
        ctx = await _unit_with_supervisor()
        async with await _client() as client:
            await client.put(
                f"/police/units/{ctx['unit']['id']}/members",
                json={"email": ctx["supervisor_user"]["email"], "role": "member"},
                headers=ctx["admin"],
            )
            response = await client.get(f"/police/supervision/units/{ctx['unit']['id']}", headers=ctx["supervisor"])
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_every_look_is_audited_and_the_owner_can_read_it(self) -> None:
        ctx = await _unit_with_supervisor()
        case_id = await _case(ctx["officer"])
        async with await _client() as client:
            await client.get(f"/police/supervision/units/{ctx['unit']['id']}", headers=ctx["supervisor"])
            log = (await client.get(f"/cases/{case_id}/police/access-log", headers=ctx["officer"])).json()
        rows = await _audit_rows("police.supervisor_case_view", case_id)

        assert len(rows) == 1
        assert rows[0].metadata_["unit"] == ctx["unit"]["id"]
        assert len(log["entries"]) == 1
        assert log["entries"][0]["who"].startswith("Supervisor")

    @pytest.mark.asyncio
    async def test_an_officer_can_see_who_supervises_them(self) -> None:
        ctx = await _unit_with_supervisor()
        async with await _client() as client:
            body = (await client.get("/police/my-units", headers=ctx["officer"])).json()
        assert body["units"][0]["my_role"] == "member"
        assert len(body["units"][0]["supervisors"]) == 1

    @pytest.mark.asyncio
    async def test_a_closed_case_drops_out(self) -> None:
        ctx = await _unit_with_supervisor()
        case_id = await _case(ctx["officer"])
        async with await _client() as client:
            await client.patch(f"/cases/{case_id}", json={"status": "closed"}, headers=ctx["officer"])
            view = await client.get(f"/police/supervision/units/{ctx['unit']['id']}", headers=ctx["supervisor"])
        assert str(case_id) not in view.text


class TestUnitAdministration:
    @pytest.mark.asyncio
    async def test_only_an_administrator_can_grant(self) -> None:
        """Nobody promotes themselves."""
        ctx = await _unit_with_supervisor()
        plain, plain_user = await _user(label="plain")
        attempts = []
        async with await _client() as client:
            for headers in (plain, ctx["supervisor"], ctx["officer"]):
                attempts.append(await client.post("/police/units", json={"name": f"U {uuid.uuid4().hex}"}, headers=headers))
                attempts.append(await client.get("/police/units", headers=headers))
                attempts.append(await client.put(f"/police/units/{ctx['unit']['id']}/members", json={"email": plain_user["email"], "role": "supervisor"}, headers=headers))
                attempts.append(await client.delete(f"/police/units/{ctx['unit']['id']}/members/{ctx['officer_user']['id']}", headers=headers))
        assert {a.status_code for a in attempts} == {403}

    @pytest.mark.asyncio
    async def test_a_grant_is_audited(self) -> None:
        ctx = await _unit_with_supervisor()
        rows = await _audit_rows("police.unit_member_set")
        mine = [r for r in rows if r.metadata_.get("member") == ctx["supervisor_user"]["id"]]
        assert mine and mine[0].metadata_["role"] == "supervisor"

    @pytest.mark.asyncio
    async def test_only_a_police_account_can_join(self) -> None:
        ctx = await _unit_with_supervisor()
        _, citizen_user = await _user(role="citizen", label="citizen")
        async with await _client() as client:
            response = await client.put(
                f"/police/units/{ctx['unit']['id']}/members",
                json={"email": citizen_user["email"], "role": "supervisor"},
                headers=ctx["admin"],
            )
            missing = await client.put(
                f"/police/units/{ctx['unit']['id']}/members",
                json={"email": "nobody@example.com"},
                headers=ctx["admin"],
            )
        assert response.status_code == 422
        assert missing.status_code == 404

    @pytest.mark.asyncio
    async def test_unit_names_are_unique(self) -> None:
        admin, _ = await _user(role="admin", label="admin")
        name = f"Unit {uuid.uuid4().hex}"
        async with await _client() as client:
            assert (await client.post("/police/units", json={"name": name}, headers=admin)).status_code == 201
            assert (await client.post("/police/units", json={"name": name}, headers=admin)).status_code == 409

    @pytest.mark.asyncio
    async def test_the_new_permission_reaches_no_other_role(self) -> None:
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            roles = (
                await session.scalars(
                    text(
                        "SELECT r.name FROM roles r JOIN role_permissions rp ON rp.role_id = r.id "
                        "JOIN permissions p ON p.id = rp.permission_id WHERE p.name = 'police:unit:supervise'"
                    )
                )
            ).all()
        assert list(roles) == ["police"]
