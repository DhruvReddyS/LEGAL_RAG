from __future__ import annotations

from langgraph.graph import END, StateGraph
from time import perf_counter

from app.agents.query_understanding import query_understanding_node
from app.agents.reasoning_agent import reasoning_node
from app.agents.response_generation import response_generation_node
from app.agents.retrieval_agent import retrieval_node
from app.agents.state import AgentState
from app.agents.verification_agent import verification_node
from app.services.llm import OllamaClient
from app.services.retrieval import HybridRetrievalService
from app.agents.role_profiles import get_role_profile, select_specialist_agent
from app.schemas.agents import AgentTraceEvent


class LegalRAGWorkflow:
    """Bounded, dependency-injected LangGraph workflow for verified legal answers."""

    def __init__(self, retrieval: HybridRetrievalService, llm: OllamaClient | None = None) -> None:
        self.retrieval = retrieval
        self.llm = llm or OllamaClient()
        graph = StateGraph(AgentState)
        graph.add_node("role_context", self._role_context)
        graph.add_node("query_understanding", self._understand)
        graph.add_node("retrieval", self._retrieve)
        graph.add_node("reasoning", self._reason)
        graph.add_node("verification", self._verify)
        graph.add_node("retry", self._retry)
        graph.add_node("response_generation", self._respond)
        graph.set_entry_point("role_context")
        graph.add_edge("role_context", "query_understanding")
        graph.add_edge("query_understanding", "retrieval")
        graph.add_edge("retrieval", "reasoning")
        graph.add_edge("reasoning", "verification")
        graph.add_conditional_edges(
            "verification",
            self._route_after_verification,
            {"retry": "retry", "proceed": "response_generation"},
        )
        graph.add_edge("retry", "retrieval")
        graph.add_edge("response_generation", END)
        self.graph = graph.compile()

    @staticmethod
    def _role_context(state: AgentState) -> dict:
        profile = get_role_profile(state.get("role", "citizen"))
        specialist = select_specialist_agent(
            profile.role,
            state.get("query", ""),
            state.get("case_id"),
        )
        trace = list(state.get("agent_trace", []))
        trace.append(
            AgentTraceEvent(
                node="role_context",
                details={
                    "role": profile.role,
                    "agent_label": profile.label,
                    "specialist_agent_id": specialist.id,
                    "specialist_agent_label": specialist.label,
                    "case_scoped": bool(state.get("case_id")),
                    "objective": profile.objective,
                    "safety_boundary": profile.safety_boundary,
                },
            )
        )
        return {
            "specialist_agent_id": specialist.id,
            "specialist_agent_label": specialist.label,
            "specialist_agent_objective": specialist.objective,
            "agent_trace": trace,
        }

    async def _understand(self, state: AgentState) -> dict:
        started = perf_counter()
        result = await query_understanding_node(state, self.llm)
        return {**result, "timings": {**state.get("timings", {}), "query_understanding_ms": round((perf_counter() - started) * 1000, 2)}}

    async def _retrieve(self, state: AgentState) -> dict:
        return await retrieval_node(state, self.retrieval)

    async def _reason(self, state: AgentState) -> dict:
        started = perf_counter()
        result = await reasoning_node(state, self.llm)
        return {**result, "timings": {**state.get("timings", {}), "reasoning_ms": round((perf_counter() - started) * 1000, 2)}}

    async def _verify(self, state: AgentState) -> dict:
        started = perf_counter()
        result = await verification_node(state, self.llm)
        return {**result, "timings": {**state.get("timings", {}), "verification_ms": round((perf_counter() - started) * 1000, 2)}}

    @staticmethod
    def _respond(state: AgentState) -> dict:
        started = perf_counter()
        result = response_generation_node(state)
        return {**result, "timings": {**state.get("timings", {}), "response_generation_ms": round((perf_counter() - started) * 1000, 2)}}

    @staticmethod
    def _retry(state: AgentState) -> dict:
        return {"retry_count": int(state.get("retry_count", 0)) + 1}

    @staticmethod
    def _route_after_verification(state: AgentState) -> str:
        return "retry" if state["verification_result"].score < 0.5 and int(state.get("retry_count", 0)) < 2 else "proceed"

    async def run(self, *, query: str, role: str, case_id: str | None, history: list[dict[str, str]]) -> AgentState:
        return await self.graph.ainvoke(
            AgentState(
                query=query,
                role=role,
                case_id=case_id,
                history=history[-8:],
                retry_count=0,
                agent_trace=[],
                timings={},
            )
        )
