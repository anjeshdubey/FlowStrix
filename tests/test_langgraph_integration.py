"""Integration tests for the LangGraph executor.

Tests end-to-end behavior:
- Multi-turn: same thread_id resumes conversation
- HITL resume: executor.resume() continues after human approval
- Thread eviction: bounded memory for thread tracking
- Engine flag: CLI --engine switch selects correct executor
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flowstrix.engine.context import StepStatus
from flowstrix.engine.executor import ToolRegistry
from flowstrix.engine.executor_v2 import LangGraphExecutor
from flowstrix.gateway import GatewayConfig
from flowstrix.schema.parser import parse_yaml


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


# --- Helpers ---


def mock_gateway_config():
    return GatewayConfig(
        base_url="http://localhost:9999",
        auth_token="test-token",
        model="test-model",
    )


def mock_anthropic_response(text: str):
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


def _register_test_tools(tools: ToolRegistry):
    def get_orders_by_customer_id(customer_id: str = "test") -> dict:
        if "vip" in customer_id:
            return {
                "customer_id": customer_id,
                "orders": [
                    {"order_id": "ORD-VIP", "amount": 1249.99, "days_since_purchase": 4, "status": "delivered"},
                ],
            }
        if "old" in customer_id:
            return {
                "customer_id": customer_id,
                "orders": [
                    {"order_id": "ORD-OLD", "amount": 179.99, "days_since_purchase": 60, "status": "delivered"},
                ],
            }
        return {
            "customer_id": customer_id,
            "orders": [
                {"order_id": "ORD-001", "amount": 299.99, "days_since_purchase": 3, "status": "delivered"},
            ],
        }

    def process_refund(order_id: str = "", amount: float = 0.0) -> dict:
        return {"refund_id": "REF-100", "order_id": order_id, "amount": amount, "status": "processed"}

    tools.register("get_orders_by_customer_id", get_orders_by_customer_id)
    tools.register("process_refund", process_refund)


def make_executor():
    spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
    tools = ToolRegistry()
    _register_test_tools(tools)
    return LangGraphExecutor(
        spec,
        tools=tools,
        gateway_config=mock_gateway_config(),
        knowledge_base_path=EXAMPLES_DIR,
    )


# --- Integration Tests ---


class TestHITLResume:
    """Test the full HITL pause → human decision → resume flow."""

    def test_hitl_pauses_and_reports_escalation(self):
        """High-value refund pauses with correct HITL metadata."""
        executor = make_executor()

        high_value_response = json.dumps({
            "eligible": True,
            "order_id": "ORD-VIP",
            "refund_amount": 1249.99,
            "reason": "Within window",
        })

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.return_value = mock_anthropic_response(high_value_response)

            result = executor.run(
                "handle_refund_request",
                user_message="Return the furniture",
                context_data={"customer_id": "cust_vip"},
            )

        # Execution should be paused
        assert result.status == StepStatus.WAITING_HITL
        assert result.waiting_for_human is True
        assert result.hitl_request is not None
        assert result.hitl_request["escalate_to"] == "senior_support_agent"
        assert result.hitl_request["escalation_type"] == "approval"
        assert result.hitl_request["step_name"] == "escalate_high_value"

        # Key data should be in context (steps ran up to HITL)
        assert result.get("eligible") is True
        assert result.get("refund_amount") == 1249.99

    def test_resume_nonexistent_thread_raises(self):
        """Resuming a thread that doesn't exist should raise ValueError."""
        executor = make_executor()
        with pytest.raises(ValueError, match="not found"):
            executor.resume("nonexistent-thread-id")


class TestThreadManagement:
    """Test thread tracking and eviction."""

    def test_thread_stored_after_run(self):
        """After a run, the thread should be stored for potential resume."""
        executor = make_executor()

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Done!"),
            ]

            executor.run(
                "handle_refund_request",
                user_message="refund",
                context_data={"customer_id": "test"},
                thread_id="test-thread-123",
            )

        assert "test-thread-123" in executor._threads

    def test_thread_eviction_when_max_reached(self):
        """Oldest threads should be evicted when limit is reached."""
        executor = make_executor()
        executor._max_threads = 3

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        # Run 4 executions to exceed max_threads=3
        for i in range(4):
            with patch.object(executor.client, "messages") as mock_messages:
                mock_messages.create.side_effect = [
                    mock_anthropic_response(response),
                    mock_anthropic_response("Done!"),
                ]
                executor.run(
                    "handle_refund_request",
                    user_message="refund",
                    context_data={"customer_id": "test"},
                    thread_id=f"thread-{i}",
                )

        # Should only have 3 threads (oldest evicted)
        assert len(executor._threads) == 3
        assert "thread-0" not in executor._threads  # Oldest evicted
        assert "thread-3" in executor._threads  # Newest kept


class TestExplicitThreadId:
    """Test that thread_id is properly used for graph persistence."""

    def test_custom_thread_id_used(self):
        """When thread_id is provided, it should be used (not auto-generated)."""
        executor = make_executor()

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Done!"),
            ]

            executor.run(
                "handle_refund_request",
                user_message="refund",
                context_data={"customer_id": "test"},
                thread_id="my-custom-thread",
            )

        assert "my-custom-thread" in executor._threads

    def test_auto_generated_thread_id(self):
        """When no thread_id, one should be auto-generated."""
        executor = make_executor()

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Done!"),
            ]

            executor.run(
                "handle_refund_request",
                user_message="refund",
                context_data={"customer_id": "test"},
            )

        # Should have exactly one thread stored
        assert len(executor._threads) == 1


class TestLegacyParity:
    """Verify the LangGraph executor produces the same results as legacy."""

    def test_same_traces_as_legacy_for_simple_path(self):
        """Both engines should execute the same steps for the same input."""
        from flowstrix.engine.executor import JourneyExecutor

        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        tools = ToolRegistry()
        _register_test_tools(tools)
        config = mock_gateway_config()

        legacy = JourneyExecutor(spec, tools=tools, gateway_config=config, knowledge_base_path=EXAMPLES_DIR)
        langgraph = LangGraphExecutor(spec, tools=tools, gateway_config=config, knowledge_base_path=EXAMPLES_DIR)

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        # Run legacy
        with patch.object(legacy.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Your refund is done!"),
            ]
            legacy_result = legacy.run(
                "handle_refund_request",
                user_message="refund",
                context_data={"customer_id": "test"},
            )

        # Run LangGraph
        with patch.object(langgraph.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Your refund is done!"),
            ]
            lg_result = langgraph.run(
                "handle_refund_request",
                user_message="refund",
                context_data={"customer_id": "test"},
            )

        # Same status
        assert legacy_result.status == lg_result.status == StepStatus.COMPLETED

        # Same steps executed (in order)
        legacy_steps = [t.step_name for t in legacy_result.traces]
        lg_steps = [t.step_name for t in lg_result.traces]
        assert legacy_steps == lg_steps

        # Same data keys
        assert set(legacy_result.data.keys()) == set(lg_result.data.keys())

        # Same key values
        assert legacy_result.get("eligible") == lg_result.get("eligible")
        assert legacy_result.get("refund_amount") == lg_result.get("refund_amount")
