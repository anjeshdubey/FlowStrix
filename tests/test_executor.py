"""Tests for FlowStrix execution engine.

Uses mocked LLM responses to test deterministic behavior
without hitting the gateway.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flowstrix.engine.context import ExecutionContext, StepStatus
from flowstrix.engine.executor import JourneyExecutor, ToolRegistry, ToolNotFoundError
from flowstrix.gateway import GatewayConfig
from flowstrix.schema.parser import parse_yaml


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

# --- Fixtures ---


def mock_gateway_config():
    """Create a gateway config that won't hit the real API."""
    return GatewayConfig(
        base_url="http://localhost:9999",
        auth_token="test-token",
        model="test-model",
    )


def mock_anthropic_response(text: str):
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


def make_executor(spec_path: str = "customer_support.yaml", tools: ToolRegistry = None):
    """Create an executor with mocked LLM client."""
    spec = parse_yaml(EXAMPLES_DIR / spec_path)
    if tools is None:
        tools = ToolRegistry()
        _register_test_tools(tools)

    executor = JourneyExecutor(
        spec,
        tools=tools,
        gateway_config=mock_gateway_config(),
        knowledge_base_path=EXAMPLES_DIR,
    )
    return executor


def _register_test_tools(tools: ToolRegistry):
    """Register deterministic test tools."""

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


# --- Tool Registry Tests ---


class TestToolRegistry:
    def test_register_and_invoke(self):
        tools = ToolRegistry()
        tools.register("add", lambda a, b: a + b)
        assert tools.invoke("add", {"a": 2, "b": 3}) == 5

    def test_invoke_missing_tool_raises(self):
        tools = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            tools.invoke("nonexistent", {})

    def test_list_tools(self):
        tools = ToolRegistry()
        tools.register("foo", lambda: None)
        tools.register("bar", lambda: None)
        assert set(tools.list_tools()) == {"foo", "bar"}


# --- Execution Context Tests ---


