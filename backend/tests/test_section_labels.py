"""The section headings are an interface, not decoration.

frontend/lib/answer-presentation.ts sorts an answer into basis, limits,
footer and body by pattern-matching the heading text the backend writes.
That coupling is invisible from either side: rename a heading here and the
frontend keeps rendering, but the "Contrary considerations" section stops
being treated as limits and lands in the generic body, where it reads as
part of the answer rather than as a caveat on it.

So the set is pinned here, and frontend/tests/section-labels.test.cjs pins
the same strings against the real classifier. Adding a role or renaming a
heading fails on both sides, which is the point: the failure names the file
that has to change with it.
"""

from __future__ import annotations

import pytest

from app.agents.response_generation import (
    CITIZEN_SECTION_LABELS,
    ROLE_SECTION_LABELS,
)

# Every heading the backend can write. Kept literal rather than derived, so
# that adding one is a deliberate edit in two repositories rather than a
# silent widening here.
EXPECTED = {
    "citizen": [
        "Direct answer",
        "Why this is the legal position",
        "How this applies to you",
        "What you can do now",
        "Important limits",
    ],
    "police": [
        "Direct answer",
        "Governing provision and legal basis",
        "Application to this matter",
        "Required procedural steps",
        "Safeguards, limits and uncertainties",
    ],
    "advocate": [
        "Direct answer",
        "Authority and legal basis",
        "Application to these facts",
        "Steps available",
        "Contrary considerations, limits and gaps",
    ],
}


def test_the_emitted_headings_are_exactly_the_pinned_set() -> None:
    assert {
        role: list(labels.values()) for role, labels in ROLE_SECTION_LABELS.items()
    } == EXPECTED, (
        "The section headings changed. frontend/lib/answer-presentation.ts "
        "classifies sections by matching these strings, and "
        "frontend/tests/section-labels.test.cjs holds the same list. Update "
        "both, or a renamed section silently changes where it renders."
    )


@pytest.mark.parametrize("role", sorted(ROLE_SECTION_LABELS))
def test_every_role_covers_the_same_five_categories(role: str) -> None:
    """A missing category drops verified claims from the answer entirely.

    The assembly iterates the label map, so a category absent from one
    role's map is a category whose verified claims are never rendered for
    that role -- silently, because nothing else references it.
    """
    assert set(ROLE_SECTION_LABELS[role]) == {
        "direct_answer",
        "legal_basis",
        "application",
        "next_step",
        "limit",
    }


@pytest.mark.parametrize("role", sorted(ROLE_SECTION_LABELS))
def test_a_limits_heading_is_recognisable_as_one(role: str) -> None:
    """The frontend routes limits by matching limit/caveat/uncertaint.

    A limits section that misses those words renders as part of the answer
    instead of as a caveat on it, which is the one misclassification that
    changes what the reader believes.
    """
    heading = ROLE_SECTION_LABELS[role]["limit"].lower()

    assert any(word in heading for word in ("limit", "caveat", "uncertaint"))


@pytest.mark.parametrize("role", sorted(ROLE_SECTION_LABELS))
def test_a_basis_heading_is_recognisable_as_one(role: str) -> None:
    heading = ROLE_SECTION_LABELS[role]["legal_basis"].lower()

    assert any(
        phrase in heading for phrase in ("legal basis", "legal position", "applies to you")
    )


@pytest.mark.parametrize("role", sorted(ROLE_SECTION_LABELS))
def test_no_heading_collides_with_the_footer_patterns(role: str) -> None:
    """"currency" or "disclaimer" in a heading sends the whole section to
    the footer, below the answer, where a reader looking for the governing
    provision will not find it."""
    for heading in ROLE_SECTION_LABELS[role].values():
        lowered = heading.lower()
        assert "currency" not in lowered
        assert "disclaimer" not in lowered


def test_an_unknown_role_gets_the_plain_language_shape() -> None:
    """Admin, and anything added later, reads the citizen version.

    Defaulting an unknown reader to the professional shape assumes an
    expertise nobody established.
    """
    from app.agents.response_generation import ROLE_SECTION_LABELS as labels

    assert labels.get("admin", CITIZEN_SECTION_LABELS) is CITIZEN_SECTION_LABELS
