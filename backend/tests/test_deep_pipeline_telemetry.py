from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.agents.orchestrator import LegalRAGWorkflow
from app.agents.query_understanding import _fallback_intent
from app.agents.reasoning_agent import _GroundedDraft, _GroundedDraftClaim
from app.agents.verification_agent import VerificationBatch
from app.services.llm import OllamaClient
from app.services.pipeline_telemetry import capture_stage_metrics
from app.services.retrieval import RetrievalHit, RetrievalTimings


class InstrumentedFakeLLM:
    def __init__(self) -> None:
        self.generate_num_predict: list[int] = []

    async def structured_with_metrics(
        self,
        prompt,
        schema,
        *,
        attempts=3,
        num_predict=1800,
    ):
        metric = {
            "operation": "structured",
            "attempt": 1,
            "prompt_eval_count": 321,
            "context_window": 16384,
            "prompt": {"characters": len(prompt)},
        }
        if schema is VerificationBatch:
            return VerificationBatch(claims=[]), [metric]
        if schema is _GroundedDraft:
            self.generate_num_predict.append(num_predict)
            metric["num_predict_limit"] = num_predict
            metric["prompt_eval_count"] = 987
            return _GroundedDraft(
                claims=[
                    _GroundedDraftClaim(
                        category="direct_answer",
                        claim="Registration is required",
                        source_chunk_ids=["chunk-1"],
                    )
                ]
            ), [metric]
        return _fallback_intent("section 154 CrPC and section 173 BNSS"), [metric]

    async def generate_with_metrics(self, prompt, *, num_predict=900):
        self.generate_num_predict.append(num_predict)
        return "Registration is required [SRC:chunk-1].", {
            "operation": "generate",
            "attempt": 1,
            "prompt_eval_count": 987,
            "context_window": 16384,
            "num_predict_limit": num_predict,
            "prompt": {"characters": len(prompt)},
        }


class InstrumentedFakeRetrieval:
    """Returns fresh evidence on every pass.

    The workflow now stops retrying when a broadened query returns the chunks
    the previous pass already saw, because generation is deterministic and the
    verdicts cannot change. A fixture that returned a fixed chunk would
    therefore exercise the no-progress guard rather than the retry bound this
    test is about.
    """

    def __init__(self) -> None:
        self.passes = 0

    async def distinctive_query_terms(self, terms, *, target):
        """The real service computes term frequencies against the corpus.

        Implemented on the fake so the tests exercise the same path as
        production rather than the retrieval node's defensive fallback,
        which would otherwise be the only branch they ever cover.
        """
        return {term: 1 for term in terms}, sorted(terms)

    async def search_across_collections_with_timings(self, query, **kwargs):
        self.passes += 1
        return [
            RetrievalHit(
                point_id=f"point-{self.passes}",
                payload={
                    "chunk_id": f"chunk-{self.passes}",
                    "title": "Procedure Code",
                    "source_type": "act",
                    "page_start": 1,
                    "page_end": 1,
                    # Evidence that actually matches the question asked. It
                    # used to read "Registration is required." against a query
                    # about an FIR being registered, sharing no stemmed token
                    # with it -- harmless until the publication gate began
                    # asking whether the evidence addresses the question, and
                    # dishonest before that.
                    "text": (
                        "An FIR shall be registered without delay when the "
                        "information discloses a cognizable offence."
                    ),
                },
                dense_score=0.8,
                sparse_score=2.0,
                fused_score=0.5,
                reranker_score=0.9,
            )
        ], RetrievalTimings(
            embedding_ms=1.25,
            qdrant_ms=2.5,
            reranking_ms=3.75,
            total_ms=7.5,
            candidate_count=20,
            result_count=1,
            reranker_input_chunk_count=20,
            reranker_input_characters=12000,
            reranker_input_utf8_bytes=12000,
            reranker_max_length=8192,
        )


class FailingGenerateLLM(InstrumentedFakeLLM):
    async def structured_with_metrics(self, prompt, schema, *, attempts=3):
        if schema is _GroundedDraft:
            error = RuntimeError("sanitized failure")
            error.telemetry_metrics = [
                {
                    "operation": "structured",
                    "wall_ms": 12.5,
                    "prompt": {"characters": len(prompt)},
                    "error_type": "TimeoutError",
                    "metrics_source": "client_error",
                }
            ]
            raise error
        return await super().structured_with_metrics(prompt, schema, attempts=attempts)


