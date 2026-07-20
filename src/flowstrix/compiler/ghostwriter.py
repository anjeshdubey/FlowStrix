"""
FlowStrix Ghostwriter — Natural language to YAML agent spec compiler.

The killer demo: "Describe what you want in plain English, get a working agent."

Architecture:
1. Takes a natural language description of desired agent behavior
2. Uses Claude (via Instructor) to emit structured Pydantic models
3. Validates the output against the FlowStrix schema
4. Serializes to YAML

This is the agent-native equivalent of "drag boxes onto a canvas" —
but the input is English and the output is a fully executable spec.
"""

from __future__ import annotations

import json
from typing import Optional

import instructor
import yaml
from openai import OpenAI
from pydantic import BaseModel, Field

from flowstrix.gateway import GatewayConfig, create_client, resolve_model

# Use a faster model with a higher free-tier TPM limit for Ghostwriter
# llama-3.1-8b-instant: 20k TPM vs llama-3.3-70b-versatile: 12k TPM
GHOSTWRITER_DEFAULT_MODEL = "llama-3.1-8b-instant"
from flowstrix.schema.models import (
    AgentSpec,
    BranchStep,
    EscalationType,
    HITLStep,
    Journey,
    KnowledgeSource,
    KnowledgeSourceType,
    LookupStep,
    Persona,
    ReasonStep,
    RespondStep,
    Simulation,
    SimulationScenario,
    ToolStep,
    Trigger,
    WaitStep,
)


# --- Intermediate models for structured generation ---


class GhostwriterInput(BaseModel):
    """What the user provides to Ghostwriter."""

    description: str = Field(description="Natural language description of the agent")
    agent_name: Optional[str] = Field(default=None, description="Desired agent identifier")
    persona_name: Optional[str] = Field(default=None, description="Agent's display name")
    tools_available: list[str] = Field(
        default_factory=list,
        description="List of available tool names (e.g., 'get_orders', 'process_refund')",
    )
    knowledge_docs: list[str] = Field(
        default_factory=list,
        description="Knowledge document paths/descriptions available to the agent",
    )


class GhostwriterResult(BaseModel):
    """Output of the Ghostwriter compilation."""

    spec: AgentSpec
    yaml_output: str
    explanation: str  # Human-readable explanation of what was generated
    confidence: float  # 0-1 confidence in the output quality


# --- Ghostwriter Compiler ---


GHOSTWRITER_SYSTEM_PROMPT = """You are FlowStrix Ghostwriter — an AI that compiles natural language descriptions into structured agent workflow specifications.

Your output MUST be a valid FlowStrix AgentSpec. The schema has these components:

## Agent Spec Structure
- **agent**: Unique identifier (snake_case)
- **persona**: Name, description, tone, guardrails (hard rules), off_limits (forbidden topics)
- **journeys**: List of goal-oriented workflows, each with:
  - name, description, trigger (when it activates)
  - steps: ordered list of primitives (see below)
- **knowledge**: External documents the agent can reference
- **simulations**: Test scenarios to verify behavior

## Step Types (The Agent Primitives)
1. **lookup** (deterministic): Fetch data from a tool. Fields: name, tool, params, output_key
2. **reason** (LLM): Evaluate context and produce structured decision. Fields: name, prompt, knowledge (list of IDs), output_schema (JSON schema for output), output_key, temperature (0.0=deterministic)
3. **respond** (LLM): Generate user-facing message. Fields: name, prompt, include_context, tone
4. **branch** (deterministic): Conditional routing. Fields: name, condition (${key} expressions), if_true, if_false
5. **hitl** (gate): Human approval checkpoint. Fields: name, condition, escalation_type (approval/handoff/review), escalate_to, context_to_share
6. **tool** (deterministic): Execute an action. Fields: name, tool, params, output_key, requires_confirmation
7. **wait** (pause): Wait for event/timeout. Fields: name, event, timeout_seconds

## Design Principles
- Start with a lookup to gather context (never reason without data)
- Use `reason` for decisions that require judgment, `branch` for simple conditions
- Always gate destructive actions behind `hitl` or `requires_confirmation`
- Reason steps should have `output_schema` for reliable downstream branching
- Keep temperature at 0.0 for decision steps, allow 0.3 for response generation
- Respond steps are terminal — they end an execution path
- branch if_true/if_false must reference step NAMES that exist in the journey

## Condition Syntax
- ${key}: Reference a context variable
- ${key} > 500: Numeric comparison
- "always": Always true (for unconditional HITL gates)

## CRITICAL RULES
- Every step must have a unique `name` within its journey
- Branch targets (if_true, if_false) must be names of other steps in the SAME journey
- Respond steps after a branch are terminal endpoints — place them AFTER all branching logic
- reason steps with output_schema flatten their output keys into context (${eligible}, ${amount}, etc.)
"""


