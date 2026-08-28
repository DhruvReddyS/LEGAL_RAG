from __future__ import annotations

from app.schemas.agents import AgentTraceEvent
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.llm import OllamaClient
from app.services.retrieval import RetrievalHit
from app.agents.role_profiles import profile_prompt, specialist_prompt


def format_evidence(hits: list[RetrievalHit]) -> str:
    blocks: list[str] = []
    for hit in hits:
        payload = hit.payload
        blocks.append(
            "CHUNK_ID: {chunk_id}\nTITLE: {title}\nPAGES: {start}-{end}\nTEXT:\n{text}".format(
                chunk_id=payload.get("chunk_id"),
                title=payload.get("title") or "Unknown",
                start=payload.get("page_start") or "?",
                end=payload.get("page_end") or "?",
                text=str(payload.get("text") or "").strip(),
            )
        )
    return "\n\n---\n\n".join(blocks)


async def reasoning_node(state: dict, llm: OllamaClient) -> dict:
    hits = list(state.get("retrieved_chunks", []))
    if not hits:
        draft = INSUFFICIENT_EVIDENCE
    else:
        prompt = f"""You are a cautious Indian legal research assistant. Answer only from EVIDENCE.
Every factual or legal claim MUST end with one or more exact markers [SRC:CHUNK_ID] copied from
EVIDENCE. Never invent a citation or use outside knowledge. If evidence is inadequate, output exactly:
{INSUFFICIENT_EVIDENCE}
State conflicts and uncertainty. Be concise. This is research assistance, not legal advice.

{profile_prompt(state.get('role', 'citizen'))}
{specialist_prompt(state)}

QUESTION: {state['query']}

EVIDENCE:
{format_evidence(hits)}"""
        draft = await llm.generate(prompt)
    trace = list(state.get("agent_trace", []))
    trace.append(
        AgentTraceEvent(
            node="reasoning",
            details={"answer_characters": len(draft), "citation_markers": draft.count("[SRC:")},
        )
    )
    return {"draft_answer": draft, "agent_trace": trace}