@pytest.mark.asyncio
async def test_deep_workflow_records_retries_input_sizes_and_actual_prompt_tokens() -> None:
    llm = InstrumentedFakeLLM()
    result = await LegalRAGWorkflow(
        InstrumentedFakeRetrieval(),  # type: ignore[arg-type]
        llm,  # type: ignore[arg-type]
    ).run(
        query="Compare section 154 CrPC and section 173 BNSS",
        role="citizen",
        case_id=None,
        history=[],
    )

    stages = result["stage_metrics"]
    stage_names = [stage["stage"] for stage in stages]
    assert stage_names.count("retrieval") == 3
    assert stage_names.count("retrieval_enrichment") == 3
    assert stage_names.count("reasoning") == 3
    assert stage_names.count("verification") == 3
    assert stage_names.count("retry") == 2
    assert stage_names[-1] == "workflow_total"
    retrieval = next(stage for stage in stages if stage["stage"] == "retrieval")
    assert retrieval["outputs"]["reranker_input_chunk_count"] == 20
    assert retrieval["outputs"]["reranker_input_characters"] == 12000
    enrichment = next(
        stage for stage in stages if stage["stage"] == "retrieval_enrichment"
    )
    assert enrichment["outputs"]["distinctive_term_count"] > 0
    assert enrichment["outputs"]["final_chunk_count"] == (
        enrichment["inputs"]["search_result_chunk_count"]
        + enrichment["outputs"]["followed_chunk_count"]
    )
    reasoning = next(stage for stage in stages if stage["stage"] == "reasoning")
    assert reasoning["llm_calls"][0]["prompt_eval_count"] == 987
    assert reasoning["llm_calls"][0]["context_window"] == 16384
    assert reasoning["llm_calls"][0]["num_predict_limit"] == 1200
    assert reasoning["outputs"]["reasoning_num_predict_limit"] == 1200
    assert llm.generate_num_predict == [1200, 1200, 1200]


def test_ollama_request_metrics_use_server_token_counts(monkeypatch) -> None:
    body = {
        "model": "test-model",
        "response": "grounded answer",
        "prompt_eval_count": 2048,
        "eval_count": 128,
        "total_duration": 2_000_000_000,
        "load_duration": 100_000_000,
        "prompt_eval_duration": 400_000_000,
        "eval_duration": 1_000_000_000,
        "done_reason": "stop",
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return json.dumps(body).encode("utf-8")

    monkeypatch.setattr("app.services.llm.urlopen", lambda *_args, **_kwargs: FakeResponse())
    _, metric = OllamaClient(model="test-model")._request_with_metrics("legal prompt")

    assert metric["prompt_eval_count"] == 2048
    assert metric["context_window"] == 16384
    assert metric["context_utilization"] == pytest.approx(0.125)
    assert metric["response_eval_count"] == 128
    assert metric["response_tokens_per_second"] == pytest.approx(128.0)


@pytest.mark.asyncio
async def test_failed_node_and_workflow_emit_sanitized_metrics() -> None:
    captured = []
    with capture_stage_metrics(captured.append):
        with pytest.raises(RuntimeError, match="sanitized failure"):
            await LegalRAGWorkflow(
                InstrumentedFakeRetrieval(),  # type: ignore[arg-type]
                FailingGenerateLLM(),  # type: ignore[arg-type]
            ).run(
                query="Synthetic failure query",
                role="citizen",
                case_id=None,
                history=[],
            )

    reasoning = next(metric for metric in captured if metric["stage"] == "reasoning")
    workflow_total = captured[-1]
    assert reasoning["outputs"] == {"completed": False, "error_type": "RuntimeError"}
    assert reasoning["llm_calls"][0]["error_type"] == "TimeoutError"
    assert workflow_total["stage"] == "workflow_total"
    assert workflow_total["outputs"] == {
        "completed": False,
        "error_type": "RuntimeError",
    }


def test_ollama_http_error_body_is_not_exposed(monkeypatch) -> None:
    secret = b"failed to parse grammar; confidential prompt material"

    def raise_http_error(*_args, **_kwargs):
        raise HTTPError(
            "http://localhost/api/generate",
            500,
            "server error",
            hdrs=None,
            fp=BytesIO(secret),
        )

    monkeypatch.setattr("app.services.llm.urlopen", raise_http_error)
    with pytest.raises(RuntimeError) as caught:
        OllamaClient(model="test-model")._request_with_metrics("private prompt")

    assert secret.decode() not in str(caught.value)
    metrics = caught.value.telemetry_metrics
    assert metrics[0]["error_type"] == "http_error"
    assert metrics[0]["http_status"] == 500
    assert "error" not in metrics[0]


@pytest.mark.asyncio
async def test_time_to_first_token_excludes_queue_wait() -> None:
    """TTFT was measured before the generation slot was acquired.

    A busy queue then looked identical to a slow prefill: a 3,000-token prompt
    reported 65 seconds to first token when the model itself was fine.
    """
    import asyncio

    from app.services.llm import OllamaClient

    client = OllamaClient(base_url="http://127.0.0.1:1", model="test-model")
    try:
        # Hold the only generation slot so the next call has to wait for it.
        await client._generation_slots.acquire()

        async def release_later() -> None:
            await asyncio.sleep(0.3)
            client._generation_slots.release()

        asyncio.create_task(release_later())
        try:
            await client.generate("probe")
        except RuntimeError as exc:
            metric = getattr(exc, "telemetry_metrics", [{}])[0]
        else:  # pragma: no cover - the endpoint is unreachable by construction
            raise AssertionError("expected the request to fail")

        # The failure path records wall time, which still contains the wait.
        assert metric["wall_ms"] >= 300
    finally:
        await client.close()
