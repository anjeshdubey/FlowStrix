"""
LangGraph Journey Executor — State machine-based execution engine.

This is the Phase 4 replacement for the synchronous while-loop executor.
Same interface (run() → ExecutionContext), but backed by LangGraph for:
- Persistent state (resume after HITL)
- Multi-turn conversations (same thread_id across invocations)
- Checkpointing (retry from last good state)

Design decisions:
- Strangler pattern: lives alongside the legacy executor
- Same API contract: run() returns ExecutionContext
- Thread-based persistence: same thread_id = same conversation
- HITL via graph interrupts: natural pause/resume semantics
"""

from __future__ import annotations

import uuid
from dataclasses import replace as dataclasses_replace
from pathlib import Path
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver

from flowstrix.engine.context import ExecutionContext, StepStatus, StepTrace
from flowstrix.engine.executor import ToolRegistry
from flowstrix.engine.graph import compile_journey_graph
from flowstrix.engine.nodes import NodeFactory
from flowstrix.engine.state import ExecutionState
from flowstrix.gateway import ChatGateway, GatewayConfig, resolve_chain, resolve_model
from flowstrix.knowledge.loader import KnowledgeLoader
from flowstrix.schema.models import AgentSpec, HandoffStep, Journey


class LangGraphExecutor:
    """Executes journeys using LangGraph state machines.

    Drop-in replacement for JourneyExecutor with the same interface.
    Adds: persistent state, multi-turn support, true HITL resume.

    Usage:
        spec = parse_yaml("agent.yaml")
        executor = LangGraphExecutor(spec, tool_registry)
        result = executor.run("handle_refund_request", user_message="I want a refund")

        # Resume after HITL:
        result = executor.resume(thread_id, approved=True)
    """

    def __init__(
        self,
        spec: AgentSpec,
        tools: ToolRegistry | None = None,
        model: str | None = None,
        gateway_config: GatewayConfig | None = None,
        knowledge_base_path: Optional[Path] = None,
        checkpointer: Any | None = None,
    ):
        self.spec = spec
        self.tools = tools or ToolRegistry()

        # Gateway setup — ChatGateway adds automatic provider fallback +
        # Upstash response caching on top of the resolved primary config.
        if gateway_config is None:
            gateway_config = GatewayConfig.from_env()
        if model:
            gateway_config = dataclasses_replace(
                gateway_config, model=resolve_model(model)
            )

        self.gateway = ChatGateway(resolve_chain(gateway_config))

        # Knowledge
        self.knowledge = KnowledgeLoader(spec, base_path=knowledge_base_path)

        # Checkpointer for state persistence
        self.checkpointer = checkpointer or MemorySaver()

        # Node factory (captures all dependencies)
        self.node_factory = NodeFactory(
            spec=spec,
            gateway=self.gateway,
            tools=self.tools,
            knowledge=self.knowledge,
        )

        # Track active threads for multi-turn (bounded to prevent memory leak)
        self._threads: dict[str, dict[str, Any]] = {}
        self._max_threads = 100  # Evict oldest when exceeded

    def run(
        self,
        journey_name: str,
        user_message: str | None = None,
        context_data: dict[str, Any] | None = None,
        thread_id: str | None = None,
        interaction_mode: str | None = None,
    ) -> ExecutionContext:
        """Execute a journey using LangGraph.

        If thread_id refers to a previously paused thread (waiting at a `wait`
        step), resumes execution with the new user_message injected. Otherwise
        starts a fresh execution.

        Args:
            journey_name: Which journey to run.
            user_message: Initial user message.
            context_data: Pre-populated context variables.
            thread_id: Thread ID for multi-turn (generates one if None).
            interaction_mode: 'conversational' | 'agent_driven' | 'structured'.
                Affects handoff step behavior.

        Returns:
            ExecutionContext with full trace and results.
        """
        journey = self._find_journey(journey_name)

        # Generate thread ID for this execution
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        # --- Multi-turn resume: if this thread is paused at a wait step, resume it ---
        if thread_id in self._threads and self._threads[thread_id].get(
            "waiting_for_input"
        ):
            return self._resume_from_wait(thread_id, user_message)

        # --- Fresh execution ---
        # Compile the journey into a graph
        compiled_graph = compile_journey_graph(
            journey=journey,
            node_factory=self.node_factory,
            checkpointer=self.checkpointer,
            interrupt_on_hitl=True,
        )

        # Initialize state
        initial_data = dict(context_data) if context_data else {}
        initial_messages: list[dict[str, str]] = []
        if user_message:
            initial_messages.append({"role": "user", "content": user_message})

        initial_state: ExecutionState = {
            "journey_name": journey_name,
            "agent_id": self.spec.agent,
            "data": initial_data,
            "messages": initial_messages,
            "traces": [],
            "current_step": journey.steps[0].name,
            "next_step": None,
            "status": "running",
            "waiting_for_human": False,
            "hitl_request": None,
            "handoff_form": None,
            "interaction_mode": interaction_mode or "agent_driven",
            "user_message": user_message,
            "steps_executed": [],
        }

        # Run the graph
        config = {"configurable": {"thread_id": thread_id}}

        try:
            # invoke() runs until completion or interrupt
            result_state = compiled_graph.invoke(initial_state, config=config)
        except Exception:
            # Graph execution failed
            ctx = self._state_to_context(initial_state)
            ctx.status = StepStatus.FAILED
            return ctx

        # Store thread info for potential resume (bounded)
        self._store_thread(thread_id, journey_name, compiled_graph, config)

        # Check if the graph was interrupted (HITL or Wait)
        return self._handle_interrupt(
            compiled_graph, config, result_state, journey, thread_id
        )

    def _resume_from_wait(
        self, thread_id: str, user_message: str | None
    ) -> ExecutionContext:
        """Resume a graph paused at a wait step with a new user message.

        Injects the new message into state, then continues the graph from
        where it left off.
        """
        thread_info = self._threads[thread_id]
        graph = thread_info["graph"]
        config = thread_info["config"]
        journey_name = thread_info["journey_name"]
        journey = self._find_journey(journey_name)

        # Inject the new user message into the graph state before resume
        update_state = {"user_message": user_message}
        graph.update_state(config, update_state)

        # Resume from the interrupt point (invoke with None continues)
        try:
            result_state = graph.invoke(None, config=config)
        except Exception:
            ctx = ExecutionContext(
                journey_name=journey_name,
                agent_id=self.spec.agent,
            )
            ctx.status = StepStatus.FAILED
            return ctx

        # Update thread info (no longer waiting for input unless it hits another wait)
        self._threads[thread_id]["waiting_for_input"] = False

        # Check for new interrupts (could hit another wait or HITL)
        return self._handle_interrupt(graph, config, result_state, journey, thread_id)

    def _handle_interrupt(
        self,
        compiled_graph: Any,
        config: dict,
        result_state: Any,
        journey: Journey,
        thread_id: str,
    ) -> ExecutionContext:
        """Check if graph was interrupted (HITL or Wait) and set state accordingly."""

        graph_state = compiled_graph.get_state(config)
        if graph_state.next:
            # Graph has pending nodes — it was interrupted
            pending_node = graph_state.next[0] if graph_state.next else None

            # Check if it's a Handoff step
            handoff_step = self._find_handoff_step(journey, pending_node)
            if handoff_step:
                # Handoff interrupts before the node runs, so we need to
                # determine if it WOULD trigger based on current state + mode
                from flowstrix.engine.nodes import _resolve_expression

                interaction_mode = result_state.get("interaction_mode", "agent_driven")
                if interaction_mode == "structured":
                    should_handoff = True
                elif interaction_mode == "conversational":
                    should_handoff = False
                else:
                    should_handoff = _resolve_expression(
                        result_state.get("data", {}), handoff_step.trigger_condition
                    )

                if should_handoff:
                    # Build form spec — same logic as the node, but pre-interrupt
                    prefilled: dict[str, Any] = {}
                    for field_id, ctx_key in handoff_step.prefill_from_context.items():
                        value = result_state.get("data", {}).get(ctx_key)
                        if value:
                            prefilled[field_id] = value

                    form_spec = {
                        "step_name": handoff_step.name,
                        "transition_message": handoff_step.transition_message,
                        "output_key": handoff_step.output_key,
                        "fields": [
                            {
                                "id": f.id,
                                "label": f.label,
                                "field_type": f.field_type,
                                "required": f.required,
                                "options": f.options,
                                "placeholder": f.placeholder,
                                "validation": f.validation,
                                "prefilled_value": prefilled.get(f.id),
                            }
                            for f in handoff_step.fields
                        ],
                    }

                    result_state = dict(result_state)  # Make mutable copy
                    result_state["waiting_for_human"] = True
                    result_state["status"] = "waiting_handoff"
                    result_state["handoff_form"] = form_spec
                    result_state["messages"] = list(
                        result_state.get("messages", [])
                    ) + [
                        {
                            "role": "assistant",
                            "content": handoff_step.transition_message,
                        }
                    ]
            else:
                # Check if it's a HITL step
                hitl_step = self._find_hitl_step(journey, pending_node)
                if hitl_step:
                    from flowstrix.engine.nodes import _resolve_expression

                    should_escalate = _resolve_expression(
                        result_state.get("data", {}), hitl_step.condition
                    )
                    if should_escalate:
                        result_state = dict(result_state)  # Make mutable copy
                        result_state["waiting_for_human"] = True
                        result_state["status"] = "waiting_hitl"
                        result_state["hitl_request"] = {
                            "escalation_type": hitl_step.escalation_type.value,
                            "escalate_to": hitl_step.escalate_to,
                            "context": {
                                k: result_state.get("data", {}).get(k)
                                for k in hitl_step.context_to_share
                            },
                            "step_name": hitl_step.name,
                        }

            # Check if it's a Wait interrupt (multi-turn pause)
            wait_step = self._find_wait_step(journey, pending_node)
            if wait_step:
                result_state = dict(result_state)  # Make mutable copy
                result_state["status"] = "waiting_input"
                # Mark the thread as waiting for user input
                if thread_id in self._threads:
                    self._threads[thread_id]["waiting_for_input"] = True

        # Convert LangGraph state → ExecutionContext
        ctx = self._state_to_context(result_state)
        ctx.thread_id = thread_id
        return ctx

    def resume(
        self,
        thread_id: str,
        approved: bool = True,
        notes: str | None = None,
    ) -> ExecutionContext:
        """Resume a HITL-paused execution.

        Args:
            thread_id: The thread that was interrupted.
            approved: Whether the human approved the action.
            notes: Optional notes from the approver.

        Returns:
            ExecutionContext with the continued execution result.
        """
        if thread_id not in self._threads:
            raise ValueError(f"Thread '{thread_id}' not found. Cannot resume.")

        thread_info = self._threads[thread_id]
        graph = thread_info["graph"]
        config = thread_info["config"]
        journey_name = thread_info["journey_name"]
        journey = self._find_journey(journey_name)

        # Update state to reflect human decision
        update_state = {
            "waiting_for_human": False,
            "status": "running",
            "data": {"hitl_approved": approved, "hitl_notes": notes or ""},
        }

        # Resume the graph from the interrupt point
        try:
            graph.update_state(config, update_state)
            result_state = graph.invoke(None, config=config)
        except Exception:
            # Resume failed
            ctx = ExecutionContext(
                journey_name=journey_name,
                agent_id=self.spec.agent,
            )
            ctx.status = StepStatus.FAILED
            return ctx

        # Check for further interrupts (e.g., hits a wait step after HITL)
        return self._handle_interrupt(graph, config, result_state, journey, thread_id)

    def _store_thread(
        self,
        thread_id: str,
        journey_name: str,
        compiled_graph: Any,
        config: dict,
    ):
        """Store thread info for potential resume (bounded to _max_threads)."""
        if len(self._threads) >= self._max_threads:
            # Evict oldest thread
            oldest_key = next(iter(self._threads))
            del self._threads[oldest_key]

        self._threads[thread_id] = {
            "journey_name": journey_name,
            "graph": compiled_graph,
            "config": config,
            "waiting_for_input": False,
        }

    def resume_handoff(
        self,
        thread_id: str,
        form_data: dict[str, Any],
    ) -> ExecutionContext:
        """Resume after a handoff form submission.

        When a handoff step interrupts execution, the UI collects structured
        form data from the user. This method injects that data back into the
        graph state and resumes execution from the interrupt point.

        Args:
            thread_id: The thread that was interrupted at a handoff step.
            form_data: The submitted form fields (field_id → value).

        Returns:
            ExecutionContext with the continued execution result.
        """
        if thread_id not in self._threads:
            raise ValueError(f"Thread '{thread_id}' not found. Cannot resume handoff.")

        thread_info = self._threads[thread_id]
        graph = thread_info["graph"]
        config = thread_info["config"]

        # Get the current graph state to find the output_key
        graph_state = graph.get_state(config)
        current_state = graph_state.values if graph_state.values else {}

        # Determine the output_key from the handoff_form spec
        handoff_form = current_state.get("handoff_form")
        output_key = (
            handoff_form.get("output_key", "handoff_data")
            if handoff_form
            else "handoff_data"
        )

        # Build the state update: inject form data under the output_key,
        # clear handoff state, and mark as running again
        merged_data = dict(current_state.get("data", {}))
        merged_data[output_key] = form_data
        # Also flatten individual fields into context for downstream ${field_id} references
        for field_id, value in form_data.items():
            merged_data[field_id] = value

        # The handoff node name is the pending node (interrupted before it)
        handoff_node_name = graph_state.next[0] if graph_state.next else None

        # Record the handoff step in traces and steps_executed
        traces = list(current_state.get("traces", []))
        traces.append(
            {
                "step_name": handoff_node_name or "handoff",
                "step_type": "handoff",
                "status": "completed",
                "output": "form submitted",
                "duration_ms": 0,
            }
        )
        steps_executed = list(current_state.get("steps_executed", []))
        if handoff_node_name:
            steps_executed.append(handoff_node_name)

        update_state = {
            "waiting_for_human": False,
            "status": "running",
            "handoff_form": None,
            "data": merged_data,
            "traces": traces,
            "steps_executed": steps_executed,
        }

        # Use as_node to tell LangGraph "this update acts as if the handoff node
        # already ran." This advances the graph past the interrupt point so
        # invoke(None) continues to the NEXT node instead of re-hitting the interrupt.
        try:
            graph.update_state(config, update_state, as_node=handoff_node_name)
            result_state = graph.invoke(None, config=config)
        except Exception:
            # Resume failed
            ctx = ExecutionContext(
                journey_name=thread_info["journey_name"],
                agent_id=self.spec.agent,
            )
            ctx.status = StepStatus.FAILED
            return ctx

        journey_name = thread_info["journey_name"]
        journey = self._find_journey(journey_name)
        return self._handle_interrupt(graph, config, result_state, journey, thread_id)

    def _find_journey(self, name: str) -> Journey:
        """Find a journey by name in the spec."""
        for j in self.spec.journeys:
            if j.name == name:
                return j
        available = [j.name for j in self.spec.journeys]
        raise ValueError(f"Journey '{name}' not found. Available: {available}")

    def _find_hitl_step(self, journey: Journey, step_name: str | None):
        """Find a HITL step by name in the journey."""
        if not step_name:
            return None
        from flowstrix.schema.models import HITLStep

        for step in journey.steps:
            if step.name == step_name and isinstance(step, HITLStep):
                return step
        return None

    def _find_wait_step(self, journey: Journey, step_name: str | None):
        """Find a Wait step by name in the journey."""
        if not step_name:
            return None
        from flowstrix.schema.models import WaitStep as WaitStepModel

        for step in journey.steps:
            if step.name == step_name and isinstance(step, WaitStepModel):
                return step
        return None

    def _find_handoff_step(self, journey: Journey, step_name: str | None):
        """Find a Handoff step by name in the journey."""
        if not step_name:
            return None
        for step in journey.steps:
            if step.name == step_name and isinstance(step, HandoffStep):
                return step
        return None

    def _state_to_context(self, state: ExecutionState) -> ExecutionContext:
        """Convert LangGraph state to ExecutionContext.

        This is the bridge that keeps the rest of FlowStrix (CLI, API, simulator)
        working without changes — they only interact with ExecutionContext.
        """
        # Map status string to enum
        status_map = {
            "running": StepStatus.RUNNING,
            "completed": StepStatus.COMPLETED,
            "failed": StepStatus.FAILED,
            "waiting_hitl": StepStatus.WAITING_HITL,
            "waiting_input": StepStatus.COMPLETED,  # From caller's perspective, turn is done
            "waiting_handoff": StepStatus.WAITING_HITL,  # Reuse HITL status for handoff pause
        }

        ctx = ExecutionContext(
            journey_name=state.get("journey_name", ""),
            agent_id=state.get("agent_id", ""),
        )

        # Populate data
        for k, v in state.get("data", {}).items():
            ctx.set(k, v)

        # Populate messages
        for msg in state.get("messages", []):
            ctx.add_message(msg["role"], msg["content"])

        # Convert traces
        for trace_entry in state.get("traces", []):
            trace = StepTrace(
                step_name=trace_entry["step_name"],
                step_type=trace_entry["step_type"],
                status=(
                    StepStatus.COMPLETED
                    if trace_entry["status"] == "completed"
                    else StepStatus.FAILED
                ),
                started_at=0,  # Not tracked in graph state (simplification)
                completed_at=0,
                output=trace_entry.get("output"),
                error=trace_entry.get("error"),
                duration_ms=trace_entry.get("duration_ms"),
                llm_usage=trace_entry.get("llm_usage"),
            )
            ctx.traces.append(trace)

        # Set status
        ctx.status = status_map.get(
            state.get("status", "completed"), StepStatus.COMPLETED
        )

        # HITL state
        ctx.waiting_for_human = state.get("waiting_for_human", False)
        ctx.hitl_request = state.get("hitl_request")

        # Handoff form state
        ctx.handoff_form = state.get("handoff_form")

        return ctx
