from __future__ import annotations

import pytest

from app.services.fast_research import FastLegalResearchService
from app.services.retrieval import RetrievalHit, RetrievalTimings


class FakeRetrieval:
    def __init__(
        self,
        hits: list[RetrievalHit],
        *,
        distinctive_terms: list[str] | None = None,
        term_document_counts: dict[str, int] | None = None,
    ) -> None:
        self.hits = hits
        self.calls: list[dict] = []
        self.distinctive_terms = distinctive_terms or []
        self.term_document_counts = term_document_counts or {}

    async def search_with_timings(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return self.hits, RetrievalTimings(
            embedding_ms=420.0,
            qdrant_ms=35.0,
            reranking_ms=0.0,
            total_ms=455.0,
            embedding_cache_hit=True,
            lexical_distinctive_terms=self.distinctive_terms,
            lexical_term_document_counts=self.term_document_counts,
        )


def hit(chunk_id: str, document_id: str, title: str, *, current: bool) -> RetrievalHit:
    return RetrievalHit(
        point_id=chunk_id,
        payload={
            "chunk_id": chunk_id,
            "canonical_document_id": document_id,
            "title": title,
            "source_type": "act",
            "act_name": title,
            "section": "154",
            "page_start": 4,
            "page_end": 5,
            "text": "The supplied Gold passage states when police must record information and the procedural requirement.",
            "is_current": current,
        },
        dense_score=0.8,
        sparse_score=4.0,
        fused_score=0.7,
        reranker_score=0.7,
    )


@pytest.mark.asyncio
async def test_fast_research_is_retrieval_only_and_exposes_currency_warning() -> None:
    retrieval = FakeRetrieval([
        hit("chunk-a", "doc-a", "Official Procedure Act", current=True),
        hit("chunk-b", "doc-b", "Official Amendment", current=False),
    ])
    service = FastLegalResearchService(retrieval)  # type: ignore[arg-type]

    result = await service.run(
        query="When must police record information?",
        role="citizen",
        case_id=None,
        history=[],
    )

    # Dense + sparse with server-side RRF, and no cross-encoder: the fast lane
    # takes its ranking from the query rather than from an unranked full-text
    # scroll, but still runs no reranker and no model.
    assert retrieval.calls[0]["rerank"] is False
    assert retrieval.calls[0].get("lexical_only") is not True
    assert "does not synthesise a final legal opinion" in result["final_answer"]
    assert "Currency notice" in result["final_answer"]
    assert [item.chunk_id for item in result["citations"]] == ["chunk-a", "chunk-b"]
    assert result["agent_trace"][0].details["no_generative_claims"] is True
    assert result["timings"]["embedding_cache_hit"] is True
    assert result["timings"]["reranking_ms"] == 0
    assert all(item.verification_status == "unverified" for item in result["citations"])


@pytest.mark.asyncio
async def test_fast_research_abstains_when_no_gold_evidence_is_found() -> None:
    result = await FastLegalResearchService(FakeRetrieval([])).run(  # type: ignore[arg-type]
        query="unsupported question", role="citizen", case_id=None, history=[]
    )

    assert result["citations"] == []
    assert result["confidence_score"] == 0
    assert result["evidence_strength"] == "insufficient"


@pytest.mark.asyncio
async def test_fast_research_rejects_missing_child_results_for_missing_pet_query() -> None:
    child_result = hit("child-a", "doc-child", "Procedure for missing children", current=True)
    child_result.payload["text"] = "Police shall register information and trace a missing child."
    result = await FastLegalResearchService(FakeRetrieval([child_result])).run(  # type: ignore[arg-type]
        query="How should I report a missing pet dog and request an FIR?",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert result["citations"] == []
    assert result["confidence_score"] == 0
    assert result["evidence_strength"] == "insufficient"
    assert result["agent_trace"][0].details["result_count"] == 0


@pytest.mark.asyncio
async def test_fast_research_prefers_distinct_authorities_before_duplicate_passages() -> None:
    first = hit("doc-a-1", "doc-a", "Authority A", current=True)
    duplicate = hit("doc-a-2", "doc-a", "Authority A", current=True)
    second = hit("doc-b-1", "doc-b", "Authority B", current=True)
    third = hit("doc-c-1", "doc-c", "Authority C", current=True)
    fourth = hit("doc-d-1", "doc-d", "Authority D", current=True)
    result = await FastLegalResearchService(FakeRetrieval([first, duplicate, second, third, fourth])).run(  # type: ignore[arg-type]
        query="When must police record information?", role="citizen", case_id=None, history=[]
    )

    assert [item.chunk_id for item in result["citations"]] == ["doc-a-1", "doc-b-1", "doc-c-1", "doc-d-1"]
    assert result["agent_trace"][0].details["unique_document_count"] == 4


@pytest.mark.asyncio
async def test_fast_research_does_not_pad_with_duplicate_authorities() -> None:
    first = hit("doc-a-1", "", "Same authority", current=True)
    duplicate = hit("doc-a-2", "", "Same authority", current=True)
    result = await FastLegalResearchService(FakeRetrieval([first, duplicate])).run(  # type: ignore[arg-type]
        query="When must police record information?", role="citizen", case_id=None, history=[]
    )

    assert [item.chunk_id for item in result["citations"]] == ["doc-a-1"]
    assert result["agent_trace"][0].details["unique_document_count"] == 1


@pytest.mark.asyncio
async def test_fast_research_bad_generic_match_cannot_report_high_confidence() -> None:
    unrelated = hit("generic-a", "doc-generic", "Unrelated judgment", current=True)
    unrelated.payload["text"] = "The party may file the case before the appropriate court."

    result = await FastLegalResearchService(
        FakeRetrieval([unrelated], distinctive_terms=["pocso"])
    ).run(  # type: ignore[arg-type]
        query="how to file a pocso case",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert result["confidence_score"] <= 0.45
    assert result["evidence_strength"] == "insufficient"
    assert all(item.verification_status == "unverified" for item in result["citations"])


@pytest.mark.asyncio
async def test_fast_research_requires_rare_distinctive_term_and_surfaces_pocso() -> None:
    generic = hit("generic-a", "doc-generic", "Unrelated judgment", current=True)
    generic.payload["text"] = "The party may file the case before the appropriate court."
    pocso = hit(
        "pocso-a",
        "doc-pocso",
        "The Protection of Children from Sexual Offences Act, 2012",
        current=True,
    )
    pocso.payload["text"] = "A person may file a POCSO case under the prescribed procedure."
    retrieval = FakeRetrieval(
        [generic, pocso],
        distinctive_terms=["pocso"],
        term_document_counts={"case": 6698, "file": 485, "pocso": 291},
    )

    result = await FastLegalResearchService(retrieval).run(  # type: ignore[arg-type]
        query="how to file a pocso case",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert [item.chunk_id for item in result["citations"]] == ["pocso-a"]
    assert result["agent_trace"][0].details["distinctive_terms"] == ["pocso"]
    assert result["citations"][0].verification_status == "unverified"
    assert result["confidence_score"] >= 0.6
    # The acronym is expanded for matching even though the query is now sent
    # whole to dense retrieval: the expansion is what lets a passage naming
    # "Protection of Children from Sexual Offences" satisfy a question that
    # only says "POCSO".
    from app.services.fast_research import _focus_tokens

    assert _focus_tokens("what does POCSO require").issuperset(
        {"pocso", "protection", "children", "sexual", "offences"}
    )


@pytest.mark.asyncio
async def test_full_act_name_satisfies_acronym_mandatory_gate() -> None:
    act = hit(
        "pocso-act",
        "doc-pocso-act",
        "The Protection of Children from Sexual Offences Act, 2012",
        current=True,
    )
    act.payload["text"] = "Protection of children from sexual offences is governed by this Act."
    retrieval = FakeRetrieval([act], distinctive_terms=["pocso"])

    result = await FastLegalResearchService(retrieval).run(  # type: ignore[arg-type]
        query="pocso case",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert [citation.chunk_id for citation in result["citations"]] == ["pocso-act"]


def test_presentation_words_are_not_legal_focus_terms() -> None:
    from app.services.fast_research import _focus_tokens

    assert _focus_tokens(
        "Explain the right to equality under Article 14 in plain language."
    ) == {"right", "equality", "article", "14"}


@pytest.mark.asyncio
async def test_high_relevance_fast_match_is_labelled_strong() -> None:
    authority = hit("article-14", "constitution", "Article 14 authority", current=True)
    authority.payload["text"] = "Article 14 guarantees equality before the law and equal protection."
    retrieval = FakeRetrieval(
        [authority],
        distinctive_terms=["equality"],
        term_document_counts={"article": 2302, "14": 2156, "equality": 242},
    )

    result = await FastLegalResearchService(retrieval).run(  # type: ignore[arg-type]
        query="Article 14 equality",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert result["confidence_score"] >= 0.75
    assert result["evidence_strength"] == "strong"


def test_discriminative_legal_words_survive_stopword_removal() -> None:
    """Presentation vocabulary is stripped; corpus vocabulary is not."""
    from app.services.fast_research import _focus_tokens

    tokens = _focus_tokens(
        "Please explain in plain language what I should tell police when "
        "reporting missing property under the law."
    )

    for kept in ("police", "reporting", "missing", "property", "law"):
        assert kept in tokens, kept
    for stripped in ("please", "explain", "plain", "language", "what", "should"):
        assert stripped not in tokens, stripped


@pytest.mark.asyncio
async def test_fast_lane_corrects_a_misspelled_acronym() -> None:
    """Typo correction ran in the Deep path only.

    "pocos" retrieved nothing in Fast while working correctly one lane over.
    """
    retrieval = FakeRetrieval([hit("chunk-a", "doc-a", "POCSO Act", current=True)])
    service = FastLegalResearchService(retrieval)  # type: ignore[arg-type]

    result = await service.run(
        query="how do I file a pocos case", role="citizen", case_id=None, history=[]
    )

    # The corrected term reaches retrieval, whichever transport it uses.
    sent = retrieval.calls[0].get("query", "")
    assert "POCSO" in sent
    assert "pocos" not in sent.casefold()
    corrections = result["agent_trace"][0].details["legal_term_corrections"]
    assert corrections == [{"from": "pocos", "to": "POCSO"}]


def test_three_letter_acronyms_are_correctable_without_becoming_ambiguous() -> None:
    """bns, bsa and ipc were below the old four-character floor."""
    from app.services.legal_term_normalization import normalize_legal_terms

    assert normalize_legal_terms("what does bnd say").normalized == "what does BNS say"
    assert normalize_legal_terms("under ipa section 302").normalized == "under IPC section 302"
    # Ambiguity must still refuse: bns and bnss are both one edit from "bnss".
    assert normalize_legal_terms("under bnss rules").normalized == "under bnss rules"