class TestExecutionContext:
    def test_set_and_get(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.set("key", "value")
        assert ctx.get("key") == "value"

    def test_get_default(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        assert ctx.get("missing", "default") == "default"

    def test_resolve_always(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        assert ctx.resolve_expression("always") is True

    def test_resolve_simple_key(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.set("eligible", True)
        assert ctx.resolve_expression("${eligible}") is True

    def test_resolve_numeric_gt(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.set("amount", 750)
        assert ctx.resolve_expression("${amount} > 500") is True
        assert ctx.resolve_expression("${amount} > 1000") is False

    def test_resolve_numeric_lt(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.set("amount", 100)
        assert ctx.resolve_expression("${amount} < 500") is True

    def test_resolve_equality(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.set("status", "active")
        assert ctx.resolve_expression("${status} == active") is True
        assert ctx.resolve_expression("${status} == inactive") is False

    def test_resolve_missing_key_is_false(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        assert ctx.resolve_expression("${nonexistent} > 500") is False

    def test_add_message(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.add_message("user", "hello")
        ctx.add_message("assistant", "hi")
        assert len(ctx.messages) == 2
        assert ctx.messages[0]["role"] == "user"

    def test_trace_lifecycle(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        trace = ctx.start_step("step1", "lookup")
        assert trace.status == StepStatus.RUNNING
        trace.complete(output="result")
        assert trace.status == StepStatus.COMPLETED
        assert trace.output == "result"
        assert trace.duration_ms is not None

    def test_trace_failure(self):
        ctx = ExecutionContext(journey_name="test", agent_id="test")
        trace = ctx.start_step("step1", "lookup")
        trace.complete(error="something broke")
        assert trace.status == StepStatus.FAILED
        assert trace.error == "something broke"


# --- Executor Tests (Mocked LLM) ---


class TestExecutorBranching:
    """Test deterministic branching logic without LLM calls."""

    def test_eligible_small_refund_path(self):
        """Eligible refund under $500 should: lookup → reason → branch → branch → tool → respond."""
        executor = make_executor()

        # Mock the LLM to return eligible + small amount
        eligible_response = json.dumps({
            "eligible": True,
            "order_id": "ORD-001",
            "refund_amount": 299.99,
            "reason": "Within 30-day window",
        })
        confirm_response = "Your refund has been processed!"

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(eligible_response),  # reason step
                mock_anthropic_response(confirm_response),   # respond step
            ]

            result = executor.run(
                "handle_refund_request",
                user_message="I want a refund",
                context_data={"customer_id": "cust_normal"},
            )

        assert result.status == StepStatus.COMPLETED
        assert result.get("eligible") is True
        assert result.get("refund_amount") == 299.99
        assert result.get("refund_result") is not None
        assert result.get("refund_result")["status"] == "processed"

        # Verify correct steps executed
        step_names = [t.step_name for t in result.traces]
        assert "fetch_order_history" in step_names
        assert "determine_eligibility" in step_names
        assert "check_eligibility" in step_names
        assert "check_amount_gate" in step_names
        assert "process_refund_action" in step_names
        assert "confirm_refund" in step_names
        # Should NOT execute the ineligible path
        assert "explain_ineligibility" not in step_names

    def test_ineligible_refund_path(self):
        """Ineligible refund should: lookup → reason → branch → respond (explain)."""
        executor = make_executor()

        ineligible_response = json.dumps({
            "eligible": False,
            "order_id": "ORD-OLD",
            "refund_amount": 0,
            "reason": "Purchase older than 30 days",
        })
        explain_response = "Sorry, your order is outside our 30-day return window."

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(ineligible_response),  # reason step
                mock_anthropic_response(explain_response),      # respond step
            ]

            result = executor.run(
                "handle_refund_request",
                user_message="Return from 2 months ago",
                context_data={"customer_id": "cust_old"},
            )

        assert result.status == StepStatus.COMPLETED
        assert result.get("eligible") is False

        step_names = [t.step_name for t in result.traces]
        assert "explain_ineligibility" in step_names
        # Should NOT execute refund processing
        assert "process_refund_action" not in step_names
        assert "confirm_refund" not in step_names

    def test_high_value_hitl_escalation(self):
        """Refund over $500 should trigger HITL and pause execution."""
        executor = make_executor()

        high_value_response = json.dumps({
            "eligible": True,
            "order_id": "ORD-VIP",
            "refund_amount": 1249.99,
            "reason": "Within window, eligible",
        })

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.return_value = mock_anthropic_response(high_value_response)

            result = executor.run(
                "handle_refund_request",
                user_message="Return the furniture",
                context_data={"customer_id": "cust_vip"},
            )

        assert result.status == StepStatus.WAITING_HITL
        assert result.waiting_for_human is True
        assert result.hitl_request is not None
        assert result.hitl_request["escalate_to"] == "senior_support_agent"
        assert result.hitl_request["escalation_type"] == "approval"

        # Should NOT have processed the refund
        step_names = [t.step_name for t in result.traces]
        assert "process_refund_action" not in step_names


class TestExecutorJSONParsing:
    """Test that the executor handles various LLM JSON output formats."""

    def test_parse_clean_json(self):
        result = JourneyExecutor._parse_json_response('{"eligible": true}')
        assert result == {"eligible": True}

    def test_parse_json_with_code_fences(self):
        text = '```json\n{"eligible": true, "amount": 100}\n```'
        result = JourneyExecutor._parse_json_response(text)
        assert result == {"eligible": True, "amount": 100}

    def test_parse_json_with_surrounding_text(self):
        text = 'Based on my analysis:\n{"eligible": false, "reason": "too old"}\nThat is my decision.'
        result = JourneyExecutor._parse_json_response(text)
        assert result == {"eligible": False, "reason": "too old"}

    def test_parse_non_json_returns_text(self):
        text = "This is just plain text with no JSON"
        result = JourneyExecutor._parse_json_response(text)
        assert result == text


class TestExecutorContextFlattening:
    """Test that structured reason outputs get flattened into context."""

    def test_reason_output_flattened(self):
        """When reason returns {"eligible": true, "amount": 100}, both keys should be in context."""
        executor = make_executor()

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        with patch.object(executor.client, "messages") as mock_messages:
            # Need responses for: reason, respond (confirm_refund)
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Done!"),
            ]

            result = executor.run(
                "handle_refund_request",
                user_message="refund please",
                context_data={"customer_id": "test"},
            )

        # Flattened keys should be accessible
        assert result.get("eligible") is True
        assert result.get("order_id") == "X"
        assert result.get("refund_amount") == 50
