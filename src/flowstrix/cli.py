"""
FlowStrix CLI — Run, validate, and inspect agent workflows.

Usage:
    flowstrix validate examples/customer_support.yaml
    flowstrix run examples/customer_support.yaml --journey handle_refund_request
    flowstrix inspect examples/customer_support.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich import box

from flowstrix.schema.parser import parse_yaml, SchemaParseError
from flowstrix.engine.executor import JourneyExecutor, ToolRegistry
from flowstrix.gateway import GatewayConfig, GatewayConfigError

# Load .env from project root (or cwd)
load_dotenv()

app = typer.Typer(
    name="flowstrix",
    help="Agent-native workflow engine — define, run, and test AI agent workflows.",
)
console = Console()


@app.command()
def validate(
    spec_path: Path = typer.Argument(..., help="Path to agent YAML spec"),
):
    """Validate an agent spec against the FlowStrix schema."""
    try:
        spec = parse_yaml(spec_path)
        console.print(f"\n[green]✓[/green] Valid agent spec: [bold]{spec.agent}[/bold]")
        console.print(f"  Persona: {spec.persona.name}")
        console.print(f"  Journeys: {len(spec.journeys)}")
        console.print(f"  Knowledge sources: {len(spec.knowledge)}")
        console.print(f"  Simulations: {len(spec.simulations)}")
        console.print()
    except SchemaParseError as e:
        console.print(f"\n[red]✗[/red] Schema validation failed:\n{e}")
        raise typer.Exit(1)
    except FileNotFoundError as e:
        console.print(f"\n[red]✗[/red] {e}")
        raise typer.Exit(1)


@app.command()
def inspect(
    spec_path: Path = typer.Argument(..., help="Path to agent YAML spec"),
):
    """Display a visual overview of an agent spec."""
    try:
        spec = parse_yaml(spec_path)
    except (SchemaParseError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]{spec.persona.name}[/bold]\n{spec.persona.description}\n\n"
            f"[dim]Tone:[/dim] {spec.persona.tone}",
            title=f"🤖 Agent: {spec.agent}",
            border_style="blue",
        )
    )

    # Journeys tree
    tree = Tree("📋 Journeys")
    for journey in spec.journeys:
        j_branch = tree.add(f"[bold]{journey.name}[/bold] — {journey.description}")
        j_branch.add(f"[dim]Trigger:[/dim] {journey.trigger.description}")
        steps_branch = j_branch.add("[dim]Steps:[/dim]")
        for step in journey.steps:
            icon = {
                "lookup": "🔍",
                "reason": "🧠",
                "respond": "💬",
                "branch": "🔀",
                "hitl": "🙋",
                "tool": "⚡",
                "wait": "⏸️",
            }.get(step.type, "•")
            steps_branch.add(f"{icon} [{step.type}] {step.name}")

    console.print(tree)

    # Knowledge sources
    if spec.knowledge:
        console.print()
        table = Table(title="📚 Knowledge Sources", box=box.SIMPLE)
        table.add_column("ID", style="cyan")
        table.add_column("Type")
        table.add_column("URI")
        table.add_column("Description")
        for ks in spec.knowledge:
            table.add_row(ks.id, ks.source_type.value, ks.uri, ks.description)
        console.print(table)

    # Simulations
    if spec.simulations:
        console.print()
        for sim in spec.simulations:
            table = Table(title=f"🧪 Simulation: {sim.name}", box=box.SIMPLE)
            table.add_column("Scenario")
            table.add_column("Expected")
            table.add_column("Runs")
            for scenario in sim.scenarios:
                table.add_row(
                    scenario.name,
                    scenario.expected_outcome,
                    str(sim.num_runs_per_scenario),
                )
            console.print(table)

    console.print()


@app.command()
def ingest(
    spec_path: Path = typer.Argument(..., help="Path to agent YAML spec"),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Specific knowledge source ID to ingest (default: all)"
    ),
):
    """Ingest knowledge documents into the vector store for semantic retrieval.

    Chunks documents and creates embeddings for RAG-based knowledge retrieval
    in reason steps.

    Example:
        flowstrix ingest examples/customer_support.yaml
        flowstrix ingest examples/customer_support.yaml --source refund_policy
    """
    from flowstrix.knowledge.loader import KnowledgeLoader

    try:
        spec = parse_yaml(spec_path)
    except (SchemaParseError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not spec.knowledge:
        console.print("[yellow]No knowledge sources defined in this spec.[/yellow]")
        raise typer.Exit(0)

    knowledge_base_path = spec_path.resolve().parent
    loader = KnowledgeLoader(spec, base_path=knowledge_base_path)

    console.print(f"\n[bold]📚 Knowledge Ingestion[/bold]")
    console.print(f"[dim]Spec:[/dim] {spec_path}")
    console.print(f"[dim]Embedding model:[/dim] BAAI/bge-small-en-v1.5 (384-dim)")
    console.print()

    if source:
        if source not in loader.sources:
            available = list(loader.sources.keys())
            console.print(f"[red]Source '{source}' not found. Available: {available}[/red]")
            raise typer.Exit(1)
        count = loader.ingest(source)
        console.print(f"  [green]✓[/green] {source}: {count} chunks")
    else:
        results = loader.ingest_all()
        for src_id, count in results.items():
            icon = "[green]✓[/green]" if count > 0 else "[yellow]⚠[/yellow]"
            console.print(f"  {icon} {src_id}: {count} chunks")

    total = loader.vector_store.count()
    console.print(f"\n[bold]Total chunks in store:[/bold] {total}")
    console.print()


@app.command()
def ask(
    spec_path: Path = typer.Argument(..., help="Path to agent YAML spec"),
    query: str = typer.Argument(..., help="Query to search knowledge for"),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Filter to specific knowledge source"
    ),
    top_k: int = typer.Option(3, "--top-k", "-k", help="Number of results"),
):
    """Search knowledge sources with a natural language query (RAG retrieval).

    Requires prior ingestion via `flowstrix ingest`.

    Example:
        flowstrix ask examples/customer_support.yaml "refund policy for electronics"
        flowstrix ask examples/customer_support.yaml "30 day window" --source refund_policy
    """
    from flowstrix.knowledge.loader import KnowledgeLoader

    try:
        spec = parse_yaml(spec_path)
    except (SchemaParseError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    knowledge_base_path = spec_path.resolve().parent
    loader = KnowledgeLoader(spec, base_path=knowledge_base_path)

    # Ingest first (in-memory, so we always need to do this)
    loader.ingest_all()

    source_ids = [source] if source else None
    results = loader.vector_store.search(query=query, top_k=top_k, source_ids=source_ids)

    console.print(f"\n[bold]🔍 Knowledge Search[/bold]")
    console.print(f"[dim]Query:[/dim] {query}")
    console.print(f"[dim]Results:[/dim] {len(results)}")
    console.print()

    if not results:
        console.print("[yellow]No relevant results found.[/yellow]")
    else:
        for i, result in enumerate(results, 1):
            src = loader.sources.get(result.source_id)
            label = src.description if src else result.source_id
            section = result.metadata.get("section", "")

            console.print(Panel(
                result.text,
                title=f"#{i} [{label}]{f' > {section}' if section else ''} — {result.score:.0%} match",
                border_style="blue" if result.score > 0.6 else "dim",
            ))

    console.print()


@app.command()
def run(
    spec_path: Path = typer.Argument(..., help="Path to agent YAML spec"),
    journey: str = typer.Option(..., "--journey", "-j", help="Journey to execute"),
    message: Optional[str] = typer.Option(
        None, "--message", "-m", help="Initial user message"
    ),
    context: Optional[str] = typer.Option(
        None, "--context", "-c", help="JSON context data"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Model override (e.g. claude-sonnet, claude-haiku)"
    ),
    engine: str = typer.Option(
        "legacy", "--engine", "-e",
        help="Execution engine: 'legacy' (while-loop) or 'langgraph' (state machine)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show execution trace"),
):
    """Execute a journey from an agent spec."""
    import json as json_mod

    try:
        spec = parse_yaml(spec_path)
    except (SchemaParseError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Load gateway config
    try:
        gateway_config = GatewayConfig.from_env()
    except GatewayConfigError as e:
        console.print(f"[red]Gateway config error:[/red] {e}")
        console.print(
            "\n[dim]Set these environment variables:[/dim]\n"
            "  export GROQ_API_KEY=gsk_...  (get a free key at https://console.groq.com)\n"
        )
        raise typer.Exit(1)

    # Parse context if provided
    context_data = None
    if context:
        try:
            context_data = json_mod.loads(context)
        except json_mod.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON context:[/red] {e}")
            raise typer.Exit(1)

    # Create executor with demo tools
    tools = ToolRegistry()
    _register_demo_tools(tools)

    # Knowledge base path = directory containing the YAML spec
    knowledge_base_path = spec_path.resolve().parent

    # Select execution engine
    if engine == "langgraph":
        from flowstrix.engine.executor_v2 import LangGraphExecutor
        executor = LangGraphExecutor(
            spec,
            tools=tools,
            model=model,
            gateway_config=gateway_config,
            knowledge_base_path=knowledge_base_path,
        )
        engine_label = "langgraph"
    else:
        executor = JourneyExecutor(
            spec,
            tools=tools,
            model=model,
            gateway_config=gateway_config,
            knowledge_base_path=knowledge_base_path,
        )
        engine_label = "legacy"

    console.print(f"\n[bold]Running journey:[/bold] {journey}")
    console.print(f"[dim]Engine:[/dim] {engine_label}")
    console.print(f"[dim]Gateway:[/dim] {gateway_config.base_url}")
    console.print(f"[dim]Model:[/dim] {executor.model}")
    if message:
        console.print(f"[dim]User message:[/dim] {message}")
    console.print()

    # Execute
    try:
        result = executor.run(journey, user_message=message, context_data=context_data)
    except Exception as e:
        console.print(f"[red]Execution failed:[/red] {e}")
        raise typer.Exit(1)

    # Display results
    status_color = {
        "completed": "green",
        "failed": "red",
        "waiting_hitl": "yellow",
    }.get(result.status.value, "white")

    console.print(
        Panel(
            f"Status: [{status_color}]{result.status.value}[/{status_color}]",
            title="Execution Result",
            border_style=status_color,
        )
    )

    # Show HITL info if paused
    if result.waiting_for_human:
        console.print(
            Panel(
                f"[yellow]⚠ Escalated to:[/yellow] {result.hitl_request['escalate_to']}\n"
                f"Type: {result.hitl_request['escalation_type']}\n"
                f"Context: {json_mod.dumps(result.hitl_request['context'], indent=2)}",
                title="🙋 Human-in-the-Loop Required",
                border_style="yellow",
            )
        )

    # Show trace
    if verbose or True:  # Always show for demo
        console.print()
        table = Table(title="Execution Trace", box=box.ROUNDED)
        table.add_column("#", style="dim")
        table.add_column("Step", style="cyan")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("Duration")
        table.add_column("Output", max_width=50)

        for i, trace in enumerate(result.traces):
            status_style = {
                "completed": "green",
                "failed": "red",
                "waiting_hitl": "yellow",
            }.get(trace.status.value, "white")

            output_preview = ""
            if trace.output:
                output_preview = str(trace.output)[:50]

            table.add_row(
                str(i + 1),
                trace.step_name,
                trace.step_type,
                f"[{status_style}]{trace.status.value}[/{status_style}]",
                f"{trace.duration_ms:.0f}ms" if trace.duration_ms else "-",
                output_preview,
            )

        console.print(table)

    # Show final context data
    if result.data:
        console.print()
        console.print("[bold]Context Data:[/bold]")
        for k, v in result.data.items():
            val_str = json_mod.dumps(v, indent=2) if isinstance(v, (dict, list)) else str(v)
            if len(val_str) > 100:
                val_str = val_str[:100] + "..."
            console.print(f"  [cyan]{k}[/cyan] = {val_str}")

    # Show conversation
    if result.messages:
        console.print()
        console.print("[bold]Conversation:[/bold]")
        for msg in result.messages:
            role_style = "blue" if msg["role"] == "user" else "green"
            console.print(f"  [{role_style}]{msg['role']}:[/{role_style}] {msg['content'][:200]}")

    console.print()


@app.command()
def simulate(
    spec_path: Path = typer.Argument(..., help="Path to agent YAML spec"),
    suite: Optional[str] = typer.Option(
        None, "--suite", "-s", help="Simulation suite to run (default: all)"
    ),
    runs: Optional[int] = typer.Option(
        None, "--runs", "-n", help="Override num_runs_per_scenario"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Model override"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-run details"),
):
    """Run simulation suites to test agent behavior with confidence scoring.

    Executes each scenario N times and evaluates outcomes using deterministic
    checks + LLM-as-judge. Reports pass rates and non-determinism.

    Example:
        flowstrix simulate examples/customer_support.yaml
        flowstrix simulate examples/customer_support.yaml --suite refund_scenarios --runs 5
    """
    from flowstrix.simulator.runner import SimulationRunner, Verdict

    try:
        spec = parse_yaml(spec_path)
    except (SchemaParseError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not spec.simulations:
        console.print("[yellow]No simulations defined in this spec.[/yellow]")
        raise typer.Exit(0)

    # Load gateway config
    try:
        gateway_config = GatewayConfig.from_env()
    except GatewayConfigError as e:
        console.print(f"[red]Gateway config error:[/red] {e}")
        raise typer.Exit(1)

    # Create runner with demo tools
    tools = ToolRegistry()
    _register_demo_tools(tools)

    knowledge_base_path = spec_path.resolve().parent

    runner = SimulationRunner(
        spec,
        tools=tools,
        gateway_config=gateway_config,
        model=model,
        knowledge_base_path=knowledge_base_path,
    )

    console.print(f"\n[bold]🧪 Simulation Runner[/bold]")
    console.print(f"[dim]Spec:[/dim] {spec_path}")
    console.print(f"[dim]Model:[/dim] {runner.model}")
    console.print(f"[dim]Suite:[/dim] {suite or 'all'}")
    if runs:
        console.print(f"[dim]Runs override:[/dim] {runs}")
    console.print()

    # Run the simulation
    try:
        result = runner.run_suite(suite_name=suite, num_runs_override=runs)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Simulation failed:[/red] {e}")
        raise typer.Exit(1)

    # Display results
    verdict_color = "green" if result.overall_verdict == Verdict.PASS else "red"

    # Summary table
    table = Table(title="Simulation Results", box=box.ROUNDED)
    table.add_column("Scenario", style="cyan")
    table.add_column("Pass Rate", justify="center")
    table.add_column("Verdict", justify="center")
    table.add_column("Deterministic", justify="center")
    table.add_column("Details", max_width=40)

    for scenario in result.scenarios:
        sc_color = "green" if scenario.verdict == Verdict.PASS else "red"
        det_icon = "✓" if scenario.is_deterministic else "[yellow]~[/yellow]"

        # Collect failure details
        details = ""
        if scenario.verdict == Verdict.FAIL:
            for run in scenario.runs:
                if not run.passed:
                    failed_checks = [c.check_name for c in run.checks if c.verdict != Verdict.PASS]
                    if failed_checks:
                        details = f"Failed: {', '.join(failed_checks)}"
                        break
                    if run.error:
                        details = f"Error: {run.error[:30]}"
                        break

        table.add_row(
            scenario.scenario_name,
            f"{scenario.pass_rate:.0%} ({scenario.pass_count}/{scenario.total_runs})",
            f"[{sc_color}]{scenario.verdict.value}[/{sc_color}]",
            det_icon,
            details,
        )

    console.print(table)

    # Verbose: per-run details
    if verbose:
        for scenario in result.scenarios:
            console.print(f"\n[bold]{scenario.scenario_name}[/bold] — {scenario.description}")
            for run in scenario.runs:
                run_color = "green" if run.passed else "red"
                console.print(
                    f"  Run {run.run_number}: [{run_color}]{run.verdict.value}[/{run_color}] "
                    f"({run.execution_time_ms:.0f}ms)"
                )
                if run.steps_executed:
                    console.print(f"    Steps: {' → '.join(run.steps_executed)}")
                for check in run.checks:
                    check_color = "green" if check.verdict == Verdict.PASS else "red"
                    console.print(
                        f"    [{check_color}]{check.verdict.value}[/{check_color}] "
                        f"{check.check_name}: {check.detail[:60]}"
                    )
                if run.error:
                    console.print(f"    [red]Error:[/red] {run.error}")

    # Overall summary
    console.print()
    console.print(
        Panel(
            f"[{verdict_color}]{result.overall_verdict.value.upper()}[/{verdict_color}] — "
            f"{result.scenarios_passed}/{result.scenarios_total} scenarios passed\n"
            f"Total runs: {result.total_runs} | Passes: {result.total_passes}\n"
            f"Time: {result.total_time_ms:.0f}ms"
            + (f"\n[yellow]Flaky scenarios: {', '.join(result.flaky_scenarios)}[/yellow]"
               if result.flaky_scenarios else ""),
            title="Summary",
            border_style=verdict_color,
        )
    )
    console.print()

    # Exit with non-zero if failed
    if result.overall_verdict != Verdict.PASS:
        raise typer.Exit(1)


@app.command()
def ghostwrite(
    description: str = typer.Argument(..., help="Natural language description of the agent"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write YAML to file (default: stdout)"
    ),
    agent_name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Agent identifier (auto-generated if omitted)"
    ),
    persona_name: Optional[str] = typer.Option(
        None, "--persona", help="Agent display name"
    ),
    tools: Optional[str] = typer.Option(
        None, "--tools", "-t", help="Comma-separated list of available tools"
    ),
    knowledge: Optional[str] = typer.Option(
        None, "--knowledge", "-k", help="Comma-separated list of knowledge doc paths"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Model override"
    ),
):
    """Compile a natural language description into a FlowStrix agent YAML spec.

    Example:
        flowstrix ghostwrite "Handle customer refund requests. Check order history,
        verify eligibility based on our 30-day policy. Escalate refunds over $500
        to a senior agent. For ineligible requests, offer store credit as alternative."
    """
    from flowstrix.compiler.ghostwriter import Ghostwriter

    # Load gateway
    try:
        gateway_config = GatewayConfig.from_env()
    except GatewayConfigError as e:
        console.print(f"[red]Gateway config error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Ghostwriter[/bold] — compiling natural language to agent spec...")
    console.print(f"[dim]Model:[/dim] {model or gateway_config.model}")
    console.print(f"[dim]Description:[/dim] {description[:100]}{'...' if len(description) > 100 else ''}")
    console.print()

    # Parse optional lists
    tools_list = [t.strip() for t in tools.split(",")] if tools else None
    knowledge_list = [k.strip() for k in knowledge.split(",")] if knowledge else None

    # Compile
    try:
        gw = Ghostwriter(gateway_config=gateway_config, model=model)
        result = gw.compile(
            description=description,
            agent_name=agent_name,
            persona_name=persona_name,
            tools_available=tools_list,
            knowledge_docs=knowledge_list,
        )
    except Exception as e:
        console.print(f"[red]Compilation failed:[/red] {e}")
        raise typer.Exit(1)

    # Display result
    console.print(Panel(
        result.explanation,
        title="Compilation Result",
        border_style="green",
    ))

    console.print(f"[dim]Confidence:[/dim] {result.confidence:.0%}")
    console.print()

    # Output YAML
    if output:
        output.write_text(result.yaml_output)
        console.print(f"[green]Written to:[/green] {output}")
    else:
        console.print(Panel(
            result.yaml_output,
            title="Generated YAML",
            border_style="blue",
        ))

    # Validate the output
    from flowstrix.schema.parser import parse_yaml_string
    try:
        parse_yaml_string(result.yaml_output)
        console.print("[green]✓ Schema validation passed[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ Schema validation warning:[/yellow] {e}")

    console.print()


@app.command()
def refine(
    spec_path: Path = typer.Argument(..., help="Path to existing agent YAML spec"),
    refinement: str = typer.Option(..., "--change", "-c", help="What to change"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write updated YAML to file"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Model override"
    ),
):
    """Refine an existing agent spec with a natural language change request.

    Example:
        flowstrix refine agent.yaml --change "Also handle exchanges, not just refunds"
    """
    from flowstrix.compiler.ghostwriter import Ghostwriter

    try:
        spec = parse_yaml(spec_path)
    except (SchemaParseError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        gateway_config = GatewayConfig.from_env()
    except GatewayConfigError as e:
        console.print(f"[red]Gateway config error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Ghostwriter[/bold] — refining {spec.agent}...")
    console.print(f"[dim]Change:[/dim] {refinement}")
    console.print()

    try:
        gw = Ghostwriter(gateway_config=gateway_config, model=model)
        result = gw.refine(current_spec=spec, refinement=refinement)
    except Exception as e:
        console.print(f"[red]Refinement failed:[/red] {e}")
        raise typer.Exit(1)

    console.print(Panel(
        result.explanation,
        title="Refinement Result",
        border_style="green",
    ))

    if output:
        output.write_text(result.yaml_output)
        console.print(f"[green]Written to:[/green] {output}")
    else:
        console.print(Panel(
            result.yaml_output,
            title="Updated YAML",
            border_style="blue",
        ))

    console.print()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
):
    """Start the FlowStrix API server.

    Exposes journey execution over HTTP + SSE streaming.

    Example:
        flowstrix serve
        flowstrix serve --port 3000 --reload
    """
    import uvicorn

    console.print(f"\n[bold]🚀 FlowStrix API Server[/bold]")
    console.print(f"[dim]Host:[/dim] {host}")
    console.print(f"[dim]Port:[/dim] {port}")
    console.print(f"[dim]Docs:[/dim] http://{host if host != '0.0.0.0' else 'localhost'}:{port}/docs")
    console.print()

    uvicorn.run(
        "flowstrix.api.server:app",
        host=host,
        port=port,
        reload=reload,
    )


def _register_demo_tools(tools: ToolRegistry) -> None:
    """Register demo tools for showcasing the engine."""

    def get_orders_by_customer_id(customer_id: str = "demo_customer") -> dict:
        """Simulated order lookup. Uses customer_id to demo different scenarios."""
        # VIP customer has high-value order (triggers HITL escalation)
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
                    },
                ],
            }
        # Old customer has expired order (triggers ineligibility)
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
                    },
                ],
            }
        # Default: standard recent order
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
                },
                {
                    "order_id": "ORD-2024-002",
                    "item": "Phone Case",
                    "date": "2024-01-10",
                    "amount": 29.50,
                    "status": "delivered",
                    "days_since_purchase": 8,
                },
            ],
        }

    def process_refund(order_id: str = "ORD-2024-001", amount: float = 0.0) -> dict:
        """Simulated refund processing."""
        return {
            "refund_id": "REF-2024-100",
            "order_id": order_id,
            "amount": amount,
            "status": "processed",
        }

    def send_email(to: str = "", subject: str = "", body: str = "") -> dict:
        """Simulated email send."""
        return {"status": "sent", "to": to, "subject": subject}

    tools.register("get_orders_by_customer_id", get_orders_by_customer_id)
    tools.register("process_refund", process_refund)
    tools.register("send_email", send_email)


if __name__ == "__main__":
    app()
