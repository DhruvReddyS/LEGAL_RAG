"""A citizen's question is often the most sensitive thing they will type.

"my husband is beating me" must not reach a log file, an access log, or a URL.
The application's own logging already records only request metadata, and every
query travels in a request body. Both are easy to undo without noticing -- one
added `?q=` parameter, or one `logger.info` that includes the payload -- so
they are asserted rather than assumed.
"""

from __future__ import annotations

import inspect
import re

from fastapi.routing import APIRoute

from main import app

# Path and method are logged. A path parameter is part of the path, so an id is
# fine and free text is not.
_FREE_TEXT_NAMES = re.compile(
    r"^(q|query|question|text|message|prompt|search|content|body|note|comment)$",
    re.IGNORECASE,
)


def test_no_route_takes_a_free_text_query_parameter() -> None:
    """URLs end up in access logs, browser history and referrer headers."""
    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        signature = inspect.signature(route.endpoint)
        for name, parameter in signature.parameters.items():
            if not _FREE_TEXT_NAMES.match(name):
                continue
            annotation = str(parameter.annotation)
            # A body model or dependency is fine; a declared Query is not.
            if "Query(" in annotation or "Query]" in annotation:
                offenders.append((route.path, name))
    assert not offenders, (
        "these routes accept free text in the URL, which is logged and stored "
        f"in browser history: {offenders}"
    )


def test_the_access_log_records_only_request_metadata() -> None:
    """The one log line emitted for every request.

    Adding the body here would put every citizen's question into the log with
    no other change visible in review.
    """
    import main

    source = inspect.getsource(main)
    start = source.index('"event": "http_request"')
    block = source[start : source.index("separators", start)]
    fields = set(re.findall(r'"(\w+)":', block))

    assert fields == {
        "event",
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
    }, f"the access log line changed shape: {sorted(fields)}"


def test_dependency_outages_do_not_log_the_exception_message() -> None:
    """An exception from the vector store or model host can carry a host, a
    port, and sometimes the payload that provoked it."""
    import main

    source = inspect.getsource(main)
    for event in ("vector_store_unavailable", "model_host_unavailable"):
        start = source.index(f'"event": "{event}"')
        block = source[start : source.index("separators", start)]
        assert '"error_type"' in block, event
        assert "str(exc)" not in block and '"error": ' not in block, (
            f"{event} logs the exception message, which can carry connection "
            "details and request content"
        )
