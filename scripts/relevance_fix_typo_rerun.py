#!/usr/bin/env python3
"""Targeted live rerun for acceptance case (c) after citation-label repair."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from relevance_fix_acceptance import INSUFFICIENT, chat, request, wait_for_job


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/evidence/fast-deep-relevance-fix-typo-rerun-raw.json"


def main() -> None:
    registration = request(
        "POST",
        "/auth/register",
        body={
            "name": "POCSO Typo Acceptance Rerun",
            "email": f"pocso-typo-rerun-{uuid.uuid4().hex}@example.com",
            "password": "EphemeralAcceptance#2026!",
            "role": "citizen",
        },
    )
    auth = {
        "access_token": str(registration["access_token"]),
        "refresh_token": str(registration["refresh_token"]),
    }
    query = "how to file a pocos case?"
    initial, fast_ms = chat(auth, query)
    terminal, progress, job_ms = wait_for_job(auth, str(initial["job_id"]))
    result = terminal.get("result") or {}
    query_events = [
        event for event in result.get("agent_trace", [])
        if event.get("node") == "query_understanding"
    ]
    citations = result.get("citations", [])
    passed = (
        initial.get("delivery_state") == "searching_more_thoroughly"
        and terminal.get("status") == "succeeded"
        and result.get("answer") not in {None, "", INSUFFICIENT}
        and str(result.get("answer", "")).count("##") >= 2
        and bool(citations)
        and all(item.get("verification_status") == "verified" for item in citations)
        and any("pocso" in str(item.get("excerpt", "")).casefold() for item in citations)
        and any(
            correction.get("to") == "POCSO"
            for event in query_events
            for correction in event.get("details", {}).get("legal_term_corrections", [])
        )
        and all(
            "pocos" not in event.get("details", {}).get("query", "").casefold()
            for event in result.get("agent_trace", [])
            if event.get("node") == "retrieval"
        )
    )
    report = {
        "schema_version": 1,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "credentials_persisted": False,
        "test_user_id": registration["user"]["id"],
        "query": query,
        "fast_client_elapsed_ms": fast_ms,
        "initial_response": initial,
        "job_elapsed_ms": job_ms,
        "progress_observations": progress,
        "terminal_job": terminal,
        "acceptance_c_passed": passed,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "acceptance_c_passed": passed}, indent=2))


if __name__ == "__main__":
    main()
