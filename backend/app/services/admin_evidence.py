"""Stored evaluation runs, read from the evidence directory.

The answer harness writes `answers-*.json`, the retrieval harness `eval-*.json`
and `retrieval-eval*.json`, and the gates write the same files beside their
output. Rows in those files hold golden-set questions and generated answers, so
only metrics and run configuration leave this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings

_ANSWER_PATTERNS = ("answers-*.json", "answer-quality-baseline.json", "gates/*/answers*.json")
_RETRIEVAL_PATTERNS = (
    "eval-*.json",
    "retrieval-eval*.json",
    "quality-baseline.json",
    "gates/*/retrieval-eval*.json",
)

# Whether a larger number is better, for reading a comparison at a glance.
LOWER_IS_BETTER = frozenset(
    {
        "false_abstention_rate",
        "latency_p50_s",
        "reading_grade_mean",
        "seconds_per_query",
        "unsupported_claims_total",
    }
)
# Item counts describe a run. A difference in them is not an improvement.
_DESCRIPTIVE_METRICS = frozenset({"items", "ground_coverage_items", "currency_items"})


def evidence_root() -> Path:
    if settings.evaluation_evidence_root:
        return Path(settings.evaluation_evidence_root)
    # backend/app/services/this.py -> repository root.
    return Path(__file__).resolve().parents[3] / "docs" / "evidence"


@dataclass(frozen=True)
class EvaluationRun:
    id: str
    kind: str
    generated_at: str | None
    collection: str | None
    golden_set: str | None
    generation_model: str | None
    embedding_model: str | None
    prompt_versions: dict[str, str]
    metrics: dict[str, float]
    by_role: dict[str, dict[str, float]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "generated_at": self.generated_at,
            "collection": self.collection,
            "golden_set": self.golden_set,
            "generation_model": self.generation_model,
            "embedding_model": self.embedding_model,
            "prompt_versions": self.prompt_versions,
            "metrics": self.metrics,
            "by_role": self.by_role,
        }


def _numbers(values: Any) -> dict[str, float]:
    if not isinstance(values, dict):
        return {}
    return {
        str(key): float(value)
        for key, value in values.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def _citation_coverage(rows: Any) -> float | None:
    """Of the answers that did not abstain, the share that cite anything."""
    if not isinstance(rows, list):
        return None
    answered = [row for row in rows if isinstance(row, dict) and not row.get("abstained")]
    if not answered:
        return None

    def cites(row: dict[str, Any]) -> bool:
        citations = row.get("citations")
        return bool(citations)

    return round(sum(1 for row in answered if cites(row)) / len(answered), 3)


def _answer_run(run_id: str, data: dict[str, Any]) -> EvaluationRun | None:
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        return None
    overall = metrics.get("overall") if isinstance(metrics.get("overall"), dict) else metrics
    by_role = metrics.get("by_role") if isinstance(metrics.get("by_role"), dict) else data.get("by_role")
    numbers = _numbers(overall)
    if not numbers:
        return None
    coverage = _citation_coverage(data.get("rows"))
    if coverage is not None:
        numbers["citation_coverage"] = coverage
    config = data.get("measurement_config") or {}
    return EvaluationRun(
        id=run_id,
        kind="answers",
        generated_at=data.get("generated_at") or data.get("recorded_at"),
        collection=config.get("collection"),
        golden_set=data.get("golden_set"),
        generation_model=config.get("generation_model"),
        embedding_model=config.get("embedding_model"),
        prompt_versions=dict(config.get("prompt_versions") or {}),
        metrics=numbers,
        by_role={role: _numbers(values) for role, values in (by_role or {}).items()},
    )


def _retrieval_run(run_id: str, data: dict[str, Any]) -> EvaluationRun | None:
    configs = data.get("configs")
    if isinstance(configs, dict):
        best = configs.get("hybrid") or next(iter(configs.values()), None)
        summary = (best or {}).get("summary") if isinstance(best, dict) else None
        config = data.get("config") or {}
    else:
        summary = data.get("metrics")
        config = data.get("measurement_config") or {}
    if not isinstance(summary, dict):
        return None
    numbers = _numbers(summary)
    if not numbers:
        return None
    by_role = summary.get("by_role") or data.get("by_role") or {}
    return EvaluationRun(
        id=run_id,
        kind="retrieval",
        generated_at=data.get("generated_at") or data.get("recorded_at"),
        collection=data.get("collection"),
        golden_set=data.get("golden_set"),
        generation_model=config.get("generation_model"),
        embedding_model=config.get("embedding_model"),
        prompt_versions=dict(config.get("prompt_versions") or {}),
        metrics=numbers,
        by_role={role: _numbers(values) for role, values in by_role.items()},
    )


_cache: dict[Path, tuple[float, EvaluationRun | None]] = {}


def _load(path: Path, root: Path, kind: str) -> EvaluationRun | None:
    modified = path.stat().st_mtime
    cached = _cache.get(path)
    if cached is not None and cached[0] == modified:
        return cached[1]
    run_id = str(path.relative_to(root).with_suffix(""))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        run = None
    else:
        builder = _answer_run if kind == "answers" else _retrieval_run
        run = builder(run_id, data) if isinstance(data, dict) else None
    _cache[path] = (modified, run)
    return run


def list_evaluation_runs() -> list[EvaluationRun]:
    """Every readable run, newest first. Synchronous: call it on a worker thread."""
    root = evidence_root()
    if not root.is_dir():
        return []
    runs: list[EvaluationRun] = []
    seen: set[Path] = set()
    for kind, patterns in (("answers", _ANSWER_PATTERNS), ("retrieval", _RETRIEVAL_PATTERNS)):
        for pattern in patterns:
            for path in sorted(root.glob(pattern)):
                if path in seen or not path.is_file():
                    continue
                seen.add(path)
                run = _load(path, root, kind)
                if run is not None:
                    runs.append(run)
    runs.sort(key=lambda run: run.generated_at or "", reverse=True)
    return runs


def compare_runs(first: EvaluationRun, second: EvaluationRun) -> dict[str, Any]:
    """Two runs side by side, and everything that makes the numbers incomparable.

    The warnings matter as much as the deltas. A difference measured against a
    different golden set or corpus is not an effect of the prompt, and reading it
    as one is how a stale measurement ends up justifying a change.
    """
    rows = []
    for metric in sorted(set(first.metrics) | set(second.metrics)):
        a, b = first.metrics.get(metric), second.metrics.get(metric)
        delta = round(b - a, 4) if a is not None and b is not None else None
        better = None
        if delta and metric not in _DESCRIPTIVE_METRICS:
            improved = delta < 0 if metric in LOWER_IS_BETTER else delta > 0
            better = "b" if improved else "a"
        rows.append({"metric": metric, "a": a, "b": b, "delta": delta, "better": better})

    prompts = sorted(set(first.prompt_versions) | set(second.prompt_versions))
    prompt_rows = [
        {
            "name": name,
            "a": first.prompt_versions.get(name),
            "b": second.prompt_versions.get(name),
            "changed": first.prompt_versions.get(name) != second.prompt_versions.get(name),
        }
        for name in prompts
    ]

    warnings: list[str] = []
    if first.kind != second.kind:
        warnings.append("These runs measure different things, so few metrics line up.")
    if first.golden_set != second.golden_set:
        warnings.append(
            f"Different golden sets ({first.golden_set} and {second.golden_set}): "
            "the numbers are not directly comparable."
        )
    if first.collection != second.collection:
        warnings.append(
            f"Different corpora ({first.collection} and {second.collection}): "
            "a change may come from volume rather than the system."
        )
    if first.generation_model != second.generation_model:
        warnings.append(
            f"Different models ({first.generation_model} and {second.generation_model})."
        )
    return {
        "a": first.summary(),
        "b": second.summary(),
        "metrics": rows,
        "prompts": prompt_rows,
        "warnings": warnings,
    }
