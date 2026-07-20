"""
Multi-Turn Evaluation Tests for WiFi Support Journey

Tests the full wifi_troubleshooting journey using the LangGraph executor
with multi-turn conversation. Each test simulates the exact Chat mode flow
a user would experience in the UI.

These are integration tests that hit the real LLM gateway.
"""

import pytest
from flowstrix.schema.parser import parse_yaml
from flowstrix.engine.executor_v2 import LangGraphExecutor
from flowstrix.engine.executor import ToolRegistry
from flowstrix.engine.context import StepStatus


@pytest.fixture
def executor():
    """Create a LangGraph executor for the wifi_support spec."""
    spec = parse_yaml("examples/wifi_support.yaml")
    return LangGraphExecutor(spec, tools=ToolRegistry())


class TestWifiMultiTurnHappyPath:
    """Full happy path: all steps fail → escalation to L2."""

    def test_turn1_greeting_and_device_ask(self, executor):
        """Turn 1: User reports issue, agent greets and asks for device info."""
        result = executor.run(
            "wifi_troubleshooting",
            user_message="My wifi keeps dropping every few minutes",
            context_data={"customer_id": "test_user"},
        )

        # Should stop at greet_and_ask_device (before wait_for_device_info)
        steps = [t.step_name for t in result.traces]
        assert "greet_and_ask_device" in steps
        assert "parse_device_info" not in steps  # hasn't run yet

        # Should have an assistant message (the greeting)
        assistant_msgs = [m for m in result.messages if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 1

        # Thread should be set for continuation
        assert result.thread_id is not None

    def test_turn2_device_identification(self, executor):
        """Turn 2: User provides device info, agent starts troubleshooting."""
        # Turn 1
        result = executor.run(
            "wifi_troubleshooting",
            user_message="My wifi keeps dropping every few minutes",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        # Turn 2 — provide device info
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Samsung Galaxy S23, Android 14",
            thread_id=thread_id,
        )

        steps = [t.step_name for t in result.traces]

        # Should have processed device info
        assert "wait_for_device_info" in steps
        assert "parse_device_info" in steps
        assert "check_device_info_clarity" in steps

        # Device identified → should go to acknowledge_device (not clarify_device)
        assert "acknowledge_device_and_start_steps" in steps
        assert "clarify_device" not in steps

    def test_turn3_router_restart_fails(self, executor):
        """Turn 3: User says restart didn't help, agent moves to cable check."""
        # Turns 1-2
        result = executor.run(
            "wifi_troubleshooting",
            user_message="My wifi keeps dropping every few minutes",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        result = executor.run(
            "wifi_troubleshooting",
            user_message="Samsung Galaxy S23, Android 14",
            thread_id=thread_id,
        )

        # Turn 3
        result = executor.run(
            "wifi_troubleshooting",
            user_message="I restarted it but still dropping",
            thread_id=thread_id,
        )

        steps = [t.step_name for t in result.traces]

        assert "evaluate_router_restart_result" in steps
        assert "check_after_router_restart" in steps
        assert "move_to_cable_check" in steps

        # Should NOT have resolved or escalated
        assert "respond_issue_resolved" not in steps
        assert "escalate_to_l2" not in steps

    def test_turn4_cables_fine(self, executor):
        """Turn 4: User says cables are fine, agent moves to forget network."""
        # Turns 1-3
        result = executor.run(
            "wifi_troubleshooting",
            user_message="My wifi keeps dropping every few minutes",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        result = executor.run(
            "wifi_troubleshooting",
            user_message="Samsung Galaxy S23, Android 14",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="I restarted it but still dropping",
            thread_id=thread_id,
        )

        # Turn 4
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Checked all cables, everything plugged in tight, still dropping",
            thread_id=thread_id,
        )

        steps = [t.step_name for t in result.traces]

        assert "evaluate_cable_check_result" in steps
        assert "check_after_cable_check" in steps
        assert "move_to_forget_network" in steps

        # Should NOT have resolved or escalated
        assert "respond_issue_resolved" not in steps
        assert "escalate_to_l2" not in steps

    def test_turn5_full_escalation(self, executor):
        """Turn 5: All steps fail, HITL escalation to L2 triggers."""
        # Full flow: turns 1-5
        result = executor.run(
            "wifi_troubleshooting",
            user_message="My wifi keeps dropping every few minutes",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        result = executor.run(
            "wifi_troubleshooting",
            user_message="Samsung Galaxy S23, Android 14",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="I restarted it but still dropping",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Checked all cables, everything plugged in tight, still dropping",
            thread_id=thread_id,
        )

        # Turn 5 — final step fails, should escalate
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Forgot the network and reconnected, still the same problem",
            thread_id=thread_id,
        )

        steps = [t.step_name for t in result.traces]

        # Should have gone through the forget/reconnect eval
        assert "evaluate_forget_reconnect_result" in steps
        assert "check_after_forget_reconnect" in steps

        # Should be waiting for HITL (L2 escalation)
        assert result.waiting_for_human is True
        assert result.hitl_request is not None
        assert result.hitl_request["escalate_to"] == "level_2_support"
        assert result.hitl_request["escalation_type"] == "handoff"

        # Context should include all troubleshooting results
        context = result.hitl_request.get("context", {})
        assert "device_type" in context or "restart_result" in context


class TestWifiMultiTurnResolvedEarly:
    """Happy path: issue resolved after router restart (turn 3)."""

    def test_resolved_after_restart(self, executor):
        """User says restart fixed it → agent celebrates, no further steps."""
        result = executor.run(
            "wifi_troubleshooting",
            user_message="My wifi isnt working at all",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        result = executor.run(
            "wifi_troubleshooting",
            user_message="Windows 11 laptop",
            thread_id=thread_id,
        )

        # User says restart worked
        result = executor.run(
            "wifi_troubleshooting",
            user_message="OK I restarted it and now its working!",
            thread_id=thread_id,
        )

        steps = [t.step_name for t in result.traces]

        assert "evaluate_router_restart_result" in steps
        assert "check_after_router_restart" in steps
        # Should go to resolved response, not cable check
        assert "respond_issue_resolved" in steps
        assert "move_to_cable_check" not in steps
        assert "escalate_to_l2" not in steps


class TestWifiMultiTurnUnclearDevice:
    """User gives vague device info, agent asks for clarification."""

    def test_unclear_device_triggers_clarification(self, executor):
        """Vague device info should trigger clarify_device branch."""
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Nothing is working",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        # Vague answer
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Just my computer",
            thread_id=thread_id,
        )

        steps = [t.step_name for t in result.traces]

        assert "parse_device_info" in steps
        assert "check_device_info_clarity" in steps
        # Should branch to clarify since info is unclear
        assert "clarify_device" in steps
        assert "acknowledge_device_and_start_steps" not in steps


class TestWifiMultiTurnResolvedAfterForget:
    """Issue resolved after forget/reconnect step."""

    def test_resolved_after_forget_reconnect(self, executor):
        """Full flow where forget network step fixes the issue."""
        result = executor.run(
            "wifi_troubleshooting",
            user_message="I cant connect to wifi on my phone",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        result = executor.run(
            "wifi_troubleshooting",
            user_message="iPhone 14, iOS 17",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Still not working after restarting",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Checked the cables, nothing changed",
            thread_id=thread_id,
        )

        # Forget network step works
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Oh wow it worked! Forgetting the network did it!",
            thread_id=thread_id,
        )

        steps = [t.step_name for t in result.traces]

        assert "evaluate_forget_reconnect_result" in steps
        assert "check_after_forget_reconnect" in steps
        assert "respond_issue_resolved" in steps
        assert "escalate_to_l2" not in steps


class TestWifiHITLResume:
    """After escalation, test HITL resume continues to handoff response."""

    def test_hitl_approve_continues_to_handoff(self, executor):
        """After L2 escalation is approved, agent notifies user of handoff."""
        # Run all 5 turns to reach HITL
        result = executor.run(
            "wifi_troubleshooting",
            user_message="WiFi keeps dropping",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        result = executor.run(
            "wifi_troubleshooting",
            user_message="Android phone, Samsung Galaxy",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Restarted router, still dropping",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Cables all fine, still same problem",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Forgot network and reconnected, still dropping every few minutes",
            thread_id=thread_id,
        )

        # Confirm we're at HITL
        assert result.waiting_for_human is True
        assert result.hitl_request["escalate_to"] == "level_2_support"

        # Resume with approval
        result = executor.resume(thread_id, approved=True, notes="Escalate to L2")

        steps = [t.step_name for t in result.traces]
        # After HITL resume, should continue to notify_l2_handoff
        assert "escalate_to_l2" in steps or "notify_l2_handoff" in steps


class TestWifiGuardrails:
    """Test guardrail behaviors."""

    def test_agent_never_asks_for_password(self, executor):
        """Agent should never ask for wifi password in its responses."""
        result = executor.run(
            "wifi_troubleshooting",
            user_message="My wifi stopped working",
            context_data={"customer_id": "test_user"},
        )
        thread_id = result.thread_id

        result = executor.run(
            "wifi_troubleshooting",
            user_message="Windows 10 PC",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Router restarted, no change",
            thread_id=thread_id,
        )
        result = executor.run(
            "wifi_troubleshooting",
            user_message="Cables are fine",
            thread_id=thread_id,
        )

        # At this point agent gives forget/reconnect instructions
        # Check agent never explicitly asks for password
        assistant_msgs = [m["content"].lower() for m in result.messages if m["role"] == "assistant"]
        for msg in assistant_msgs:
            assert "what is your password" not in msg
            assert "tell me your password" not in msg
            assert "share your password" not in msg
