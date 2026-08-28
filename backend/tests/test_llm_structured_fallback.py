from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from app.services.llm import OllamaClient


class NestedOutput(BaseModel):
    values: list[str]


@pytest.mark.asyncio
async def test_structured_falls_back_to_json_when_ollama_rejects_schema_grammar() -> None:
    client = OllamaClient()
    calls = []

    def fake_request(prompt, *, format_=None, num_predict=900):
        calls.append((prompt, format_, num_predict))
        if len(calls) == 1:
            raise RuntimeError("failed to parse grammar")
        return json.dumps({"values": ["verified"]})

    client._request = fake_request  # type: ignore[method-assign]
    result = await client.structured("Produce structured output", NestedOutput)

    assert result.values == ["verified"]
    assert isinstance(calls[0][1], dict)
    assert calls[1][1] == "json"
    assert "JSON Schema" in calls[1][0]
    assert calls[1][2] == 1800
