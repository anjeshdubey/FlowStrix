"""
FlowStrix API Server — FastAPI + SSE streaming for real-time agent execution.

Exposes the journey executor over HTTP so FlowStrix is demo-able in a browser.
Supports synchronous execution, Server-Sent Events streaming, and HITL resume.

Start with: flowstrix serve
Or directly: uvicorn flowstrix.api.server:app --reload
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from flowstrix.api.models import (
    GhostwriteJourneyResponse,
    GhostwriteRequest,
    GhostwriteResponse,
    GhostwriteStepResponse,
    HandoffInfo,
    HandoffResumeRequest,
    HealthResponse,
    HITLInfo,
    HITLResumeRequest,
    JourneyDetail,
    JourneyStepDetail,
    JourneySummary,
    RunRequest,
    RunResponse,
    SpecSummary,
    StepEvent,
    StepTraceResponse,
)
from flowstrix.api.session import ExecutionSession, SessionManager
from flowstrix.engine.context import ExecutionContext, StepStatus
from flowstrix.engine.executor import JourneyExecutor, ToolRegistry
from flowstrix.engine.executor_v2 import LangGraphExecutor
from flowstrix.gateway import GatewayConfig, GatewayConfigError
from flowstrix.schema.parser import SchemaParseError, parse_yaml

# Load .env
load_dotenv()

# --- App Setup ---

app = FastAPI(
    title="FlowStrix API",
    description="Agent-native workflow engine — execute, stream, and test AI agent journeys.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permissive for POC; lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Shared State ---

sessions = SessionManager()
_gateway_config: Optional[GatewayConfig] = None

# Project root — for resolving relative spec paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# --- LangGraph Executor Cache ---
# Persistent executor instances per spec path. Keeps thread state alive across
# requests so multi-turn conversations work (same executor = same _threads dict).
_langgraph_executors: dict[str, LangGraphExecutor] = {}


def _get_langgraph_executor(
    spec_path: str,
    spec: Any,
    tools: ToolRegistry,
    gateway_config: Optional[GatewayConfig],
    model: Optional[str],
    knowledge_base_path: Optional[Path],
) -> LangGraphExecutor:
    """Get or create a cached LangGraph executor for a spec.

    The executor holds in-memory thread state (paused graphs). Reusing the
    same instance across requests is what makes multi-turn work.
    """
    if spec_path not in _langgraph_executors:
        _langgraph_executors[spec_path] = LangGraphExecutor(
            spec,
            tools=tools,
            gateway_config=gateway_config,
            model=model,
            knowledge_base_path=knowledge_base_path,
        )
    return _langgraph_executors[spec_path]


def _resolve_spec_path(spec_path: str) -> Path:
    """Resolve a spec path — try absolute, then relative to CWD, then relative to project root."""
    p = Path(spec_path)
    if p.is_absolute() and p.exists():
        return p
    # Try relative to CWD
    if p.exists():
        return p.resolve()
    # Try relative to project root
    project_relative = _PROJECT_ROOT / spec_path
    if project_relative.exists():
        return project_relative
    return p  # Return as-is; caller handles 404


def get_gateway_config() -> GatewayConfig:
    """Lazy-load gateway config from environment."""
    global _gateway_config
    if _gateway_config is None:
        _gateway_config = GatewayConfig.from_env()
    return _gateway_config


def _register_demo_tools(tools: ToolRegistry) -> None:
    """Register demo tools (same as CLI)."""

    def get_orders_by_customer_id(customer_id: str = "demo_customer") -> dict:
        if "vip" in customer_id.lower() or "high" in customer_id.lower():
            return {
                "customer_id": customer_id,
                "orders": [
                    {
                        "order_id": "ORD-2024-VIP",
                        "item": "Premium Furniture Set",
                        "date": "2024-01-14",
                        "amount": 1249.99,
                        "status": "delivered",
                        "days_since_purchase": 4,
                    }
                ],
            }
        if "old" in customer_id.lower() or "expired" in customer_id.lower():
            return {
                "customer_id": customer_id,
                "orders": [
                    {
                        "order_id": "ORD-2024-OLD",
                        "item": "Wireless Speaker",
                        "date": "2023-11-20",
                        "amount": 179.99,
                        "status": "delivered",
                        "days_since_purchase": 60,
                    }
                ],
            }
        return {
            "customer_id": customer_id,
            "orders": [
                {
                    "order_id": "ORD-2024-001",
                    "item": "Wireless Headphones",
                    "date": "2024-01-15",
                    "amount": 299.99,
                    "status": "delivered",
                    "days_since_purchase": 3,
                }
            ],
        }

    def process_refund(order_id: str = "ORD-2024-001", amount: float = 0.0) -> dict:
        return {
            "refund_id": "REF-2024-100",
            "order_id": order_id,
            "amount": amount,
            "status": "processed",
        }

    def send_email(to: str = "", subject: str = "", body: str = "") -> dict:
        return {"status": "sent", "to": to, "subject": subject}

    tools.register("get_orders_by_customer_id", get_orders_by_customer_id)
    tools.register("process_refund", process_refund)
    tools.register("send_email", send_email)

    # --- IT Access Request Demo Tools ---

    def get_employee_by_id(employee_id: str = "emp_001") -> dict:
        """Look up employee info by ID."""
        employees = {
            "emp_001": {
                "employee_id": "emp_001",
                "name": "Alex Chen",
                "role": "Senior Data Analyst",
                "team": "Business Intelligence",
                "manager": "Sarah Kim",
                "tenure_days": 450,
                "department": "Analytics",
            },
            "emp_002": {
                "employee_id": "emp_002",
                "name": "Jordan Rivera",
                "role": "Junior Developer",
                "team": "Platform Engineering",
                "manager": "Mike Torres",
                "tenure_days": 15,
                "department": "Engineering",
            },
        }
        return employees.get(
            employee_id,
            {
                "employee_id": employee_id,
                "name": "Demo Employee",
                "role": "Software Engineer",
                "team": "Product",
                "manager": "Jane Doe",
                "tenure_days": 200,
                "department": "Engineering",
            },
        )

    def classify_access_target(request_text: str = "") -> dict:
        """Classify the access target from the request text."""
        text_lower = request_text.lower()
        if any(
            kw in text_lower
            for kw in ["production", "prod", "customer data", "database"]
        ):
            return {
                "target_system": "production_database",
                "category": "data_store",
                "sensitivity": "high",
                "current_access": "none",
            }
        elif any(kw in text_lower for kw in ["export", "external", "pii"]):
            return {
                "target_system": "data_export_api",
                "category": "data_export",
                "sensitivity": "critical",
                "current_access": "none",
            }
        elif any(kw in text_lower for kw in ["slack", "channel"]):
            return {
                "target_system": "slack_channel",
                "category": "communication",
                "sensitivity": "low",
                "current_access": "none",
            }
        elif any(kw in text_lower for kw in ["staging", "sandbox", "dev"]):
            return {
                "target_system": "staging_environment",
                "category": "environment",
                "sensitivity": "medium",
                "current_access": "none",
            }
        return {
            "target_system": "unknown_system",
            "category": "general",
            "sensitivity": "medium",
            "current_access": "none",
        }

    def provision_access(
        employee_id: str = "",
        target_system: str = "",
        access_level: str = "standard",
        duration_days: str = "30",
    ) -> dict:
        """Provision access to a system for an employee."""
        return {
            "status": "provisioned",
            "employee_id": employee_id,
            "target_system": target_system,
            "access_level": access_level,
            "duration_days": int(duration_days),
            "provisioned_at": "2026-05-31T10:00:00Z",
            "expires_at": f"2026-06-{min(30, int(duration_days))}T10:00:00Z",
            "ticket_id": "ACC-2026-001",
        }

    tools.register("get_employee_by_id", get_employee_by_id)
    tools.register("classify_access_target", classify_access_target)
    tools.register("provision_access", provision_access)


def _build_run_response(
    session: ExecutionSession, ctx: ExecutionContext
) -> RunResponse:
    """Convert ExecutionContext to API response."""
    traces = []
    for t in ctx.traces:
        output_preview = None
        if t.output:
            output_preview = str(t.output)[:100]
        usage = t.llm_usage or {}
        traces.append(
            StepTraceResponse(
                step_name=t.step_name,
                step_type=t.step_type,
                status=t.status.value,
                duration_ms=t.duration_ms,
                output_preview=output_preview,
                tokens_in=usage.get("tokens_in"),
                tokens_out=usage.get("tokens_out"),
            )
        )

    hitl_info = None
    if ctx.waiting_for_human and ctx.hitl_request:
        hitl_info = HITLInfo(
            escalation_type=ctx.hitl_request.get("escalation_type", ""),
            escalate_to=ctx.hitl_request.get("escalate_to", ""),
            context=ctx.hitl_request.get("context", {}),
            step_name=ctx.hitl_request.get("step_name", ""),
        )

    handoff_info = None
    if ctx.waiting_for_human and ctx.handoff_form:
        handoff_info = HandoffInfo(
            step_name=ctx.handoff_form.get("step_name", ""),
            transition_message=ctx.handoff_form.get("transition_message", ""),
            output_key=ctx.handoff_form.get("output_key", ""),
            fields=ctx.handoff_form.get("fields", []),
        )

    execution_time = 0.0
    if ctx.completed_at and ctx.started_at:
        execution_time = (ctx.completed_at - ctx.started_at) * 1000
    elif ctx.started_at:
        execution_time = (time.time() - ctx.started_at) * 1000

    # Prefer thread_id from execution context (may be auto-generated by executor)
    # Fall back to session's thread_id (from original request)
    resolved_thread_id = getattr(ctx, "thread_id", None) or session.thread_id

    return RunResponse(
        execution_id=session.id,
        status=ctx.status.value,
        journey_name=ctx.journey_name,
        traces=traces,
        context_data=ctx.data,
        messages=ctx.messages,
        hitl_info=hitl_info,
        handoff_info=handoff_info,
        execution_time_ms=execution_time,
        thread_id=resolved_thread_id,
    )


# --- Health ---


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check server health and gateway connectivity."""
    try:
        config = get_gateway_config()
        return HealthResponse(
            status="ok",
            model=config.model,
            provider=config.provider,
            gateway_configured=True,
        )
    except GatewayConfigError:
        return HealthResponse(
            status="ok",
            gateway_configured=False,
        )


