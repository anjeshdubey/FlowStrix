"""
FlowStrix Schema Models — The YAML contract for agent-native workflows.

Design philosophy:
- Deterministic where possible, probabilistic where necessary
- Every LLM call is bounded by guardrails and fallbacks
- Human-in-the-loop is a first-class primitive, not an afterthought
- Auditability is built in — every step produces a trace
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# --- Enums ---


class StepType(str, Enum):
    """The primitives an agent can execute."""

    LOOKUP = "lookup"  # Deterministic: fetch data from a tool/API
    REASON = "reason"  # Probabilistic: LLM reasoning with context
    RESPOND = "respond"  # Probabilistic: generate user-facing response
    BRANCH = "branch"  # Deterministic: conditional routing
    HITL = "hitl"  # Checkpoint: require human approval/handoff
    TOOL = "tool"  # Deterministic: execute an action (write, update, trigger)
    WAIT = "wait"  # Pause: wait for external event or time
    HANDOFF = "handoff"  # Smart modality switch: conversation → structured form


class EscalationType(str, Enum):
    """How HITL escalation works."""

    APPROVAL = "approval"  # Human approves/rejects, agent continues
    HANDOFF = "handoff"  # Full transfer to human agent
    REVIEW = "review"  # Human reviews but agent can proceed


class KnowledgeSourceType(str, Enum):
    """Types of knowledge sources."""

    DOCUMENT = "document"  # PDF, markdown, text files
    URL = "url"  # Web content
    API = "api"  # Structured API endpoint
    DATABASE = "database"  # SQL/record queries


# --- Step Definitions ---


class LookupStep(BaseModel):
    """Deterministic data retrieval. Equivalent to Flow's 'Get Records' element."""

    type: Literal["lookup"] = "lookup"
    name: str = Field(description="Human-readable step name")
    tool: str = Field(description="Tool/function to invoke")
    params: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    output_key: str = Field(description="Key to store result in journey context")
    on_failure: str | None = Field(
        default=None, description="Step to jump to on failure (fault path)"
    )


class ReasonStep(BaseModel):
    """LLM reasoning step. The agent thinks about context and produces a decision.

    This is the key differentiator from Flow — instead of a Decision element with
    explicit conditions, the LLM evaluates context against knowledge and produces
    a structured output.
    """

    type: Literal["reason"] = "reason"
    name: str = Field(description="Human-readable step name")
    prompt: str = Field(description="What the agent should reason about")
    knowledge: list[str] = Field(
        default_factory=list, description="Knowledge source IDs to inject as context"
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description="Expected structured output (JSON schema). Forces deterministic output shape.",
    )
    output_key: str = Field(description="Key to store reasoning result")
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="0.0 = deterministic, 1.0 = creative. Default: deterministic.",
    )
    max_tokens: int = Field(default=1024, description="Token budget for reasoning")


class RespondStep(BaseModel):
    """Generate a user-facing response. Bounded by persona and tone."""

    type: Literal["respond"] = "respond"
    name: str = Field(description="Human-readable step name")
    prompt: str = Field(description="What to communicate to the user")
    tone: str | None = Field(default=None, description="Override default persona tone")
    include_context: list[str] = Field(
        default_factory=list, description="Context keys to reference in response"
    )


class BranchStep(BaseModel):
    """Deterministic conditional routing. Like Flow's Decision element."""

    type: Literal["branch"] = "branch"
    name: str = Field(description="Human-readable step name")
    condition: str = Field(
        description="Expression to evaluate (supports context key references like ${eligible})"
    )
    if_true: str = Field(description="Step name to jump to if condition is true")
    if_false: str = Field(description="Step name to jump to if condition is false")


class HITLStep(BaseModel):
    """Human-in-the-loop checkpoint. First-class primitive.

    Maps to Flow's Pause element + approval processes, but designed for
    conversational agents rather than record-based workflows.
    """

    type: Literal["hitl"] = "hitl"
    name: str = Field(description="Human-readable step name")
    condition: str = Field(
        description="When to escalate (expression). Always escalates if 'always'."
    )
    escalation_type: EscalationType = Field(default=EscalationType.APPROVAL)
    escalate_to: str = Field(
        default="human_agent", description="Who/what to escalate to"
    )
    context_to_share: list[str] = Field(
        default_factory=list, description="Context keys to pass to the human"
    )
    timeout_seconds: int | None = Field(
        default=None, description="Auto-proceed after timeout (None = wait forever)"
    )
    timeout_action: str | None = Field(
        default=None, description="Step to jump to on timeout"
    )


class ToolStep(BaseModel):
    """Execute a deterministic action (write record, send email, trigger event)."""

    type: Literal["tool"] = "tool"
    name: str = Field(description="Human-readable step name")
    tool: str = Field(description="Tool/function to invoke")
    params: dict[str, Any] = Field(default_factory=dict)
    output_key: str | None = Field(default=None, description="Key to store result")
    on_failure: str | None = Field(default=None, description="Fault path")
    requires_confirmation: bool = Field(
        default=False, description="Require user confirmation before executing"
    )


class WaitStep(BaseModel):
    """Pause execution until an event or timeout. Like Flow's Pause element."""

    type: Literal["wait"] = "wait"
    name: str = Field(description="Human-readable step name")
    event: str | None = Field(default=None, description="Event to wait for")
    timeout_seconds: int | None = Field(default=None, description="Max wait time")
    resume_step: str | None = Field(default=None, description="Step to resume at")


