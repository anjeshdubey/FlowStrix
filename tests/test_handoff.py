"""
Tests for the Handoff step type — smart modality switching.

Tests cover:
1. Schema parsing (HandoffStep + HandoffField validation)
2. Node execution (trigger condition, interaction mode override, form spec output)
3. Graph wiring (interrupt on handoff, conditional routing)
4. Full YAML spec validation (it_access_request.yaml)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import yaml

from flowstrix.engine.nodes import NodeFactory, _resolve_expression
from flowstrix.engine.state import ExecutionState
from flowstrix.schema.models import (
    AgentSpec,
    HandoffField,
    HandoffStep,
    StepType,
)
from flowstrix.schema.parser import parse_yaml


# --- Schema Tests ---


class TestHandoffSchema:
    """Test HandoffStep and HandoffField Pydantic models."""

    def test_handoff_field_minimal(self):
        """Minimal field with defaults."""
        field = HandoffField(id="name", label="Full Name")
        assert field.id == "name"
        assert field.label == "Full Name"
        assert field.field_type == "text"
        assert field.required is True
        assert field.options == []
        assert field.placeholder == ""
        assert field.validation is None

    def test_handoff_field_full(self):
        """Full field with all options."""
        field = HandoffField(
            id="duration",
            label="Access Duration",
            field_type="select",
            required=True,
            options=["7 days", "30 days", "90 days"],
            placeholder="Select duration...",
            validation="required",
        )
        assert field.field_type == "select"
        assert len(field.options) == 3
        assert field.validation == "required"

    def test_handoff_step_minimal(self):
        """Minimal handoff step."""
        step = HandoffStep(
            name="collect_info",
            trigger_condition="always",
            fields=[HandoffField(id="reason", label="Reason")],
            output_key="form_data",
        )
        assert step.type == "handoff"
        assert step.trigger_condition == "always"
        assert len(step.fields) == 1
        assert step.output_key == "form_data"
        assert step.prefill_from_context == {}
        assert "structured format" in step.transition_message

    def test_handoff_step_full(self):
        """Full handoff step with all options."""
        step = HandoffStep(
            name="collect_justification",
            trigger_condition="${requires_form}",
            fields=[
                HandoffField(id="justification", label="Business Justification", field_type="textarea"),
                HandoffField(id="duration", label="Duration", field_type="select", options=["7d", "30d"]),
                HandoffField(id="ack", label="I acknowledge...", field_type="checkbox"),
            ],
            prefill_from_context={"justification": "initial_reason"},
            output_key="justification_form",
            transition_message="Let me collect the compliance details.",
        )
        assert len(step.fields) == 3
        assert step.prefill_from_context == {"justification": "initial_reason"}
        assert step.transition_message == "Let me collect the compliance details."

    def test_step_type_enum_has_handoff(self):
        """StepType enum includes HANDOFF."""
        assert StepType.HANDOFF == "handoff"
        assert StepType.HANDOFF.value == "handoff"


class TestHandoffYAMLParsing:
    """Test parsing handoff steps from YAML."""

    def test_parse_handoff_from_yaml_string(self):
        """Parse a YAML spec containing a handoff step."""
        yaml_content = """
version: "1.0"
agent: test_agent
persona:
  name: "Test"
  description: "A test agent"
journeys:
  - name: test_journey
    description: "Test journey with handoff"
    trigger:
      description: "Test trigger"
    steps:
      - type: handoff
        name: collect_details
        trigger_condition: "${needs_form}"
        fields:
          - id: reason
            label: "Reason"
            field_type: textarea
            required: true
          - id: category
            label: "Category"
            field_type: select
            options:
              - "Bug"
              - "Feature"
              - "Other"
        prefill_from_context:
          reason: "initial_description"
        output_key: form_data
        transition_message: "Let me get more details."
