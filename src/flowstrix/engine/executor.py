"""
FlowStrix Journey Executor — Runs agent workflows step by step.

This is the runtime engine. It takes a parsed AgentSpec + Journey and
executes it, managing context, LLM calls, tool invocations, and HITL gates.

Architecture notes:
- Each step type has a dedicated handler
- LLM calls go through a unified interface (swappable models)
- HITL checkpoints pause execution and return control to the caller
- Every step produces a trace for auditability
- Deterministic steps (lookup, branch, tool) never touch the LLM
- Probabilistic steps (reason, respond) always go through the LLM
"""

from __future__ import annotations

import json
from dataclasses import replace as dataclasses_replace
from pathlib import Path
from typing import Any, Callable, Optional

from flowstrix.engine.context import ExecutionContext, StepStatus
from flowstrix.gateway import ChatGateway, GatewayConfig, resolve_chain, resolve_model
from flowstrix.knowledge.loader import KnowledgeLoader
from flowstrix.schema.models import (
    AgentSpec,
    BranchStep,
    HITLStep,
    Journey,
    LookupStep,
    ReasonStep,
    RespondStep,
    Step,
    ToolStep,
    WaitStep,
)


class ToolRegistry:
    """Registry of available tools the agent can invoke.

    Tools are deterministic functions — the agent-native equivalent of
    Flow's Apex Actions or External Services.
    """

    def __init__(self):
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        """Register a tool function."""
        self._tools[name] = fn

    def invoke(self, name: str, params: dict[str, Any]) -> Any:
        """Invoke a registered tool."""
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not registered")
        return self._tools[name](**params)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())


class ToolNotFoundError(Exception):
    pass


