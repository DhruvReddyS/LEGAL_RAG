"""Three methods take a target. All three must refuse an unscoped private one.

`_assert_case_scoped` was written because `RetrievalFilters.case_ids` is
applied only when non-empty: for the public corpus that is right, and for a
private collection an empty list does not mean "this case", it means "every
case in the collection". Its own docstring says the isolation "is currently
held by three call sites all remembering" and that convention is the wrong
mechanism for the boundary between one investigation's evidence and another's.

It was called on one path. `HybridRetrievalService` has three public methods
that take a `RetrievalTarget`, apply its filters and query the named
collection:

    search_across_collections_with_timings   guarded
    fetch_followed_provisions                not guarded -- scrolls documents
    distinctive_query_terms                  not guarded -- counts terms

Neither gap was reachable: both unguarded methods are called only with the
global corpus. That is the condition the guard exists to stop depending on,
and the two new call sites the docstring anticipated are exactly the ones that
arrived without it.

These tests exercise the refusal, so the guard cannot be removed from any of
the three without failing here. They construct no client and reach no
collection: the refusal happens before any I/O, which is the property under
test.
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
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalTarget,
)


@pytest.fixture
def service() -> HybridRetrievalService:
    """A service with no client, no embedder and no thread pools.

    Deliberately skips __init__. If a refusal ever stops happening before the
    I/O, these tests fail with AttributeError rather than passing quietly,
    which is the behaviour we want from a guard test.
    """
    return HybridRetrievalService.__new__(HybridRetrievalService)


def _unscoped(collection: str) -> RetrievalTarget:
    # corpus_tiers=[] as well, so `to_qdrant()` returns None and there is no
    # filter of any kind: the worst case, and the one a caller producing a
    # case target from an empty id would actually create.
    return RetrievalTarget(collection, RetrievalFilters(corpus_tiers=[]))


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", sorted(CASE_SCOPED_COLLECTIONS))
async def test_following_citations_refuses_an_unscoped_private_target(
    service, collection
) -> None:
    with pytest.raises(ValueError) as error:
        await service.fetch_followed_provisions([], target=_unscoped(collection), query="theft")
    assert "every matter" in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", sorted(CASE_SCOPED_COLLECTIONS))
async def test_counting_distinctive_terms_refuses_an_unscoped_private_target(
    service, collection
) -> None:
    """A count is weaker than a document and still discloses.

    How many chunks across every matter contain a term is not this matter's
    business, and an unscoped count would also make "rare" mean rare across
    the whole collection rather than within the case -- which is the number
    the abstention gate downstream reads.
    """
    with pytest.raises(ValueError) as error:
        await service.distinctive_query_terms({"theft"}, target=_unscoped(collection))
    assert "every matter" in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", sorted(CASE_SCOPED_COLLECTIONS))
async def test_a_scoped_private_target_is_not_refused(service, collection) -> None:
    """The guard must not be a blanket ban on private collections.

    It fails on the attribute access that follows, not on the guard, which is
    how we know it got past it.
    """
    scoped = RetrievalTarget(collection, RetrievalFilters(corpus_tiers=[], case_ids=["case-1"]))
    with pytest.raises(AttributeError):
        await service.distinctive_query_terms({"theft"}, target=scoped)


@pytest.mark.asyncio
async def test_the_public_corpus_needs_no_case_and_is_never_refused(service) -> None:
    """No case filter on the public corpus means the whole corpus, correctly."""
    public = RetrievalTarget(GLOBAL_LEGAL_CORPUS, RetrievalFilters())
    with pytest.raises(AttributeError):
        await service.distinctive_query_terms({"theft"}, target=public)


def test_the_set_of_guarded_methods_is_the_set_that_takes_a_target() -> None:
    """A fourth method taking a target must be guarded too.

    This is the test that generalises: it reads the source rather than the
    behaviour, so a new public method accepting a RetrievalTarget without the
    guard fails here instead of shipping.
    """
    import inspect
    import re

    from app.services import retrieval

    source = inspect.getsource(retrieval.HybridRetrievalService)
    # Each `async def name(...)` whose signature mentions a RetrievalTarget.
    bodies = re.split(r"\n    (?=async def |def )", source)
    takes_target = [
        body
        for body in bodies
        if re.search(r"target[s]?\s*:\s*(?:list\[)?RetrievalTarget", body)
    ]
    assert len(takes_target) >= 3, "expected at least the three known methods"
    for body in takes_target:
        name = re.match(r"(?:async )?def (\w+)", body.strip())
        assert name is not None
        if name.group(1).startswith("_"):
            # `_query_target` is internal and reached only through the guarded
            # public path, which has already asserted scope.
            continue
        assert "_assert_case_scoped" in body, (
            f"{name.group(1)} takes a RetrievalTarget and never asserts case scope; "
            "an empty case_ids on a private collection means every case"
        )
