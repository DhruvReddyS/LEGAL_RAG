from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Awaitable, Callable
from langgraph.graph import END, StateGraph
from time import perf_counter, perf_counter_ns

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
from app.services.pipeline_telemetry import append_stage_metric, text_size


ProgressCallback = Callable[[str, str, dict], Awaitable[None]]
_progress_callback: ContextVar[ProgressCallback | None] = ContextVar(
    "legal_rag_progress_callback", default=None
)


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
        # A retry that rediscovers the same evidence cannot change the
        # answer, so the expensive stages are skipped rather than repeated.
        graph.add_conditional_edges(
            "retrieval",
            self._route_after_retrieval,
            {"reason": "reasoning", "skip": "response_generation"},
        )
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
    async def _notify(stage: str, transition: str, data: dict | None = None) -> None:
        callback = _progress_callback.get()
        if callback is not None:
            await callback(stage, transition, data or {})

    @staticmethod
    def _role_context(state: AgentState) -> dict:
        started_ns = perf_counter_ns()
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
        stage_metrics = append_stage_metric(
            state,
            stage="role_context",
            started_ns=started_ns,
            inputs={
                "query": text_size(str(state.get("query") or "")),
                "history_messages": len(state.get("history", [])),
                "case_scoped": bool(state.get("case_id")),
            },
            outputs={
                "role": profile.role,
                "specialist_agent_id": specialist.id,
            },
        )
        return {
            "specialist_agent_id": specialist.id,
            "specialist_agent_label": specialist.label,
            "specialist_agent_objective": specialist.objective,
            "agent_trace": trace,
            "stage_metrics": stage_metrics,
        }

    async def _understand(self, state: AgentState) -> dict:
        await self._notify("query_understanding", "started")
        started = perf_counter()
        result = await query_understanding_node(state, self.llm)
        await self._notify("query_understanding", "completed")
        return {**result, "timings": {**state.get("timings", {}), "query_understanding_ms": round((perf_counter() - started) * 1000, 2)}}

    async def _retrieve(self, state: AgentState) -> dict:
        await self._notify("retrieval", "started")
        result = await retrieval_node(state, self.retrieval)
        await self._notify(
            "retrieval",
            "completed",
            {"candidate_count": len(result.get("retrieved_chunks", []))},
        )
        return result

    async def _reason(self, state: AgentState) -> dict:
        await self._notify("reasoning", "started")
        started = perf_counter()
        result = await reasoning_node(state, self.llm)
        await self._notify("reasoning", "completed")
        retry_index = int(state.get("retry_count", 0))
        return {**result, "timings": {**state.get("timings", {}), f"reasoning_{retry_index}_ms": round((perf_counter() - started) * 1000, 2)}}

    async def _verify(self, state: AgentState) -> dict:
        await self._notify("verification", "started")
        started = perf_counter()
        result = await verification_node(state, self.llm)
        verification = result.get("verification_result")
        await self._notify(
            "verification",
            "completed",
            {"score": verification.score if verification is not None else None},
        )
        retry_index = int(state.get("retry_count", 0))
        return {**result, "timings": {**state.get("timings", {}), f"verification_{retry_index}_ms": round((perf_counter() - started) * 1000, 2)}}

    async def _respond(self, state: AgentState) -> dict:
        await self._notify("response_generation", "started")
        started = perf_counter()
        result = response_generation_node(state)
        await self._notify(
            "response_generation",
            "completed",
            {"citation_count": len(result.get("citations", []))},
        )
        return {**result, "timings": {**state.get("timings", {}), "response_generation_ms": round((perf_counter() - started) * 1000, 2)}}

    @staticmethod
    def _retry(state: AgentState) -> dict:
        started_ns = perf_counter_ns()
        next_retry = int(state.get("retry_count", 0)) + 1
        return {
            "retry_count": next_retry,
            # Carried forward so the next verification can tell whether the
            # broadened query actually found anything new.
            "previous_retrieval_signature": state.get("retrieval_signature", ()),
            "stage_metrics": append_stage_metric(
                state,
                stage="retry",
                started_ns=started_ns,
                retry_index=next_retry,
                inputs={"previous_verification_score": state["verification_result"].score},
                outputs={"next_retry_index": next_retry},
            ),
        }

    @staticmethod
    def _route_after_verification(state: AgentState) -> str:
        """Retry only when a retry can still change something.

        The loop is bounded at two, but a bound is not the same as progress. A
        broadened query that returns the evidence the previous pass already saw
        will, at temperature 0.0, produce the same claims and the same verdicts.
        A measured run spent 84 seconds - a quarter of its total - re-deriving a
        byte-identical result before abstaining anyway.
        """
        if state["verification_result"].score >= 0.5:
            return "proceed"
        if int(state.get("retry_count", 0)) >= 2:
            return "proceed"
        return "retry"

    @staticmethod
    def _route_after_retrieval(state: AgentState) -> str:
        """Skip re-deriving an answer from evidence already seen.

        The retry broadens the query, but a broadened query often returns the
        same passages. Generation runs at temperature 0.0, so identical evidence
        yields identical claims and identical verdicts. A measured run spent 70
        seconds on reasoning and verification to reproduce a result it already
        had, then abstained on it anyway.

        The check has to sit here rather than at the verification branch: until
        the retry's retrieval has actually run, there is no way to know whether
        it found anything new. The previous pass's verification_result stays in
        state and remains valid, because it was computed over this same
        evidence.
        """
        if not int(state.get("retry_count", 0)):
            return "reason"
        if state.get("verification_result") is None:
            return "reason"
        signature = state.get("retrieval_signature", ())
        if signature and signature == state.get("previous_retrieval_signature"):
            return "skip"
        return "reason"

    async def run(
        self,
        *,
        query: str,
        role: str,
        case_id: str | None,
        history: list[dict[str, str]],
        progress_callback: ProgressCallback | None = None,
        document_context: str = "",
    ) -> AgentState:
        workflow_started_ns = perf_counter_ns()
        run_id = str(uuid.uuid4())
        initial_state = AgentState(
            query=query,
            document_context=document_context,
            role=role,
            case_id=case_id,
            history=history[-8:],
            retry_count=0,
            agent_trace=[],
            timings={},
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            stage_metrics=[],
        )
        callback_token = _progress_callback.set(progress_callback)
        try:
            result = await self.graph.ainvoke(initial_state)
        except Exception as exc:
            append_stage_metric(
                initial_state,
                stage="workflow_total",
                started_ns=workflow_started_ns,
                inputs={
                    "query": text_size(query),
                    "history_messages": len(history[-8:]),
                    "role": role,
                    "case_scoped": bool(case_id),
                },
                outputs={"completed": False, "error_type": type(exc).__name__},
            )
            raise
        finally:
            _progress_callback.reset(callback_token)
        result["stage_metrics"] = append_stage_metric(
            result,
            stage="workflow_total",
            started_ns=workflow_started_ns,
            retry_index=int(result.get("retry_count", 0)),
            inputs={
                "query": text_size(query),
                "history_messages": len(history[-8:]),
                "role": role,
                "case_scoped": bool(case_id),
            },
            outputs={
                "completed": True,
                "citation_count": len(result.get("citations", [])),
                "retry_count": int(result.get("retry_count", 0)),
                "evidence_strength": result.get("evidence_strength"),
            },
        )
        result["timings"] = {
            **result.get("timings", {}),
            "workflow_total_ms": result["stage_metrics"][-1]["duration_ms"],
        }
        return result
