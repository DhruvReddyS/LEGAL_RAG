"""A repealed Act may ground a published claim. It may never do so silently.

`CurrencyDecision.may_ground_a_published_claim` returns `saves_prior_conduct`
for a superseded source, because an offence committed before 1 July 2024 is
still tried under the old codes and refusing to answer about it would decline
the law that actually governs. The docstring states the condition attached to
that permission:

    The label is not optional in the second and third cases, which is why
    callers take the whole decision rather than this flag on its own.

Deep's response generation took the whole decision and then dropped the label
whenever the successor was unknown. Its only record was
`replaced[name] = decision.superseded_by`, guarded by
`if decision.superseded_by`, and a superseded source skips the `unverified`
branch too -- so for a repealed Act with no recorded successor the answer said
nothing at all about currency, while still resting a published legal claim on
it.

Reachability, stated precisely, because the first version of these tests
overstated it. A *payload* cannot produce this state: the `is_superseded`
branch of `resolve_currency` hardcodes `saves_prior_conduct=False`, so a
flag-marked source cannot ground a claim at all. The repeal table always names
a successor, and so do all four saving entries in `currency_status.json`
today. The one route in is a curated-table entry marking an instrument
superseded and prior-conduct-saving without naming what replaced it -- a
hand-edit to a reviewed JSON file, which is why these tests patch the resolver
rather than pretending a payload reaches it.

So this is latent, not live. It is worth closing because the contract above is
explicit, because the Fast lane already warns on such a source while Deep
stayed silent, and because that is the third currency divergence between the
lanes found in this audit.

No Qdrant, no embedder, no model.
"""

from __future__ import annotations

import pytest

from app.agents.response_generation import response_generation_node
from app.schemas.agents import ClaimVerification, QueryIntent, VerificationResult
from app.services.currency import CurrencyDecision, CurrencyStatus, resolve_currency
from app.services.fast_research import currency_notice
from app.services.retrieval import RetrievalHit


# A superseded instrument that still governs prior conduct and whose successor
# this corpus does not record.
SUCCESSORLESS = {
    "chunk_id": "manual-1",
    "text": "Every prisoner shall be provided with adequate bedding.",
    "title": "The Model Prison Manual",
    "act_name": "The Model Prison Manual",
    "section": "12",
    "source_type": "manual",
    "page_start": 40,
    "page_end": 40,
    "is_superseded": True,
    "saves_prior_conduct": True,
}


def _hit(payload: dict) -> RetrievalHit:
    return RetrievalHit(
        point_id=str(payload["chunk_id"]),
        payload=payload,
        dense_score=0.8,
        sparse_score=0.2,
        fused_score=0.5,
        reranker_score=0.5,
    )


def _state(payload: dict) -> dict:
    claim = "A prisoner is entitled to adequate bedding"
    return {
        "role": "citizen",
        "query": "What bedding must a prison provide?",
        "retrieved_chunks": [_hit(payload)],
        "evidence_addresses_question": True,
        "draft_answer": f"[LEGAL_BASIS] {claim} [SRC:{payload['chunk_id']}]",
        "verification_result": VerificationResult(
            score=1.0,
            supported_claims=1,
            total_claims=1,
            claims=[
                ClaimVerification(
                    claim=claim,
                    chunk_id=str(payload["chunk_id"]),
                    category="legal_basis",
                    verdict="yes",
                    reason="",
                )
            ],
            unsupported_claims=[],
        ),
        "intent": QueryIntent(retrieval_query="prison bedding"),
        "agent_trace": [],
        "stage_metrics": [],
        "timings": {},
    }


SAVING_WITHOUT_SUCCESSOR = CurrencyDecision(
    status=CurrencyStatus.SUPERSEDED,
    superseded_by=None,
    basis="Curated entry: repealed, saves prior conduct, successor not recorded.",
    source="curated",
    saves_prior_conduct=True,
)


@pytest.fixture
def successorless(monkeypatch):
    """Resolve this one source the way a curated entry would.

    Patched at the resolver because that is the only route in. See the module
    docstring: the payload branch cannot produce a saving superseded source,
    so building the payload and hoping would test nothing.
    """
    monkeypatch.setattr(
        "app.agents.response_generation.resolve_currency",
        lambda payload: SAVING_WITHOUT_SUCCESSOR,
    )


