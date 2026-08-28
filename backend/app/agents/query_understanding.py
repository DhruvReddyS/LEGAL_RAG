from __future__ import annotations

import re

from app.schemas.agents import AgentTraceEvent, QueryIntent
from app.services.llm import OllamaClient
from app.agents.role_profiles import profile_prompt, specialist_prompt


def _fallback_intent(query: str) -> QueryIntent:
    entities = re.findall(
        r"\b(?:section\s+\d+[A-Za-z]?|article\s+\d+[A-Za-z]?|IPC|BNS|CrPC|BNSS|BSA|POCSO|NDPS)\b",
        query,
        flags=re.IGNORECASE,
    )
    return QueryIntent(
        intent="legal_research",
        entities=list(dict.fromkeys(entities)),
        language="English",
        complexity="complex" if len(query.split()) > 25 or len(entities) > 1 else "simple",
        retrieval_query=query,
    )


async def query_understanding_node(state: dict, llm: OllamaClient) -> dict:
    history = "\n".join(
        f"{item['role']}: {item['content'][:1000]}" for item in state.get("history", [])[-8:]
    )
    prompt = f"""Analyze this legal research query. Return only JSON matching the supplied schema.
Identify the intent, legal entities (Acts, sections, cases), language, complexity, and a standalone
retrieval_query that resolves references from conversation history. Never answer the legal question.

{profile_prompt(state.get('role', 'citizen'))}
{specialist_prompt(state)}
Conversation history:
{history or '(none)'}

Current query: {state['query']}"""
    try:
        intent = await llm.structured(prompt, QueryIntent)
    except RuntimeError:
        intent = _fallback_intent(state["query"])
    trace = list(state.get("agent_trace", []))
    trace.append(
        AgentTraceEvent(
            node="query_understanding",
            details={
                "intent": intent.intent,
                "entities": intent.entities,
                "language": intent.language,
                "complexity": intent.complexity,
            },
        )
    )
    return {"intent": intent, "retrieval_query": intent.retrieval_query, "agent_trace": trace}
