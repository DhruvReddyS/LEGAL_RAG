"""One matter's evidence must never surface in another's research.

`RetrievalFilters.case_ids` is applied only when non-empty. For the public
corpus that is right -- no case filter means the whole corpus. For a private
collection it is a disclosure: an empty list does not mean "this case", it
means "every case in the collection".

Every call site sets it correctly today. That is exactly why this test exists:
the boundary between one investigation's evidence and another's is currently
held by three call sites all remembering, and the police and advocate modules
are about to add more.
"""

from __future__ import annotations

import pytest

from app.ingestion.init_qdrant import (
    ADVOCATE_CASE_DATA,
    GLOBAL_LEGAL_CORPUS,
    POLICE_CASE_DATA,
)
from app.services.retrieval import (
    CASE_SCOPED_COLLECTIONS,
    RetrievalFilters,
    RetrievalTarget,
    _assert_case_scoped,
)


class TestTheGuard:
    @pytest.mark.parametrize("collection", [POLICE_CASE_DATA, ADVOCATE_CASE_DATA])
    def test_a_private_collection_without_a_case_is_refused(self, collection) -> None:
        target = RetrievalTarget(collection, RetrievalFilters(corpus_tiers=[]))

        with pytest.raises(ValueError) as error:
            _assert_case_scoped([target])

        assert "every matter" in str(error.value)

    @pytest.mark.parametrize("collection", [POLICE_CASE_DATA, ADVOCATE_CASE_DATA])
    def test_a_scoped_private_query_is_allowed(self, collection) -> None:
        target = RetrievalTarget(
            collection, RetrievalFilters(corpus_tiers=[], case_ids=["case-a"])
        )

        _assert_case_scoped([target])

    def test_the_public_corpus_needs_no_case(self) -> None:
        """An unscoped public query is the normal citizen path."""
        _assert_case_scoped([RetrievalTarget(GLOBAL_LEGAL_CORPUS, RetrievalFilters())])

    def test_a_mixed_query_is_judged_per_target(self) -> None:
        """Deep research queries the public corpus and one case together."""
        with pytest.raises(ValueError):
            _assert_case_scoped(
                [
                    RetrievalTarget(GLOBAL_LEGAL_CORPUS, RetrievalFilters()),
                    RetrievalTarget(POLICE_CASE_DATA, RetrievalFilters(corpus_tiers=[])),
                ]
            )

    def test_both_private_collections_are_covered(self) -> None:
        """A third case corpus added later must be added here too."""
        assert CASE_SCOPED_COLLECTIONS == {POLICE_CASE_DATA, ADVOCATE_CASE_DATA}


class TestTheGuardIsWiredIn:
    @pytest.mark.asyncio
    async def test_the_search_entry_point_enforces_it(self) -> None:
        """The guard is worthless if it is only called by its own test."""
        from app.services.retrieval import HybridRetrievalService

        service = HybridRetrievalService()
        try:
            with pytest.raises(ValueError) as error:
                await service.search_across_collections_with_timings(
                    "what does the evidence show",
                    targets=[
                        RetrievalTarget(
                            POLICE_CASE_DATA, RetrievalFilters(corpus_tiers=[])
                        )
                    ],
                )
            assert "private case evidence" in str(error.value)
        finally:
            await service.close()


class TestEveryProductionCallSiteScopesItsQuery:
    def test_no_call_site_builds_an_unscoped_private_target(self) -> None:
        """Reads the source rather than trusting the three we know about.

        A new module adding a private target without `case_ids` would pass
        every other test in the suite and fail only in production, against
        real evidence.
        """
        import ast
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        private_names = {"POLICE_CASE_DATA", "ADVOCATE_CASE_DATA"}
        offenders: list[str] = []

        for path in sorted((backend / "app").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "id", None) != "RetrievalTarget":
                    continue
                arguments = list(node.args) + [kw.value for kw in node.keywords]
                names = {
                    child.id
                    for argument in arguments
                    for child in ast.walk(argument)
                    if isinstance(child, ast.Name)
                }
                if not (names & private_names):
                    continue
                source = ast.dump(node)
                if "case_ids" not in source:
                    offenders.append(f"{path.relative_to(backend)}:{node.lineno}")

        assert not offenders, (
            "these build a private-corpus retrieval target without case_ids: "
            f"{offenders}"
        )
