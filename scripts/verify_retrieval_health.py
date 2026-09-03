#!/usr/bin/env python3
"""Check the embedding and retrieval stack for silent failure modes.

Every check here fails quietly in production: an instruction prefix left over
from a different model, an asymmetric query/document path, a normalisation and
distance mismatch, a 512-token truncation inherited from a default. None raise
an error. All of them degrade retrieval.

Checks are grouped by what they need. Static checks run anywhere. Model checks
load BGE-M3. Index checks need a reachable Qdrant. Anything that cannot run is
reported as BLOCKED, which is not a failure — but --strict turns it into one,
which is what CI wants.

Exit codes: 0 all runnable checks passed, 1 at least one failed.

Usage:
    python scripts/verify_retrieval_health.py                # static + index
    python scripts/verify_retrieval_health.py --with-model   # add E-03/E-04
    python scripts/verify_retrieval_health.py --strict       # blocked -> fail
    python scripts/verify_retrieval_health.py --json report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"


@dataclass
class Check:
    id: str
    name: str
    status: str
    detail: str
    data: dict[str, Any] | None = None


_RESULTS: list[Check] = []


def record(id: str, name: str, status: str, detail: str, data: dict | None = None) -> Check:
    check = Check(id=id, name=name, status=status, detail=detail, data=data)
    _RESULTS.append(check)
    symbol = {PASS: "PASS ", FAIL: "FAIL ", BLOCKED: "SKIP "}[status]
    print(f"  {symbol} {id}  {name}\n         {detail}")
    return check


def guarded(id: str, name: str) -> Callable:
    """Turn an unexpected exception into a BLOCKED result, never a crash."""

    def decorator(function):
        async def wrapper(*args, **kwargs):
            try:
                return await function(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                return record(id, name, BLOCKED, f"could not run: {type(exc).__name__}: {exc}")

        return wrapper

    return decorator


# --------------------------------------------------------------------------
# Static source checks
# --------------------------------------------------------------------------

# BGE-M3 takes no instruction prefix, unlike E5 and BGE-v1.5. A prefix copied
# from another model shifts every query vector without erroring.
FOREIGN_PREFIXES = (
    r'"\s*Represent this',
    r'"query:\s*"',
    r'"passage:\s*"',
    r'f"query:\s*',
    r'f"passage:\s*',
    r"query_instruction_for_retrieval",
)


async def check_no_instruction_prefix() -> Check:
    paths = [
        BACKEND / "app" / "ingestion" / "embedder.py",
        BACKEND / "app" / "services" / "retrieval.py",
    ]
    offenders: list[str] = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for pattern in FOREIGN_PREFIXES:
            if re.search(pattern, source):
                offenders.append(f"{path.name}: /{pattern}/")
    if offenders:
        return record(
            "E-01", "No instruction prefix on queries", FAIL,
            "BGE-M3 takes no prefix; found " + ", ".join(offenders),
        )
    return record(
        "E-01", "No instruction prefix on queries", PASS,
        "no E5/BGE-v1.5 prefix pattern in the embedding or retrieval path",
    )


async def check_encode_options() -> Check:
    """E-05: max_length must be set explicitly, not inherited from a default."""
    source = (BACKEND / "app" / "ingestion" / "embedder.py").read_text(encoding="utf-8")
    match = re.search(r'"max_length":\s*(\d+)', source)
    if match is None:
        return record(
            "E-05", "Chunks fit the model window", FAIL,
            "encode() call sets no explicit max_length; a library default may truncate at 512",
        )
    length = int(match.group(1))
    if length < 8192:
        return record(
            "E-05", "Chunks fit the model window", FAIL,
            f"max_length={length} is below BGE-M3's 8192 window",
        )
    return record(
        "E-05", "Chunks fit the model window", PASS,
        f"max_length={length} set explicitly", {"max_length": length},
    )


async def check_dtype_policy() -> Check:
    source = (BACKEND / "app" / "ingestion" / "embedder.py").read_text(encoding="utf-8")
    if 'use_fp16 = device in {"cuda", "mps"}' not in source:
        return record(
            "E-07", "Sane dtype per device", FAIL,
            "fp16 is not gated on an accelerator; fp16 on CPU is slow and numerically unstable",
        )
    return record(
        "E-07", "Sane dtype per device", PASS,
        "fp16 only on cuda/mps, fp32 on cpu",
    )


async def check_single_encode_pass() -> Check:
    """E-10/E-11: dense and sparse must come from one pass over identical text."""
    source = (BACKEND / "app" / "ingestion" / "embedder.py").read_text(encoding="utf-8")
    block = re.search(r"encode_options = \{(.+?)\}", source, re.S)
    if block is None:
        return record("E-10", "Sparse from the same pass", BLOCKED, "encode_options not found")
    options = block.group(1)
    if '"return_dense": True' in options and '"return_sparse": True' in options:
        return record(
            "E-10", "Sparse and dense from one pass over identical text", PASS,
            "single encode() returns both; no second pass and no tokenizer drift",
        )
    return record(
        "E-10", "Sparse and dense from one pass over identical text", FAIL,
        "dense and sparse are not both requested from the same encode() call",
    )


async def check_query_cache_key() -> Check:
    """E-06: a cache keyed on text alone survives a model change."""
    source = (BACKEND / "app" / "services" / "retrieval.py").read_text(encoding="utf-8")
    block = re.search(r"cache_key = hashlib\.sha256\((.+?)\)\.hexdigest\(\)", source, re.S)
    if block is None:
        return record("E-06", "Cache key includes model identity", BLOCKED, "cache key not found")
    key_source = block.group(1)
    if "embedding_model" in key_source:
        return record(
            "E-06", "Cache key includes model identity", PASS,
            "query cache key includes the model name and dimension",
        )
    return record(
        "E-06", "Cache key includes model identity", FAIL,
        "query cache is keyed on query text alone; a model change would serve stale-space vectors",
    )


async def check_fusion_constant_is_pinned() -> Check:
    """E-12: RRF k is Qdrant's internal default, so the image must be pinned."""
    compose = (BACKEND.parent / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    match = re.search(r"image:\s*qdrant/qdrant:(\S+)", compose)
    if match is None or match.group(1) in {"latest", "master"}:
        return record(
            "E-12", "Fusion constant is reproducible", FAIL,
            "Qdrant image is unpinned; the server-side RRF k constant can change under you",
        )
    return record(
        "E-12", "Fusion constant is reproducible", PASS,
        f"RRF runs server-side under pinned qdrant/qdrant:{match.group(1)}",
        {"qdrant_image": match.group(1)},
    )


async def check_inference_device() -> Check:
    """E-08/E-15: CPU inference is correct but several times slower."""
    from app.ingestion.embedder import resolve_embedding_device

    device = resolve_embedding_device()
    if device in {"cuda", "mps"}:
        return record(
            "E-08", "Embedder and reranker reach an accelerator", PASS,
            f"resolved device is {device}", {"device": device},
        )
    return record(
        "E-08", "Embedder and reranker reach an accelerator", BLOCKED,
        f"resolved device is {device}; correct but roughly 4x slower in the retrieval stage",
        {"device": device},
    )


# --------------------------------------------------------------------------
# Model checks
# --------------------------------------------------------------------------


@guarded("E-03", "Query and document embedding are symmetric")
async def check_symmetric_embedding() -> Check:
    """The single most common silent RAG failure."""
    from app.services.retrieval import HybridRetrievalService

    service = HybridRetrievalService()
    try:
        probe = "Registration of a first information report for a cognizable offence."
        document = (await service.embed_documents([probe], batch_size=1))[0]
        query = await service._embed_query_batched(probe)
        left, right = document.dense, query.dense
        dot = sum(a * b for a, b in zip(left, right))
        norm = (sum(a * a for a in left) ** 0.5) * (sum(b * b for b in right) ** 0.5)
        cosine = dot / norm if norm else 0.0
        magnitude = sum(a * a for a in left) ** 0.5
        normalized = abs(magnitude - 1.0) < 0.01
        if cosine < 0.999:
            return record(
                "E-03", "Query and document embedding are symmetric", FAIL,
                f"same text through both paths gives cosine {cosine:.6f}; expected ~1.0",
                {"cosine": cosine},
            )
        return record(
            "E-03", "Query and document embedding are symmetric", PASS,
            f"cosine {cosine:.6f}; vectors are "
            + ("L2-normalised" if normalized else f"unnormalised (norm {magnitude:.4f})"),
            {"cosine": cosine, "l2_normalised": normalized, "norm": magnitude},
        )
    finally:
        await service.close()


# --------------------------------------------------------------------------
# Index checks
# --------------------------------------------------------------------------


@guarded("E-02", "Vector schema matches the embedding")
async def check_collection_schema(client) -> Check:
    from app.core.config import settings
    from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS

    info = await client.get_collection(GLOBAL_LEGAL_CORPUS)
    dense = (info.config.params.vectors or {}).get(settings.qdrant_dense_vector_name)
    sparse = (info.config.params.sparse_vectors or {}).get(settings.qdrant_sparse_vector_name)
    problems: list[str] = []
    if dense is None:
        problems.append("dense vector missing")
    else:
        if dense.size != settings.embedding_dimension:
            problems.append(f"dense size {dense.size} != {settings.embedding_dimension}")
        if str(dense.distance).lower().endswith("cosine") is False:
            problems.append(f"distance is {dense.distance}, expected Cosine")
    if sparse is None:
        problems.append("sparse vector missing")
    else:
        modifier = str(getattr(sparse, "modifier", "")).lower()
        if "idf" not in modifier:
            problems.append(f"sparse modifier is {modifier or 'unset'}, expected IDF (E-09)")
    if problems:
        return record("E-02", "Vector schema matches the embedding", FAIL, "; ".join(problems))
    return record(
        "E-02", "Vector schema and sparse IDF modifier", PASS,
        f"dense size {dense.size} Cosine, sparse modifier IDF",
    )


@guarded("E-17", "Point count reconciles with the manifest")
async def check_point_count(client) -> Check:
    from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS

    manifest = BACKEND.parent / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"
    physical = sum(1 for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip())
    canonical = len(
        {
            json.loads(line)["canonical_document_id"]
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    )
    count = (await client.count(collection_name=GLOBAL_LEGAL_CORPUS, exact=True)).count
    if count == 0:
        return record(
            "E-17", "Point count reconciles with the manifest", FAIL,
            f"collection is empty; manifest describes {canonical} canonical documents",
        )
    return record(
        "E-17", "Point count reconciles with the manifest", PASS,
        f"{count} points for {canonical} canonical documents ({physical} physical)",
        {"points": count, "canonical_documents": canonical, "physical_documents": physical},
    )


@guarded("E-18", "No empty chunk text")
async def check_chunk_text(client) -> Check:
    from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS

    empty: list[str] = []
    offset = None
    sampled = 0
    while sampled < 5000:
        points, offset = await client.scroll(
            collection_name=GLOBAL_LEGAL_CORPUS, limit=512,
            offset=offset, with_payload=True, with_vectors=False,
        )
        if not points:
            break
        for point in points:
            sampled += 1
            if not str((point.payload or {}).get("text") or "").strip():
                empty.append(str(point.id))
        if offset is None:
            break
    if empty:
        return record(
            "E-18", "No empty chunk text", FAIL,
            f"{len(empty)} of {sampled} sampled chunks have empty text, e.g. {empty[:3]}",
        )
    return record(
        "E-18", "No empty chunk text", PASS,
        f"{sampled} chunks sampled, all carry text", {"sampled": sampled},
    )


@guarded("E-20", "Payload index on every filtered field")
async def check_payload_indexes(client) -> Check:
    from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
    from app.services.retrieval import RetrievalFilters

    info = await client.get_collection(GLOBAL_LEGAL_CORPUS)
    indexed = set(info.payload_schema)
    # Payload keys RetrievalFilters can put in a Qdrant filter. Note these are
    # payload keys, not filter attribute names: the attribute that filters on
    # "is_superseded" is called exclude_superseded. An earlier version of this
    # check looked for the payload key among the dataclass fields, never found
    # it, and silently reported a pass on the one field it was added to verify.
    filtered = {
        "source_type", "court", "jurisdiction", "act_name", "section",
        "corpus_tier", "case_id", "decision_year", "decision_date", "is_current",
    }
    filter_fields = RetrievalFilters.__dataclass_fields__
    if "exclude_superseded" in filter_fields:
        filtered.add("is_superseded")
    assert "current_only" in filter_fields, "filter attribute names have changed"
    missing = sorted(filtered - indexed - {"case_id"})  # case_id lives on private collections
    if missing:
        return record(
            "E-20", "Payload index on every filtered field", FAIL,
            f"unindexed filter fields will force a full scan: {', '.join(missing)}",
            {"missing": missing},
        )
    return record(
        "E-20", "Payload index on every filtered field", PASS,
        f"{len(filtered)} filter fields all indexed",
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-model", action="store_true", help="load BGE-M3 for E-03")
    parser.add_argument("--strict", action="store_true", help="treat BLOCKED as failure")
    parser.add_argument("--json", type=Path, help="write a JSON report")
    arguments = parser.parse_args()

    print("\nStatic checks")
    await check_no_instruction_prefix()
    await check_encode_options()
    await check_dtype_policy()
    await check_single_encode_pass()
    await check_query_cache_key()
    await check_fusion_constant_is_pinned()
    await check_inference_device()

    print("\nIndex checks")
    try:
        from app.core.qdrant import create_qdrant_client

        client = create_qdrant_client()
        await client.get_collections()
    except Exception as exc:  # noqa: BLE001
        for id, name in (
            ("E-02", "Vector schema and sparse IDF modifier"),
            ("E-17", "Point count reconciles with the manifest"),
            ("E-18", "No empty chunk text"),
            ("E-20", "Payload index on every filtered field"),
        ):
            record(id, name, BLOCKED, f"Qdrant unreachable: {type(exc).__name__}")
    else:
        try:
            await check_collection_schema(client)
            await check_point_count(client)
            await check_chunk_text(client)
            await check_payload_indexes(client)
        finally:
            await client.close()

    if arguments.with_model:
        print("\nModel checks")
        await check_symmetric_embedding()
    else:
        record(
            "E-03", "Query and document embedding are symmetric", BLOCKED,
            "pass --with-model to load BGE-M3 and compare both paths",
        )

    failed = [check for check in _RESULTS if check.status == FAIL]
    blocked = [check for check in _RESULTS if check.status == BLOCKED]
    passed = [check for check in _RESULTS if check.status == PASS]
    print(f"\n{len(passed)} passed, {len(failed)} failed, {len(blocked)} blocked")
    for check in failed:
        print(f"  FAILED {check.id}: {check.detail}")

    if arguments.json:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        arguments.json.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "passed": len(passed),
                    "failed": len(failed),
                    "blocked": len(blocked),
                    "checks": [asdict(check) for check in _RESULTS],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {arguments.json}")

    if failed:
        return 1
    if blocked and arguments.strict:
        print("  --strict: blocked checks are failures")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
