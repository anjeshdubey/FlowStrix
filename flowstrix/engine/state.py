"""
LangGraph Execution State — The typed state that flows through the graph.

This is the LangGraph equivalent of ExecutionContext, designed as a TypedDict
for use with LangGraph's StateGraph. We convert to/from ExecutionContext at
the boundaries so downstream consumers (CLI, API, simulator) remain unchanged.

Note: Uses Optional[] syntax (not `X | None`) for Python 3.9 compatibility
with LangGraph's runtime type evaluation via get_type_hints().
"""

from typing import Any, Dict, List, Optional, TypedDict


class StepTraceEntry(TypedDict):
    """A single step trace record for the graph state."""

    step_name: str
    step_type: str
    status: str  # "completed" | "failed" | "running"
    output: Any
    error: Optional[str]
    duration_ms: Optional[float]


class ExecutionState(TypedDict):
    """LangGraph state schema for journey execution.

    Design decisions:
    - Flat structure for easy serialization/checkpointing
    - All fields are optional-safe (have defaults via graph initialization)
    - Maps 1:1 to ExecutionContext fields for easy conversion
    """

    # Identity
    journey_name: str
    agent_id: str

    # Data store (equivalent to ctx.data / Flow variables)
    data: Dict[str, Any]

    # Conversation history
    messages: List[Dict[str, str]]

    # Execution trace (append-only audit log)
    traces: List[StepTraceEntry]

    # Step routing
    current_step: str  # Name of the current step being executed
    next_step: Optional[str]  # Explicit jump target (from branch/failure)

    # Execution status
    status: str  # "running" | "completed" | "failed" | "waiting_hitl"

    # HITL state
    waiting_for_human: bool
    hitl_request: Optional[Dict[str, Any]]

    # Handoff form state (smart modality switch)
    handoff_form: Optional[Dict[str, Any]]

    # Interaction mode (conversational | agent_driven | structured)
    interaction_mode: Optional[str]

    # User input (initial message + context)
    user_message: Optional[str]

    # Step execution metadata
    steps_executed: List[str]  # Ordered list of step names that ran
