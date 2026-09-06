"""Every route that names a case must prove the caller owns it.

The red-team suite proves that retrieval does not leak across matters. It
cannot prove anything about an endpoint written after it, and case-scoped
endpoints keep being added -- FIR drafting, defence analysis, storage,
document analysis, and now the investigation timeline.

The failure guarded against is somebody adding `/cases/{case_id}/something`
whose dependency authenticates the caller but never checks that the caller
owns the matter, which looks correct, passes review, and lets any signed-in
user read any case by guessing a UUID.

Half of that is already defended without this file, which is worth knowing
before trusting it: require_permission infers case_id_param="case_id" for
any permission named like "police:*:own", so simply forgetting the keyword
argument on such a permission is harmless. Confirmed by mutation --
removing it changes nothing.

What the inference does not cover, and this does:

* a case-scoped route guarded by a permission outside that naming pattern,
  such as chat:use, where nothing infers a binding;
* a route that passes infer_case_id=False;
* a checker bound to a parameter the path does not have, which disables the
  check while looking deliberate.

All three are mutation-verified. This walks the routing table rather than
naming endpoints, so a new route in any of those shapes fails the moment it
is registered, without anyone remembering to come back here.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from app.core.rbac import PermissionChecker

CASE_PARAM = re.compile(r"\{case_id\}")


def _all_api_routes(container) -> list[APIRoute]:
    """Flatten the routing tree.

    This FastAPI version keeps an included router as a single nested object
    rather than splicing its routes into the parent, so iterating app.routes
    yields three endpoints out of well over a hundred. A non-recursive walk
    here would find nothing case-scoped and every assertion below would pass
    over an empty list -- which is what the vacuity guard exists to catch.
    """
    found: list[APIRoute] = []
    for route in getattr(container, "routes", []):
        if isinstance(route, APIRoute):
            found.append(route)
            continue
        # An included router appears as an opaque wrapper that exposes no
        # `routes` of its own; the real APIRouter hangs off original_router.
        nested = getattr(route, "original_router", None) or route
        if nested is not route or hasattr(nested, "routes"):
            found.extend(_all_api_routes(nested))
    return found


def _case_scoped_routes() -> list[APIRoute]:
    from main import app

    return [r for r in _all_api_routes(app) if CASE_PARAM.search(r.path)]


def _ownership_checkers(route: APIRoute) -> list[PermissionChecker]:
    """Every PermissionChecker in the route's dependency tree that binds a case.

    Walks the whole tree rather than the top level: the checker is usually a
    parameter default, but nothing stops it being nested in a shared
    dependency, and a nested one protects the route just as well.
    """
    found: list[PermissionChecker] = []
    pending = [route.dependant]
    while pending:
        dependant = pending.pop()
        call = getattr(dependant, "call", None)
        if isinstance(call, PermissionChecker) and call.case_id_param is not None:
            found.append(call)
        pending.extend(dependant.dependencies)
    return found


def test_there_are_case_scoped_routes_to_check() -> None:
    """A vacuity guard.

    If the path pattern ever stops matching -- a prefix rename, a router
    that stops being registered -- every assertion below passes over an
    empty list and this file reports success while checking nothing.
    """
    assert len(_case_scoped_routes()) >= 8


@pytest.mark.parametrize(
    "route", _case_scoped_routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}"
)
def test_every_case_scoped_route_checks_ownership(route: APIRoute) -> None:
    checkers = _ownership_checkers(route)

    assert checkers, (
        f"{sorted(route.methods)[0]} {route.path} names a case but no "
        "PermissionChecker binds it. Authentication alone lets any signed-in "
        "user read any matter by guessing a UUID. Pass "
        'case_id_param="case_id" to require_permission.'
    )


@pytest.mark.parametrize(
    "route", _case_scoped_routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}"
)
def test_the_bound_parameter_matches_the_path(route: APIRoute) -> None:
    """Binding the wrong parameter name silently disables the check.

    PermissionChecker reads the named parameter out of the request. If the
    path says {case_id} and the checker was given "id", the lookup finds
    nothing and raises a 400 -- or worse, on a route that also carries an
    "id" for something else, it validates ownership of the wrong object.
    """
    for checker in _ownership_checkers(route):
        assert "{" + str(checker.case_id_param) + "}" in route.path, (
            f"{route.path} binds {checker.case_id_param!r}, which is not a "
            "path parameter of this route"
        )
