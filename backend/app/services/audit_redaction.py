"""What may leave an agent trace for the audit log, and what an audit read shows.

The retrieval node's trace carries `query`, `initial_query` and `topic_query`.
Sync Deep copied the whole trace into audit metadata, so a citizen's question sat
near-verbatim in `audit_logs`, readable at /admin/audit, and it outlives the user
because the actor column is SET NULL on delete.

An allowlist rather than a list of known-bad keys. The next trace field somebody
adds should stay out by default. Numbers and booleans describe what a run did;
any string might be what somebody said.
"""

from __future__ import annotations

from typing import Any

# Keys that hold text a person wrote or evidence somebody uploaded, in rows
# written before the allowlist existed. Read paths drop them recursively.
_TEXT_KEYS = frozenset(
    {
        "agent_trace",
        "answer",
        "content",
        "correction_text",
        "current",
        "excerpt",
        "initial_query",
        "objective",
        "previous",
        "prompt",
        "query",
        "question",
        "safety_boundary",
        "text",
        "topic_query",
    }
)


def trace_for_audit(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each node, with only the numeric and boolean details it reported."""
    return [
        {
            "node": str(event.get("node", "")),
            "details": {
                str(key): value
                for key, value in (event.get("details") or {}).items()
                if isinstance(value, (bool, int, float))
            },
        }
        for event in trace
    ]


def redact_audit_metadata(value: Any) -> Any:
    """A copy of stored audit metadata with any user or evidence text removed.

    The migration scrubs rows it can identify. This is the second layer: an
    administrator reading the log must not see text in any row, however old.
    """
    if isinstance(value, dict):
        return {
            key: redact_audit_metadata(item)
            for key, item in value.items()
            if str(key).casefold() not in _TEXT_KEYS
        }
    if isinstance(value, list):
        return [redact_audit_metadata(item) for item in value]
    return value
