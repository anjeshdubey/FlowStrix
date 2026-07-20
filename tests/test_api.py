"""Tests for FlowStrix API Server.

Uses FastAPI TestClient with mocked LLM to test endpoints without
hitting the gateway.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from flowstrix.api.server import app, sessions


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
CUSTOMER_SUPPORT_SPEC = str(EXAMPLES_DIR / "customer_support.yaml")


@pytest.fixture
def client():
    """Create a test client with fresh session state."""
    from flowstrix.api.server import _langgraph_executors
    sessions._sessions.clear()
    _langgraph_executors.clear()
    return TestClient(app)


def mock_anthropic_response(text: str):
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


# --- Health ---


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


# --- Spec Inspection ---


class TestSpecInspection:
    def test_get_spec(self, client):
        response = client.get(f"/api/specs/{CUSTOMER_SUPPORT_SPEC}")
        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "customer_support"
        assert data["persona_name"] != ""
        assert len(data["journeys"]) >= 1

    def test_get_spec_journeys(self, client):
        response = client.get(f"/api/specs/{CUSTOMER_SUPPORT_SPEC}")
        data = response.json()
        journey_names = [j["name"] for j in data["journeys"]]
        assert "handle_refund_request" in journey_names

    def test_get_spec_not_found(self, client):
        response = client.get("/api/specs/nonexistent.yaml")
        assert response.status_code == 404

    def test_get_spec_invalid(self, client):
        # Use pyproject.toml as an invalid YAML spec file
        invalid_path = str(Path(__file__).parent.parent / "pyproject.toml")
        response = client.get(f"/api/specs/{invalid_path}")
        assert response.status_code == 422


# --- Journey Execution ---


class TestRunJourney:
    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.engine.executor.create_client")
    def test_run_success(self, mock_create_client, mock_gateway, client):
        """Test successful journey execution with mocked LLM."""
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        # Mock LLM responses (reason + respond steps)
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = [
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 299.99, "reason": "Within policy"}'
            ),
            mock_anthropic_response(
                "Your refund of $299.99 has been processed!"
            ),
        ]

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "I want a refund for my headphones",
            "context": {"customer_id": "cust_123"},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["journey_name"] == "handle_refund_request"
        assert data["execution_id"] != ""
        assert len(data["traces"]) > 0
        assert data["execution_time_ms"] > 0

    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.engine.executor.create_client")
    def test_run_hitl_pause(self, mock_create_client, mock_gateway, client):
        """Test HITL escalation pauses execution."""
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        # VIP customer triggers high-value branch → HITL
        mock_client.messages.create.side_effect = [
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 1249.99, "reason": "Eligible but high value"}'
            ),
        ]

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "Return the furniture",
            "context": {"customer_id": "cust_vip"},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "waiting_hitl"
        assert data["hitl_info"] is not None
        assert data["hitl_info"]["escalate_to"] != ""

    def test_run_spec_not_found(self, client):
        response = client.post("/api/run", json={
            "spec_path": "nonexistent.yaml",
            "journey": "test",
        })
        assert response.status_code == 404

    @patch("flowstrix.api.server.get_gateway_config")
    def test_run_journey_not_found(self, mock_gateway, client):
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "nonexistent_journey",
        })
        assert response.status_code == 404
        assert "nonexistent_journey" in response.json()["detail"]


# --- HITL Resume ---


class TestHITLResume:
    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.engine.executor.create_client")
    def test_resume_approved(self, mock_create_client, mock_gateway, client):
        """Test approving a HITL-paused execution."""
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = [
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 1249.99, "reason": "High value"}'
            ),
        ]

        # First: create a HITL-paused execution
        run_response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "Return furniture",
            "context": {"customer_id": "cust_vip"},
        })

        execution_id = run_response.json()["execution_id"]

        # Now: resume it
        resume_response = client.post(
            f"/api/executions/{execution_id}/resume",
            json={"approved": True, "notes": "Manager approved"},
        )

        assert resume_response.status_code == 200
        data = resume_response.json()
        assert data["status"] == "completed"
        assert data["context_data"]["hitl_approved"] is True

    def test_resume_not_found(self, client):
        response = client.post(
            "/api/executions/nonexistent/resume",
            json={"approved": True},
        )
        assert response.status_code == 404


# --- Execution History ---


class TestExecutionHistory:
    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.engine.executor.create_client")
    def test_get_execution(self, mock_create_client, mock_gateway, client):
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = [
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 299.99, "reason": "OK"}'
            ),
            mock_anthropic_response("Refund processed!"),
        ]

        # Run a journey
        run_response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "refund please",
            "context": {"customer_id": "cust_123"},
        })
        execution_id = run_response.json()["execution_id"]

        # Retrieve it
        get_response = client.get(f"/api/executions/{execution_id}")
        assert get_response.status_code == 200
        assert get_response.json()["execution_id"] == execution_id

    def test_get_execution_not_found(self, client):
        response = client.get("/api/executions/nonexistent")
        assert response.status_code == 404

    def test_list_executions_empty(self, client):
        response = client.get("/api/executions")
        assert response.status_code == 200
        assert response.json() == []


# --- SSE Streaming ---


class TestStreaming:
    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.engine.executor.create_client")
    def test_stream_endpoint(self, mock_create_client, mock_gateway, client):
        """Test SSE stream returns events."""
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = [
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 299.99, "reason": "OK"}'
            ),
            mock_anthropic_response("Done!"),
        ]

        response = client.post("/api/stream", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "refund",
            "context": {"customer_id": "cust_123"},
        })

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Parse SSE events
        body = response.text
        assert "event: step" in body
        assert "event: result" in body


# --- LangGraph Engine Selection ---


class TestLangGraphEngine:
    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.api.server._get_langgraph_executor")
    def test_run_with_langgraph_engine(self, mock_get_executor, mock_gateway, client):
        """Test that engine='langgraph' uses LangGraphExecutor."""
        from flowstrix.gateway import GatewayConfig
        from flowstrix.engine.context import ExecutionContext, StepStatus

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        # Mock executor returned by cache function
        mock_executor = MagicMock()
        mock_get_executor.return_value = mock_executor

        # Create a mock ExecutionContext to be returned by run()
        mock_ctx = ExecutionContext(
            journey_name="handle_refund_request",
            agent_id="customer_support",
        )
        mock_ctx.status = StepStatus.COMPLETED
        mock_executor.run.return_value = mock_ctx

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "I want a refund",
            "engine": "langgraph",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["journey_name"] == "handle_refund_request"

        # Verify cached executor was obtained and run() was called
        mock_get_executor.assert_called_once()
        mock_executor.run.assert_called_once_with(
            "handle_refund_request",
            user_message="I want a refund",
            context_data=None,
            thread_id=None,
            interaction_mode=None,
        )

    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.api.server._get_langgraph_executor")
    def test_run_with_thread_id_returns_thread_id(self, mock_get_executor, mock_gateway, client):
        """Test that thread_id is passed through and returned in response."""
        from flowstrix.gateway import GatewayConfig
        from flowstrix.engine.context import ExecutionContext, StepStatus

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_executor = MagicMock()
        mock_get_executor.return_value = mock_executor

        mock_ctx = ExecutionContext(
            journey_name="handle_refund_request",
            agent_id="customer_support",
        )
        mock_ctx.status = StepStatus.COMPLETED
        mock_ctx.thread_id = "test-thread-abc123"
        mock_executor.run.return_value = mock_ctx

        thread_id = "test-thread-abc123"

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "Continue our conversation",
            "engine": "langgraph",
            "thread_id": thread_id,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == thread_id

        # Verify thread_id was passed to executor.run()
        mock_executor.run.assert_called_once_with(
            "handle_refund_request",
            user_message="Continue our conversation",
            context_data=None,
            thread_id=thread_id,
            interaction_mode=None,
        )

    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.engine.executor.create_client")
    def test_run_default_uses_legacy_executor(self, mock_create_client, mock_gateway, client):
        """Test that no engine field (default) uses the legacy JourneyExecutor."""
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = [
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 299.99, "reason": "OK"}'
            ),
            mock_anthropic_response("Refund processed!"),
        ]

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "refund please",
            "context": {"customer_id": "cust_123"},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        # No thread_id for legacy
        assert data["thread_id"] is None

    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.engine.executor.create_client")
    def test_run_explicit_legacy_engine(self, mock_create_client, mock_gateway, client):
        """Test that engine='legacy' explicitly uses JourneyExecutor."""
        from flowstrix.gateway import GatewayConfig

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = [
            mock_anthropic_response(
                '{"eligible": true, "refund_amount": 299.99, "reason": "OK"}'
            ),
            mock_anthropic_response("Done!"),
        ]

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "refund",
            "context": {"customer_id": "cust_123"},
            "engine": "legacy",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"


# --- Handoff / Interaction Mode Tests ---


class TestHandoffAPI:
    """Test handoff-related API behavior."""

    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.api.server.LangGraphExecutor")
    def test_run_passes_interaction_mode(self, mock_lg_class, mock_gateway, client):
        """Test that interaction_mode is passed through to the executor."""
        from flowstrix.gateway import GatewayConfig
        from flowstrix.engine.context import ExecutionContext, StepStatus

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_executor = MagicMock()
        mock_lg_class.return_value = mock_executor

        mock_ctx = ExecutionContext(
            journey_name="handle_refund_request",
            agent_id="customer_support",
        )
        mock_ctx.status = StepStatus.COMPLETED
        mock_executor.run.return_value = mock_ctx

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "test",
            "engine": "langgraph",
            "interaction_mode": "structured",
        })

        assert response.status_code == 200
        mock_executor.run.assert_called_once_with(
            "handle_refund_request",
            user_message="test",
            context_data=None,
            thread_id=None,
            interaction_mode="structured",
        )

    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.api.server.LangGraphExecutor")
    def test_run_returns_handoff_info(self, mock_lg_class, mock_gateway, client):
        """Test that handoff_info is included in response when execution pauses at a handoff."""
        from flowstrix.gateway import GatewayConfig
        from flowstrix.engine.context import ExecutionContext, StepStatus

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_executor = MagicMock()
        mock_lg_class.return_value = mock_executor

        # Simulate a paused-at-handoff context
        mock_ctx = ExecutionContext(
            journey_name="handle_access_request",
            agent_id="it_access_agent",
        )
        mock_ctx.status = StepStatus.WAITING_HITL
        mock_ctx.waiting_for_human = True
        mock_ctx.handoff_form = {
            "step_name": "collect_justification",
            "transition_message": "Let me collect the details.",
            "output_key": "justification_form",
            "fields": [
                {"id": "reason", "label": "Reason", "field_type": "textarea", "required": True,
                 "options": [], "placeholder": "", "validation": None, "prefilled_value": None},
            ],
        }
        mock_executor.run.return_value = mock_ctx

        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "test",
            "engine": "langgraph",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "waiting_hitl"
        assert data["handoff_info"] is not None
        assert data["handoff_info"]["step_name"] == "collect_justification"
        assert data["handoff_info"]["output_key"] == "justification_form"
        assert len(data["handoff_info"]["fields"]) == 1
        assert data["handoff_info"]["fields"][0]["id"] == "reason"

    def test_resume_handoff_not_found(self, client):
        """Test resume_handoff returns 404 for unknown execution."""
        response = client.post("/api/executions/nonexistent/resume_handoff", json={
            "form_data": {"reason": "test"},
        })
        assert response.status_code == 404

    @patch("flowstrix.api.server.get_gateway_config")
    @patch("flowstrix.api.server.LangGraphExecutor")
    def test_resume_handoff_success(self, mock_lg_class, mock_gateway, client):
        """Test resume_handoff injects form data and resumes execution."""
        from flowstrix.gateway import GatewayConfig
        from flowstrix.engine.context import ExecutionContext, StepStatus

        mock_gateway.return_value = GatewayConfig(
            base_url="http://localhost:9999",
            auth_token="test-token",
            model="test-model",
        )

        mock_executor = MagicMock()
        mock_lg_class.return_value = mock_executor

        # First call: execution pauses at handoff
        mock_ctx_paused = ExecutionContext(
            journey_name="handle_access_request",
            agent_id="it_access_agent",
        )
        mock_ctx_paused.status = StepStatus.WAITING_HITL
        mock_ctx_paused.waiting_for_human = True
        mock_ctx_paused.handoff_form = {
            "step_name": "collect_justification",
            "transition_message": "Let me collect the details.",
            "output_key": "justification_form",
            "fields": [],
        }
        mock_executor.run.return_value = mock_ctx_paused

        # Run journey to get it into waiting state
        response = client.post("/api/run", json={
            "spec_path": CUSTOMER_SUPPORT_SPEC,
            "journey": "handle_refund_request",
            "message": "need access",
            "engine": "langgraph",
            "thread_id": "thread-handoff-1",
        })
        assert response.status_code == 200
        execution_id = response.json()["execution_id"]

        # Now resume with form data
        mock_ctx_resumed = ExecutionContext(
            journey_name="handle_access_request",
            agent_id="it_access_agent",
        )
        mock_ctx_resumed.status = StepStatus.COMPLETED
        mock_executor.resume_handoff.return_value = mock_ctx_resumed

        resume_response = client.post(f"/api/executions/{execution_id}/resume_handoff", json={
            "form_data": {
                "business_justification": "Data analysis for Q2 report",
                "duration": "30 days",
            },
        })

        assert resume_response.status_code == 200
        data = resume_response.json()
        assert data["status"] == "completed"

        # Verify resume_handoff was called with correct args
        mock_executor.resume_handoff.assert_called_once_with(
            "thread-handoff-1",
            form_data={
                "business_justification": "Data analysis for Q2 report",
                "duration": "30 days",
            },
        )
