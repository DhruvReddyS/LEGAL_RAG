from __future__ import annotations

import asyncio
import math
from pathlib import Path

from app.core.config import settings
from app.services.retrieval import HybridRetrievalService, RetrievalFilters, RetrievalHit


SMOKE_QUERIES = (
    "mandatory FIR registration",
    "arrest safeguards",
    "anticipatory bail",
    "default bail",
    "quashing FIR",
    "electronic evidence",
    "POCSO",
    "NDPS",
    "IPC to BNS mapping",
    "CrPC to BNSS mapping",
    "Evidence Act to BSA mapping",
    "privacy constitutional criminal rights",
)

# Every synonym group must occur somewhere in the retrieved evidence set.
CONCEPT_EXPECTATIONS: dict[str, tuple[tuple[str, ...], ...]] = {
    "mandatory FIR registration": (
        ("fir", "first information report"),
        ("mandatory", "register", "registration"),
    ),
    "arrest safeguards": (("arrest", "arrested"), ("safeguard", "right", "procedure")),
    "anticipatory bail": (("anticipatory bail", "section 438", "sec. 438"),),
    "default bail": (("default bail", "statutory bail", "section 167", "sec. 167"),),
    "quashing FIR": (
        ("quash", "quashing"),
        ("fir", "first information report"),
    ),
    "electronic evidence": (("electronic evidence", "electronic record", "digital evidence"),),
    "POCSO": (("pocso", "protection of children from sexual offences"),),
    "NDPS": (("ndps", "narcotic drugs and psychotropic substances"),),
    "IPC to BNS mapping": (
        ("ipc", "indian penal code"),
        ("bns", "bharatiya nyaya sanhita"),
    ),
    "CrPC to BNSS mapping": (
        ("crpc", "code of criminal procedure"),
        ("bnss", "bharatiya nagarik suraksha sanhita"),
    ),
    "Evidence Act to BSA mapping": (
        ("evidence act", "indian evidence act"),
        ("bsa", "bharatiya sakshya adhiniyam"),
    ),
    "privacy constitutional criminal rights": (
        ("privacy",),
        ("constitution", "constitutional", "fundamental right", "article 21"),
    ),
}

REQUIRED_RESULT_PAYLOAD_FIELDS = frozenset(
    {
        "title",
        "source_type",
        "court",
        "act_name",
        "section",
        "page_start",
        "page_end",
        "corpus_tier",
        "verified_official",
        "text",
    }
)


class SmokeValidationError(RuntimeError):
    pass


def _cell(value: object) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def validate_smoke_hits(query: str, hits: list[RetrievalHit]) -> list[str]:
    issues: list[str] = []
    if not hits:
        return ["no results returned"]
    evidence_parts: list[str] = []
    for rank, hit in enumerate(hits, 1):
        payload = hit.payload
        missing = sorted(REQUIRED_RESULT_PAYLOAD_FIELDS - payload.keys())
        if missing:
            issues.append(f"result {rank} missing payload fields: {', '.join(missing)}")
        if payload.get("corpus_tier") != "gold":
            issues.append(f"result {rank} is not Gold corpus")
        if payload.get("verified_official") is not True:
            issues.append(f"result {rank} is not verified official")
        # Official guidance, commission reports, and constitutional materials can
        # be valid legal evidence without a court or Act locator. Title + exact
        # page range is the universal citation contract; court/Act/section are
        # richer locators when that metadata exists.
        if not str(payload.get("title") or "").strip():
            issues.append(f"result {rank} has no citation title")
        page_start, page_end = payload.get("page_start"), payload.get("page_end")
        if not isinstance(page_start, int) or not isinstance(page_end, int) or not (
            1 <= page_start <= page_end
        ):
            issues.append(f"result {rank} has invalid page citation")
        modality_scores = {
            "dense": hit.dense_score,
            "sparse": hit.sparse_score,
        }
        if not any(
            isinstance(score, (int, float)) and math.isfinite(score)
            for score in modality_scores.values()
        ):
            issues.append(f"result {rank} has no valid dense or sparse score")
        for score_name, score in modality_scores.items():
            # RRF takes the union of both result sets. A point found by only one
            # modality legitimately has no score from the other modality.
            if score is not None and (
                not isinstance(score, (int, float)) or not math.isfinite(score)
            ):
                issues.append(f"result {rank} has invalid {score_name} score")
        for score_name, score in {
            "fused": hit.fused_score,
            "reranker": hit.reranker_score,
        }.items():
            if not isinstance(score, (int, float)) or not math.isfinite(score):
                issues.append(f"result {rank} has invalid {score_name} score")
        evidence_parts.extend(
            str(payload.get(field) or "")
            for field in ("title", "source_type", "court", "act_name", "section", "text")
        )

    evidence = " ".join(evidence_parts).casefold()
    for synonyms in CONCEPT_EXPECTATIONS[query]:
        if not any(synonym.casefold() in evidence for synonym in synonyms):
            issues.append(f"expected concept absent: {' / '.join(synonyms)}")
    return issues


