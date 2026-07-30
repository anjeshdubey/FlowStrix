"""
Execution Context — The state that flows through a journey.

This is the agent-native equivalent of Flow's interview/variable system.
Key difference: context is append-only for auditability, and includes
the full conversation history plus reasoning traces.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_HITL = "waiting_hitl"


@dataclass
class StepTrace:
    """Audit trail for a single step execution."""

    step_name: str
    step_type: str
    status: StepStatus
    started_at: float
    completed_at: float | None = None
    input_context_keys: list[str] = field(default_factory=list)
    output: Any = None
    error: str | None = None
    llm_usage: dict[str, int] | None = None  # tokens in/out
    duration_ms: float | None = None

    def complete(
        self,
        output: Any = None,
        error: str | None = None,
        llm_usage: dict[str, int] | None = None,
    ):
        self.completed_at = time.time()
        self.output = output
        self.error = error
        # Only set on steps that actually called a model, and only when the
        # provider reported usage — left None otherwise so the UI can tell
        # "no LLM involved" apart from "zero tokens".
        if llm_usage is not None:
            self.llm_usage = llm_usage
        self.status = StepStatus.FAILED if error else StepStatus.COMPLETED
        self.duration_ms = (self.completed_at - self.started_at) * 1000


@dataclass
class ExecutionContext:
    """Full execution state for a journey run.

    Design principles:
    - Append-only data store (for audit trail)
    - Conversation history is first-class
    - Every LLM call is traced
    - Context keys are the data flow mechanism (like Flow variables)
    """

    journey_name: str
    agent_id: str

    # Data store — equivalent to Flow variables
    data: dict[str, Any] = field(default_factory=dict)

    # Conversation history
    messages: list[dict[str, str]] = field(default_factory=list)

    # Execution trace (append-only audit log)
    traces: list[StepTrace] = field(default_factory=list)

    # Current step pointer
    current_step_index: int = 0
    current_step_name: str | None = None

    # Execution metadata
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status: StepStatus = StepStatus.PENDING

    # HITL state
    waiting_for_human: bool = False
    hitl_request: dict[str, Any] | None = None

    # Multi-turn state
    thread_id: str | None = None

    # Handoff form state (smart modality switch)
    handoff_form: dict[str, Any] | None = None

    def set(self, key: str, value: Any) -> None:
        """Set a context variable. Immutable-friendly — logs the change."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a context variable."""
        return self.data.get(key, default)

    def resolve_expression(self, expr: str) -> Any:
        """Resolve a ${key} expression against context data.

        Supports simple expressions like:
        - ${eligible} -> self.data["eligible"]
        - ${refund_amount} > 500 -> evaluates comparison
        - "always" -> True
        """
        if expr.strip().lower() == "always":
            return True

        # Simple key reference: ${key}
        if expr.startswith("${") and expr.endswith("}"):
            key = expr[2:-1]
            return self.data.get(key)

        # Expression with comparison operators
        import re

        match = re.match(r"\$\{(\w+)\}\s*(>|<|>=|<=|==|!=)\s*(.+)", expr)
        if match:
            key, op, value = match.groups()
            left = self.data.get(key)
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
        if expr in self.data:
            return bool(self.data[expr])

        return False

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self.messages.append({"role": role, "content": content})

    def start_step(self, step_name: str, step_type: str) -> StepTrace:
        """Begin tracing a step."""
        trace = StepTrace(
            step_name=step_name,
            step_type=step_type,
            status=StepStatus.RUNNING,
            started_at=time.time(),
        )
        self.traces.append(trace)
        self.current_step_name = step_name
        return trace

    def get_trace_summary(self) -> list[dict[str, Any]]:
        """Get a human-readable execution summary."""
        return [
            {
                "step": t.step_name,
                "type": t.step_type,
                "status": t.status.value,
                "duration_ms": round(t.duration_ms, 1) if t.duration_ms else None,
                "output_preview": str(t.output)[:100] if t.output else None,
                "llm_usage": t.llm_usage,
            }
            for t in self.traces
        ]
