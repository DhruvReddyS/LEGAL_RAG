#!/usr/bin/env python3
"""Record the live strong-match Fast acceptance case."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from relevance_fix_acceptance import chat, request


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/evidence/fast-deep-relevance-fix-strong-fast-rerun-raw.json"


def main() -> None:
    registration = request(
        "POST",
        "/auth/register",
        body={
            "name": "Strong Fast Acceptance Rerun",
            "email": f"strong-fast-rerun-{uuid.uuid4().hex}@example.com",
            "password": "EphemeralAcceptance#2026!",
            "role": "citizen",
        },
    )
    auth = {
        "access_token": str(registration["access_token"]),
        "refresh_token": str(registration["refresh_token"]),
    }
    query = "Article 14 equality"
    response, elapsed_ms = chat(auth, query)
    passed = (
        response.get("delivery_state") == "complete"
        and response.get("response_mode") == "fast"
        and response.get("evidence_strength") == "strong"
        and float(response.get("confidence_score", 0)) >= 0.75
        and bool(response.get("citations"))
        and all(
            citation.get("verification_status") == "unverified"
            for citation in response.get("citations", [])
        )
    )
    report = {
        "schema_version": 1,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "credentials_persisted": False,
        "test_user_id": registration["user"]["id"],
        "query": query,
        "client_elapsed_ms": elapsed_ms,
        "response": response,
        "acceptance_a_passed": passed,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "acceptance_a_passed": passed}, indent=2))


if __name__ == "__main__":
    main()