# --- Spec Management ---


@app.get("/api/specs")
async def list_specs():
    """List all available agent spec YAML files in the examples directory."""
    examples_dir = _PROJECT_ROOT / "examples"
    specs = []
    if examples_dir.exists():
        for f in sorted(examples_dir.glob("*.yaml")):
            try:
                spec = parse_yaml(f)
                specs.append(
                    {
                        "path": f"examples/{f.name}",
                        "agent": spec.agent,
                        "persona_name": spec.persona.name,
                        "journey_count": len(spec.journeys),
                    }
                )
            except Exception:
                # Skip invalid files
                specs.append(
                    {
                        "path": f"examples/{f.name}",
                        "agent": f.stem,
                        "persona_name": "",
                        "journey_count": 0,
                    }
                )
    return specs


class SaveSpecRequest(BaseModel):
    """Request to save a YAML spec to disk."""

    filename: str = Field(description="Filename (e.g. 'pto_handler.yaml')")
    yaml_content: str = Field(description="Full YAML content to save")


@app.post("/api/specs")
async def save_spec(request: SaveSpecRequest):
    """Save a generated spec YAML to the examples directory."""
    # Sanitize filename
    filename = request.filename.strip()
    if not filename.endswith(".yaml"):
        filename += ".yaml"
    # Prevent path traversal
    filename = Path(filename).name

    examples_dir = _PROJECT_ROOT / "examples"
    examples_dir.mkdir(exist_ok=True)
    target = examples_dir / filename

    # Validate YAML parses correctly
    try:
        import yaml as yaml_lib

        yaml_lib.safe_load(request.yaml_content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}")

    # Write file
    target.write_text(request.yaml_content)

    return {
        "path": f"examples/{filename}",
        "saved": True,
        "message": f"Spec saved to examples/{filename}",
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile):
    """Upload a file and extract text content for use as a ghostwriter prompt.

    Supports: .txt, .md, .yaml, .yml, .json, .docx, .pdf
    Returns the extracted text which can be fed into the ghostwriter.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Get file extension
    ext = Path(file.filename).suffix.lower()
    allowed = {".txt", ".md", ".yaml", ".yml", ".json", ".docx", ".pdf", ".rtf"}
    if ext not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(allowed))}",
        )

    content_bytes = await file.read()
    extracted_text = ""

    if ext in {".txt", ".md", ".yaml", ".yml", ".json", ".rtf"}:
        # Plain text files — decode directly
        try:
            extracted_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = content_bytes.decode("latin-1")

    elif ext == ".docx":
        # Word documents — extract paragraph text
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            from io import BytesIO

            docx_zip = zipfile.ZipFile(BytesIO(content_bytes))
            xml_content = docx_zip.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Extract all text from w:t elements
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for para in tree.iter(f"{{{ns['w']}}}p"):
                texts = [t.text for t in para.iter(f"{{{ns['w']}}}t") if t.text]
                if texts:
                    paragraphs.append("".join(texts))
            extracted_text = "\n".join(paragraphs)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to parse .docx: {e}")

    elif ext == ".pdf":
        # PDF — try simple text extraction
        try:
            import io

            # Use a basic PDF text extractor (no heavy dependencies)
            # Extract text between stream markers as a lightweight approach
            text_parts = []
            # Try pypdf if available
            try:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(content_bytes))
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                extracted_text = "\n".join(text_parts)
            except ImportError:
                # Fallback: decode what we can from the raw bytes
                try:
                    raw = content_bytes.decode("latin-1")
                    # Very basic: look for text between BT and ET markers
                    import re

                    bt_et = re.findall(r"BT\s*(.*?)\s*ET", raw, re.DOTALL)
                    for block in bt_et:
                        # Extract Tj strings
                        tj_matches = re.findall(r"\((.*?)\)", block)
                        text_parts.extend(tj_matches)
                    extracted_text = " ".join(text_parts)
                except Exception:
                    raise HTTPException(
                        status_code=422,
                        detail="PDF parsing requires 'pypdf'. Install with: pip install pypdf",
                    )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {e}")

    if not extracted_text.strip():
        raise HTTPException(
            status_code=422, detail="Could not extract any text from the file"
        )

    # Truncate extremely long content (LLM context window consideration)
    max_chars = 50000
    truncated = len(extracted_text) > max_chars
    if truncated:
        extracted_text = extracted_text[:max_chars]

    return {
        "filename": file.filename,
        "content": extracted_text.strip(),
        "char_count": len(extracted_text.strip()),
        "truncated": truncated,
    }


@app.get("/api/specs/{spec_path:path}", response_model=SpecSummary)
async def get_spec(spec_path: str):
    """Inspect an agent spec — list journeys, steps, knowledge sources."""
    path = _resolve_spec_path(spec_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Spec not found: {spec_path}")

    try:
        spec = parse_yaml(path)
    except (SchemaParseError, Exception) as e:
        raise HTTPException(status_code=422, detail=f"Invalid spec: {e}")

    journeys = []
    for j in spec.journeys:
        step_types = [s.type for s in j.steps]
        journeys.append(
            JourneySummary(
                name=j.name,
                description=j.description,
                trigger_description=j.trigger.description,
                step_count=len(j.steps),
                step_types=step_types,
            )
        )

    return SpecSummary(
        agent=spec.agent,
        persona_name=spec.persona.name,
        persona_description=spec.persona.description,
        journeys=journeys,
        knowledge_sources=len(spec.knowledge),
        simulations=len(spec.simulations),
    )


@app.get("/api/yaml/{spec_path:path}")
async def get_spec_yaml(spec_path: str):
    """Get the raw YAML content of a spec file."""
    path = _resolve_spec_path(spec_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Spec not found: {spec_path}")

    return {"path": spec_path, "yaml_content": path.read_text()}


@app.get("/api/discover/{spec_path:path}")
async def get_spec_detail(spec_path: str):
    """Get full spec details including all journey steps — for canvas rendering.

    Used by Discover mode to display an existing workflow on the visual canvas.
    """
    path = _resolve_spec_path(spec_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Spec not found: {spec_path}")

    try:
        spec = parse_yaml(path)
    except (SchemaParseError, Exception) as e:
        raise HTTPException(status_code=422, detail=f"Invalid spec: {e}")

    journeys = []
    for j in spec.journeys:
        steps = []
        for s in j.steps:
            steps.append(
                JourneyStepDetail(
                    name=s.name,
                    type=s.type,
                    description=_get_step_description(s),
                    prompt=_get_step_prompt(s),
                    condition=getattr(s, "condition", None),
                    if_true=getattr(s, "if_true", None),
                    if_false=getattr(s, "if_false", None),
                    escalate_to=getattr(s, "escalate_to", None),
                )
            )
        journeys.append(
            JourneyDetail(
                name=j.name,
                description=j.description,
                trigger_description=j.trigger.description,
                steps=steps,
            )
        )

    return {
        "agent": spec.agent,
        "persona_name": spec.persona.name,
        "persona_description": spec.persona.description,
        "journeys": journeys,
        "knowledge_sources": len(spec.knowledge),
        "simulations": len(spec.simulations),
    }


# --- Journey Execution (Synchronous) ---


@app.post("/api/run", response_model=RunResponse)
async def run_journey(request: RunRequest):
    """Execute a journey and return the full result.

    This is the synchronous endpoint — waits for execution to complete.
    For real-time streaming, use /api/stream instead.
    """
    # Parse spec
    spec_path = _resolve_spec_path(request.spec_path)
    if not spec_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Spec not found: {request.spec_path}"
        )

    try:
        spec = parse_yaml(spec_path)
    except SchemaParseError as e:
        raise HTTPException(status_code=422, detail=f"Invalid spec: {e}")

    # Verify journey exists
    journey_names = [j.name for j in spec.journeys]
    if request.journey not in journey_names:
        raise HTTPException(
            status_code=404,
            detail=f"Journey '{request.journey}' not found. Available: {journey_names}",
        )

    # Load gateway config
    try:
        gateway_config = get_gateway_config()
    except GatewayConfigError as e:
        raise HTTPException(status_code=503, detail=f"Gateway not configured: {e}")

    # Determine engine
    engine = request.engine or "legacy"

    # Create session
    session = sessions.create(request.spec_path, request.journey)
    session.engine = engine
    session.thread_id = request.thread_id
    sessions.update(session.id, status="running")

    # Create executor
    tools = ToolRegistry()
    _register_demo_tools(tools)
    knowledge_base_path = spec_path.resolve().parent

    if engine == "langgraph":
        executor = _get_langgraph_executor(
            spec_path=request.spec_path,
            spec=spec,
            tools=tools,
            gateway_config=gateway_config,
            model=request.model,
            knowledge_base_path=knowledge_base_path,
        )

        # Execute in thread (non-blocking)
        try:
            ctx = await asyncio.to_thread(
                executor.run,
                request.journey,
                user_message=request.message,
                context_data=request.context if request.context else None,
                thread_id=request.thread_id,
                interaction_mode=request.interaction_mode,
            )
        except Exception as e:
            sessions.update(session.id, status="failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Execution failed: {e}")

        # Store executor for HITL/handoff resume
        session._langgraph_executor = executor  # type: ignore[attr-defined]
    else:
        executor_legacy = JourneyExecutor(
            spec,
            tools=tools,
            gateway_config=gateway_config,
            model=request.model,
            knowledge_base_path=knowledge_base_path,
        )

        # Execute in thread (non-blocking)
        try:
            ctx = await asyncio.to_thread(
                executor_legacy.run,
                request.journey,
                user_message=request.message,
                context_data=request.context if request.context else None,
            )
        except Exception as e:
            sessions.update(session.id, status="failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Execution failed: {e}")

    # Update session — persist auto-generated thread_id from executor
    if not session.thread_id and hasattr(ctx, "thread_id") and ctx.thread_id:
        session.thread_id = ctx.thread_id

    status = ctx.status.value
    sessions.update(session.id, context=ctx, status=status)

    return _build_run_response(session, ctx)


# --- Journey Execution (SSE Streaming) ---


@app.post("/api/stream")
async def stream_journey(request: RunRequest):
    """Execute a journey with Server-Sent Events streaming.

    Streams step events as they complete, then the final result.
    Connect with EventSource or fetch() with ReadableStream.
    """
    # Validate inputs
    spec_path = _resolve_spec_path(request.spec_path)
    if not spec_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Spec not found: {request.spec_path}"
        )

    try:
        spec = parse_yaml(spec_path)
    except SchemaParseError as e:
        raise HTTPException(status_code=422, detail=f"Invalid spec: {e}")

    journey_names = [j.name for j in spec.journeys]
    if request.journey not in journey_names:
        raise HTTPException(
            status_code=404,
            detail=f"Journey '{request.journey}' not found. Available: {journey_names}",
        )

    try:
        gateway_config = get_gateway_config()
    except GatewayConfigError as e:
        raise HTTPException(status_code=503, detail=f"Gateway not configured: {e}")

    # Determine engine
    engine = request.engine or "legacy"

    # Create session
    session = sessions.create(request.spec_path, request.journey)
    session.engine = engine
    session.thread_id = request.thread_id

    async def event_generator():
        """Generate SSE events as execution progresses."""
        sessions.update(session.id, status="running")

        # Setup executor
        tools = ToolRegistry()
        _register_demo_tools(tools)
        knowledge_base_path = spec_path.resolve().parent

        if engine == "langgraph":
            executor = _get_langgraph_executor(
                spec_path=request.spec_path,
                spec=spec,
                tools=tools,
                gateway_config=gateway_config,
                model=request.model,
                knowledge_base_path=knowledge_base_path,
            )
        else:
            executor = JourneyExecutor(
                spec,
                tools=tools,
                gateway_config=gateway_config,
                model=request.model,
                knowledge_base_path=knowledge_base_path,
            )

        # Track which traces we've already sent
        sent_trace_count = 0

        # Run executor in background thread
        ctx_holder: list[Optional[ExecutionContext]] = [None]
        error_holder: list[Optional[str]] = [None]

        def execute():
            try:
                if engine == "langgraph":
                    ctx_holder[0] = executor.run(
                        request.journey,
                        user_message=request.message,
                        context_data=request.context if request.context else None,
                        thread_id=request.thread_id,
                    )
                else:
                    ctx_holder[0] = executor.run(
                        request.journey,
                        user_message=request.message,
                        context_data=request.context if request.context else None,
                    )
            except Exception as e:
                error_holder[0] = str(e)

        # Start execution
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, execute)

        # Poll for new traces while execution runs
        while not task.done():
            await asyncio.sleep(0.1)

            # Check if executor has produced new traces (via shared context)
            # Since executor.run() doesn't expose intermediate context,
            # we'll stream events after completion (for now)

        # Wait for task to finish
        await task

        if error_holder[0]:
            sessions.update(session.id, status="failed", error=error_holder[0])
            event = StepEvent(
                event="execution_failed",
                status="failed",
                output_preview=error_holder[0][:100],
                timestamp=time.time(),
            )
            yield f"event: error\ndata: {event.model_dump_json()}\n\n"
            return

        ctx = ctx_holder[0]
        if ctx is None:
            return

        sessions.update(session.id, context=ctx, status=ctx.status.value)

        # Stream all step traces as events
        for trace in ctx.traces:
            output_preview = str(trace.output)[:100] if trace.output else None
            usage = trace.llm_usage or {}
            event = StepEvent(
                event="step_completed",
                step_name=trace.step_name,
                step_type=trace.step_type,
                status=trace.status.value,
                output_preview=output_preview,
                tokens_in=usage.get("tokens_in"),
                tokens_out=usage.get("tokens_out"),
                timestamp=trace.completed_at or time.time(),
            )
            yield f"event: step\ndata: {event.model_dump_json()}\n\n"
            await asyncio.sleep(0.05)  # Small delay for client rendering

        # Final result
        response = _build_run_response(session, ctx)
        yield f"event: result\ndata: {response.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- HITL Resume ---


@app.post("/api/executions/{execution_id}/resume", response_model=RunResponse)
async def resume_hitl(execution_id: str, request: HITLResumeRequest):
    """Resume a HITL-paused execution after human decision.

    For LangGraph engine: uses true graph resume with persistent state.
    For legacy engine: stores the decision and updates status.
    """
    session = sessions.get(execution_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Execution '{execution_id}' not found"
        )

    if session.status != "waiting_hitl":
        raise HTTPException(
            status_code=409,
            detail=f"Execution is not waiting for HITL (status: {session.status})",
        )

    # LangGraph engine: use true graph resume
    if session.engine == "langgraph":
        lg_executor = getattr(session, "_langgraph_executor", None)
        if lg_executor is None or session.thread_id is None:
            raise HTTPException(
                status_code=500,
                detail="LangGraph executor or thread_id not available for resume",
            )

        try:
            ctx = await asyncio.to_thread(
                lg_executor.resume,
                session.thread_id,
                approved=request.approved,
                notes=request.notes,
            )
        except Exception as e:
            sessions.update(session.id, status="failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Resume failed: {e}")

        status = ctx.status.value
        sessions.update(session.id, context=ctx, status=status)
        return _build_run_response(session, ctx)

    # Legacy engine: record the decision
    if session.context:
        session.context.set("hitl_approved", request.approved)
        if request.notes:
            session.context.set("hitl_notes", request.notes)

        if request.approved:
            session.context.waiting_for_human = False
            session.context.status = StepStatus.COMPLETED
            sessions.update(session.id, status="completed", context=session.context)
        else:
            session.context.status = StepStatus.FAILED
            sessions.update(session.id, status="failed", context=session.context)

        return _build_run_response(session, session.context)

    raise HTTPException(status_code=500, detail="Session has no execution context")


# --- Handoff Resume ---


@app.post("/api/executions/{execution_id}/resume_handoff", response_model=RunResponse)
async def resume_handoff(execution_id: str, request: HandoffResumeRequest):
    """Resume a handoff-paused execution after form submission.

    When a handoff step interrupts execution to collect structured data,
    the UI presents a form. This endpoint receives the submitted form data
    and resumes execution from where it paused.
    """
    session = sessions.get(execution_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Execution '{execution_id}' not found"
        )

    if session.status != "waiting_hitl":
        raise HTTPException(
            status_code=409,
            detail=f"Execution is not waiting for handoff (status: {session.status})",
        )

    # Handoff resume only supported on LangGraph engine
    if session.engine != "langgraph":
        raise HTTPException(
            status_code=400,
            detail="Handoff resume requires the LangGraph engine",
        )

    lg_executor = getattr(session, "_langgraph_executor", None)
    if lg_executor is None or session.thread_id is None:
        raise HTTPException(
            status_code=500,
            detail="LangGraph executor or thread_id not available for resume",
        )

    try:
        ctx = await asyncio.to_thread(
            lg_executor.resume_handoff,
            session.thread_id,
            form_data=request.form_data,
        )
    except Exception as e:
        sessions.update(session.id, status="failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Handoff resume failed: {e}")

    status = ctx.status.value
    sessions.update(session.id, context=ctx, status=status)
    return _build_run_response(session, ctx)


# --- Execution History ---


@app.get("/api/executions/{execution_id}", response_model=RunResponse)
async def get_execution(execution_id: str):
    """Get execution result by ID."""
    session = sessions.get(execution_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Execution '{execution_id}' not found"
        )

    if session.context is None:
        raise HTTPException(status_code=404, detail="Execution has not started yet")

    return _build_run_response(session, session.context)


@app.get("/api/executions")
async def list_executions():
    """List all execution sessions."""
    return [
        {
            "id": s.id,
            "spec_path": s.spec_path,
            "journey_name": s.journey_name,
            "status": s.status,
            "created_at": s.created_at,
        }
        for s in sessions.list_all()
    ]


# --- Ghostwriter ---


@app.post("/api/ghostwrite", response_model=GhostwriteResponse)
async def ghostwrite(request: GhostwriteRequest):
    """Generate an agent spec from natural language description.

    Uses the Ghostwriter compiler (Claude + Instructor) to produce a
    validated FlowStrix spec from plain English.
    """
    try:
        gateway_config = get_gateway_config()
    except GatewayConfigError as e:
        raise HTTPException(status_code=503, detail=f"Gateway not configured: {e}")

    from flowstrix.compiler.ghostwriter import Ghostwriter

    try:
        gw = Ghostwriter(gateway_config=gateway_config)
        result = await asyncio.to_thread(
            gw.compile,
            description=request.description,
            agent_name=request.agent_name,
            persona_name=request.persona_name,
            tools_available=(
                request.tools_available if request.tools_available else None
            ),
            knowledge_docs=request.knowledge_docs if request.knowledge_docs else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ghostwriter failed: {e}")

    # Convert to response format
    journeys = []
    for j in result.spec.journeys:
        steps = []
        for s in j.steps:
            step_data = GhostwriteStepResponse(
                name=s.name,
                type=s.type,
                description=_get_step_description(s),
                prompt=_get_step_prompt(s),
                condition=getattr(s, "condition", None),
                if_true=getattr(s, "if_true", None),
                if_false=getattr(s, "if_false", None),
                escalate_to=getattr(s, "escalate_to", None),
                output_key=getattr(s, "output_key", None),
                tool=getattr(s, "tool", None),
            )
            steps.append(step_data)

        journeys.append(
            GhostwriteJourneyResponse(
                name=j.name,
                description=j.description,
                trigger_description=j.trigger.description,
                steps=steps,
            )
        )

    return GhostwriteResponse(
        agent_name=result.spec.agent,
        persona_name=result.spec.persona.name,
        persona_description=result.spec.persona.description,
        journeys=journeys,
        yaml_output=result.yaml_output,
        explanation=result.explanation,
        confidence=result.confidence,
    )


def _get_step_description(step) -> str:
    """Extract description from a step (varies by type)."""
    if hasattr(step, "prompt") and step.prompt:
        return step.prompt[:120]
    if hasattr(step, "description") and step.description:
        return step.description
    return f"{step.type} step: {step.name}"


def _get_step_prompt(step) -> str | None:
    """Extract the full prompt from a step if it has one."""
    if hasattr(step, "prompt"):
        return step.prompt
    return None


# --- WebSocket ---


@app.websocket("/api/ws/run")
async def websocket_run(ws: WebSocket):
    """WebSocket endpoint for real-time journey execution.

    Send a RunRequest JSON, receive StepEvent messages as execution progresses.
    """
    await ws.accept()

    try:
        # Receive run request
        data = await ws.receive_json()
        request = RunRequest(**data)

        # Validate
        spec_path = _resolve_spec_path(request.spec_path)
        if not spec_path.exists():
            await ws.send_json({"error": f"Spec not found: {request.spec_path}"})
            await ws.close()
            return

        try:
            spec = parse_yaml(spec_path)
        except SchemaParseError as e:
            await ws.send_json({"error": f"Invalid spec: {e}"})
            await ws.close()
            return

        try:
            gateway_config = get_gateway_config()
        except GatewayConfigError as e:
            await ws.send_json({"error": f"Gateway not configured: {e}"})
            await ws.close()
            return

        # Setup + execute
        engine = request.engine or "legacy"
        session = sessions.create(request.spec_path, request.journey)
        session.engine = engine
        session.thread_id = request.thread_id
        sessions.update(session.id, status="running")

        await ws.send_json(
            {
                "event": "execution_started",
                "execution_id": session.id,
                "thread_id": session.thread_id,
            }
        )

        tools = ToolRegistry()
        _register_demo_tools(tools)
        knowledge_base_path = spec_path.resolve().parent

        if engine == "langgraph":
            executor = _get_langgraph_executor(
                spec_path=request.spec_path,
                spec=spec,
                tools=tools,
                gateway_config=gateway_config,
                model=request.model,
                knowledge_base_path=knowledge_base_path,
            )
        else:
            executor = JourneyExecutor(
                spec,
                tools=tools,
                gateway_config=gateway_config,
                model=request.model,
                knowledge_base_path=knowledge_base_path,
            )

        # Execute in thread
        try:
            if engine == "langgraph":
                ctx = await asyncio.to_thread(
                    executor.run,
                    request.journey,
                    user_message=request.message,
                    context_data=request.context if request.context else None,
                    thread_id=request.thread_id,
                )
                session._langgraph_executor = executor  # type: ignore[attr-defined]
            else:
                ctx = await asyncio.to_thread(
                    executor.run,
                    request.journey,
                    user_message=request.message,
                    context_data=request.context if request.context else None,
                )
        except Exception as e:
            sessions.update(session.id, status="failed", error=str(e))
            await ws.send_json({"event": "execution_failed", "error": str(e)})
            await ws.close()
            return

        sessions.update(session.id, context=ctx, status=ctx.status.value)

        # Send step events
        for trace in ctx.traces:
            event = {
                "event": "step_completed",
                "step_name": trace.step_name,
                "step_type": trace.step_type,
                "status": trace.status.value,
                "duration_ms": trace.duration_ms,
                "output_preview": str(trace.output)[:100] if trace.output else None,
            }
            await ws.send_json(event)

        # Send final result
        response = _build_run_response(session, ctx)
        await ws.send_json(
            {
                "event": "execution_completed",
                "result": response.model_dump(mode="json"),
            }
        )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"event": "error", "error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# --- Static Files (UI) ---
# Serve built frontend if ui/dist exists (production mode)

_ui_dist = Path(__file__).parent.parent.parent / "ui" / "dist"
if _ui_dist.exists():
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
