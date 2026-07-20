"""Tests for parallel step execution (fan-out/fan-in).

Validates:
- Detection of independent consecutive lookup/tool steps as parallelizable
- Correct refusal to parallelize dependent steps
- Parallel group node produces same final state as sequential execution
- Integration with full graph compilation and execution
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from flowstrix.engine.graph import (
    _detect_parallel_groups,
    _extract_param_references,
    _make_parallel_node,
    compile_journey_graph,
)
from flowstrix.engine.nodes import NodeFactory
from flowstrix.engine.state import ExecutionState
from flowstrix.schema.models import (
    BranchStep,
    Journey,
    LookupStep,
    ReasonStep,
    RespondStep,
    ToolStep,
    Trigger,
)


# --- Helpers ---


def _make_lookup(name: str, tool: str, params: Dict[str, Any], output_key: str) -> LookupStep:
    """Create a LookupStep for testing."""
    return LookupStep(name=name, tool=tool, params=params, output_key=output_key)


def _make_tool(name: str, tool: str, params: Dict[str, Any], output_key: str) -> ToolStep:
    """Create a ToolStep for testing."""
    return ToolStep(name=name, tool=tool, params=params, output_key=output_key)


def _make_base_state() -> ExecutionState:
    """Create a minimal execution state for testing."""
    return {
        "journey_name": "test",
        "agent_id": "test_agent",
        "data": {"customer_id": "cust_123", "order_id": "ORD-001"},
        "messages": [],
        "traces": [],
        "current_step": "step_a",
        "next_step": None,
        "status": "running",
        "waiting_for_human": False,
        "hitl_request": None,
        "user_message": None,
        "steps_executed": [],
    }


# --- Detection Tests ---


class TestDetectParallelGroups:
    """Test _detect_parallel_groups correctly identifies parallelizable steps."""

    def test_two_independent_lookups_detected(self):
        """Two consecutive lookups with no cross-dependency are detected as parallelizable."""
        steps = [
            _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
            _make_lookup("fetch_profile", "get_profile", {"customer_id": "${customer_id}"}, "profile"),
        ]

        groups = _detect_parallel_groups(steps)

        assert len(groups) == 1
        assert len(groups[0]) == 2
        assert groups[0][0].name == "fetch_orders"
        assert groups[0][1].name == "fetch_profile"

    def test_dependent_lookups_not_parallelized(self):
        """Two consecutive lookups where the second depends on the first's output_key
        are NOT parallelized."""
        steps = [
            _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
            _make_lookup("fetch_order_details", "get_details", {"order_data": "${orders}"}, "details"),
        ]

        groups = _detect_parallel_groups(steps)

        assert len(groups) == 0

    def test_three_independent_lookups(self):
        """Three independent lookups should form one group of three."""
        steps = [
            _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
            _make_lookup("fetch_profile", "get_profile", {"customer_id": "${customer_id}"}, "profile"),
            _make_lookup("fetch_settings", "get_settings", {"customer_id": "${customer_id}"}, "settings"),
        ]

        groups = _detect_parallel_groups(steps)

        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_mixed_independent_and_dependent(self):
        """First two are independent, third depends on first — group should be size 2."""
        steps = [
            _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
            _make_lookup("fetch_profile", "get_profile", {"customer_id": "${customer_id}"}, "profile"),
            _make_lookup("enrich_orders", "enrich", {"data": "${orders}"}, "enriched"),
        ]

        groups = _detect_parallel_groups(steps)

        assert len(groups) == 1
        assert len(groups[0]) == 2
        assert groups[0][0].name == "fetch_orders"
        assert groups[0][1].name == "fetch_profile"

    def test_single_lookup_not_parallelized(self):
        """A single lookup step should not form a parallel group."""
        steps = [
            _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
        ]

        groups = _detect_parallel_groups(steps)
        assert len(groups) == 0

    def test_non_lookup_tool_steps_break_run(self):
        """Non-lookup/tool steps break the consecutive run."""
        steps = [
            _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
            ReasonStep(
                name="think",
                prompt="analyze",
                output_key="analysis",
            ),
            _make_lookup("fetch_profile", "get_profile", {"customer_id": "${customer_id}"}, "profile"),
        ]

        groups = _detect_parallel_groups(steps)
        assert len(groups) == 0

    def test_tool_steps_can_be_parallelized(self):
        """Tool steps (not just lookups) should be candidates for parallelization."""
        steps = [
            _make_tool("send_email", "send_email", {"to": "${email}"}, "email_result"),
            _make_tool("send_sms", "send_sms", {"phone": "${phone}"}, "sms_result"),
        ]

        groups = _detect_parallel_groups(steps)

        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_mixed_lookup_and_tool_parallelized(self):
        """A mix of independent lookup and tool steps should parallelize."""
        steps = [
            _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
            _make_tool("log_access", "log", {"user": "${customer_id}"}, "log_result"),
        ]

        groups = _detect_parallel_groups(steps)

        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_empty_params_are_independent(self):
        """Steps with empty params are always independent of previous steps."""
        steps = [
            _make_lookup("fetch_time", "get_time", {}, "current_time"),
            _make_lookup("fetch_config", "get_config", {}, "config"),
        ]

        groups = _detect_parallel_groups(steps)

        assert len(groups) == 1
        assert len(groups[0]) == 2


class TestExtractParamReferences:
    """Test _extract_param_references correctly identifies ${key} references."""

    def test_single_reference(self):
        step = _make_lookup("s", "t", {"id": "${customer_id}"}, "out")
        refs = _extract_param_references(step)
        assert refs == {"customer_id"}

    def test_multiple_references(self):
        step = _make_lookup("s", "t", {"id": "${customer_id}", "order": "${order_id}"}, "out")
        refs = _extract_param_references(step)
        assert refs == {"customer_id", "order_id"}

    def test_no_references(self):
        step = _make_lookup("s", "t", {"id": "literal_value"}, "out")
        refs = _extract_param_references(step)
        assert refs == set()

    def test_non_string_params_ignored(self):
        step = _make_lookup("s", "t", {"count": 5, "flag": True}, "out")
        refs = _extract_param_references(step)
        assert refs == set()


# --- Parallel Node Tests ---


class TestMakeParallelNode:
    """Test _make_parallel_node creates correct composite behavior."""

    def test_parallel_node_merges_data(self):
        """Parallel group node produces merged data from all sub-nodes."""

        def node_a(state: ExecutionState) -> dict:
            data = dict(state.get("data", {}))
            data["orders"] = [{"id": "ORD-1"}]
            return {
                "data": data,
                "traces": state["traces"] + [{"step_name": "a", "step_type": "lookup", "status": "completed", "output": None, "error": None, "duration_ms": 1.0}],
                "steps_executed": state["steps_executed"] + ["a"],
            }

        def node_b(state: ExecutionState) -> dict:
            data = dict(state.get("data", {}))
            data["profile"] = {"name": "Test User"}
            return {
                "data": data,
                "traces": state["traces"] + [{"step_name": "b", "step_type": "lookup", "status": "completed", "output": None, "error": None, "duration_ms": 2.0}],
                "steps_executed": state["steps_executed"] + ["b"],
            }

        parallel_fn = _make_parallel_node([node_a, node_b], ["a", "b"])
        state = _make_base_state()
        result = parallel_fn(state)

        # Both data keys should be present
        assert "orders" in result["data"]
        assert "profile" in result["data"]
        assert result["data"]["orders"] == [{"id": "ORD-1"}]
        assert result["data"]["profile"] == {"name": "Test User"}

    def test_parallel_node_concatenates_traces(self):
        """Traces from all sub-nodes are concatenated in order."""

        def node_a(state: ExecutionState) -> dict:
            return {
                "data": dict(state.get("data", {})),
                "traces": state["traces"] + [{"step_name": "a", "step_type": "lookup", "status": "completed", "output": "a_out", "error": None, "duration_ms": 1.0}],
                "steps_executed": state["steps_executed"] + ["a"],
            }

        def node_b(state: ExecutionState) -> dict:
            return {
                "data": dict(state.get("data", {})),
                "traces": state["traces"] + [{"step_name": "b", "step_type": "lookup", "status": "completed", "output": "b_out", "error": None, "duration_ms": 2.0}],
                "steps_executed": state["steps_executed"] + ["b"],
            }

        parallel_fn = _make_parallel_node([node_a, node_b], ["a", "b"])
        state = _make_base_state()
        result = parallel_fn(state)

        # Should have both traces
        assert len(result["traces"]) == 2
        assert result["traces"][0]["step_name"] == "a"
        assert result["traces"][1]["step_name"] == "b"

    def test_parallel_node_concatenates_steps_executed(self):
        """steps_executed from all sub-nodes are concatenated."""

        def node_a(state: ExecutionState) -> dict:
            return {
                "data": dict(state.get("data", {})),
                "traces": state["traces"] + [{"step_name": "a", "step_type": "lookup", "status": "completed", "output": None, "error": None, "duration_ms": 1.0}],
                "steps_executed": state["steps_executed"] + ["a"],
            }

        def node_b(state: ExecutionState) -> dict:
            return {
                "data": dict(state.get("data", {})),
                "traces": state["traces"] + [{"step_name": "b", "step_type": "lookup", "status": "completed", "output": None, "error": None, "duration_ms": 2.0}],
                "steps_executed": state["steps_executed"] + ["b"],
            }

        parallel_fn = _make_parallel_node([node_a, node_b], ["a", "b"])
        state = _make_base_state()
        result = parallel_fn(state)

        assert result["steps_executed"] == ["a", "b"]

    def test_parallel_node_same_result_as_sequential(self):
        """A parallel group node produces the same final state as running
        the same nodes sequentially."""

        def node_a(state: ExecutionState) -> dict:
            data = dict(state.get("data", {}))
            data["orders"] = [{"id": "ORD-1", "amount": 99.99}]
            return {
                "data": data,
                "traces": state["traces"] + [{"step_name": "fetch_orders", "step_type": "lookup", "status": "completed", "output": data["orders"], "error": None, "duration_ms": 5.0}],
                "steps_executed": state["steps_executed"] + ["fetch_orders"],
            }

        def node_b(state: ExecutionState) -> dict:
            data = dict(state.get("data", {}))
            data["profile"] = {"name": "Test", "tier": "gold"}
            return {
                "data": data,
                "traces": state["traces"] + [{"step_name": "fetch_profile", "step_type": "lookup", "status": "completed", "output": data["profile"], "error": None, "duration_ms": 3.0}],
                "steps_executed": state["steps_executed"] + ["fetch_profile"],
            }

        state = _make_base_state()

        # --- Sequential execution ---
        seq_result_a = node_a(state)
        # Apply result_a to state for sequential node_b
        seq_state_after_a: ExecutionState = {**state}  # type: ignore
        seq_state_after_a["data"] = seq_result_a["data"]
        seq_state_after_a["traces"] = seq_result_a["traces"]
        seq_state_after_a["steps_executed"] = seq_result_a["steps_executed"]
        seq_result_b = node_b(seq_state_after_a)

        # --- Parallel execution ---
        parallel_fn = _make_parallel_node([node_a, node_b], ["fetch_orders", "fetch_profile"])
        par_result = parallel_fn(state)

        # Both should have the same data keys
        assert "orders" in par_result["data"]
        assert "profile" in par_result["data"]
        assert par_result["data"]["orders"] == seq_result_b["data"]["orders"]
        assert par_result["data"]["profile"] == seq_result_b["data"]["profile"]

        # Both should have traces for both steps
        par_trace_names = [t["step_name"] for t in par_result["traces"]]
        seq_trace_names = [t["step_name"] for t in seq_result_b["traces"]]
        assert set(par_trace_names) == set(seq_trace_names)

        # Both should have both step names executed
        assert set(par_result["steps_executed"]) == set(seq_result_b["steps_executed"])

    def test_parallel_node_preserves_original_data(self):
        """Original state data keys are preserved in the merged result."""

        def node_a(state: ExecutionState) -> dict:
            data = dict(state.get("data", {}))
            data["new_key"] = "new_value"
            return {
                "data": data,
                "traces": state["traces"] + [{"step_name": "a", "step_type": "lookup", "status": "completed", "output": None, "error": None, "duration_ms": 1.0}],
                "steps_executed": state["steps_executed"] + ["a"],
            }

        parallel_fn = _make_parallel_node([node_a], ["a"])
        state = _make_base_state()
        result = parallel_fn(state)

        # Original keys preserved
        assert result["data"]["customer_id"] == "cust_123"
        assert result["data"]["order_id"] == "ORD-001"
        # New key added
        assert result["data"]["new_key"] == "new_value"


# --- Integration Tests ---


class TestParallelGraphCompilation:
    """Test that parallel groups integrate correctly with full graph compilation."""

    def test_compile_with_parallel_lookups(self):
        """A journey with two independent lookups should compile and run correctly."""
        from flowstrix.engine.executor import ToolRegistry
        from flowstrix.knowledge.loader import KnowledgeLoader
        from flowstrix.schema.models import AgentSpec, Persona

        # Define a simple journey with two independent lookups followed by a branch
        journey = Journey(
            name="test_parallel",
            description="Test parallel execution",
            trigger=Trigger(description="test"),
            steps=[
                _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
                _make_lookup("fetch_profile", "get_profile", {"customer_id": "${customer_id}"}, "profile"),
                BranchStep(
                    name="check_vip",
                    condition="${eligible}",
                    if_true="approve",
                    if_false="deny",
                ),
                RespondStep(name="approve", prompt="Approved"),
                RespondStep(name="deny", prompt="Denied"),
            ],
        )

        spec = AgentSpec(
            agent="test_agent",
            persona=Persona(name="Test", description="Test agent"),
            journeys=[journey],
        )

        tools = ToolRegistry()
        tools.register("get_orders", lambda customer_id="": {"orders": [{"id": "ORD-1"}]})
        tools.register("get_profile", lambda customer_id="": {"name": "Test", "tier": "gold"})

        mock_client = MagicMock()
        knowledge = KnowledgeLoader(spec)

        factory = NodeFactory(
            spec=spec,
            client=mock_client,
            model="test-model",
            tools=tools,
            knowledge=knowledge,
        )

        # Should compile without errors
        graph = compile_journey_graph(
            journey=journey,
            node_factory=factory,
            interrupt_on_hitl=False,
        )

        assert hasattr(graph, "invoke")

    def test_parallel_execution_produces_correct_data(self):
        """End-to-end: parallel lookups should produce merged data accessible to later steps."""
        from flowstrix.engine.executor import ToolRegistry
        from flowstrix.engine.executor_v2 import LangGraphExecutor
        from flowstrix.gateway import GatewayConfig
        from flowstrix.schema.models import AgentSpec, Persona

        # Journey: two independent lookups -> branch on a pre-set key
        journey = Journey(
            name="test_parallel_e2e",
            description="End-to-end parallel test",
            trigger=Trigger(description="test"),
            steps=[
                _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
                _make_lookup("fetch_profile", "get_profile", {"customer_id": "${customer_id}"}, "profile"),
                RespondStep(name="summarize", prompt="Summarize the data"),
            ],
        )

        spec = AgentSpec(
            agent="test_agent",
            persona=Persona(name="Test", description="Test agent"),
            journeys=[journey],
        )

        tools = ToolRegistry()
        tools.register("get_orders", lambda customer_id="": [{"id": "ORD-1", "amount": 50}])
        tools.register("get_profile", lambda customer_id="": {"name": "Alice", "vip": True})

        gateway_config = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        executor = LangGraphExecutor(
            spec,
            tools=tools,
            gateway_config=gateway_config,
        )

        # Mock the LLM response for the respond step
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Here is your summary."
        mock_response.content = [mock_content]

        from unittest.mock import patch
        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.return_value = mock_response

            result = executor.run(
                "test_parallel_e2e",
                user_message="show me",
                context_data={"customer_id": "cust_123"},
            )

        # Both lookup results should be in the data
        assert result.get("orders") == [{"id": "ORD-1", "amount": 50}]
        assert result.get("profile") == {"name": "Alice", "vip": True}

        # Both steps should appear in traces
        trace_names = [t.step_name for t in result.traces]
        assert "fetch_orders" in trace_names
        assert "fetch_profile" in trace_names

    def test_dependent_steps_still_sequential(self):
        """When steps have dependencies, they should NOT be parallelized and
        still execute correctly in sequence."""
        from flowstrix.engine.executor import ToolRegistry
        from flowstrix.engine.executor_v2 import LangGraphExecutor
        from flowstrix.gateway import GatewayConfig
        from flowstrix.schema.models import AgentSpec, Persona

        # Journey: lookup A -> lookup B (depends on A's output) -> respond
        journey = Journey(
            name="test_sequential",
            description="Test sequential execution preserved",
            trigger=Trigger(description="test"),
            steps=[
                _make_lookup("fetch_orders", "get_orders", {"customer_id": "${customer_id}"}, "orders"),
                _make_lookup("fetch_details", "get_order_details", {"order_data": "${orders}"}, "details"),
                RespondStep(name="summarize", prompt="Summarize"),
            ],
        )

        spec = AgentSpec(
            agent="test_agent",
            persona=Persona(name="Test", description="Test agent"),
            journeys=[journey],
        )

        # Track call order to verify sequential execution
        call_order: List[str] = []

        def get_orders(customer_id=""):
            call_order.append("get_orders")
            return [{"id": "ORD-1"}]

        def get_order_details(order_data=""):
            call_order.append("get_order_details")
            return {"id": "ORD-1", "items": ["Widget"]}

        tools = ToolRegistry()
        tools.register("get_orders", get_orders)
        tools.register("get_order_details", get_order_details)

        gateway_config = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        executor = LangGraphExecutor(
            spec,
            tools=tools,
            gateway_config=gateway_config,
        )

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Summary complete."
        mock_response.content = [mock_content]

        from unittest.mock import patch
        with patch.object(executor.client, "messages") as mock_messages:
            mock_messages.create.return_value = mock_response

            result = executor.run(
                "test_sequential",
                user_message="details please",
                context_data={"customer_id": "cust_123"},
            )

        # Both tools should have been called in order
        assert call_order == ["get_orders", "get_order_details"]

        # Results should be correct
        assert result.get("orders") == [{"id": "ORD-1"}]
        assert result.get("details") == {"id": "ORD-1", "items": ["Widget"]}
