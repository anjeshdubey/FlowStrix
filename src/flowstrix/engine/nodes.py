"""
LangGraph Node Functions — One function per step type.

Each node takes ExecutionState, performs its operation, and returns
a partial state update. Deterministic nodes never touch the LLM.
Probabilistic nodes (reason, respond) go through the ChatGateway
(provider fallback + Upstash response caching).

Architecture:
- Nodes are pure functions (state in → partial state out)
- Side effects (LLM calls, tool invocations) happen inside nodes
- The graph wiring (edges, branches) is in graph.py
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from flowstrix.engine.state import ExecutionState, StepTraceEntry
from flowstrix.gateway import ChatGateway
from flowstrix.schema.models import (
    AgentSpec,
    BranchStep,
    HandoffStep,
    HITLStep,
    LookupStep,
    ReasonStep,
    RespondStep,
    ToolStep,
    WaitStep,
)


def _make_trace(
    step_name: str,
    step_type: str,
    output: Any = None,
    error: str | None = None,
    duration_ms: float | None = None,
) -> StepTraceEntry:
    """Create a trace entry."""
    return StepTraceEntry(
        step_name=step_name,
        step_type=step_type,
        status="failed" if error else "completed",
        output=output,
        error=error,
        duration_ms=duration_ms,
    )


def _resolve_expression(data: dict[str, Any], expr: str) -> Any:
    """Resolve a ${key} expression against state data.

    Duplicates ExecutionContext.resolve_expression logic for use in graph nodes.
    """
    if expr.strip().lower() == "always":
        return True

    # Simple key reference: ${key}
    if expr.startswith("${") and expr.endswith("}"):
        key = expr[2:-1]
        return data.get(key)

    # Expression with comparison operators
    match = re.match(r"\$\{(\w+)\}\s*(>|<|>=|<=|==|!=)\s*(.+)", expr)
    if match:
        key, op, value = match.groups()
        left = data.get(key)
        if left is None:
            return False

        # Try numeric comparison
        try:
            right = float(value.strip())
            left = float(left)
        except (ValueError, TypeError):
            right = value.strip().strip("\"'")

        ops = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        return ops[op](left, right)

    # Boolean context key (no ${} wrapper)
    if expr in data:
        return bool(data[expr])

    return False


def _resolve_params(params: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Resolve ${} references in tool parameters."""
    resolved = {}
    for k, v in params.items():
        if isinstance(v, str) and "${" in v:

            def replace_ref(m: re.Match) -> str:
                key = m.group(1)
                return str(data.get(key, ""))

            resolved[k] = re.sub(r"\$\{(\w+)\}", replace_ref, v)
        else:
            resolved[k] = v
    return resolved


def _parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response, handling markdown code fences."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return text


