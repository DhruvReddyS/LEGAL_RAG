from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from app.core.config import settings


T = TypeVar("T", bound=BaseModel)


class OllamaClient:
    """Small, testable boundary around the self-hosted Ollama API."""

    def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model

    def _request(
        self,
        prompt: str,
        *,
        format_: dict[str, Any] | str | None = None,
        num_predict: int = 900,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # The graph supplies bounded evidence, so a 16K window is ample and
            # avoids reserving the 40K model profile's much larger KV cache.
            "think": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 16384,
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
        try:
            with urlopen(request, timeout=240) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                detail = ""
            raise RuntimeError(
                f"Ollama generation failed with HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama generation failed: {exc}") from exc
        text = str(body.get("response") or "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty response")
        return text

    async def generate(self, prompt: str) -> str:
        return await asyncio.to_thread(self._request, prompt)

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
                raw = await asyncio.to_thread(
                    self._request,
                    request_prompt,
                    format_=request_format,
                    num_predict=1800,
                )
                return schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                if "failed to parse grammar" in str(exc).casefold():
                    grammar_fallback = True
        raise RuntimeError(f"Ollama structured output failed after {attempts} attempts") from last_error
