"""Tests for FlowStrix Simulation Runner.

Tests the simulation evaluation logic with mocked LLM responses.
Verifies: pass/fail checks, LLM judge, journey inference, aggregation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import time

import pytest

from flowstrix.engine.context import ExecutionContext, StepStatus, StepTrace
from flowstrix.engine.executor import ToolRegistry
from flowstrix.gateway import GatewayConfig
from flowstrix.schema.parser import parse_yaml
from flowstrix.simulator.runner import (
    CheckResult,
    RunResult,
    ScenarioResult,
    SimulationResult,
    SimulationRunner,
    Verdict,
)


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _trace(step_name: str, step_type: str) -> StepTrace:
    """Create a completed StepTrace for testing."""
    return StepTrace(
        step_name=step_name,
        step_type=step_type,
        status=StepStatus.COMPLETED,
        started_at=time.time(),
    )


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


def make_runner():
    """Create a SimulationRunner with mocked gateway."""
    spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")
    tools = ToolRegistry()
    _register_test_tools(tools)

    runner = SimulationRunner(
        spec,
        tools=tools,
        gateway_config=mock_gateway_config(),
        knowledge_base_path=EXAMPLES_DIR,
    )
    return runner


# --- Data Model Tests ---


class TestVerdict:
    def test_verdict_values(self):
        assert Verdict.PASS == "pass"
        assert Verdict.FAIL == "fail"
        assert Verdict.ERROR == "error"


class TestRunResult:
    def test_passed_property(self):
        run = RunResult(run_number=1, verdict=Verdict.PASS)
        assert run.passed is True

    def test_failed_property(self):
        run = RunResult(run_number=1, verdict=Verdict.FAIL)
        assert run.passed is False

    def test_error_property(self):
        run = RunResult(run_number=1, verdict=Verdict.ERROR, error="boom")
        assert run.passed is False


class TestScenarioResult:
    def test_empty_scenario(self):
        sr = ScenarioResult(scenario_name="test", description="Test scenario")
        assert sr.pass_rate == 0.0
        assert sr.total_runs == 0
        assert sr.is_deterministic is True

    def test_all_pass(self):
        sr = ScenarioResult(
            scenario_name="test",
            description="Test",
            runs=[
                RunResult(run_number=1, verdict=Verdict.PASS),
                RunResult(run_number=2, verdict=Verdict.PASS),
                RunResult(run_number=3, verdict=Verdict.PASS),
            ],
        )
        assert sr.pass_rate == 1.0
        assert sr.pass_count == 3
        assert sr.verdict == Verdict.PASS
        assert sr.is_deterministic is True

    def test_all_fail(self):
        sr = ScenarioResult(
            scenario_name="test",
            description="Test",
            runs=[
                RunResult(run_number=1, verdict=Verdict.FAIL),
                RunResult(run_number=2, verdict=Verdict.FAIL),
            ],
        )
        assert sr.pass_rate == 0.0
        assert sr.verdict == Verdict.FAIL
        assert sr.is_deterministic is True

    def test_flaky_scenario(self):
        sr = ScenarioResult(
            scenario_name="test",
            description="Test",
            runs=[
                RunResult(run_number=1, verdict=Verdict.PASS),
                RunResult(run_number=2, verdict=Verdict.FAIL),
                RunResult(run_number=3, verdict=Verdict.PASS),
            ],
        )
        assert sr.pass_rate == pytest.approx(2 / 3)
        assert sr.is_deterministic is False

    def test_pass_threshold(self):
        sr = ScenarioResult(
            scenario_name="test",
            description="Test",
            pass_threshold=0.5,
            runs=[
                RunResult(run_number=1, verdict=Verdict.PASS),
                RunResult(run_number=2, verdict=Verdict.FAIL),
            ],
        )
        assert sr.verdict == Verdict.PASS  # 50% >= 0.5 threshold


class TestSimulationResult:
    def test_overall_pass(self):
        result = SimulationResult(
            suite_name="test",
            scenarios=[
                ScenarioResult(
                    scenario_name="s1",
                    description="",
                    runs=[RunResult(run_number=1, verdict=Verdict.PASS)],
                ),
                ScenarioResult(
                    scenario_name="s2",
                    description="",
                    runs=[RunResult(run_number=1, verdict=Verdict.PASS)],
                ),
            ],
        )
        assert result.overall_verdict == Verdict.PASS
        assert result.scenarios_passed == 2
        assert result.scenarios_total == 2
        assert result.total_runs == 2
        assert result.total_passes == 2

    def test_overall_fail(self):
        result = SimulationResult(
            suite_name="test",
            scenarios=[
                ScenarioResult(
                    scenario_name="s1",
                    description="",
                    runs=[RunResult(run_number=1, verdict=Verdict.PASS)],
                ),
                ScenarioResult(
                    scenario_name="s2",
                    description="",
                    runs=[RunResult(run_number=1, verdict=Verdict.FAIL)],
                ),
            ],
        )
        assert result.overall_verdict == Verdict.FAIL
        assert result.scenarios_passed == 1

    def test_flaky_scenarios_list(self):
        result = SimulationResult(
            suite_name="test",
            scenarios=[
                ScenarioResult(
                    scenario_name="stable",
                    description="",
                    runs=[
                        RunResult(run_number=1, verdict=Verdict.PASS),
                        RunResult(run_number=2, verdict=Verdict.PASS),
                    ],
                ),
                ScenarioResult(
                    scenario_name="flaky",
                    description="",
                    runs=[
                        RunResult(run_number=1, verdict=Verdict.PASS),
                        RunResult(run_number=2, verdict=Verdict.FAIL),
                    ],
                ),
            ],
        )
        assert result.flaky_scenarios == ["flaky"]


# --- Evaluation Logic Tests ---


class TestEvaluateRun:
    """Test _evaluate_run checks without hitting LLM."""

    def test_expected_steps_pass(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.expected_steps = ["fetch_order_data", "evaluate_eligibility"]
        scenario.must_not = []
        scenario.expected_outcome = None  # Skip LLM judge

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = [
            _trace("fetch_order_data", "lookup"),
            _trace("evaluate_eligibility", "reason"),
            _trace("respond", "respond"),
        ]

        checks = runner._evaluate_run(ctx, scenario)

        expected_check = next(c for c in checks if c.check_name == "expected_steps")
        assert expected_check.verdict == Verdict.PASS

    def test_expected_steps_fail_missing(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.expected_steps = ["fetch_order_data", "process_refund_action"]
        scenario.must_not = []
        scenario.expected_outcome = None

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = [
            _trace("fetch_order_data", "lookup"),
        ]

        checks = runner._evaluate_run(ctx, scenario)

        expected_check = next(c for c in checks if c.check_name == "expected_steps")
        assert expected_check.verdict == Verdict.FAIL
        assert "process_refund_action" in expected_check.detail

    def test_must_not_pass(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.expected_steps = []
        scenario.must_not = ["escalate_high_value"]
        scenario.expected_outcome = None

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = [
            _trace("fetch_order_data", "lookup"),
        ]

        checks = runner._evaluate_run(ctx, scenario)

        must_not_check = next(c for c in checks if c.check_name == "must_not")
        assert must_not_check.verdict == Verdict.PASS

    def test_must_not_fail_violated(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.expected_steps = []
        scenario.must_not = ["escalate_high_value"]
        scenario.expected_outcome = None

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = [
            _trace("escalate_high_value", "hitl"),
        ]

        checks = runner._evaluate_run(ctx, scenario)

        must_not_check = next(c for c in checks if c.check_name == "must_not")
        assert must_not_check.verdict == Verdict.FAIL
        assert "escalate_high_value" in must_not_check.detail

    def test_execution_status_fail(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.expected_steps = []
        scenario.must_not = []
        scenario.expected_outcome = None

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.FAILED
        ctx.traces = []

        checks = runner._evaluate_run(ctx, scenario)

        status_check = next(c for c in checks if c.check_name == "execution_status")
        assert status_check.verdict == Verdict.FAIL

    def test_execution_status_pass(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.expected_steps = []
        scenario.must_not = []
        scenario.expected_outcome = None

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = []

        checks = runner._evaluate_run(ctx, scenario)

        status_check = next(c for c in checks if c.check_name == "execution_status")
        assert status_check.verdict == Verdict.PASS


class TestLLMJudge:
    """Test _llm_judge with mocked LLM responses."""

    def test_judge_pass(self):
        runner = make_runner()

        # Mock the judge client
        runner.judge_client = MagicMock()
        runner.judge_client.messages.create.return_value = mock_anthropic_response(
            "PASS\nThe refund was processed correctly for the eligible item."
        )

        scenario = MagicMock()
        scenario.description = "Customer requests refund for recent purchase"
        scenario.expected_outcome = "Refund is processed successfully"

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = [
            _trace("fetch_order_data", "lookup"),
            _trace("process_refund_action", "tool"),
        ]
        ctx.messages = [
            {"role": "user", "content": "I want a refund"},
            {"role": "assistant", "content": "Your refund has been processed!"},
        ]

        result = runner._llm_judge(ctx, scenario)
        assert result.verdict == Verdict.PASS
        assert "processed correctly" in result.detail

    def test_judge_fail(self):
        runner = make_runner()

        runner.judge_client = MagicMock()
        runner.judge_client.messages.create.return_value = mock_anthropic_response(
            "FAIL\nThe agent escalated when it should have auto-approved."
        )

        scenario = MagicMock()
        scenario.description = "Small refund request"
        scenario.expected_outcome = "Refund is auto-approved without human review"

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = [_trace("escalate_high_value", "hitl")]
        ctx.messages = []

        result = runner._llm_judge(ctx, scenario)
        assert result.verdict == Verdict.FAIL

    def test_judge_error_on_exception(self):
        runner = make_runner()

        runner.judge_client = MagicMock()
        runner.judge_client.messages.create.side_effect = Exception("Connection timeout")

        scenario = MagicMock()
        scenario.description = "Test"
        scenario.expected_outcome = "Something happens"

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.status = StepStatus.COMPLETED
        ctx.traces = []
        ctx.messages = []

        result = runner._llm_judge(ctx, scenario)
        assert result.verdict == Verdict.ERROR
        assert "Connection timeout" in result.detail


# --- Journey Inference Tests ---


class TestInferJourney:
    def test_infer_from_keywords(self):
        runner = make_runner()

        scenario = MagicMock()
        scenario.description = "Customer wants a refund for broken headphones"
        scenario.user_messages = ["I want my money back"]
        scenario.expected_steps = []

        result = runner._infer_journey(scenario)
        assert result == "handle_refund_request"

    def test_infer_from_expected_steps(self):
        runner = make_runner()

        scenario = MagicMock()
        scenario.description = "Some scenario"
        scenario.user_messages = []
        scenario.expected_steps = ["fetch_order_data", "evaluate_eligibility"]

        result = runner._infer_journey(scenario)
        assert result == "handle_refund_request"

    def test_infer_fallback_to_first(self):
        runner = make_runner()

        scenario = MagicMock()
        scenario.description = "completely unrelated topic"
        scenario.user_messages = []
        scenario.expected_steps = []

        result = runner._infer_journey(scenario)
        # Should fallback to first journey
        assert result == runner.spec.journeys[0].name


# --- Context Building Tests ---


class TestBuildScenarioContext:
    def test_standard_customer(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.description = "Customer wants refund for headphones"

        ctx = runner._build_scenario_context(scenario)
        assert ctx["customer_id"] == "cust_standard"

    def test_vip_customer(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.description = "Customer returning $750 furniture order"

        ctx = runner._build_scenario_context(scenario)
        assert ctx["customer_id"] == "cust_vip"

    def test_old_order_customer(self):
        runner = make_runner()
        scenario = MagicMock()
        scenario.description = "Customer with purchase from 45 days ago"

        ctx = runner._build_scenario_context(scenario)
        assert ctx["customer_id"] == "cust_old"


# --- Suite Finding Tests ---


class TestFindSuites:
    def test_find_by_name(self):
        runner = make_runner()
        suites = runner._find_suites("refund_scenarios")
        assert len(suites) == 1
        assert suites[0].name == "refund_scenarios"

    def test_find_all(self):
        runner = make_runner()
        suites = runner._find_suites(None)
        assert len(suites) == len(runner.spec.simulations)

    def test_find_nonexistent_raises(self):
        runner = make_runner()
        with pytest.raises(ValueError, match="not found"):
            runner._find_suites("nonexistent_suite")


# --- Integration: Full Run With Mocked LLM ---


class TestFullSimulationRun:
    """Test run_suite with mocked LLM to verify end-to-end flow."""

    @patch("flowstrix.engine.executor.create_client")
    @patch("flowstrix.simulator.runner.create_client")
    def test_single_run_standard_refund(self, mock_sim_client, mock_exec_client):
        """Test a single run of the standard refund scenario."""
        # Mock executor LLM (reason + respond steps)
        exec_client = MagicMock()
        mock_exec_client.return_value = exec_client

        # The executor will call messages.create for reason and respond steps
        exec_client.messages.create.side_effect = [
            # reason step: eligibility evaluation
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 299.99, "reason": "Within 30-day window"}'
            ),
            # respond step: customer message
            mock_anthropic_response(
                "Your refund of $299.99 has been processed! You should see it in 3-5 business days."
            ),
        ]

        # Mock judge LLM
        judge_client = MagicMock()
        mock_sim_client.return_value = judge_client
        judge_client.messages.create.return_value = mock_anthropic_response(
            "PASS\nRefund was processed successfully for the eligible order."
        )

        runner = make_runner()
        # Override the judge client with our mock
        runner.judge_client = judge_client

        result = runner.run_suite("refund_scenarios", num_runs_override=1)

        # At least one scenario should have run
        assert result.scenarios_total >= 1
        assert result.total_runs >= 1