class NodeFactory:
    """Factory that creates LangGraph node functions bound to runtime dependencies.

    Nodes need access to: LLM client, model name, tool registry, knowledge loader,
    and the agent spec. This factory captures those dependencies and returns
    clean node functions that only take state.
    """

    def __init__(
        self,
        spec: AgentSpec,
        gateway: ChatGateway,
        tools: Any,  # ToolRegistry
        knowledge: Any,  # KnowledgeLoader
    ):
        self.spec = spec
        self.gateway = gateway
        self.tools = tools
        self.knowledge = knowledge

    def _build_system_prompt(self) -> str:
        """Build system prompt from persona spec."""
        persona = self.spec.persona
        parts = [
            f"You are {persona.name}. {persona.description}",
            f"Tone: {persona.tone}",
        ]
        if persona.guardrails:
            parts.append("## Guardrails (MUST follow)")
            for g in persona.guardrails:
                parts.append(f"- {g}")
        if persona.off_limits:
            parts.append("## Off-Limits Topics (REFUSE these)")
            for t in persona.off_limits:
                parts.append(f"- {t}")
        return "\n".join(parts)

    def _build_context_block(
        self,
        data: dict[str, Any],
        messages: list[dict[str, str]],
        knowledge_ids: list[str],
        query: str = "",
    ) -> str:
        """Build context block from state data + knowledge sources."""
        parts = []

        if data:
            parts.append("### Execution Context")
            for k, v in data.items():
                parts.append(f"- {k}: {json.dumps(v) if not isinstance(v, str) else v}")

        if messages:
            parts.append("### Conversation History")
            parts.append(
                "\n".join(f"{m['role']}: {m['content']}" for m in messages[-5:])
            )

        if knowledge_ids:
            parts.append("### Relevant Knowledge")
            if query and any(self.knowledge.is_ingested(kid) for kid in knowledge_ids):
                knowledge_content = self.knowledge.retrieve(
                    query=query, knowledge_ids=knowledge_ids, top_k=3
                )
            else:
                knowledge_content = self.knowledge.load_multiple(knowledge_ids)
            parts.append(knowledge_content)

        return "\n".join(parts)

    def make_lookup_node(self, step: LookupStep) -> Callable[[ExecutionState], dict]:
        """Create a node function for a lookup step."""

        def node(state: ExecutionState) -> dict:
            start = time.time()
            try:
                resolved_params = _resolve_params(step.params, state["data"])
                result = self.tools.invoke(step.tool, resolved_params)
                data = {**state["data"], step.output_key: result}
                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name, "lookup", output=result, duration_ms=duration
                )
                return {
                    "data": data,
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }
            except Exception as e:
                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name, "lookup", error=str(e), duration_ms=duration
                )
                update: dict[str, Any] = {
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }
                if step.on_failure:
                    update["next_step"] = step.on_failure
                return update

        return node

    def make_reason_node(self, step: ReasonStep) -> Callable[[ExecutionState], dict]:
        """Create a node function for a reason step."""

        def node(state: ExecutionState) -> dict:
            start = time.time()
            system_prompt = self._build_system_prompt()

            # Build RAG query
            rag_query = step.prompt
            if state["messages"]:
                rag_query = f"{state['messages'][-1].get('content', '')} {step.prompt}"

            context_block = self._build_context_block(
                state["data"], state["messages"], step.knowledge, query=rag_query
            )

            user_prompt = f"""## Task
{step.prompt}

## Available Context
{context_block}
"""
            if step.output_schema:
                user_prompt += f"""
## Required Output Format
Respond ONLY with valid JSON (no markdown fences, no explanation). Match this schema:
{json.dumps(step.output_schema, indent=2)}
"""

            result_text = self.gateway.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=step.temperature,
                max_tokens=step.max_tokens,
            )
            if step.output_schema:
                result = _parse_json_response(result_text)
            else:
                result = result_text

            # Update data — store result + flatten dict keys
            data = {**state["data"], step.output_key: result}
            if isinstance(result, dict):
                for k, v in result.items():
                    data[k] = v

            duration = (time.time() - start) * 1000
            trace = _make_trace(
                step.name, "reason", output=result, duration_ms=duration
            )
            return {
                "data": data,
                "traces": state["traces"] + [trace],
                "steps_executed": state["steps_executed"] + [step.name],
            }

        return node

    def make_respond_node(self, step: RespondStep) -> Callable[[ExecutionState], dict]:
        """Create a node function for a respond step."""

        def node(state: ExecutionState) -> dict:
            start = time.time()
            system_prompt = self._build_system_prompt()

            context_parts = []
            for key in step.include_context:
                val = state["data"].get(key)
                if val:
                    context_parts.append(f"{key}: {val}")

            msg_history = "\n".join(
                f"{m['role']}: {m['content']}" for m in state["messages"]
            )

            user_prompt = f"""Generate a response to the user.

## Instruction
{step.prompt}

## Context
{chr(10).join(context_parts) if context_parts else 'No additional context.'}

## Conversation History
{msg_history}
"""
            if step.tone:
                user_prompt += f"\n## Tone\n{step.tone}\n"

            result = self.gateway.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            messages = state["messages"] + [{"role": "assistant", "content": result}]

            duration = (time.time() - start) * 1000
            trace = _make_trace(
                step.name, "respond", output=result, duration_ms=duration
            )
            return {
                "messages": messages,
                "traces": state["traces"] + [trace],
                "steps_executed": state["steps_executed"] + [step.name],
            }

        return node

    def make_branch_node(self, step: BranchStep) -> Callable[[ExecutionState], dict]:
        """Create a node function for a branch step.

        The branch node evaluates the condition and sets `next_step` to the
        appropriate target. The actual routing is done by a conditional edge
        in the graph wiring (graph.py).
        """

        def node(state: ExecutionState) -> dict:
            start = time.time()
            condition_result = _resolve_expression(state["data"], step.condition)
            target = step.if_true if condition_result else step.if_false

            duration = (time.time() - start) * 1000
            trace = _make_trace(
                step.name,
                "branch",
                output=f"branched to: {target}",
                duration_ms=duration,
            )
            return {
                "next_step": target,
                "traces": state["traces"] + [trace],
                "steps_executed": state["steps_executed"] + [step.name],
            }

        return node

    def make_hitl_node(self, step: HITLStep) -> Callable[[ExecutionState], dict]:
        """Create a node function for a HITL step.

        If the condition is met, sets waiting_for_human=True and status=waiting_hitl.
        The graph uses an interrupt_before on HITL nodes to pause execution.
        """

        def node(state: ExecutionState) -> dict:
            start = time.time()
            should_escalate = _resolve_expression(state["data"], step.condition)

            if should_escalate:
                hitl_request = {
                    "escalation_type": step.escalation_type.value,
                    "escalate_to": step.escalate_to,
                    "context": {k: state["data"].get(k) for k in step.context_to_share},
                    "step_name": step.name,
                }
                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name, "hitl", output="escalated to human", duration_ms=duration
                )
                return {
                    "waiting_for_human": True,
                    "hitl_request": hitl_request,
                    "status": "waiting_hitl",
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }
            else:
                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name,
                    "hitl",
                    output="condition not met, continuing",
                    duration_ms=duration,
                )
                return {
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }

        return node

    def make_tool_node(self, step: ToolStep) -> Callable[[ExecutionState], dict]:
        """Create a node function for a tool step."""

        def node(state: ExecutionState) -> dict:
            start = time.time()
            try:
                resolved_params = _resolve_params(step.params, state["data"])
                result = self.tools.invoke(step.tool, resolved_params)
                data = {**state["data"]}
                if step.output_key:
                    data[step.output_key] = result

                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name, "tool", output=result, duration_ms=duration
                )
                return {
                    "data": data,
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }
            except Exception as e:
                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name, "tool", error=str(e), duration_ms=duration
                )
                update: dict[str, Any] = {
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }
                if step.on_failure:
                    update["next_step"] = step.on_failure
                return update

        return node

    def make_wait_node(self, step: WaitStep) -> Callable[[ExecutionState], dict]:
        """Create a node function for a wait step.

        Wait nodes interrupt execution (via interrupt_before in graph.py).
        When resumed, the executor injects the new user_message into state
        before the graph continues. This node just records the trace and
        passes through — the actual pause happens at the graph level.
        """

        def node(state: ExecutionState) -> dict:
            start = time.time()
            # When this node actually runs (after resume), the new user_message
            # has been injected into state. Add it to the messages list.
            updates: dict = {}
            user_msg = state.get("user_message")
            if user_msg:
                updates["messages"] = state["messages"] + [
                    {"role": "user", "content": user_msg}
                ]

            duration = (time.time() - start) * 1000
            trace = _make_trace(
                step.name, "wait", output="resumed", duration_ms=duration
            )
            updates["traces"] = state["traces"] + [trace]
            updates["steps_executed"] = state["steps_executed"] + [step.name]
            return updates

        return node

    def make_handoff_node(self, step: HandoffStep) -> Callable[[ExecutionState], dict]:
        """Create a node for a handoff step.

        Evaluates trigger condition (respects interaction_mode override).
        If triggered, pauses execution and emits a form spec for the UI to render inline.
        Reuses the HITL interrupt mechanism — same pause/resume pattern.
        """

        def node(state: ExecutionState) -> dict:
            start = time.time()

            # Interaction mode can override the trigger condition
            interaction_mode = state.get("interaction_mode", "agent_driven")
            if interaction_mode == "structured":
                should_handoff = True
            elif interaction_mode == "conversational":
                should_handoff = False
            else:
                # agent_driven: use the step's trigger_condition
                should_handoff = _resolve_expression(
                    state["data"], step.trigger_condition
                )

            if should_handoff:
                # Pre-fill fields from context
                prefilled: dict[str, Any] = {}
                for field_id, ctx_key in step.prefill_from_context.items():
                    value = state["data"].get(ctx_key)
                    if value:
                        prefilled[field_id] = value

                # Build form spec for the UI
                form_spec: dict[str, Any] = {
                    "step_name": step.name,
                    "transition_message": step.transition_message,
                    "output_key": step.output_key,
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
                        for f in step.fields
                    ],
                }

                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name, "handoff", output="form surfaced", duration_ms=duration
                )

                # Add transition message to conversation
                messages = state["messages"] + [
                    {"role": "assistant", "content": step.transition_message}
                ]

                return {
                    "waiting_for_human": True,
                    "handoff_form": form_spec,
                    "status": "waiting_handoff",
                    "messages": messages,
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }
            else:
                # Condition not met — skip handoff, continue conversationally
                duration = (time.time() - start) * 1000
                trace = _make_trace(
                    step.name,
                    "handoff",
                    output="condition not met, staying conversational",
                    duration_ms=duration,
                )
                return {
                    "traces": state["traces"] + [trace],
                    "steps_executed": state["steps_executed"] + [step.name],
                }

        return node
