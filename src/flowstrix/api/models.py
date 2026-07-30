"""
FlowStrix API Models — Pydantic request/response schemas for the REST API.

Separate from schema/models.py (agent spec) — these are HTTP contract models.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# --- Request Models ---


class RunRequest(BaseModel):
    """Request to execute a journey."""

    spec_path: str = Field(description="Path to agent YAML spec file")
    journey: str = Field(description="Journey name to execute")
    message: Optional[str] = Field(default=None, description="Initial user message")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Initial context data"
    )
    model: Optional[str] = Field(
        default=None, description="Model override (e.g. claude-haiku)"
    )
    engine: Optional[str] = Field(
        default=None, description="Engine: 'legacy' or 'langgraph'"
    )
    thread_id: Optional[str] = Field(
        default=None, description="Thread ID for multi-turn conversations"
    )
    interaction_mode: Optional[str] = Field(
        default=None,
        description="Interaction mode: 'conversational' | 'agent_driven' | 'structured'. Affects handoff step behavior.",
    )


class HITLResumeRequest(BaseModel):
    """Request to resume a HITL-paused execution."""

    approved: bool = Field(description="Whether the human approved the action")
    notes: Optional[str] = Field(default=None, description="Optional reviewer notes")


class HandoffResumeRequest(BaseModel):
    """Request to resume execution after handoff form submission."""

    form_data: dict[str, Any] = Field(
        description="Submitted form field values (field_id → value)"
    )


# --- Response Models ---


class StepTraceResponse(BaseModel):
    """A single step execution trace."""

    step_name: str
    step_type: str
    status: str
    duration_ms: Optional[float] = None
    output_preview: Optional[str] = None
    # Token counts for steps that called a model. Null for deterministic
    # steps (which never touch an LLM) and for cache hits (which spend no
    # tokens) — the two cases are distinguishable by step_type.
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


class HITLInfo(BaseModel):
    """HITL escalation details when execution is paused."""

    escalation_type: str
    escalate_to: str
    context: dict[str, Any] = Field(default_factory=dict)
    step_name: str


class HandoffInfo(BaseModel):
    """Handoff form details when execution is paused for structured input."""

    step_name: str
    transition_message: str
    output_key: str
    fields: list[dict[str, Any]] = Field(default_factory=list)


class RunResponse(BaseModel):
    """Full execution result."""

    execution_id: str
    status: str  # completed, failed, waiting_hitl, waiting_handoff
    journey_name: str
    traces: list[StepTraceResponse] = Field(default_factory=list)
    context_data: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, str]] = Field(default_factory=list)
    hitl_info: Optional[HITLInfo] = None
    handoff_info: Optional[HandoffInfo] = None
    execution_time_ms: float = 0.0
    thread_id: Optional[str] = None


class StepEvent(BaseModel):
    """Real-time step event for SSE/WebSocket streaming."""

    event: str  # step_started, step_completed, execution_completed, execution_failed
    step_name: Optional[str] = None
    step_type: Optional[str] = None
    status: Optional[str] = None
    output_preview: Optional[str] = None
    # Mirrors StepTraceResponse so the live trace panel can show token counts
    # as steps stream in, rather than only after the final result arrives.
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    timestamp: float = 0.0


class SpecSummary(BaseModel):
    """Summary of a loaded agent spec."""

    agent: str
    persona_name: str
    persona_description: str
    journeys: list[JourneySummary] = Field(default_factory=list)
    knowledge_sources: int = 0
    simulations: int = 0


class JourneyStepDetail(BaseModel):
    """Detailed step info for discovery/inspection."""

    name: str
    type: str
    description: str
    prompt: Optional[str] = None
    condition: Optional[str] = None
    if_true: Optional[str] = None
    if_false: Optional[str] = None
    escalate_to: Optional[str] = None


class JourneySummary(BaseModel):
    """Summary of a single journey."""

    name: str
    description: str
    trigger_description: str
    step_count: int
    step_types: list[str] = Field(default_factory=list)


class JourneyDetail(BaseModel):
    """Full journey detail with steps for canvas rendering."""

    name: str
    description: str
    trigger_description: str
    steps: list[JourneyStepDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
    model: Optional[str] = None
    provider: Optional[str] = None
    gateway_configured: bool = False


# --- Ghostwriter Models ---


class GhostwriteRequest(BaseModel):
    """Request to generate an agent spec from natural language."""

    description: str = Field(
        description="Natural language description of desired agent behavior"
    )
    agent_name: Optional[str] = Field(
        default=None, description="Desired agent identifier"
    )
    persona_name: Optional[str] = Field(
        default=None, description="Agent persona display name"
    )
    tools_available: list[str] = Field(
        default_factory=list, description="Available tool names"
    )
    knowledge_docs: list[str] = Field(
        default_factory=list, description="Knowledge document paths"
    )


class GhostwriteStepResponse(BaseModel):
    """A step in the generated journey."""

    name: str
    type: str
    description: str
    prompt: Optional[str] = None
    condition: Optional[str] = None
    if_true: Optional[str] = None
    if_false: Optional[str] = None
    escalate_to: Optional[str] = None
    output_key: Optional[str] = None
    tool: Optional[str] = None


class GhostwriteJourneyResponse(BaseModel):
    """A generated journey."""

    name: str
    description: str
    trigger_description: str
    steps: list[GhostwriteStepResponse]


class GhostwriteResponse(BaseModel):
    """Response from ghostwriter compilation."""

    agent_name: str
    persona_name: str
    persona_description: str
    journeys: list[GhostwriteJourneyResponse]
    yaml_output: str
    explanation: str
    confidence: float
