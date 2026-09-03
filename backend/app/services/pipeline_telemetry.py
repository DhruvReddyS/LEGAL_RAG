from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from time import perf_counter_ns
from typing import Any, Callable, Iterator


logger = logging.getLogger("legal_rag.pipeline")
_metric_sink: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "pipeline_metric_sink",
    default=None,
)


def elapsed_ms(started_ns: int) -> float:
    """Return an unrounded monotonic elapsed duration in milliseconds."""

    return (perf_counter_ns() - started_ns) / 1_000_000


def text_size(text: str) -> dict[str, int]:
    """Describe text without claiming an estimated tokenizer count is exact."""

    return {
        "characters": len(text),
        "utf8_bytes": len(text.encode("utf-8")),
        "whitespace_tokens": len(text.split()),
    }


def append_stage_metric(
    state: dict[str, Any],
    *,
    stage: str,
    started_ns: int,
    retry_index: int = 0,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    llm_calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    metrics = list(state.get("stage_metrics", []))
    metric = {
        "sequence": len(metrics) + 1,
        "run_id": state.get("run_id"),
        "run_started_at": state.get("started_at"),
        "stage": stage,
        "retry_index": retry_index,
        "duration_ms": elapsed_ms(started_ns),
        "inputs": inputs or {},
        "outputs": outputs or {},
        "llm_calls": llm_calls or [],
    }
    metrics.append(metric)
    # The structured log contains sizes and timings only, never prompt/evidence text.
    logger.info("pipeline_stage %s", json.dumps(metric, ensure_ascii=True, sort_keys=True))
    sink = _metric_sink.get()
    if sink is not None:
        sink(metric)
    return metrics


@contextmanager
def capture_stage_metrics(
    sink: Callable[[dict[str, Any]], None],
) -> Iterator[None]:
    token: Token[Callable[[dict[str, Any]], None] | None] = _metric_sink.set(sink)
    try:
        yield
    finally:
        _metric_sink.reset(token)


async def generate_with_metrics(
    llm: Any,
    prompt: str,
    *,
    num_predict: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    instrumented = getattr(llm, "generate_with_metrics", None)
    if callable(instrumented):
        if num_predict is None:
            text, metric = await instrumented(prompt)
        else:
            text, metric = await instrumented(prompt, num_predict=num_predict)
        return text, [metric]

    started_ns = perf_counter_ns()
    text = await llm.generate(prompt)
    return text, [
        {
            "operation": "generate",
            "wall_ms": elapsed_ms(started_ns),
            "prompt": text_size(prompt),
            "prompt_eval_count": None,
            "context_window": None,
            "num_predict_limit": num_predict,
            "metrics_source": "client_fallback",
        }
    ]


async def structured_with_metrics(
    llm: Any,
    prompt: str,
    schema: type[Any],
    *,
    attempts: int = 3,
) -> tuple[Any, list[dict[str, Any]]]:
    instrumented = getattr(llm, "structured_with_metrics", None)
    if callable(instrumented):
        return await instrumented(prompt, schema, attempts=attempts)

    started_ns = perf_counter_ns()
    value = await llm.structured(prompt, schema, attempts=attempts)
    return value, [
        {
            "operation": "structured",
            "attempt": 1,
            "wall_ms": elapsed_ms(started_ns),
            "prompt": text_size(prompt),
            "prompt_eval_count": None,
            "context_window": None,
            "metrics_source": "client_fallback",
        }
    ]
