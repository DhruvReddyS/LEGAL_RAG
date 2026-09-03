#!/usr/bin/env python3
"""Run and preserve the scoped Fast/Deep relevance-fix acceptance evidence."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "docs/evidence/fast-deep-relevance-fix-acceptance-raw.json"
BASE_URL = "http://localhost:8000"
INSUFFICIENT = "I could not find enough reliable support in the indexed legal corpus for this answer."


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(method: str, path: str, *, body: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8')}") from exc


def persist(report: dict[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def chat(auth: dict[str, str], query: str) -> tuple[dict, float]:
    started = time.perf_counter_ns()
    response = request(
        "POST",
        "/chat/query",
        body={"query": query, "response_mode": "fast"},
        token=auth["access_token"],
    )
    return response, (time.perf_counter_ns() - started) / 1_000_000


def wait_for_job(auth: dict[str, str], job_id: str, *, timeout_seconds: int = 1200) -> tuple[dict, list[dict], float]:
    started = time.perf_counter_ns()
    deadline = time.monotonic() + timeout_seconds
    observations: list[dict] = []
    previous: tuple[str, int] | None = None
    next_refresh = time.monotonic() + 240
    while time.monotonic() < deadline:
        if time.monotonic() >= next_refresh:
            refreshed = request(
                "POST",
                "/auth/refresh",
                body={"refresh_token": auth["refresh_token"]},
            )
            auth.update(
                access_token=str(refreshed["access_token"]),
                refresh_token=str(refreshed["refresh_token"]),
            )
            next_refresh = time.monotonic() + 240
        job = request("GET", f"/jobs/{job_id}", token=auth["access_token"])
        state = (str(job["status"]), int(job["progress"]))
        if state != previous:
            observations.append({"observed_at": now(), "status": state[0], "progress": state[1]})
            previous = state
            print(json.dumps({"job_id": job_id, **observations[-1]}), flush=True)
        if state[0] in {"succeeded", "failed", "cancelled"}:
            return job, observations, (time.perf_counter_ns() - started) / 1_000_000
        time.sleep(2)
    raise TimeoutError(f"job {job_id} exceeded {timeout_seconds} seconds")


def find_trace(response: dict, node: str) -> list[dict]:
    return [event for event in response.get("agent_trace", []) if event.get("node") == node]


def main() -> None:
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at": now(),
        "base_url": BASE_URL,
        "credentials_persisted": False,
        "cases": {},
        "acceptance": {},
    }
    suffix = uuid.uuid4().hex
    registration = request(
        "POST",
        "/auth/register",
        body={
            "name": "Scoped Relevance Acceptance",
            "email": f"relevance-acceptance-{suffix}@example.com",
            "password": "EphemeralAcceptance#2026!",
            "role": "citizen",
        },
    )
    auth = {
        "access_token": str(registration["access_token"]),
        "refresh_token": str(registration["refresh_token"]),
    }
    report["test_user_id"] = registration["user"]["id"]

    strong_query = "Explain the right to equality under Article 14 in plain language."
    strong, strong_ms = chat(auth, strong_query)
    report["cases"]["strong_article_fast"] = {
        "query": strong_query,
        "client_elapsed_ms": strong_ms,
        "response": strong,
    }
    persist(report)

    pocso_query = "how to file a pocso case"
    pocso, pocso_ms = chat(auth, pocso_query)
    report["cases"]["correct_pocso_fast"] = {
        "query": pocso_query,
        "client_elapsed_ms": pocso_ms,
        "response": pocso,
    }
    persist(report)

    typo_query = "how to file a pocos case?"
    typo_initial, typo_fast_ms = chat(auth, typo_query)
    typo_job, typo_progress, typo_job_ms = wait_for_job(auth, str(typo_initial["job_id"]))
    report["cases"]["typo_pocos_auto_deep"] = {
        "query": typo_query,
        "fast_client_elapsed_ms": typo_fast_ms,
        "initial_response": typo_initial,
        "job_elapsed_ms": typo_job_ms,
        "progress_observations": typo_progress,
        "terminal_job": typo_job,
    }
    persist(report)

    unsupported_query = "What licensing procedure applies to teleportation booths on Mars?"
    unsupported_initial, unsupported_fast_ms = chat(auth, unsupported_query)
    unsupported_job, unsupported_progress, unsupported_job_ms = wait_for_job(
        auth, str(unsupported_initial["job_id"])
    )
    report["cases"]["unsupported_auto_deep"] = {
        "query": unsupported_query,
        "fast_client_elapsed_ms": unsupported_fast_ms,
        "initial_response": unsupported_initial,
        "job_elapsed_ms": unsupported_job_ms,
        "progress_observations": unsupported_progress,
        "terminal_job": unsupported_job,
    }

    strong_citations = strong.get("citations", [])
    pocso_citations = pocso.get("citations", [])
    typo_result = typo_job.get("result") or {}
    unsupported_result = unsupported_job.get("result") or {}
    report["acceptance"] = {
        "a_strong_article_stays_fast": (
            strong.get("delivery_state") == "complete"
            and strong.get("response_mode") == "fast"
            and float(strong.get("confidence_score", 0)) >= float(strong.get("escalation_threshold") or 0.6)
            and bool(strong_citations)
            and all(item.get("verification_status") == "unverified" for item in strong_citations)
        ),
        "b_primary_pocso_act_is_first": (
            pocso.get("delivery_state") == "complete"
            and bool(pocso_citations)
            and pocso_citations[0].get("title") == "The Protection of Children from Sexual Offences Act, 2012"
        ),
        "c_typo_auto_deep_complete_cited_explanation": (
            typo_initial.get("delivery_state") == "searching_more_thoroughly"
            and typo_job.get("status") == "succeeded"
            and typo_result.get("answer") not in {None, "", INSUFFICIENT}
            and str(typo_result.get("answer", "")).count("##") >= 2
            and bool(typo_result.get("citations"))
            and any(
                "protection of children from sexual offences" in str(item.get("title", "")).casefold()
                or "pocso" in str(item.get("title", "")).casefold()
                or "pocso" in str(item.get("excerpt", "")).casefold()
                for item in typo_result.get("citations", [])
            )
            and all(
                item.get("verification_status") == "verified"
                for item in typo_result.get("citations", [])
            )
            and bool(find_trace(typo_result, "query_understanding"))
            and any(
                correction.get("to") == "POCSO"
                for trace in find_trace(typo_result, "query_understanding")
                for correction in trace.get("details", {}).get("legal_term_corrections", [])
            )
        ),
        "d_unsupported_still_abstains": (
            unsupported_initial.get("delivery_state") == "searching_more_thoroughly"
            and unsupported_job.get("status") == "succeeded"
            and unsupported_result.get("answer") == INSUFFICIENT
            and unsupported_result.get("citations") == []
        ),
        "e_honest_quality_scoring_and_labels": (
            strong.get("confidence_score") != unsupported_initial.get("confidence_score")
            and find_trace(strong, "fast_retrieval")[0]["details"].get("confidence_method")
            == "weighted_coverage_recall_x_mandatory_term_match_rate"
            and all(item.get("verification_status") == "unverified" for item in strong_citations)
            and unsupported_initial.get("citations") == []
        ),
    }
    report["completed_at"] = now()
    report["all_acceptance_checks_passed"] = all(report["acceptance"].values())
    persist(report)
    print(json.dumps({"output": str(OUTPUT), **report["acceptance"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
