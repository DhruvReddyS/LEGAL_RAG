"""Prompt versions, derived from the code that builds them.

The PRD requires that every eval result record the prompt version alongside
the model, temperature and seed, and that prompts be versioned artifacts. A
number someone remembers to bump is not that: it goes stale the first time a
prompt is edited in a hurry, and a stale version is worse than none, because
two different prompts then claim the same identity and the eval history
silently stops meaning anything.

So the version is a fingerprint of the source of the function that constructs
the prompt. It changes exactly when the code that produces the prompt changes,
and cannot be forgotten. It also changes for edits that do not alter the prompt
text -- a refactor of the same function -- which is the safe direction: a
spurious version bump costs a re-measurement, a missed one costs the ability
to compare results at all.
"""

from __future__ import annotations

import hashlib
import inspect
from typing import Callable

_FINGERPRINT_CHARACTERS = 12


def _fingerprint(builder: Callable[..., object]) -> str:
    source = inspect.getsource(builder)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:_FINGERPRINT_CHARACTERS]


def _builders() -> dict[str, Callable[..., object]]:
    # Imported lazily so importing this module does not drag in the agent
    # graph, its model client and their dependencies.
    from app.agents.defence_strategy_agent import DefenceStrategyAgent
    from app.agents.drafting_agent import LegalDraftingAgent
    from app.agents.query_understanding import query_understanding_node
    from app.agents.reasoning_agent import reasoning_node
    from app.agents.verification_agent import verification_node
    from app.services.document_analysis import DocumentAnalysisService

    return {
        "query_understanding": query_understanding_node,
        "reasoning": reasoning_node,
        "verification": verification_node,
        "drafting_fact_extraction": LegalDraftingAgent._extract_facts,
        "defence_strategy": DefenceStrategyAgent.run,
        "document_analysis": DocumentAnalysisService.analyze,
    }


def prompt_versions() -> dict[str, str]:
    """A fingerprint per prompt, for recording alongside a measurement."""
    return {name: _fingerprint(builder) for name, builder in _builders().items()}


def registered_prompt_names() -> frozenset[str]:
    return frozenset(_builders())