class Ghostwriter:
    """Compiles natural language descriptions into FlowStrix agent specs.

    Usage:
        gw = Ghostwriter()
        result = gw.compile("Handle refund requests. Escalate amounts over $500.")
        print(result.yaml_output)
    """

    def __init__(
        self,
        gateway_config: Optional[GatewayConfig] = None,
        model: Optional[str] = None,
    ):
        if gateway_config is None:
            gateway_config = GatewayConfig.from_env()

        raw_client = create_client(gateway_config)
        self.client = instructor.from_openai(raw_client)
        # Default to the provider's standard model for Ghostwriting
        default_model = "gemini-2.5-flash" if gateway_config.provider == "gemini" else GHOSTWRITER_DEFAULT_MODEL
        self.model = resolve_model(model or default_model)

    def compile(
        self,
        description: str,
        agent_name: Optional[str] = None,
        persona_name: Optional[str] = None,
        tools_available: Optional[list[str]] = None,
        knowledge_docs: Optional[list[str]] = None,
        max_retries: int = 2,
    ) -> GhostwriterResult:
        """Compile a natural language description into a FlowStrix agent spec.

        Args:
            description: Plain English description of desired agent behavior.
            agent_name: Optional agent identifier override.
            persona_name: Optional persona display name.
            tools_available: List of tool names the agent can use.
            knowledge_docs: List of knowledge document paths/descriptions.
            max_retries: Number of retries on validation failure.

        Returns:
            GhostwriterResult with validated spec, YAML output, and explanation.
        """
        user_prompt = self._build_prompt(
            description, agent_name, persona_name, tools_available, knowledge_docs
        )

        # Use Instructor for structured output directly into AgentSpec
        spec = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            max_retries=max_retries,
            messages=[
                {"role": "system", "content": GHOSTWRITER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_model=AgentSpec,
        )

        # Generate YAML output
        yaml_output = self._spec_to_yaml(spec)

        # Generate explanation
        explanation = self._generate_explanation(spec)

        # Calculate confidence (basic heuristic for now)
        confidence = self._estimate_confidence(spec, description)

        return GhostwriterResult(
            spec=spec,
            yaml_output=yaml_output,
            explanation=explanation,
            confidence=confidence,
        )

    def refine(
        self,
        current_spec: AgentSpec,
        refinement: str,
        max_retries: int = 2,
    ) -> GhostwriterResult:
        """Refine an existing spec based on feedback.

        Example: "Also handle exchanges, not just refunds"
        """
        current_yaml = self._spec_to_yaml(current_spec)

        user_prompt = f"""Here is the current agent specification:

```yaml
{current_yaml}
```

## Refinement Request
{refinement}

Update the agent spec to incorporate this refinement. Keep everything else unchanged unless it conflicts with the new requirement. Return the complete updated AgentSpec.
"""

        spec = self.client.chat.completions.create(
            model=self.model,
            max_tokens=8192,
            max_retries=max_retries,
            messages=[
                {"role": "system", "content": GHOSTWRITER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_model=AgentSpec,
        )

        yaml_output = self._spec_to_yaml(spec)
        explanation = f"Refined: {refinement}\n\n{self._generate_explanation(spec)}"
        confidence = self._estimate_confidence(spec, refinement)

        return GhostwriterResult(
            spec=spec,
            yaml_output=yaml_output,
            explanation=explanation,
            confidence=confidence,
        )

    def _build_prompt(
        self,
        description: str,
        agent_name: Optional[str],
        persona_name: Optional[str],
        tools_available: Optional[list[str]],
        knowledge_docs: Optional[list[str]],
    ) -> str:
        """Build the compilation prompt from user inputs."""
        parts = [f"## Agent Description\n{description}"]

        if agent_name:
            parts.append(f"\n## Agent ID\n{agent_name}")

        if persona_name:
            parts.append(f"\n## Persona Name\n{persona_name}")

        if tools_available:
            parts.append(f"\n## Available Tools\n" + "\n".join(f"- {t}" for t in tools_available))

        if knowledge_docs:
            parts.append(
                f"\n## Available Knowledge Documents\n"
                + "\n".join(f"- {d}" for d in knowledge_docs)
            )

        parts.append(
            "\n## Instructions\n"
            "Generate a complete FlowStrix AgentSpec based on the description above. "
            "Include appropriate guardrails, at least one journey with proper branching, "
            "and test simulation scenarios."
        )

        return "\n".join(parts)

    @staticmethod
    def _spec_to_yaml(spec: AgentSpec) -> str:
        """Convert an AgentSpec to clean YAML."""
        # mode="json" ensures enums serialize as strings, not Python objects
        data = spec.model_dump(mode="json", exclude_none=True, exclude_defaults=False)

        # Custom YAML formatting
        yaml_str = yaml.dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )

        # Add a header comment
        header = "# FlowStrix Agent Spec — Generated by Ghostwriter\n\n"
        return header + yaml_str

    @staticmethod
    def _generate_explanation(spec: AgentSpec) -> str:
        """Generate a human-readable explanation of what was compiled."""
        lines = [
            f"Generated agent **{spec.agent}** with persona '{spec.persona.name}'.",
            f"\nJourneys ({len(spec.journeys)}):",
        ]

        for j in spec.journeys:
            step_types = [s.type for s in j.steps]
            lines.append(f"  - **{j.name}**: {j.description}")
            lines.append(f"    Steps: {' → '.join(step_types)}")

        if spec.knowledge:
            lines.append(f"\nKnowledge sources: {len(spec.knowledge)}")

        if spec.simulations:
            total_scenarios = sum(len(s.scenarios) for s in spec.simulations)
            lines.append(f"Test scenarios: {total_scenarios}")

        guardrail_count = len(spec.persona.guardrails)
        if guardrail_count:
            lines.append(f"Guardrails: {guardrail_count} safety constraints")

        return "\n".join(lines)

    @staticmethod
    def _estimate_confidence(spec: AgentSpec, description: str) -> float:
        """Rough heuristic for output quality. Will improve with real eval in Phase 5."""
        score = 0.5  # Base

        # Has at least one journey
        if spec.journeys:
            score += 0.1

        # Journeys have multiple step types (not just respond)
        if spec.journeys:
            all_types = set()
            for j in spec.journeys:
                for s in j.steps:
                    all_types.add(s.type)
            if len(all_types) >= 3:
                score += 0.1

        # Has guardrails
        if spec.persona.guardrails:
            score += 0.05

        # Has simulations
        if spec.simulations:
            score += 0.1

        # Has knowledge sources
        if spec.knowledge:
            score += 0.05

        # Has HITL somewhere
        has_hitl = any(
            any(s.type == "hitl" for s in j.steps)
            for j in spec.journeys
        )
        if has_hitl:
            score += 0.1

        return min(score, 1.0)