def test_the_permission_to_ground_a_claim_really_does_exist_here() -> None:
    """The premise. If this stopped being true the defect would be moot."""
    assert SAVING_WITHOUT_SUCCESSOR.status is CurrencyStatus.SUPERSEDED
    assert SAVING_WITHOUT_SUCCESSOR.superseded_by is None
    assert SAVING_WITHOUT_SUCCESSOR.may_ground_a_published_claim is True
    assert SAVING_WITHOUT_SUCCESSOR.requires_a_currency_label is True


def test_a_payload_alone_cannot_reach_this_state() -> None:
    """Pins the reachability claim rather than asserting it in prose.

    `is_superseded: True` hardcodes `saves_prior_conduct=False`, so a
    flag-marked superseded source cannot ground a published claim at all. If
    that ever changes, this fails and the live/latent distinction above has to
    be rewritten.
    """
    decision = resolve_currency(SUCCESSORLESS)
    assert decision.status is CurrencyStatus.SUPERSEDED
    assert decision.saves_prior_conduct is False
    assert decision.may_ground_a_published_claim is False


def test_a_claim_grounded_on_it_is_published(successorless) -> None:
    """Confirms the answer is not refused, so the warning is what protects."""
    result = response_generation_node(_state(SUCCESSORLESS))
    assert "adequate bedding" in result["final_answer"]
    assert len(result["citations"]) == 1


def test_the_answer_says_it_is_no_longer_in_force(successorless) -> None:
    answer = response_generation_node(_state(SUCCESSORLESS))["final_answer"]
    assert "## Source currency" in answer
    assert "no longer in force" in answer
    assert "The Model Prison Manual" in answer


def test_the_answer_says_the_successor_is_not_recorded(successorless) -> None:
    """"No longer in force" without this reads as an omission a reader can fix.

    They cannot: the corpus does not know the successor, and saying so is what
    sends them to the official text instead of to a pointer that is not there.
    """
    answer = response_generation_node(_state(SUCCESSORLESS))["final_answer"]
    assert "does not record" in answer


def test_a_superseded_source_with_a_known_successor_still_names_it() -> None:
    """The behaviour that already worked must not regress.

    Unpatched: a payload naming its own successor reaches the
    `payload_successor` branch, which honours `saves_prior_conduct`.
    """
    with_successor = {**SUCCESSORLESS, "replaced_by": "The Model Prison Manual, 2016"}
    answer = response_generation_node(_state(with_successor))["final_answer"]
    assert "was replaced by The Model Prison Manual, 2016" in answer
    assert "does not record" not in answer


def test_an_in_force_source_produces_no_currency_section() -> None:
    """A warning on every answer carries no information."""
    in_force = {
        "chunk_id": "bnss-35",
        "text": "A police officer may arrest without a warrant in the cases stated.",
        "title": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
        "act_name": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
        "section": "35",
        "source_type": "act",
        "page_start": 12,
        "page_end": 12,
        "is_current": True,
    }
    answer = response_generation_node(_state(in_force))["final_answer"]
    assert "## Source currency" not in answer


def test_the_two_lanes_agree_about_this_source(successorless) -> None:
    """The divergence that made this worth fixing.

    Fast already warned on this source. Deep did not. Three currency
    divergences between lanes have now been found in this codebase, each one a
    lane reading the payload for itself instead of asking the shared
    primitive.
    """
    fast = currency_notice([SUCCESSORLESS])
    deep = response_generation_node(_state(SUCCESSORLESS))["final_answer"]
    assert fast is not None
    assert "no longer in force" in fast
    assert "no longer in force" in deep
    assert "The Model Prison Manual" in fast
    assert "The Model Prison Manual" in deep


def test_a_superseded_source_that_saves_nothing_cannot_ground_a_claim_at_all() -> None:
    """The first of the three cases, unchanged: refusal, not a label.

    A manual replaced by a later edition governs no period at all, so there is
    nothing to warn about -- it must not reach the reader in the first place.
    """
    decision = CurrencyDecision(
        status=CurrencyStatus.SUPERSEDED,
        superseded_by=None,
        basis="test",
        source="test",
        saves_prior_conduct=False,
    )
    assert decision.may_ground_a_published_claim is False
    # The payload route produces exactly this, which is why it abstains.
    answer = response_generation_node(_state(SUCCESSORLESS))["final_answer"]
    assert "adequate bedding" not in answer
