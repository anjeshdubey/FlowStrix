"""
FlowStrix Session Manager — Tracks active and completed execution sessions.

In-memory storage for POC. Production would use Redis or a database.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from flowstrix.engine.context import ExecutionContext


@dataclass
class ExecutionSession:
    """A tracked execution session."""

    id: str
    spec_path: str
    journey_name: str
    context: Optional[ExecutionContext] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: str = "pending"  # pending, running, completed, failed, waiting_hitl
    error: Optional[str] = None
    engine: str = "legacy"  # "legacy" or "langgraph"
    thread_id: Optional[str] = None


class SessionManager:
    """In-memory session store for execution tracking.

    Tracks active and recently completed executions.
    Enables HITL resume and execution history.
    """

    def __init__(self, max_sessions: int = 100):
        self._sessions: dict[str, ExecutionSession] = {}
        self._max_sessions = max_sessions

    def create(self, spec_path: str, journey_name: str) -> ExecutionSession:
        """Create a new execution session."""
        session_id = str(uuid.uuid4())[:8]
        session = ExecutionSession(
            id=session_id,
            spec_path=spec_path,
            journey_name=journey_name,
            status="pending",
        )
        self._sessions[session_id] = session
        self._cleanup_old()
        return session

    def get(self, session_id: str) -> Optional[ExecutionSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def update(
        self,
        session_id: str,
        context: Optional[ExecutionContext] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update a session's state."""
        session = self._sessions.get(session_id)
        if session is None:
            return

        if context is not None:
            session.context = context
        if status is not None:
            session.status = status
            if status in ("completed", "failed"):
                session.completed_at = time.time()
        if error is not None:
            session.error = error

    def list_active(self) -> list[ExecutionSession]:
        """List all active (non-completed) sessions."""
        return [
            s for s in self._sessions.values()
            if s.status in ("pending", "running", "waiting_hitl")
        ]

    def list_all(self) -> list[ExecutionSession]:
        """List all sessions (active + completed)."""
        return list(self._sessions.values())

    def _cleanup_old(self) -> None:
        """Remove oldest completed sessions if over capacity."""
        if len(self._sessions) <= self._max_sessions:
            return

        # Sort by created_at, remove oldest completed
        completed = [
            s for s in self._sessions.values()
            if s.status in ("completed", "failed")
        ]
        completed.sort(key=lambda s: s.created_at)

        while len(self._sessions) > self._max_sessions and completed:
            old = completed.pop(0)
            del self._sessions[old.id]