class JourneyExecutor:
    """Executes a journey (workflow) against an agent spec.

    Usage:
        spec = parse_yaml("agent.yaml")
        executor = JourneyExecutor(spec, tool_registry)
        result = await executor.run("handle_refund_request", user_message="I want a refund")
    """

    def __init__(
        self,
        spec: AgentSpec,
        tools: ToolRegistry | None = None,
        model: str | None = None,
        gateway_config: GatewayConfig | None = None,
        knowledge_base_path: Optional[Path] = None,
    ):
        self.spec = spec
        self.tools = tools or ToolRegistry()

        # Use gateway config (auto-loads from env if not provided)
        if gateway_config is None:
            gateway_config = GatewayConfig.from_env()
        if model:
            gateway_config = dataclasses_replace(
                gateway_config, model=resolve_model(model)
            )

        # ChatGateway adds automatic provider fallback + Upstash response
        # caching on top of the resolved primary config.
        self.gateway = ChatGateway(resolve_chain(gateway_config))

        # Knowledge loader for injecting documents into reason steps
        self.knowledge = KnowledgeLoader(spec, base_path=knowledge_base_path)

    def run(
        self,
        journey_name: str,
        user_message: str | None = None,
        context_data: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        """Execute a journey synchronously.

        Args:
            journey_name: Which journey to run.
            user_message: Initial user message (if conversational).
            context_data: Pre-populated context variables.

        Returns:
            ExecutionContext with full trace and results.
        """
        # Find the journey
        journey = self._find_journey(journey_name)

        # Initialize context
        ctx = ExecutionContext(
            journey_name=journey_name,
            agent_id=self.spec.agent,
        )
        if context_data:
            for k, v in context_data.items():
                ctx.set(k, v)
        if user_message:
            ctx.add_message("user", user_message)

        ctx.status = StepStatus.RUNNING

        # Execute steps
        step_index = 0
        steps_by_name = {s.name: (i, s) for i, s in enumerate(journey.steps)}

        # Build reachability: steps that are only reachable via explicit jump
        # (branch targets, HITL timeout targets, fault paths).
        # These steps are "islands" — sequential fallthrough should not reach them.
        jump_targets = set()
        for s in journey.steps:
            if isinstance(s, BranchStep):
                jump_targets.add(s.if_true)
                jump_targets.add(s.if_false)
            if hasattr(s, "on_failure") and s.on_failure:
                jump_targets.add(s.on_failure)
            if hasattr(s, "timeout_action") and s.timeout_action:
                jump_targets.add(s.timeout_action)

        reached_via_jump = False

        while step_index < len(journey.steps):
            step = journey.steps[step_index]
            ctx.current_step_index = step_index

            # Execute the step
            next_step = self._execute_step(step, ctx)

            # Handle HITL pause
            if ctx.waiting_for_human:
                ctx.status = StepStatus.WAITING_HITL
                return ctx

            # Handle explicit jump (branch/failure/timeout)
            if next_step is not None:
                if next_step in steps_by_name:
                    step_index = steps_by_name[next_step][0]
                    reached_via_jump = True
                else:
                    # Step name not found — treat as completion
                    break
            else:
                step_index += 1

                # Stop sequential execution if next step is a jump target
                # (it's an "island" only reachable via explicit branch/jump).
                # This prevents bleed-through from one terminal path to another.
                if (
                    step_index < len(journey.steps)
                    and journey.steps[step_index].name in jump_targets
                ):
                    break

        ctx.status = StepStatus.COMPLETED
        return ctx

    def _find_journey(self, name: str) -> Journey:
        """Find a journey by name in the spec."""
        for j in self.spec.journeys:
            if j.name == name:
                return j
        available = [j.name for j in self.spec.journeys]
        raise ValueError(f"Journey '{name}' not found. Available: {available}")

    def _execute_step(self, step: Step, ctx: ExecutionContext):
        """Execute a single step. Returns next step name if jumping, None to continue."""
        trace = ctx.start_step(step.name, step.type)

        try:
            if isinstance(step, LookupStep):
                result = self._exec_lookup(step, ctx)
                trace.complete(output=result)

            elif isinstance(step, ReasonStep):
                result = self._exec_reason(step, ctx)
                trace.complete(output=result)

            elif isinstance(step, RespondStep):
                result = self._exec_respond(step, ctx)
                trace.complete(output=result)

            elif isinstance(step, BranchStep):
                next_step = self._exec_branch(step, ctx)
                trace.complete(output=f"branched to: {next_step}")
                return next_step

            elif isinstance(step, HITLStep):
                should_escalate = self._exec_hitl(step, ctx)
                if should_escalate:
                    trace.complete(output="escalated to human")
                    return None  # Paused
                trace.complete(output="condition not met, continuing")

            elif isinstance(step, ToolStep):
                result = self._exec_tool(step, ctx)
                trace.complete(output=result)

            elif isinstance(step, WaitStep):
                trace.complete(output="waiting")
                # In a real system, this would pause and resume later
                return None

            else:
                trace.complete(error=f"Unknown step type: {type(step)}")

        except Exception as e:
            trace.complete(error=str(e))
            # Check for fault path
            if hasattr(step, "on_failure") and step.on_failure:
                return step.on_failure

        return None

    def _exec_lookup(self, step: LookupStep, ctx: ExecutionContext) -> Any:
        """Execute a lookup step — deterministic tool call for data retrieval."""
        # Resolve any ${} references in params
        resolved_params = self._resolve_params(step.params, ctx)
        result = self.tools.invoke(step.tool, resolved_params)
        ctx.set(step.output_key, result)
        return result

    def _exec_reason(self, step: ReasonStep, ctx: ExecutionContext) -> Any:
        """Execute a reasoning step — LLM evaluates context and produces structured output."""
        # Build the reasoning prompt
        system_prompt = self._build_system_prompt()

        # Use step prompt + user message as RAG query for semantic retrieval
        rag_query = step.prompt
        if ctx.messages:
            rag_query = f"{ctx.messages[-1].get('content', '')} {step.prompt}"

        context_block = self._build_context_block(ctx, step.knowledge, query=rag_query)

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

        # Cached + fallback-aware LLM call (Upstash exact-match cache, then
        # provider chain with automatic failover).
        result_text = self.gateway.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=step.temperature,
            max_tokens=step.max_tokens,
        )

        # Try to parse as JSON if output_schema is defined
        if step.output_schema:
            result = self._parse_json_response(result_text)
        else:
            result = result_text

        ctx.set(step.output_key, result)

        # Flatten structured output keys into context for ${key} resolution
        # e.g., {"eligible": true, "refund_amount": 299} -> ctx["eligible"], ctx["refund_amount"]
        if isinstance(result, dict):
            for k, v in result.items():
                ctx.set(k, v)

        return result

    def _exec_respond(self, step: RespondStep, ctx: ExecutionContext) -> str:
        """Execute a respond step — generate user-facing message."""
        system_prompt = self._build_system_prompt()

        # Include referenced context
        context_parts = []
        for key in step.include_context:
            val = ctx.get(key)
            if val:
                context_parts.append(f"{key}: {val}")

        user_prompt = f"""Generate a response to the user.

## Instruction
{step.prompt}

## Context
{chr(10).join(context_parts) if context_parts else 'No additional context.'}

## Conversation History
{self._format_messages(ctx.messages)}
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
        ctx.add_message("assistant", result)
        return result

    def _exec_branch(self, step: BranchStep, ctx: ExecutionContext) -> str:
        """Execute a branch — purely deterministic conditional."""
        condition_result = ctx.resolve_expression(step.condition)
        if condition_result:
            return step.if_true
        return step.if_false

    def _exec_hitl(self, step: HITLStep, ctx: ExecutionContext) -> bool:
        """Check HITL condition and escalate if needed."""
        should_escalate = ctx.resolve_expression(step.condition)

        if should_escalate:
            ctx.waiting_for_human = True
            ctx.hitl_request = {
                "escalation_type": step.escalation_type.value,
                "escalate_to": step.escalate_to,
                "context": {k: ctx.get(k) for k in step.context_to_share},
                "step_name": step.name,
            }
            return True

        return False

    def _exec_tool(self, step: ToolStep, ctx: ExecutionContext) -> Any:
        """Execute a tool action — deterministic, potentially destructive."""
        resolved_params = self._resolve_params(step.params, ctx)
        result = self.tools.invoke(step.tool, resolved_params)
        if step.output_key:
            ctx.set(step.output_key, result)
        return result

    # --- Helpers ---

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
        self, ctx: ExecutionContext, knowledge_ids: list[str], query: str = ""
    ) -> str:
        """Build context block from execution state + knowledge sources.

        Args:
            ctx: Current execution context.
            knowledge_ids: Knowledge source IDs to include.
            query: Optional query for semantic retrieval (RAG mode).
                   If provided and sources are ingested, uses vector search.
                   Otherwise falls back to full document loading.
        """
        parts = []

        # Include relevant context data
        if ctx.data:
            parts.append("### Execution Context")
            for k, v in ctx.data.items():
                parts.append(f"- {k}: {json.dumps(v) if not isinstance(v, str) else v}")

        # Include conversation history
        if ctx.messages:
            parts.append("### Conversation History")
            parts.append(self._format_messages(ctx.messages[-5:]))  # Last 5 messages

        # Load knowledge — use RAG if available, otherwise full documents
        if knowledge_ids:
            parts.append("### Relevant Knowledge")
            if query and any(self.knowledge.is_ingested(kid) for kid in knowledge_ids):
                # Phase 3: semantic retrieval
                knowledge_content = self.knowledge.retrieve(
                    query=query,
                    knowledge_ids=knowledge_ids,
                    top_k=3,
                )
            else:
                # Phase 1 fallback: full document injection
                knowledge_content = self.knowledge.load_multiple(knowledge_ids)
            parts.append(knowledge_content)

        return "\n".join(parts)

    def _format_messages(self, messages: list[dict[str, str]]) -> str:
        """Format conversation messages for LLM context."""
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    def _resolve_params(
        self, params: dict[str, Any], ctx: ExecutionContext
    ) -> dict[str, Any]:
        """Resolve ${} references in tool parameters."""
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and "${" in v:
                # Extract key from ${key}
                import re

                def replace_ref(match):
                    key = match.group(1)
                    return str(ctx.get(key, ""))

                resolved[k] = re.sub(r"\$\{(\w+)\}", replace_ref, v)
            else:
                resolved[k] = v
        return resolved

    @staticmethod
    def _parse_json_response(text: str) -> Any:
        """Parse JSON from LLM response, handling markdown code fences.

        LLMs often wrap JSON in ```json ... ``` blocks. This strips that
        and extracts the raw JSON reliably.
        """
        import re

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences: ```json ... ``` or ``` ... ```
        fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object in the text
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Give up — return raw text
        return text
