"""Tests for FlowStrix schema parsing and validation."""

from pathlib import Path

import pytest

from flowstrix.schema.models import AgentSpec, StepType
from flowstrix.schema.parser import parse_yaml, parse_yaml_string, SchemaParseError


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


class TestSchemaValidation:
    """Test that valid YAML specs parse correctly."""

    def test_parse_customer_support_example(self):
        """The flagship example should parse without errors."""
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")

        assert spec.agent == "customer_support"
        assert spec.persona.name == "Alex"
        assert len(spec.journeys) == 2
        assert len(spec.knowledge) == 3
        assert len(spec.simulations) == 1

    def test_journey_structure(self):
        """Journeys should have correct step types."""
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")

        refund_journey = spec.journeys[0]
        assert refund_journey.name == "handle_refund_request"
        assert refund_journey.steps[0].type == "lookup"
        assert refund_journey.steps[1].type == "reason"
        assert refund_journey.steps[2].type == "branch"

    def test_hitl_step_parsed(self):
        """HITL steps should have escalation details."""
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")

        refund_journey = spec.journeys[0]
        hitl_steps = [s for s in refund_journey.steps if s.type == "hitl"]
        assert len(hitl_steps) == 1
        assert hitl_steps[0].escalate_to == "senior_support_agent"
        assert hitl_steps[0].timeout_seconds == 300

    def test_persona_guardrails(self):
        """Persona guardrails should be preserved."""
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")

        assert len(spec.persona.guardrails) == 4
        assert "Never promise refunds" in spec.persona.guardrails[0]

    def test_simulation_scenarios(self):
        """Simulations should have correct scenario structure."""
        spec = parse_yaml(EXAMPLES_DIR / "customer_support.yaml")

        sim = spec.simulations[0]
        assert sim.name == "refund_scenarios"
        assert len(sim.scenarios) == 3
        assert sim.num_runs_per_scenario == 5
        assert sim.pass_threshold == 0.8


class TestSchemaRejection:
    """Test that invalid specs produce clear errors."""

    def test_empty_yaml_rejected(self):
        with pytest.raises(SchemaParseError):
            parse_yaml_string("")

    def test_missing_agent_id_rejected(self):
        with pytest.raises(SchemaParseError):
            parse_yaml_string("""
persona:
  name: "Test"
  description: "Test agent"
journeys: []
""")

    def test_invalid_step_type_rejected(self):
        with pytest.raises(SchemaParseError):
            parse_yaml_string("""
agent: test
persona:
  name: "Test"
  description: "Test"
journeys:
  - name: test_journey
    description: "Test"
    trigger:
      description: "test"
    steps:
      - type: invalid_type
        name: bad_step
""")

    def test_missing_required_fields_rejected(self):
        with pytest.raises(SchemaParseError):
            parse_yaml_string("""
agent: test
persona:
  name: "Test"
  description: "Test"
journeys:
  - name: test_journey
    description: "Test"
    trigger:
      description: "test"
    steps:
      - type: reason
        name: incomplete_reason
        # missing: prompt, output_key
""")


class TestExpressionResolution:
    """Test context expression evaluation."""

    def test_simple_key_reference(self):
        from flowstrix.engine.context import ExecutionContext

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.set("eligible", True)

        assert ctx.resolve_expression("${eligible}") is True

    def test_numeric_comparison(self):
        from flowstrix.engine.context import ExecutionContext

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        ctx.set("refund_amount", 750)

        assert ctx.resolve_expression("${refund_amount} > 500") is True
        assert ctx.resolve_expression("${refund_amount} < 500") is False

    def test_always_condition(self):
        from flowstrix.engine.context import ExecutionContext

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        assert ctx.resolve_expression("always") is True

    def test_missing_key_is_falsy(self):
        from flowstrix.engine.context import ExecutionContext

        ctx = ExecutionContext(journey_name="test", agent_id="test")
        assert ctx.resolve_expression("${nonexistent}") is None
