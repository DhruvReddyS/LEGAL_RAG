"""Every prompt sent to the model must have a version recorded with a result.

The PRD requires prompts to be versioned artifacts and every eval result to
carry the version it was measured under. A hand-maintained number does not
achieve that: it goes stale the first time a prompt is edited quickly, and a
stale version is worse than none, because two different prompts then claim the
same identity and the eval history stops meaning anything.

The version is therefore a fingerprint of the source of the function that
builds the prompt. The test that matters is not that fingerprints exist, but
that no prompt escapes the registry.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.agents.prompt_registry import prompt_versions, registered_prompt_names

_BACKEND = Path(__file__).resolve().parents[1]

# Where a prompt is assigned before being sent to the model.
_ASSIGNS_A_PROMPT = re.compile(r"^\s*(?:retry_)?prompt\s*=\s*f?[\"']{3}", re.MULTILINE)


def _functions_that_build_prompts() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted((_BACKEND / "app").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if not _ASSIGNS_A_PROMPT.search(source):
            continue
        tree = ast.parse(source)
        lines = {
            source[: match.start()].count("\n") + 1
            for match in _ASSIGNS_A_PROMPT.finditer(source)
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(node.lineno <= line <= (node.end_lineno or 0) for line in lines):
                found.add((str(path.relative_to(_BACKEND)), node.name))
    return found


def test_every_prompt_building_function_is_registered() -> None:
    """The guard against a new agent shipping unversioned.

    Adding a prompt is a normal change; remembering to register it is not
    something a reviewer will reliably catch.
    """
    from app.agents import prompt_registry

    registered_sources = {
        (
            str(Path(builder.__code__.co_filename).resolve().relative_to(_BACKEND)),
            builder.__name__,
        )
        for builder in prompt_registry._builders().values()
    }
    discovered = _functions_that_build_prompts()

    unregistered = discovered - registered_sources
    assert not unregistered, (
        "these functions build a prompt but no version is recorded for them, so "
        f"a result measured under them cannot be reproduced: {sorted(unregistered)}"
    )


def test_a_version_is_produced_for_every_registered_prompt() -> None:
    versions = prompt_versions()

    assert set(versions) == set(registered_prompt_names())
    assert all(re.fullmatch(r"[0-9a-f]{12}", value) for value in versions.values())


def test_versions_differ_between_prompts() -> None:
    """Identical fingerprints would mean the registry is reading one function."""
    versions = prompt_versions()

    assert len(set(versions.values())) == len(versions)


def test_the_version_is_stable_across_calls() -> None:
    assert prompt_versions() == prompt_versions()
