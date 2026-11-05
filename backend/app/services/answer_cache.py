"""Serve an already verified Deep answer when the same question comes back.

Deep latency is 97% language model, and the model is not being downgraded, so a
repeat of a question is the one case where that time can be saved outright:
"what are my rights on arrest" should not cost a minute every time it is asked.

Everything an answer depends on is part of the key, so a change to any of it is a
miss rather than a stale answer: role, collection, model, prompts, quarantined
documents and curated currency. Only a fresh question qualifies. Case material,
an uploaded document or earlier turns all change what the right answer is.
Only a published answer with citations is kept, so a refusal is always retried.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from time import monotonic
from typing import Any

from app.agents.prompt_registry import prompt_versions
from app.core.config import settings
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.quarantine import quarantined_document_ids

TIME_TO_LIVE_SECONDS = 24 * 60 * 60


def cacheable_request(*, case_id: str | None, history: list, document_context: str) -> bool:
    return case_id is None and not history and not document_context


def _cacheable_result(result: dict[str, Any]) -> bool:
    answer = result.get("final_answer")
    return bool(answer) and answer != INSUFFICIENT_EVIDENCE and bool(result.get("citations"))


def _currency_version() -> int:
    try:
        path = Path(settings.legal_kb_root) / "metadata" / "currency_status.json"
        return path.stat().st_mtime_ns
    except OSError:
        return 0


class AnswerCache:
    def __init__(self, *, limit: int | None = None, time_to_live: float = TIME_TO_LIVE_SECONDS) -> None:
        self._limit = settings.answer_cache_size if limit is None else limit
        self._time_to_live = time_to_live
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._prompts: dict[str, str] | None = None

    def _key(self, query: str, role: str) -> str:
        if self._prompts is None:
            self._prompts = prompt_versions()
        return hashlib.sha256(
            json.dumps(
                [
                    " ".join(query.casefold().split()),
                    role,
                    settings.qdrant_global_collection,
                    settings.ollama_model,
                    self._prompts,
                    sorted(quarantined_document_ids()),
                    _currency_version(),
                ],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    def get(self, query: str, role: str) -> dict[str, Any] | None:
        if not self._limit:
            return None
        key = self._key(query, role)
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, result = entry
        if monotonic() - stored_at > self._time_to_live:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return copy.deepcopy(result)

    def put(self, query: str, role: str, result: dict[str, Any]) -> None:
        if not self._limit or not _cacheable_result(result):
            return
        self._entries[self._key(query, role)] = (monotonic(), copy.deepcopy(result))
        while len(self._entries) > self._limit:
            self._entries.popitem(last=False)
