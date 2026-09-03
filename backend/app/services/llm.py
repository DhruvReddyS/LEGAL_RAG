from __future__ import annotations

import asyncio
import json
from time import perf_counter_ns
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.services.pipeline_telemetry import text_size


T = TypeVar("T", bound=BaseModel)


class OllamaClient:
    """Small, testable boundary around the self-hosted Ollama API."""

    def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self._generation_slots = asyncio.Semaphore(settings.ollama_generation_concurrency)
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(240.0))
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._http_client.aclose()

    async def _async_request_with_metrics(
        self,
        prompt: str,
        *,
        format_: dict[str, Any] | str | None = None,
        num_predict: int = 900,
        operation: str = "generate",
        attempt: int = 1,
    ) -> tuple[str, dict[str, Any]]:
        if self._closed:
            raise RuntimeError("Ollama client is closed")
        context_window = 16384
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "think": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": context_window,
                "num_predict": num_predict,
            },
        }
        if format_ is not None:
            payload["format"] = format_
        started_ns = perf_counter_ns()
        first_token_ms: float | None = None
        try:
            async with self._generation_slots:
                async with self._http_client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode(
                            "utf-8", errors="replace"
                        )[:2000]
                        error = RuntimeError(
                            f"Ollama generation failed with HTTP {response.status_code}"
                        )
                        error.grammar_failure = (  # type: ignore[attr-defined]
                            "failed to parse grammar" in detail.casefold()
                        )
                        error.telemetry_metrics = [  # type: ignore[attr-defined]
                            self._failure_metric(
                                prompt,
                                started_ns=started_ns,
                                operation=operation,
                                attempt=attempt,
                                error_type="http_error",
                                http_status=response.status_code,
                                num_predict=num_predict,
                                context_window=context_window,
                            )
                        ]
                        raise error
                    pieces: list[str] = []
                    body: dict[str, Any] = {}
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        piece = str(chunk.get("response") or "")
                        if piece:
                            if first_token_ms is None:
                                first_token_ms = (
                                    perf_counter_ns() - started_ns
                                ) / 1_000_000
                            pieces.append(piece)
                        body.update(chunk)
                    body["response"] = "".join(pieces)
        except (httpx.RequestError, ValueError) as exc:
            error = RuntimeError(f"Ollama generation failed ({type(exc).__name__})")
            error.telemetry_metrics = [  # type: ignore[attr-defined]
                self._failure_metric(
                    prompt,
                    started_ns=started_ns,
                    operation=operation,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                    num_predict=num_predict,
                    context_window=context_window,
                )
            ]
            raise error from exc
        text = str(body.get("response") or "").strip()
        if not text:
            error = RuntimeError("Ollama returned an empty response")
            error.telemetry_metrics = [  # type: ignore[attr-defined]
                self._failure_metric(
                    prompt,
                    started_ns=started_ns,
                    operation=operation,
                    attempt=attempt,
                    error_type="empty_response",
                    num_predict=num_predict,
                    context_window=context_window,
                )
            ]
            raise error
        return text, self._success_metric(
            body,
            text,
            prompt,
            started_ns=started_ns,
            operation=operation,
            attempt=attempt,
            num_predict=num_predict,
            context_window=context_window,
            first_token_ms=first_token_ms,
        )

    def _request_with_metrics(
        self,
        prompt: str,
        *,
        format_: dict[str, Any] | str | None = None,
        num_predict: int = 900,
        operation: str = "generate",
        attempt: int = 1,
    ) -> tuple[str, dict[str, Any]]:
        context_window = 16384
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # The graph supplies bounded evidence, so a 16K window is ample and
            # avoids reserving the 40K model profile's much larger KV cache.
            "think": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": context_window,
                "num_predict": num_predict,
            },
        }
        if format_ is not None:
            payload["format"] = format_
        request = Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started_ns = perf_counter_ns()
        try:
            with urlopen(request, timeout=240) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                detail = ""
            error = RuntimeError(f"Ollama generation failed with HTTP {exc.code}")
            error.grammar_failure = "failed to parse grammar" in detail.casefold()  # type: ignore[attr-defined]
            error.telemetry_metrics = [  # type: ignore[attr-defined]
                self._failure_metric(
                    prompt,
                    started_ns=started_ns,
                    operation=operation,
                    attempt=attempt,
                    error_type="http_error",
                    http_status=exc.code,
                    num_predict=num_predict,
                    context_window=context_window,
                )
            ]
            raise error from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = RuntimeError(f"Ollama generation failed ({type(exc).__name__})")
            error.telemetry_metrics = [  # type: ignore[attr-defined]
                self._failure_metric(
                    prompt,
                    started_ns=started_ns,
                    operation=operation,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                    num_predict=num_predict,
                    context_window=context_window,
                )
            ]
            raise error from exc
        text = str(body.get("response") or "").strip()
        if not text:
            error = RuntimeError("Ollama returned an empty response")
            error.telemetry_metrics = [  # type: ignore[attr-defined]
                self._failure_metric(
                    prompt,
                    started_ns=started_ns,
                    operation=operation,
                    attempt=attempt,
                    error_type="empty_response",
                    num_predict=num_predict,
                    context_window=context_window,
                )
            ]
            raise error
        return text, self._success_metric(
            body,
            text,
            prompt,
            started_ns=started_ns,
            operation=operation,
            attempt=attempt,
            num_predict=num_predict,
            context_window=context_window,
        )

    def _success_metric(
        self,
        body: dict[str, Any],
        text: str,
        prompt: str,
        *,
        started_ns: int,
        operation: str,
        attempt: int,
        num_predict: int,
        context_window: int,
        first_token_ms: float | None = None,
    ) -> dict[str, Any]:
        prompt_eval_count = body.get("prompt_eval_count")
        eval_count = body.get("eval_count")
        metric: dict[str, Any] = {
            "operation": operation,
            "attempt": attempt,
            "model": str(body.get("model") or self.model),
            "wall_ms": (perf_counter_ns() - started_ns) / 1_000_000,
            "prompt": text_size(prompt),
            # Ollama's tokenizer-derived value is authoritative when present.
            "prompt_eval_count": (
                int(prompt_eval_count) if isinstance(prompt_eval_count, (int, float)) else None
            ),
            "context_window": context_window,
            "context_utilization": (
                float(prompt_eval_count) / context_window
                if isinstance(prompt_eval_count, (int, float))
                else None
            ),
            "num_predict_limit": num_predict,
            "response_characters": len(text),
            "time_to_first_response_token_ms": first_token_ms,
            "response_eval_count": int(eval_count) if isinstance(eval_count, (int, float)) else None,
            "done_reason": body.get("done_reason"),
            "ollama_total_duration_ms": self._nanoseconds_to_ms(body.get("total_duration")),
            "ollama_load_duration_ms": self._nanoseconds_to_ms(body.get("load_duration")),
            "ollama_prompt_eval_duration_ms": self._nanoseconds_to_ms(
                body.get("prompt_eval_duration")
            ),
            "ollama_eval_duration_ms": self._nanoseconds_to_ms(body.get("eval_duration")),
            "metrics_source": "ollama_response",
        }
        eval_duration = body.get("eval_duration")
        if isinstance(eval_count, (int, float)) and isinstance(eval_duration, (int, float)) and eval_duration > 0:
            metric["response_tokens_per_second"] = float(eval_count) / (float(eval_duration) / 1_000_000_000)
        return metric

    @staticmethod
    def _nanoseconds_to_ms(value: Any) -> float | None:
        if not isinstance(value, (int, float)):
            return None
        return float(value) / 1_000_000

    def _failure_metric(
        self,
        prompt: str,
        *,
        started_ns: int,
        operation: str,
        attempt: int,
        error_type: str,
        num_predict: int,
        context_window: int,
        http_status: int | None = None,
    ) -> dict[str, Any]:
        return {
            "operation": operation,
            "attempt": attempt,
            "model": self.model,
            "wall_ms": (perf_counter_ns() - started_ns) / 1_000_000,
            "prompt": text_size(prompt),
            "prompt_eval_count": None,
            "context_window": context_window,
            "prompt_context_utilization": None,
            "num_predict_limit": num_predict,
            "error_type": error_type,
            "http_status": http_status,
            "metrics_source": "client_error",
        }

    def _request(
        self,
        prompt: str,
        *,
        format_: dict[str, Any] | str | None = None,
        num_predict: int = 900,
    ) -> str:
        text, _ = self._request_with_metrics(
            prompt,
            format_=format_,
            num_predict=num_predict,
        )
        return text

    async def generate(self, prompt: str) -> str:
        text, _ = await self._async_request_with_metrics(prompt)
        return text

    async def generate_with_metrics(
        self,
        prompt: str,
        *,
        num_predict: int = 900,
    ) -> tuple[str, dict[str, Any]]:
        return await self._async_request_with_metrics(
            prompt,
            num_predict=num_predict,
            operation="generate",
        )

    async def structured(self, prompt: str, schema: type[T], *, attempts: int = 3) -> T:
        last_error: Exception | None = None
        schema_json = schema.model_json_schema()
        grammar_fallback = False
        for _ in range(attempts):
            try:
                request_prompt = prompt
                request_format: dict[str, Any] | str = schema_json
                if grammar_fallback:
                    request_format = "json"
                    request_prompt = (
                        f"{prompt}\n\nReturn one JSON object matching this JSON Schema exactly:\n"
                        f"{json.dumps(schema_json, ensure_ascii=False)}"
                    )
                if "_request" in self.__dict__:
                    raw = await asyncio.to_thread(
                        self._request,
                        request_prompt,
                        format_=request_format,
                        num_predict=1800,
                    )
                else:
                    raw, _ = await self._async_request_with_metrics(
                        request_prompt,
                        format_=request_format,
                        num_predict=1800,
                        operation="structured",
                    )
                return schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                if getattr(exc, "grammar_failure", False) or (
                    "failed to parse grammar" in str(exc).casefold()
                ):
                    grammar_fallback = True
        raise RuntimeError(f"Ollama structured output failed after {attempts} attempts") from last_error

    async def structured_with_metrics(
        self,
        prompt: str,
        schema: type[T],
        *,
        attempts: int = 3,
    ) -> tuple[T, list[dict[str, Any]]]:
        last_error: Exception | None = None
        schema_json = schema.model_json_schema()
        grammar_fallback = False
        metrics: list[dict[str, Any]] = []
        for attempt in range(1, attempts + 1):
            request_prompt = prompt
            request_format: dict[str, Any] | str = schema_json
            if grammar_fallback:
                request_format = "json"
                request_prompt = (
                    f"{prompt}\n\nReturn one JSON object matching this JSON Schema exactly:\n"
                    f"{json.dumps(schema_json, ensure_ascii=False)}"
                )
            try:
                raw, metric = await self._async_request_with_metrics(
                    request_prompt,
                    format_=request_format,
                    num_predict=1800,
                    operation="structured",
                    attempt=attempt,
                )
                try:
                    value = schema.model_validate_json(raw)
                except (ValidationError, json.JSONDecodeError) as exc:
                    metric["parse_status"] = "invalid"
                    metric["parse_error"] = type(exc).__name__
                    metrics.append(metric)
                    last_error = exc
                    continue
                metric["parse_status"] = "valid"
                metrics.append(metric)
                return value, metrics
            except RuntimeError as exc:
                last_error = exc
                metrics.extend(getattr(exc, "telemetry_metrics", []))
                if getattr(exc, "grammar_failure", False) or (
                    "failed to parse grammar" in str(exc).casefold()
                ):
                    grammar_fallback = True
        error = RuntimeError(f"Ollama structured output failed after {attempts} attempts")
        error.telemetry_metrics = metrics  # type: ignore[attr-defined]
        raise error from last_error
