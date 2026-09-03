#!/usr/bin/env python3
"""Measure Ollama prefill and decode throughput against prompt size.

Deep latency was attributed to a container/Metal problem. It is not: decode
falls as the KV cache grows, and the recorded runs used 6.5k-13k token
prompts. This harness records the curve so a latency claim can be checked
against the prompt size it was measured at.

Writes a JSON evidence file including machine, model, quantisation, context
window and GPU residency, so a measurement is never separated from its
configuration.

Usage:
    python scripts/ollama_throughput_baseline.py \
        --model qwen3-14b-16k:latest --num-ctx 16384 \
        --prompt-tokens 500,6500,13000 \
        --out docs/evidence/ollama-throughput-<host>.json
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Legal-register filler so token counts resemble real corpus evidence rather
# than repeated single tokens, which prefill handles unrepresentatively well.
FILLER = (
    "The officer in charge of a police station shall, upon receipt of information "
    "relating to the commission of a cognizable offence, reduce the substance thereof "
    "to writing and read it over to the informant, who shall sign the same. A copy of "
    "the information so recorded shall be given forthwith, free of cost, to the informant. "
)


def build_prompt(target_tokens: int) -> str:
    return (
        "LEGAL EVIDENCE:\n"
        + FILLER * max(1, target_tokens // 55)
        + "\n\nQUESTION: In two sentences, state the duty described above."
    )


def generate(
    base_url: str, model: str, num_ctx: int, prompt: str, num_predict: int
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.0, "num_ctx": num_ctx, "num_predict": num_predict},
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read().decode("utf-8"))


def measure(body: dict[str, Any]) -> dict[str, Any]:
    prompt_tokens = int(body.get("prompt_eval_count") or 0)
    output_tokens = int(body.get("eval_count") or 0)
    prefill_ns = int(body.get("prompt_eval_duration") or 0)
    decode_ns = int(body.get("eval_duration") or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "load_ms": round(int(body.get("load_duration") or 0) / 1e6, 2),
        "prefill_ms": round(prefill_ns / 1e6, 2),
        "decode_ms": round(decode_ns / 1e6, 2),
        "prefill_tokens_per_second": (
            round(prompt_tokens / (prefill_ns / 1e9), 2) if prefill_ns else None
        ),
        "decode_tokens_per_second": (
            round(output_tokens / (decode_ns / 1e9), 2) if decode_ns else None
        ),
        "done_reason": body.get("done_reason"),
    }


def gpu_residency() -> str:
    """Capture `ollama ps`, which reports the CPU/GPU split for a loaded model."""
    try:
        return subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=15
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable: {type(exc).__name__}"


def host_profile() -> dict[str, Any]:
    profile: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    if sys.platform == "darwin":
        for key, command in (
            ("chip", ["sysctl", "-n", "machdep.cpu.brand_string"]),
            ("memory_bytes", ["sysctl", "-n", "hw.memsize"]),
        ):
            try:
                profile[key] = subprocess.run(
                    command, capture_output=True, text=True, timeout=10
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                profile[key] = "unavailable"
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3-14b-16k:latest")
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument("--prompt-tokens", default="500,6500,13000")
    parser.add_argument("--num-predict", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()

    targets = [int(value) for value in arguments.prompt_tokens.split(",")]

    # Absorb model load and any first-call compilation before measuring.
    generate(arguments.base_url, arguments.model, arguments.num_ctx, "Warm up.", 16)

    records: list[dict[str, Any]] = []
    for target in targets:
        prompt = build_prompt(target)
        for repeat in range(1, arguments.repeats + 1):
            body = generate(
                arguments.base_url, arguments.model, arguments.num_ctx, prompt,
                arguments.num_predict,
            )
            record = {"target_prompt_tokens": target, "repeat": repeat, **measure(body)}
            records.append(record)
            print(
                f"~{target:>6} tok  ctx={arguments.num_ctx:<6} "
                f"actual={record['prompt_tokens']:<7} out={record['output_tokens']:<5} "
                f"prefill={record['prefill_ms'] / 1000:7.2f}s "
                f"decode={record['decode_ms'] / 1000:7.2f}s | "
                f"prefill_tps={record['prefill_tokens_per_second']:>8} "
                f"decode_tps={record['decode_tokens_per_second']:>7}"
            )

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": arguments.model,
        "num_ctx": arguments.num_ctx,
        "num_predict": arguments.num_predict,
        "host": host_profile(),
        "gpu_residency": gpu_residency(),
        "records": records,
    }
    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {arguments.out}")


if __name__ == "__main__":
    main()
