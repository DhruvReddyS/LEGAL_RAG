#!/usr/bin/env python3
"""Load fictional demo cases through the running API, and warm the demo questions.

Every person, place and event in these files is invented. Accounts must already exist
and accept DEMO_PASSWORD: demo-citizen@example.com, demo-police@example.com and
demo-advocate@example.com. Running it again changes nothing that is already there.

Warming asks each demo question once, so a repeat in the demo comes from verified
answers already held in memory. They last until the API restarts.

    DEMO_PASSWORD=... .venv-ingest/bin/python scripts/seed_demo.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import os
import sys
import time
import uuid

import httpx

BASE = os.environ.get("DEMO_API", "http://127.0.0.1:8000")
JOB_DONE = {"succeeded", "failed", "cancelled"}

POLICE_CASE = "Theft of motorcycle at Ameerpet (demo)"
POLICE_FILES = {
    "complaint-ravi-teja.txt": (
        "Complaint of Ravi Teja, recorded on 12/03/2024 at Ameerpet police station.\n\n"
        "On 10 March 2024 at about 9 pm I parked my motorcycle outside my shop in Ameerpet. "
        "When I came out at about 10 pm it was gone. I saw a man named Suresh Naidu riding away on it.\n\n"
        "I informed the police on 11.03.2024. The motorcycle is worth forty thousand rupees."
    ),
    "statement-anita-rao.txt": (
        "Statement of Anita Rao recorded on 13/03/2024 by Constable Lakshmi Prasad.\n\n"
        "On 10 March 2024 at about 11 pm I saw Suresh Naidu near the bus stand in Kukatpally "
        "with a motorcycle. I am a neighbour of Ravi Teja. He told me the motorcycle was worth "
        "sixty thousand rupees."
    ),
    "arrest-memo.txt": (
        "Arrest memo. The accused Suresh Naidu was arrested on 15th March, 2024 at Kukatpally by "
        "Sub-Inspector K. Venkat. His brother was informed of the arrest on the same day. "
        "He was produced before the Magistrate on 16/03/2024. Next date of hearing: 20/01/2027."
    ),
}

ADVOCATE_CASE = "State v. Suresh Naidu, bail application (demo)"
ADVOCATE_FILES = {
    "fir-copy.txt": (
        "First Information Report registered on 12/03/2024 on the complaint of Ravi Teja. "
        "Alleged offence: theft of a motorcycle on 10 March 2024 at about 9 pm at Ameerpet."
    ),
    "client-instructions.txt": (
        "Instructions from Suresh Naidu recorded on 18/03/2024. He says he was at his sister's "
        "house in Kukatpally on 10 March 2024 from 8 pm until 11 pm. He has no previous cases. "
        "He has been in custody since 15th March, 2024."
    ),
}

WARM = (
    ("citizen", "My boss has not paid my salary for three months"),
    ("citizen", "A cheque given to me has bounced. What can I do?"),
    ("citizen", "What are my rights if I am arrested?"),
    ("police", "When can police arrest without a warrant?"),
    ("police", "What must police do when arresting a woman?"),
    ("advocate", "What are the grounds for anticipatory bail?"),
    ("advocate", "When is an accused entitled to default bail?"),
)


def _sign_in(client: httpx.Client, role: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": f"demo-{role}@example.com", "password": password})
    if response.status_code != 200:
        sys.exit(f"cannot sign in as demo-{role}@example.com: {response.status_code}. Does the account exist?")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _consent(client: httpx.Client, headers: dict[str, str]) -> None:
    """Skipped quietly where consent is not enforced, as in development."""
    config = client.get("/account/status", headers=headers)
    consent = config.json().get("consent", {}) if config.status_code == 200 else {}
    if consent.get("required") and not consent.get("accepted_version"):
        client.post("/account/consent", json={"notice_version": consent.get("current_version")}, headers=headers)


def _wait_for(client: httpx.Client, headers: dict[str, str], job_id: str, limit: float = 180) -> str:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        status = client.get(f"/jobs/{job_id}", headers=headers).json().get("status", "")
        if status in JOB_DONE:
            return status
        time.sleep(2)
    return "timed out"


def _seed_case(client: httpx.Client, headers: dict[str, str], title: str, files: dict[str, str]) -> str:
    listed = client.get("/cases", headers=headers).json()
    cases = listed.get("cases", listed) if isinstance(listed, dict) else listed
    for case in cases:
        if case.get("title") == title:
            print(f"  already there: {title}")
            return str(case["id"])
    created = client.post("/cases", json={"title": title}, headers=headers)
    created.raise_for_status()
    case_id = str(created.json()["id"])
    for name, text in files.items():
        stored = client.post(
            f"/cases/{case_id}/storage/objects",
            files={"file": (name, text.encode(), "text/plain")},
            headers=headers,
        )
        stored.raise_for_status()
        job = client.post(
            "/jobs/ocr-ingestion",
            json={"case_id": case_id, "object_id": stored.json()["id"], "doc_type": "statement"},
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
        )
        job.raise_for_status()
        print(f"  {name}: {_wait_for(client, headers, job.json()['id'])}")
    return case_id


def _record_police_dates(client: httpx.Client, headers: dict[str, str], case_id: str) -> None:
    """Dates relative to today, so the dashboard has something real to show on any day.

    Without them the police dashboard reads zero everywhere and the deadline tools have
    nothing to compute. An arrest twenty hours ago leaves four hours of the s.58 limit, so
    this replaces what is there on every run, and the case is fictional.
    """
    path = f"/cases/{case_id}/investigation/facts"
    now = datetime.now(timezone.utc)
    recorded = client.put(
        path,
        json={
            "information_recorded_at": (now - timedelta(days=3)).isoformat(),
            "arrested_at": (now - timedelta(hours=20)).isoformat(),
            "arrested_under_warrant": False,
            "gravity": "other",
        },
        headers=headers,
    )
    recorded.raise_for_status()
    print("  dates recorded")


def _record_advocate_dates(client: httpx.Client, headers: dict[str, str], case_id: str) -> None:
    """A hearing and a limitation date ahead of today, unless some are still ahead."""
    path = f"/cases/{case_id}/advocate/calendar"
    today = datetime.now(timezone.utc).date()
    listed = client.get(path, headers=headers)
    listed.raise_for_status()
    body = listed.json()
    events = body.get("items") or body.get("events") or [] if isinstance(body, dict) else body
    if any(str(event.get("due_on")) >= today.isoformat() for event in events):
        print("  calendar already has dates ahead")
        return
    for kind, title, days in (
        ("hearing", "Bail hearing before the Sessions Court", 3),
        ("limitation", "Last date to file the criminal revision", 24),
    ):
        created = client.post(
            path,
            json={"kind": kind, "title": title, "due_on": (today + timedelta(days=days)).isoformat()},
            headers=headers,
        )
        created.raise_for_status()
    print("  calendar dates recorded")


def main() -> int:
    password = os.environ.get("DEMO_PASSWORD")
    if not password:
        print("Set DEMO_PASSWORD to the demo accounts' password.", file=sys.stderr)
        return 2
    with httpx.Client(base_url=BASE, timeout=300) as client:
        tokens = {role: _sign_in(client, role, password) for role in ("citizen", "police", "advocate")}
        for headers in tokens.values():
            _consent(client, headers)
        print("Demo cases")
        police_case = _seed_case(client, tokens["police"], POLICE_CASE, POLICE_FILES)
        _record_police_dates(client, tokens["police"], police_case)
        advocate_case = _seed_case(client, tokens["advocate"], ADVOCATE_CASE, ADVOCATE_FILES)
        _record_advocate_dates(client, tokens["advocate"], advocate_case)
        print("Warming demo questions")
        failures = 0
        for role, question in WARM:
            started = time.perf_counter()
            answer = client.post(
                "/chat/query", json={"query": question, "response_mode": "deep"}, headers=tokens[role]
            )
            body = answer.json() if answer.status_code == 200 else {}
            cited = len(body.get("citations") or [])
            print(f"  {role}: {time.perf_counter() - started:.0f}s, {cited} sources: {question}")
            failures += answer.status_code != 200 or cited == 0
            # The per-user limit on Deep requests allows two a minute.
            time.sleep(31)
    if failures:
        print(f"{failures} demo question(s) did not publish an answer: choose others or check them.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
