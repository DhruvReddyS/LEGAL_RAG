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
        followed: list[RetrievalHit] | None = None,
    ) -> None:
        self.hits = hits
        self.calls: list[dict] = []
        self.distinctive_terms = distinctive_terms or []
        self.term_document_counts = term_document_counts or {}
        self.followed = followed or []

    async def search_with_timings(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return self.hits, RetrievalTimings(
            embedding_ms=420.0,
            qdrant_ms=35.0,
            reranking_ms=0.0,
            total_ms=455.0,
            embedding_cache_hit=True,
        )

    async def distinctive_query_terms(self, terms, *, target):
        """The Fast lane computes these itself now.

        It stopped being able to read them from the timings when the lane moved
        off the lexical path, which is what let the mandatory-term gate quietly
        become a no-op.
        """
        del terms, target
        return dict(self.term_document_counts), list(self.distinctive_terms)

    async def fetch_followed_provisions(self, hits, *, target, query=""):
        del hits, target, query
        return list(self.followed)


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
    retrieval = FakeRetrieval(
        [
            hit("chunk-a", "doc-a", "Official Procedure Act", current=True),
            hit("chunk-b", "doc-b", "Official Amendment", current=False),
        ]
    )
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
async def test_fast_research_rejects_missing_child_results_for_missing_pet_query() -> (
    None
):
    child_result = hit(
        "child-a", "doc-child", "Procedure for missing children", current=True
    )
    child_result.payload["text"] = (
        "Police shall register information and trace a missing child."
    )
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
async def test_fast_research_prefers_distinct_authorities_before_duplicate_passages() -> (
    None
):
    first = hit("doc-a-1", "doc-a", "Authority A", current=True)
    duplicate = hit("doc-a-2", "doc-a", "Authority A", current=True)
    second = hit("doc-b-1", "doc-b", "Authority B", current=True)
    third = hit("doc-c-1", "doc-c", "Authority C", current=True)
    fourth = hit("doc-d-1", "doc-d", "Authority D", current=True)
    result = await FastLegalResearchService(
        FakeRetrieval([first, duplicate, second, third, fourth])
    ).run(  # type: ignore[arg-type]
        query="When must police record information?",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert [item.chunk_id for item in result["citations"]] == [
        "doc-a-1",
        "doc-b-1",
        "doc-c-1",
        "doc-d-1",
    ]
    assert result["agent_trace"][0].details["unique_document_count"] == 4


@pytest.mark.asyncio
async def test_fast_research_does_not_pad_with_duplicate_authorities() -> None:
    first = hit("doc-a-1", "", "Same authority", current=True)
    duplicate = hit("doc-a-2", "", "Same authority", current=True)
    result = await FastLegalResearchService(FakeRetrieval([first, duplicate])).run(  # type: ignore[arg-type]
        query="When must police record information?",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert [item.chunk_id for item in result["citations"]] == ["doc-a-1"]
    assert result["agent_trace"][0].details["unique_document_count"] == 1


@pytest.mark.asyncio
async def test_fast_research_places_exact_implementation_before_commentary() -> None:
    commentary = hit("commentary", "doc-case", "Arrest judgment", current=True)
    commentary.payload["text"] = (
        "The grounds of arrest must be communicated to the arrested person."
    )
    provision = hit("bnss-47", "doc-bnss", "BNSS", current=True)
    provision.payload["section"] = "47"
    provision.payload["retrieval_enrichment_relation"] = "implementation_bridge"
    retrieval = FakeRetrieval([commentary], followed=[provision])

    result = await FastLegalResearchService(retrieval).run(  # type: ignore[arg-type]
        query="Must grounds of arrest be communicated to the arrested person?",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert [item.chunk_id for item in result["citations"]][:2] == [
        "bnss-47",
        "commentary",
    ]
    assert result["timings"]["followed_chunk_count"] == 1


@pytest.mark.asyncio
async def test_fast_research_bad_generic_match_cannot_report_high_confidence() -> None:
    unrelated = hit("generic-a", "doc-generic", "Unrelated judgment", current=True)
    unrelated.payload["text"] = (
        "The party may file the case before the appropriate court."
    )

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
async def test_fast_research_requires_rare_distinctive_term_and_surfaces_pocso() -> (
    None
):
    generic = hit("generic-a", "doc-generic", "Unrelated judgment", current=True)
    generic.payload["text"] = (
        "The party may file the case before the appropriate court."
    )
    pocso = hit(
        "pocso-a",
        "doc-pocso",
        "The Protection of Children from Sexual Offences Act, 2012",
        current=True,
    )
    pocso.payload["text"] = (
        "A person may file a POCSO case under the prescribed procedure."
    )
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
    act.payload["text"] = (
        "Protection of children from sexual offences is governed by this Act."
    )
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


def test_plural_focus_term_matches_singular_statutory_wording() -> None:
    from app.services.fast_research import _lexical_coverage

    assert (
        _lexical_coverage(
            {"loudspeakers", "noise"},
            {"text": "The authority may regulate loudspeaker noise at night."},
        )
        == 1.0
    )


@pytest.mark.asyncio
async def test_high_relevance_fast_match_is_labelled_strong() -> None:
    authority = hit("article-14", "constitution", "Article 14 authority", current=True)
    authority.payload["text"] = (
        "Article 14 guarantees equality before the law and equal protection."
    )
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
    assert (
        normalize_legal_terms("under ipa section 302").normalized
        == "under IPC section 302"
    )
    # Ambiguity must still refuse: bns and bnss are both one edit from "bnss".
    assert normalize_legal_terms("under bnss rules").normalized == "under bnss rules"


class TestDistinctiveTermsAreNotReadFromTimings:
    """The regression this class exists to prevent.

    `lexical_distinctive_terms` is populated only by the lexical retrieval
    path. When the Fast lane moved to dense+sparse RRF it stopped travelling
    that path, so the field arrived empty and `_mandatory_focus_match` -- which
    treats an empty requirement set as "nothing required" -- became a no-op.
    The only surviving gate was an unweighted coverage floor, and abstention
    against the golden set fell to 0.33: four of six known corpus gaps were
    answered rather than declined.

    Nothing failed. The suite kept passing because the test double supplied
    the field through the timings, faithfully reproducing a path production no
    longer used. So the double below deliberately returns *empty* timings and
    supplies the terms only through the method, which is where the lane must
    now get them.
    """

    class TimingsWithoutDistinctiveTerms(FakeRetrieval):
        """The RRF path, which carries no lexical term statistics at all.

        The fields this once had to blank no longer exist: removing the dead
        lexical path took them with it, so the lane cannot read them even by
        accident. The test remains because the *behaviour* it protects -- the
        gate applying from terms the lane computed itself -- is what matters,
        not the mechanism that once broke it.
        """

    @pytest.mark.asyncio
    async def test_the_gate_still_applies_when_timings_carry_nothing(self) -> None:
        # This passage must clear the coverage floor, or the floor rejects it
        # first and the mandatory-term gate is never reached -- which is what
        # made two earlier versions of this test pass against the bug it was
        # written to catch. Of {landlord, security, deposit, returned} it
        # carries three, so coverage is 0.75 against a floor of 0.34, and the
        # one term it lacks is the one that decides the topic. The query is
        # also free of acronyms, whose expansion adds tokens the passage
        # cannot match and pushes coverage back under the floor.
        generic = hit("generic-a", "doc-generic", "Unrelated judgment", current=True)
        generic.payload["text"] = (
            "The security amount shall be returned as a deposit to the party "
            "on the conclusion of the proceedings."
        )
        retrieval = self.TimingsWithoutDistinctiveTerms(
            [generic],
            distinctive_terms=["landlord"],
            term_document_counts={
                "security": 1129,
                "deposit": 152,
                "returned": 261,
                "landlord": 37,
            },
        )

        result = await FastLegalResearchService(retrieval).run(  # type: ignore[arg-type]
            query="landlord security deposit returned",
            role="citizen",
            case_id=None,
            history=[],
        )

        assert result["evidence_strength"] == "insufficient", (
            "a passage that does not contain the query's distinctive term was "
            "published; the mandatory-term gate is not being applied"
        )
        assert result["citations"] == []


class TestAQuestionThatNamesNoSubject:
    """A query of nothing but stopwords must not be answered.

    Vector search always returns its nearest neighbours, and every relevance
    test in this lane is vacuously satisfied when there are no terms to test:
    `_lexical_coverage` divided by an empty token set and returned 1.0, and
    the mandatory-term gate had nothing to require. Measured before this was
    fixed, "what is that?" came back at *moderate* confidence citing the Model
    Prison Manual -- an unrelated passage presented as an answer to a question
    the system could not have understood.
    """

    @pytest.mark.parametrize("query", ["what is that?", "how do i", "the", "?"])
    @pytest.mark.asyncio
    async def test_it_is_declined_rather_than_answered(self, query: str) -> None:
        unrelated = hit("x", "doc-x", "Model Prison Manual", current=True)
        unrelated.payload["text"] = (
            "Prisoners shall be allotted work according to capacity."
        )

        result = await FastLegalResearchService(FakeRetrieval([unrelated])).run(  # type: ignore[arg-type]
            query=query, role="citizen", case_id=None, history=[]
        )

        assert result["evidence_strength"] == "insufficient"
        assert result["confidence_score"] == 0.0
        assert result["citations"] == []
        assert (
            result["agent_trace"][0].details["abstention_reason"]
            == "no_searchable_terms"
        )

    def test_coverage_of_nothing_is_not_perfect_coverage(self) -> None:
        """The permissive default that made the above possible.

        Kept at 0.0 so the failure cannot return through a different caller.
        """
        from app.services.fast_research import _lexical_coverage

        assert _lexical_coverage(set(), {"text": "any passage at all"}) == 0.0

    @pytest.mark.asyncio
    async def test_a_real_question_is_unaffected(self) -> None:
        """The guard must not swallow questions that do name a subject."""
        passage = hit("a", "doc-a", "Code of Criminal Procedure", current=True)
        passage.payload["text"] = (
            "The officer in charge of a police station shall reduce the "
            "information relating to the commission of a cognizable offence "
            "to writing."
        )

        result = await FastLegalResearchService(FakeRetrieval([passage])).run(  # type: ignore[arg-type]
            query="must police reduce information to writing?",
            role="citizen",
            case_id=None,
            history=[],
        )

        assert result["citations"] != []


class TestTheHarnessCannotDriftFromTheLane:
    """One selection, used by the lane and by the evaluation harness.

    The harness has reimplemented this twice and drifted both times: once it
    applied only the coverage floor, crediting the mandatory-term requirement
    with nothing, and once it scored citation accuracy on the raw retrieved
    list -- a third of whose slots repeat a document the reader has already
    been shown. Both made the recorded numbers describe a system nobody runs.
    """

    def _hit(self, chunk_id: str, text: str, document: str) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(
            payload={
                "chunk_id": chunk_id,
                "text": text,
                "canonical_document_id": document,
                "title": document,
                "act_name": document,
            }
        )

    def test_the_coverage_floor_is_applied(self) -> None:
        from app.services.fast_research import _focus_tokens, publishable_hits

        question = "When must a woman police officer be involved in an arrest?"
        focus = _focus_tokens(question)
        on_topic = self._hit(
            "a", "A woman police officer shall make the arrest.", "doc-a"
        )
        off_topic = self._hit(
            "b", "The schedule of fees for licences is annexed.", "doc-b"
        )

        kept = publishable_hits(
            [on_topic, off_topic],
            query=question,
            focus_tokens=focus,
            distinctive_terms=set(),
        )

        assert [h.payload["chunk_id"] for h in kept] == ["a"]

    def test_the_mandatory_term_is_applied_too(self) -> None:
        """The half the first drifted harness silently dropped."""
        from app.services.fast_research import _focus_tokens, publishable_hits

        question = "What can be done about noise from a neighbouring factory?"
        focus = _focus_tokens(question)
        # High word overlap, but never mentions the required rare term.
        plausible = self._hit(
            "a",
            "What can be done about a neighbouring factory is a question for the board.",
            "doc-a",
        )

        kept = publishable_hits(
            [plausible], query=question, focus_tokens=focus, distinctive_terms={"noise"}
        )

        assert kept == [], "a passage lacking the required term is not an answer"

    def test_one_passage_per_document(self) -> None:
        from app.services.fast_research import _select_diverse_hits

        hits = [
            self._hit("a1", "text", "doc-a"),
            self._hit("a2", "text", "doc-a"),
            self._hit("b1", "text", "doc-b"),
        ]

        selected = _select_diverse_hits(hits, 5)

        assert [h.payload["chunk_id"] for h in selected] == ["a1", "b1"]