class HandoffField(BaseModel):
    """A single form field in a handoff step."""

    id: str = Field(description="Field identifier (stored in output)")
    label: str = Field(description="Display label for the field")
    field_type: str = Field(
        default="text",
        description="Field type: text, textarea, select, multiselect, date, checkbox, file",
    )
    required: bool = Field(default=True)
    options: list[str] = Field(
        default_factory=list, description="Options for select/multiselect fields"
    )
    placeholder: str = Field(default="")
    validation: str | None = Field(
        default=None,
        description="Validation rule (e.g., 'min_length:10', 'required_if:data_export==true')",
    )


class HandoffStep(BaseModel):
    """Smart handoff — agent decides when to switch from conversation to structured form.

    The agent evaluates context (field count, complexity, compliance triggers)
    and produces a form spec for the UI to render inline. This is the bridge
    between conversational and structured interaction.

    Reuses the HITL interrupt mechanism — same pause/resume pattern,
    but returns a form spec instead of an approval request.
    """

    type: Literal["handoff"] = "handoff"
    name: str = Field(description="Human-readable step name")

    # Trigger logic — when should the agent switch to a form?
    trigger_condition: str = Field(
        description="Expression that triggers handoff (e.g., 'sensitive_access == true', or 'always')"
    )

    # Form definition — what fields to collect
    fields: list[HandoffField] = Field(description="Structured fields to collect via form")

    # AI pre-fill — agent populates what it already knows from conversation
    prefill_from_context: dict[str, str] = Field(
        default_factory=dict,
        description="Map of field_id → context_key to auto-populate from conversation data",
    )

    # Output
    output_key: str = Field(description="Key to store form submission data")

    # Agent message when switching
    transition_message: str = Field(
        default="Let me collect some additional details in a structured format.",
        description="What the agent says when transitioning to the form",
    )


# Union type for all steps
Step = Annotated[
    Union[
        LookupStep, ReasonStep, RespondStep, BranchStep,
        HITLStep, ToolStep, WaitStep, HandoffStep,
    ],
    Field(discriminator="type"),
]


# --- Journey (Workflow) Definition ---


class Trigger(BaseModel):
    """What activates a journey. Maps to Flow's Start element / trigger conditions."""

    description: str = Field(
        description="Natural language description of when this journey activates"
    )
    intent_keywords: list[str] = Field(
        default_factory=list, description="Keywords/phrases that signal this intent"
    )
    conditions: dict[str, Any] = Field(
        default_factory=dict, description="Structured conditions (context state checks)"
    )


class Journey(BaseModel):
    """A goal-oriented workflow. Sierra calls these 'Journeys', Flow calls them 'Flows'.

    The key difference: a Journey is outcome-oriented (defined by what it achieves),
    while a Flow is process-oriented (defined by its steps).
    """

    name: str = Field(description="Unique journey identifier")
    description: str = Field(description="What this journey achieves (outcome-oriented)")
    trigger: Trigger = Field(description="When/how this journey activates")
    steps: list[Step] = Field(description="Ordered steps to execute")
    fallback: str | None = Field(
        default=None, description="What to do if the journey fails entirely"
    )
    max_turns: int = Field(
        default=20, description="Safety limit on conversation turns"
    )


# --- Knowledge Sources ---


class KnowledgeSource(BaseModel):
    """External knowledge the agent can access during reasoning steps."""

    id: str = Field(description="Unique identifier referenced in ReasonSteps")
    source_type: KnowledgeSourceType
    uri: str = Field(description="Location of the knowledge (path, URL, connection string)")
    description: str = Field(description="What this knowledge contains")
    refresh_interval_seconds: int | None = Field(
        default=None, description="How often to re-index (None = manual)"
    )


# --- Simulations (Testing) ---


class SimulationScenario(BaseModel):
    """A test scenario. The agent-native equivalent of a Flow test case."""

    name: str = Field(description="Scenario name")
    description: str = Field(description="Natural language scenario description")
    user_messages: list[str] = Field(
        default_factory=list,
        description="Scripted user messages (if empty, AI generates the conversation)",
    )
    expected_outcome: str = Field(description="What should happen")
    expected_steps: list[str] = Field(
        default_factory=list, description="Steps that must be executed"
    )
    must_not: list[str] = Field(
        default_factory=list, description="Things that must NOT happen"
    )


class Simulation(BaseModel):
    """Test suite definition. Runs AI-driven conversations to verify agent behavior."""

    name: str = Field(description="Simulation suite name")
    scenarios: list[SimulationScenario]
    num_runs_per_scenario: int = Field(
        default=5, description="Run each scenario N times (tests non-determinism)"
    )
    pass_threshold: float = Field(
        default=0.8, description="% of runs that must pass for scenario to be green"
    )


# --- Top-Level Agent Spec ---


class Persona(BaseModel):
    """The agent's identity and behavioral boundaries."""

    name: str = Field(description="Agent display name")
    description: str = Field(description="Who this agent is")
    tone: str = Field(default="professional and helpful", description="Communication style")
    guardrails: list[str] = Field(
        default_factory=list,
        description="Hard constraints (e.g., 'never discuss competitor pricing')",
    )
    off_limits: list[str] = Field(
        default_factory=list, description="Topics to refuse/redirect"
    )


class AgentSpec(BaseModel):
    """The top-level agent definition. This is what a YAML file compiles into.

    Philosophy: An agent = persona + journeys + knowledge + guardrails.
    The engine activates the right journey based on context, executes steps,
    and the persona/guardrails constrain all LLM-powered steps.
    """

    version: str = Field(default="1.0", description="Schema version")
    agent: str = Field(description="Unique agent identifier")
    persona: Persona
    journeys: list[Journey] = Field(description="Available workflows")
    knowledge: list[KnowledgeSource] = Field(
        default_factory=list, description="Knowledge sources"
    )
    simulations: list[Simulation] = Field(
        default_factory=list, description="Test suites"
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime configuration (model, temperature defaults, etc.)",
    )
