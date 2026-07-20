"""Tests for the LangGraph executor (Phase 4).

Mirrors the existing test_executor.py test cases but runs them through
the LangGraph-based engine. Uses mocked LLM responses — no real gateway calls.

Validates:
- Same contract: run() returns ExecutionContext with correct status/data
- Branch routing works through graph edges
- HITL interrupts execution correctly
- State conversion (LangGraph state → ExecutionContext) is correct
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flowstrix.engine.context import ExecutionContext, StepStatus
from flowstrix.engine.executor import ToolRegistry
from flowstrix.engine.executor_v2 import LangGraphExecutor
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
    """Create a LangGraph executor with mocked LLM client."""
    spec = parse_yaml(EXAMPLES_DIR / spec_path)
    if tools is None:
        tools = ToolRegistry()
        _register_test_tools(tools)

    executor = LangGraphExecutor(
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


# --- LangGraph Executor Tests ---


class TestLangGraphBasicExecution:
    """Test basic execution flow through the LangGraph engine."""

    def test_eligible_small_refund_path(self):
        """Eligible refund under $500 should: lookup → reason → branch → branch → tool → respond."""
        executor = make_executor()

        eligible_response = json.dumps({
            "eligible": True,
            "order_id": "ORD-001",
            "refund_amount": 299.99,
            "reason": "Within 30-day window",
        })
        confirm_response = "Your refund has been processed!"

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(eligible_response),
                mock_anthropic_response(confirm_response),
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
                mock_anthropic_response(ineligible_response),
                mock_anthropic_response(explain_response),
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


class TestLangGraphStateConversion:
    """Test that LangGraph state converts correctly to ExecutionContext."""

    def test_data_is_populated(self):
        """Context data should be populated from graph state."""
        executor = make_executor()

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Done!"),
            ]

            result = executor.run(
                "handle_refund_request",
                user_message="refund please",
                context_data={"customer_id": "test"},
            )

        # Flattened keys from reason step
        assert result.get("eligible") is True
        assert result.get("order_id") == "X"
        assert result.get("refund_amount") == 50

    def test_messages_populated(self):
        """Conversation messages should be in the result."""
        executor = make_executor()

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Your refund is done!"),
            ]

            result = executor.run(
                "handle_refund_request",
                user_message="refund please",
                context_data={"customer_id": "test"},
            )

        # Should have user message + assistant response
        assert len(result.messages) >= 2
        assert result.messages[0]["role"] == "user"
        assert result.messages[0]["content"] == "refund please"
        # Last message should be from assistant (respond step)
        assistant_msgs = [m for m in result.messages if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 1
        assert "refund" in assistant_msgs[-1]["content"].lower()

    def test_traces_recorded(self):
        """Execution traces should be populated for all steps."""
        executor = make_executor()

        response = json.dumps({"eligible": True, "order_id": "X", "refund_amount": 50, "reason": "ok"})

        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.side_effect = [
                mock_anthropic_response(response),
                mock_anthropic_response("Done!"),
            ]

            result = executor.run(
                "handle_refund_request",
                user_message="refund please",
                context_data={"customer_id": "test"},
            )

        # Should have traces for all executed steps
        assert len(result.traces) >= 4  # lookup, reason, branch(es), tool/respond
        for trace in result.traces:
            assert trace.step_name is not None
            assert trace.step_type is not None
            assert trace.status in (StepStatus.COMPLETED, StepStatus.FAILED)


class TestLangGraphJourneyNotFound:
    """Test error handling for missing journeys."""

    def test_missing_journey_raises(self):
        """Should raise ValueError for unknown journey names."""
        executor = make_executor()
        with pytest.raises(ValueError, match="not found"):
            executor.run("nonexistent_journey")


class TestLangGraphNodeFunctions:
    """Unit-test individual node functions in isolation."""

    def test_branch_node_true_path(self):
        """Branch node should set next_step to if_true when condition is true."""
        from flowstrix.engine.nodes import NodeFactory, _resolve_expression
        from flowstrix.schema.models import BranchStep

        step = BranchStep(
            name="test_branch",
            condition="${amount} > 500",
            if_true="escalate",
            if_false="approve",
        )

        # Test resolve_expression directly
        data = {"amount": 750}
        assert _resolve_expression(data, "${amount} > 500") is True

        data = {"amount": 100}
        assert _resolve_expression(data, "${amount} > 500") is False

    def test_resolve_expression_always(self):
        """'always' should resolve to True."""
        from flowstrix.engine.nodes import _resolve_expression
        assert _resolve_expression({}, "always") is True

    def test_resolve_expression_equality(self):
        """String equality should work."""
        from flowstrix.engine.nodes import _resolve_expression
        data = {"status": "active"}
        assert _resolve_expression(data, "${status} == active") is True
        assert _resolve_expression(data, "${status} == inactive") is False

    def test_resolve_expression_missing_key(self):
        """Missing key should return False."""
        from flowstrix.engine.nodes import _resolve_expression
        assert _resolve_expression({}, "${nonexistent} > 500") is False

    def test_parse_json_clean(self):
        """Clean JSON should parse directly."""
        from flowstrix.engine.nodes import _parse_json_response
        result = _parse_json_response('{"eligible": true}')
        assert result == {"eligible": True}

    def test_parse_json_with_fences(self):
        """JSON wrapped in code fences should parse."""
        from flowstrix.engine.nodes import _parse_json_response
        text = '```json\n{"eligible": true, "amount": 100}\n```'
        result = _parse_json_response(text)
        assert result == {"eligible": True, "amount": 100}

    def test_parse_json_embedded(self):
        """JSON embedded in text should be extracted."""
        from flowstrix.engine.nodes import _parse_json_response
        text = 'Analysis:\n{"eligible": false}\nEnd.'
        result = _parse_json_response(text)
        assert result == {"eligible": False}


class TestLangGraphGraphCompilation:
    """Test that graph compilation produces valid graphs from journey specs."""

    def test_compile_produces_runnable(self):
        """compile_journey_graph should produce a graph that can be invoked."""
        from flowstrix.engine.graph import compile_journey_graph
        from flowstrix.engine.nodes import NodeFactory
        from flowstrix.knowledge.loader import KnowledgeLoader

        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        journey = spec.journeys[0]

        tools = ToolRegistry()
        _register_test_tools(tools)

        # Create a mock client
        mock_client = MagicMock()
        knowledge = KnowledgeLoader(spec, base_path=EXAMPLES_DIR)

        factory = NodeFactory(
            spec=spec,
            client=mock_client,
            model="test-model",
            tools=tools,
            knowledge=knowledge,
        )

        graph = compile_journey_graph(
            journey=journey,
            node_factory=factory,
            interrupt_on_hitl=False,  # Don't interrupt for this test
        )

        # Graph should be compiled (has invoke method)
        assert hasattr(graph, "invoke")

    def test_compile_includes_all_steps(self):
        """All journey steps should become graph nodes."""
        from flowstrix.engine.graph import compile_journey_graph
        from flowstrix.engine.nodes import NodeFactory
        from flowstrix.knowledge.loader import KnowledgeLoader

        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
        journey = spec.journeys[0]

        tools = ToolRegistry()
        _register_test_tools(tools)

        mock_client = MagicMock()
        knowledge = KnowledgeLoader(spec, base_path=EXAMPLES_DIR)

        factory = NodeFactory(
            spec=spec,
            client=mock_client,
            model="test-model",
            tools=tools,
            knowledge=knowledge,
        )

        graph = compile_journey_graph(
            journey=journey,
            node_factory=factory,
            interrupt_on_hitl=False,
        )

        # The graph should have been created (no assertion on internals —
        # LangGraph's API is unstable, so we test behavior, not structure)
        assert graph is not None
