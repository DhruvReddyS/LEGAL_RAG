"""Can any caller reach evidence belonging to a matter they do not own?

The disclosure this suite generalises was found by running the application,
not by reading it: an administrator's general search swept every case id in
the database into the private-collection targets. Two static audits had passed
over the same code, and the whole correctness suite was green.

So the assertions here are made at two levels, because they fail differently:

  * what came back  -- a foreign marker in the results is a leak that reached
    the caller.
  * what was asked  -- a private collection appearing in the query targets at
    all is a leak that has not reached the caller yet. The admin bug was
    visible at this level first.

Every test runs against real Qdrant with real embeddings. The fixture asserts
both cases hold evidence before any test body runs, so nothing here can pass
because the index was empty.
"""

from __future__ import annotations

import pytest

from app.ingestion.init_qdrant import (
    ADVOCATE_CASE_DATA,
    GLOBAL_LEGAL_CORPUS,
    POLICE_CASE_DATA,
)
from tests.redteam.conftest import SHARED_QUERY

pytestmark = [pytest.mark.asyncio, pytest.mark.redteam, pytest.mark.object_storage]

SEARCH = "/retrieval/scoped-search"
BODY = {"query": SHARED_QUERY, "candidate_limit": 20, "result_limit": 10}


def _returned_text(payload: dict) -> str:
    return " ".join(
        str((hit.get("payload") or {}).get("text") or "") for hit in payload["results"]
    )


class TestGeneralSearchNeverTouchesAnotherMatter:
    """A general search is not an authorised matter for anyone."""

    @pytest.mark.parametrize(
        "role", ["citizen", "police", "police_two", "advocate", "advocate_two", "admin"]
    )
    async def test_no_foreign_evidence_is_returned(self, world, role) -> None:
        actor = world.actor(role)
        response = await world.client.post(
            f"{SEARCH}?mode=general", json=BODY, headers=actor.headers
        )
        assert response.status_code == 200, response.text

        text = _returned_text(response.json())
        for marker in world.foreign_markers(role):
            assert marker not in text, (
                f"{role} general search returned evidence marked {marker}, which "
                "belongs to another user's matter"
            )

    @pytest.mark.parametrize("role", ["citizen", "admin"])
    async def test_a_caller_who_owns_no_case_queries_no_private_collection(
        self, world, role
    ) -> None:
        """The level the administrator disclosure was visible at.

        A citizen owns no case and an administrator owns none of these; neither
        should cause a private collection to be queried at all.
        """
        actor = world.actor(role)
        response = await world.client.post(
            f"{SEARCH}?mode=general", json=BODY, headers=actor.headers
        )
        assert response.status_code == 200, response.text

        assert world.retrieval.private_collections_queried() == set(), (
            f"{role} general search queried a private case corpus"
        )
        collections = [t.collection_name for t in world.retrieval.targets_of_last_call()]
        assert collections == [GLOBAL_LEGAL_CORPUS]

    @pytest.mark.parametrize(
        "role", ["citizen", "police", "police_two", "advocate", "advocate_two", "admin"]
    )
    async def test_no_foreign_case_id_is_enumerated(self, world, role) -> None:
        """The administrator bug, stated as the property rather than the case.

        `authorized_case_ids` is the server telling the caller which matters it
        considered theirs. A foreign id here is a disclosure even before any
        evidence is returned.
        """
        actor = world.actor(role)
        response = await world.client.post(
            f"{SEARCH}?mode=general", json=BODY, headers=actor.headers
        )
        assert response.status_code == 200, response.text

        returned = set(response.json()["authorized_case_ids"])
        foreign = {
            str(tenant.case_id)
            for name, tenant in world.tenants.items()
            if name != role and tenant.case_id
        }
        assert not (returned & foreign), (
            f"{role} general search enumerated another user's cases: {returned & foreign}"
        )
        assert world.retrieval.case_ids_queried() & foreign == set()