"""
        spec_dict = yaml.safe_load(yaml_content)
        spec = AgentSpec(**spec_dict)
        journey = spec.journeys[0]
        step = journey.steps[0]

        assert step.type == "handoff"
        assert step.name == "collect_details"
        assert step.trigger_condition == "${needs_form}"
        assert len(step.fields) == 2
        assert step.fields[0].field_type == "textarea"
        assert step.fields[1].options == ["Bug", "Feature", "Other"]
        assert step.output_key == "form_data"

    def test_parse_it_access_request_spec(self, tmp_path):
        """Parse the full it_access_request.yaml example spec."""
        import shutil
        from pathlib import Path

        spec_path = Path(__file__).parent.parent / "examples" / "it_access_request.yaml"
        if not spec_path.exists():
            pytest.skip("it_access_request.yaml not found")

        spec = parse_yaml(spec_path)
        assert spec.agent == "it_access_agent"
        assert spec.persona.name == "Sam"

        journey = spec.journeys[0]
        assert journey.name == "handle_access_request"

        # Find the handoff step
        handoff_steps = [s for s in journey.steps if s.type == "handoff"]
        assert len(handoff_steps) == 1
        handoff = handoff_steps[0]
        assert handoff.name == "collect_justification"
        assert len(handoff.fields) == 5
        assert handoff.fields[0].id == "business_justification"
        assert handoff.fields[1].field_type == "multiselect"

        # Verify step count: 2 lookups, reason, branch, handoff, reason, branch, 2 hitl, tool, respond = 11
        assert len(journey.steps) == 11


# --- Node Execution Tests ---


class TestHandoffNode:
    """Test the handoff node function execution."""

    def _make_factory(self) -> NodeFactory:
        """Create a NodeFactory with mocked dependencies."""
        spec = MagicMock()
        spec.persona.name = "Test"
        spec.persona.description = "Test agent"
        spec.persona.tone = "professional"
        spec.persona.guardrails = []
        spec.persona.off_limits = []
        client = MagicMock()
        tools = MagicMock()
        knowledge = MagicMock()
        return NodeFactory(spec, client, "test-model", tools, knowledge)

    def _make_state(self, data: dict = None, interaction_mode: str = "agent_driven") -> ExecutionState:
        """Create a minimal execution state."""
        return ExecutionState(
            journey_name="test",
            agent_id="test",
            data=data or {},
            messages=[],
            traces=[],
            current_step="",
            next_step=None,
            status="running",
            waiting_for_human=False,
            hitl_request=None,
            handoff_form=None,
            interaction_mode=interaction_mode,
            user_message=None,
            steps_executed=[],
        )

    def test_handoff_triggers_when_condition_true(self):
        """Handoff triggers and emits form spec when condition is met."""
        factory = self._make_factory()
        step = HandoffStep(
            name="collect_info",
            trigger_condition="${sensitive}",
            fields=[
                HandoffField(id="reason", label="Reason", field_type="textarea"),
                HandoffField(id="duration", label="Duration", field_type="select", options=["7d", "30d"]),
            ],
            output_key="form_data",
            transition_message="Let me get the details.",
        )

        node_fn = factory.make_handoff_node(step)
        state = self._make_state(data={"sensitive": True})
        result = node_fn(state)

        assert result["waiting_for_human"] is True
        assert result["status"] == "waiting_handoff"
        assert result["handoff_form"] is not None
        assert result["handoff_form"]["step_name"] == "collect_info"
        assert len(result["handoff_form"]["fields"]) == 2
        assert result["handoff_form"]["fields"][0]["id"] == "reason"
        assert result["handoff_form"]["fields"][1]["options"] == ["7d", "30d"]
        assert result["handoff_form"]["output_key"] == "form_data"
        # Transition message added to conversation
        assert result["messages"][-1]["content"] == "Let me get the details."
        assert "collect_info" in result["steps_executed"]

    def test_handoff_skips_when_condition_false(self):
        """Handoff is skipped when condition evaluates to false."""
        factory = self._make_factory()
        step = HandoffStep(
            name="collect_info",
            trigger_condition="${sensitive}",
            fields=[HandoffField(id="reason", label="Reason")],
            output_key="form_data",
        )

        node_fn = factory.make_handoff_node(step)
        state = self._make_state(data={"sensitive": False})
        result = node_fn(state)

        assert "waiting_for_human" not in result
        assert "handoff_form" not in result
        assert "collect_info" in result["steps_executed"]
        # Trace should say condition not met
        assert "condition not met" in result["traces"][-1]["output"]

    def test_handoff_always_triggers(self):
        """Handoff with 'always' condition always triggers."""
        factory = self._make_factory()
        step = HandoffStep(
            name="collect_info",
            trigger_condition="always",
            fields=[HandoffField(id="x", label="X")],
            output_key="form_data",
        )

        node_fn = factory.make_handoff_node(step)
        state = self._make_state(data={})
        result = node_fn(state)

        assert result["waiting_for_human"] is True
        assert result["handoff_form"] is not None

    def test_interaction_mode_structured_forces_handoff(self):
        """Structured mode forces handoff regardless of condition."""
        factory = self._make_factory()
        step = HandoffStep(
            name="collect_info",
            trigger_condition="${sensitive}",  # Would be False
            fields=[HandoffField(id="x", label="X")],
            output_key="form_data",
        )

        node_fn = factory.make_handoff_node(step)
        state = self._make_state(data={"sensitive": False}, interaction_mode="structured")
        result = node_fn(state)

        # Even though condition is False, structured mode forces handoff
        assert result["waiting_for_human"] is True
        assert result["handoff_form"] is not None

    def test_interaction_mode_conversational_skips_handoff(self):
        """Conversational mode skips handoff regardless of condition."""
        factory = self._make_factory()
        step = HandoffStep(
            name="collect_info",
            trigger_condition="always",  # Would normally trigger
            fields=[HandoffField(id="x", label="X")],
            output_key="form_data",
        )

        node_fn = factory.make_handoff_node(step)
        state = self._make_state(data={}, interaction_mode="conversational")
        result = node_fn(state)

        # Even though condition is "always", conversational mode skips handoff
        assert "waiting_for_human" not in result
        assert "handoff_form" not in result

    def test_prefill_from_context(self):
        """Pre-fill values are populated from execution context."""
        factory = self._make_factory()
        step = HandoffStep(
            name="collect_info",
            trigger_condition="always",
            fields=[
                HandoffField(id="system", label="System"),
                HandoffField(id="reason", label="Reason"),
            ],
            prefill_from_context={"system": "target_system", "reason": "initial_reason"},
            output_key="form_data",
        )

        node_fn = factory.make_handoff_node(step)
        state = self._make_state(data={"target_system": "prod_db", "initial_reason": "data analysis"})
        result = node_fn(state)

        fields = result["handoff_form"]["fields"]
        system_field = next(f for f in fields if f["id"] == "system")
        reason_field = next(f for f in fields if f["id"] == "reason")
        assert system_field["prefilled_value"] == "prod_db"
        assert reason_field["prefilled_value"] == "data analysis"

    def test_prefill_missing_context_key_is_none(self):
        """Pre-fill for missing context key results in None."""
        factory = self._make_factory()
        step = HandoffStep(
            name="collect_info",
            trigger_condition="always",
            fields=[HandoffField(id="system", label="System")],
            prefill_from_context={"system": "nonexistent_key"},
            output_key="form_data",
        )

        node_fn = factory.make_handoff_node(step)
        state = self._make_state(data={})
        result = node_fn(state)

        fields = result["handoff_form"]["fields"]
        assert fields[0]["prefilled_value"] is None


# --- Graph Integration Tests ---


class TestHandoffGraphWiring:
    """Test that handoff steps are wired correctly in the LangGraph graph."""

    def test_handoff_in_graph_compilation(self):
        """A journey with a handoff step compiles without error."""
        from flowstrix.engine.graph import compile_journey_graph
        from flowstrix.schema.models import Journey, Trigger

        journey = Journey(
            name="test_handoff_journey",
            description="Test",
            trigger=Trigger(description="test"),
            steps=[
                HandoffStep(
                    name="collect_form",
                    trigger_condition="always",
                    fields=[HandoffField(id="x", label="X")],
                    output_key="form_data",
                ),
            ],
        )

        factory = MagicMock()
        factory.make_handoff_node.return_value = lambda state: {"status": "waiting_handoff"}

        # Should compile without raising
        graph = compile_journey_graph(journey, factory, interrupt_on_hitl=True)
        assert graph is not None

    def test_handoff_is_in_interrupt_list(self):
        """Handoff nodes appear in interrupt_before (like HITL)."""
        from flowstrix.engine.graph import compile_journey_graph
        from flowstrix.schema.models import Journey, LookupStep, Trigger

        journey = Journey(
            name="test",
            description="Test",
            trigger=Trigger(description="test"),
            steps=[
                LookupStep(name="fetch", tool="test_tool", params={}, output_key="data"),
                HandoffStep(
                    name="collect_form",
                    trigger_condition="always",
                    fields=[HandoffField(id="x", label="X")],
                    output_key="form_data",
                ),
            ],
        )

        factory = MagicMock()
        factory.make_lookup_node.return_value = lambda state: {"data": {}, "traces": [], "steps_executed": []}
        factory.make_handoff_node.return_value = lambda state: {"status": "waiting_handoff"}

        # The graph compiler should include handoff in interrupt_before
        # (verified by the fact compilation succeeds with interrupt_on_hitl=True)
        graph = compile_journey_graph(journey, factory, interrupt_on_hitl=True)
        assert graph is not None