async def run_smoke_tests(*, corpus_root: Path | None = None) -> Path:
    root = corpus_root or Path(settings.legal_kb_root)
    report_path = root / "logs/retrieval_smoke_tests.md"
    lines = [
        "# Gold Corpus Retrieval Smoke Tests",
        "",
        "Pipeline: BGE-M3 dense + learned sparse → Qdrant RRF → BGE reranker.",
        "All searches are restricted to `corpus_tier = gold`.",
        "",
    ]
    validation_failures: list[str] = []
    service = HybridRetrievalService()
    try:
        for query in SMOKE_QUERIES:
            hits = await service.search(
                query,
                filters=RetrievalFilters(corpus_tiers=["gold"]),
                candidate_limit=20,
                result_limit=5,
            )
            query_issues = validate_smoke_hits(query, hits)
            validation_failures.extend(f"{query}: {issue}" for issue in query_issues)
            lines.extend(
                [
                    f"## {query}",
                    "",
                    f"Validation: **{'FAIL' if query_issues else 'PASS'}**",
                    "",
                    "| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |",
                    "|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|",
                ]
            )
            for rank, hit in enumerate(hits, start=1):
                payload = hit.payload
                court_or_act = payload.get("court") or payload.get("act_name")
                page = (
                    payload.get("page_start")
                    if payload.get("page_start") == payload.get("page_end")
                    else f"{payload.get('page_start')}–{payload.get('page_end')}"
                )
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(rank),
                            _cell(payload.get("title")),
                            _cell(payload.get("source_type")),
                            _cell(court_or_act),
                            _cell(payload.get("section")),
                            _cell(page),
                            _cell(round(hit.dense_score, 6) if hit.dense_score is not None else None),
                            _cell(round(hit.sparse_score, 6) if hit.sparse_score is not None else None),
                            _cell(round(hit.fused_score, 6)),
                            _cell(round(hit.reranker_score, 6)),
                            _cell(payload.get("corpus_tier")),
                            _cell(payload.get("verified_official")),
                        ]
                    )
                    + " |"
                )
            if not hits:
                lines.append("| — | No results | — | — | — | — | — | — | — | — | — | — |")
            if query_issues:
                lines.extend(["", "Validation issues:"])
                lines.extend(f"- {issue}" for issue in query_issues)
            lines.append("")
    finally:
        await service.close()
    lines.extend(["## Overall validation", ""])
    if validation_failures:
        lines.append(f"**FAIL** — {len(validation_failures)} issue(s) detected.")
        lines.extend(f"- {failure}" for failure in validation_failures)
    else:
        lines.append("**PASS** — all queries returned valid, concept-matching Gold evidence.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if validation_failures:
        raise SmokeValidationError(
            f"Retrieval smoke validation failed with {len(validation_failures)} issue(s); "
            f"see {report_path}"
        )
    return report_path


def main() -> None:
    path = asyncio.run(run_smoke_tests())
    print(path)


if __name__ == "__main__":
    main()