class TestANamedMatterIsReachableOnlyByItsOwner:
    @pytest.mark.parametrize("role", ["police", "police_two", "advocate", "advocate_two"])
    async def test_an_owner_reaches_their_own_evidence(self, world, role) -> None:
        """The permissive direction. Without it, a suite that returned nothing
        to anyone would score perfectly."""
        actor = world.actor(role)
        response = await world.client.post(
            f"{SEARCH}?mode=case_specific&case_id={actor.case_id}",
            json=BODY,
            headers=actor.headers,
        )
        assert response.status_code == 200, response.text

        text = _returned_text(response.json())
        assert actor.marker in text, f"{role} could not retrieve their own evidence"
        assert response.json()["authorized_case_ids"] == [str(actor.case_id)]

        # The named-matter path needs the negative direction too. Asserting only
        # that the owner sees their own evidence passes unchanged if the Qdrant
        # case filter is dropped entirely -- the owner still sees theirs, along
        # with everyone else's.
        for marker in world.foreign_markers(role):
            assert marker not in text, (
                f"{role}'s own matter also returned {marker}, which belongs to "
                "another user's matter"
            )
        seen_cases = {
            str((hit.get("payload") or {}).get("case_id"))
            for hit in response.json()["results"]
            if (hit.get("payload") or {}).get("case_id")
        }
        assert seen_cases <= {str(actor.case_id)}, (
            f"{role}'s own matter returned foreign case ids: {seen_cases}"
        )

    @pytest.mark.parametrize(
        ("role", "target"),
        [
            ("citizen", "police"),
            ("citizen", "advocate"),
            ("police", "advocate"),
            ("advocate", "police"),
            # Same role, same collection -- the cell where only the case filter
            # stands between two investigations.
            ("police", "police_two"),
            ("police_two", "police"),
            ("advocate", "advocate_two"),
            ("advocate_two", "advocate"),
        ],
    )
    async def test_a_stranger_is_refused_without_disclosure(
        self, world, role, target
    ) -> None:
        """404, not 403: a 403 would confirm the matter exists."""
        actor = world.actor(role)
        victim = world.actor(target)
        response = await world.client.post(
            f"{SEARCH}?mode=case_specific&case_id={victim.case_id}",
            json=BODY,
            headers=actor.headers,
        )

        assert response.status_code == 404, (
            f"{role} reached {target}'s matter: {response.status_code} {response.text[:200]}"
        )
        assert world.retrieval.private_collections_queried() == set(), (
            f"{role} caused a private corpus query while being refused"
        )

    @pytest.mark.parametrize(
        ("role", "sibling"),
        [("police", "police_two"), ("advocate", "advocate_two")],
    )
    async def test_an_owner_does_not_see_a_sibling_matter_in_the_same_corpus(
        self, world, role, sibling
    ) -> None:
        """The strongest test of the case filter itself.

        Two police investigations share a collection, a role and a near
        identical statement. Nothing separates them but `case_id`, so this is
        the only cell where deleting that filter is guaranteed to show. With
        one case per collection the collection boundary was quietly doing the
        work and the filter could be removed with every test still green.
        """
        actor = world.actor(role)
        other = world.actor(sibling)
        response = await world.client.post(
            f"{SEARCH}?mode=case_specific&case_id={actor.case_id}",
            json=BODY,
            headers=actor.headers,
        )
        assert response.status_code == 200, response.text

        text = _returned_text(response.json())
        assert actor.marker in text
        assert other.marker not in text, (
            f"{role} saw {sibling}'s evidence from the same collection"
        )


class TestTheModeArgumentsCannotBeAbused:
    async def test_a_named_matter_requires_a_case(self, world) -> None:
        response = await world.client.post(
            f"{SEARCH}?mode=case_specific",
            json=BODY,
            headers=world.actor("police").headers,
        )
        assert response.status_code == 422

    async def test_a_general_search_rejects_a_case_id(self, world) -> None:
        """Otherwise a case id on a general search is silently ignored, and
        which of the two rules applied becomes ambiguous."""
        police = world.actor("police")
        response = await world.client.post(
            f"{SEARCH}?mode=general&case_id={police.case_id}",
            json=BODY,
            headers=police.headers,
        )
        assert response.status_code == 422

    async def test_an_unauthenticated_caller_reaches_nothing(self, world) -> None:
        response = await world.client.post(f"{SEARCH}?mode=general", json=BODY)
        assert response.status_code == 401
        assert world.retrieval.private_collections_queried() == set()


class TestRegressionsFromEarlierDisclosures:
    """The two already fixed, kept as tests rather than as commit messages."""

    async def test_an_admin_general_search_does_not_sweep_every_matter(
        self, world
    ) -> None:
        """`resolve_authorized_case_scope` skipped the owner filter for
        administrators in both modes. In general mode that enumerated every
        case in the database and built private targets for all of them."""
        response = await world.client.post(
            f"{SEARCH}?mode=general", json=BODY, headers=world.actor("admin").headers
        )
        assert response.status_code == 200, response.text

        assert response.json()["authorized_case_ids"] == []
        assert world.retrieval.private_collections_queried() == set()
        text = _returned_text(response.json())
        for marker in ("POLICEALPHA77", "ADVOCATEBRAVO99"):
            assert marker not in text

    async def test_an_admin_may_still_open_a_named_matter(self, world) -> None:
        """The narrowing must not have broken support and audit. Naming the
        matter is what makes it authorised, and what leaves a record."""
        police = world.actor("police")
        response = await world.client.post(
            f"{SEARCH}?mode=case_specific&case_id={police.case_id}",
            json=BODY,
            headers=world.actor("admin").headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["authorized_case_ids"] == [str(police.case_id)]

    async def test_an_unscoped_private_query_is_refused_at_the_service(
        self, world
    ) -> None:
        """`case_ids` is applied only when non-empty, so an empty list against
        a private collection means every matter in it. The shared search entry
        point refuses rather than returning them."""
        from app.services.retrieval import RetrievalFilters, RetrievalTarget

        with pytest.raises(ValueError) as error:
            await world.retrieval.inner.search_across_collections_with_timings(
                SHARED_QUERY,
                targets=[
                    RetrievalTarget(POLICE_CASE_DATA, RetrievalFilters(corpus_tiers=[]))
                ],
            )
        assert "private case evidence" in str(error.value)

    @pytest.mark.parametrize("collection", [POLICE_CASE_DATA, ADVOCATE_CASE_DATA])
    async def test_the_refusal_covers_both_private_corpora(
        self, world, collection
    ) -> None:
        from app.services.retrieval import RetrievalFilters, RetrievalTarget

        with pytest.raises(ValueError):
            await world.retrieval.inner.search_across_collections_with_timings(
                SHARED_QUERY,
                targets=[RetrievalTarget(collection, RetrievalFilters(corpus_tiers=[]))],
            )
