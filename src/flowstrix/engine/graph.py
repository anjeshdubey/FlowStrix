"""
LangGraph Graph Compiler — Compiles a Journey spec into a LangGraph StateGraph.

This is the bridge between FlowStrix's YAML-defined journeys and LangGraph's
state machine runtime. Given a Journey, it:

1. Creates a node for each step (via NodeFactory)
2. Wires edges based on step order + branch targets
3. Sets up conditional routing for branch nodes
4. Configures HITL interrupts
5. Returns a compiled graph ready to invoke

Architecture:
- Each Journey becomes one graph (graphs are lightweight, compiled once per run)
- Branch nodes use conditional edges to route based on state["next_step"]
- HITL nodes can interrupt execution (for external resume)
- Terminal steps route to END
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from flowstrix.engine.nodes import NodeFactory
from flowstrix.engine.state import ExecutionState
from flowstrix.schema.models import (
    BranchStep,
    HandoffStep,
    HITLStep,
    Journey,
    LookupStep,
    ReasonStep,
    RespondStep,
    Step,
    ToolStep,
    WaitStep,
)


def compile_journey_graph(
    journey: Journey,
    node_factory: NodeFactory,
    checkpointer: Optional[Any] = None,
    interrupt_on_hitl: bool = True,
) -> Any:
    """Compile a Journey into a LangGraph StateGraph.

    Args:
        journey: The Journey spec to compile.
        node_factory: Factory with bound dependencies (client, tools, etc.)
        checkpointer: Optional checkpointer for state persistence.
                      Defaults to MemorySaver if None.
        interrupt_on_hitl: If True, HITL nodes interrupt execution for external resume.

    Returns:
        A compiled LangGraph graph ready for .invoke() or .stream().
    """
    graph = StateGraph(ExecutionState)

    steps = journey.steps
    step_names = [s.name for s in steps]

    # Track which steps are branch targets (only reachable via jump)
    jump_targets: set[str] = set()
    for s in steps:
        if isinstance(s, BranchStep):
            jump_targets.add(s.if_true)
            jump_targets.add(s.if_false)
        if hasattr(s, "on_failure") and s.on_failure:
            jump_targets.add(s.on_failure)
        if hasattr(s, "timeout_action") and s.timeout_action:
            jump_targets.add(s.timeout_action)

    # --- Detect parallel groups before adding nodes ---
    parallel_groups = _detect_parallel_groups(steps)

    # Build a set of step names that are part of a parallel group
    parallelized_steps: set[str] = set()
    for group in parallel_groups:
        for step in group:
            parallelized_steps.add(step.name)

    # --- Step 1: Add nodes ---
    hitl_nodes: list[str] = []
    wait_nodes: list[str] = []

    for step in steps:
        if step.name in parallelized_steps:
            # Skip individual nodes for parallelized steps; they get a group node
            continue
        node_fn = _create_node(step, node_factory)
        graph.add_node(step.name, node_fn)
        if isinstance(step, (HITLStep, HandoffStep)):
            hitl_nodes.append(step.name)
        elif isinstance(step, WaitStep):
            wait_nodes.append(step.name)

    # Add parallel group nodes
    parallel_group_names: Dict[str, List[Step]] = {}  # group_node_name -> steps in group
    for group in parallel_groups:
        group_name = "__parallel__" + "__".join(s.name for s in group)
        node_fns = [_create_node(step, node_factory) for step in group]
        parallel_node_fn = _make_parallel_node(node_fns, [s.name for s in group])
        graph.add_node(group_name, parallel_node_fn)
        parallel_group_names[group_name] = group

    # Add a terminal node that marks execution complete
    def _complete_node(state: ExecutionState) -> dict:
        return {"status": "completed"}

    graph.add_node("__complete__", _complete_node)

    # --- Step 2: Set entry point ---
    # If the first step is part of a parallel group, use the group node name
    first_step_name = steps[0].name
    entry_name = _resolve_node_name(first_step_name, parallel_groups, parallelized_steps)
    graph.set_entry_point(entry_name)

    # --- Step 3: Wire edges ---
    # We need to iterate through the steps, but skip those inside parallel groups
    # (the group is represented as a single node)
    i = 0
    while i < len(steps):
        step = steps[i]

        if step.name in parallelized_steps:
            # Find which group this step belongs to
            group = _find_group_for_step(step.name, parallel_groups)
            if group is None:
                i += 1
                continue
            group_name = "__parallel__" + "__".join(s.name for s in group)

            # Only wire edges once per group (when we hit the first step in the group)
            if step.name == group[0].name:
                # Wire the group node like a sequential step
                # Find the next step after the group
                last_group_index = i + len(group) - 1
                _add_sequential_edge_for_node(
                    graph, group_name, steps, last_group_index, step_names,
                    jump_targets, parallelized_steps, parallel_groups
                )

            i += 1
        elif isinstance(step, BranchStep):
            # Branch nodes use conditional edges based on next_step
            _add_branch_edges(graph, step, step_names)
            i += 1
        elif isinstance(step, HITLStep):
            # HITL nodes: if escalated → END (interrupted), else → next step
            _add_hitl_edges(graph, step, steps, i, step_names, jump_targets)
            i += 1
        elif isinstance(step, HandoffStep):
            # Handoff nodes: same pattern as HITL — if form surfaced → complete, else → next
            _add_hitl_edges(graph, step, steps, i, step_names, jump_targets)
            i += 1
        else:
            # Sequential step → next step (or complete if terminal)
            _add_sequential_edge(
                graph, step, steps, i, step_names, jump_targets,
                parallelized_steps=parallelized_steps,
                parallel_groups=parallel_groups,
            )
            i += 1

    # --- Step 4: Configure interrupts ---
    # Both HITL and Wait nodes interrupt execution.
    # HITL: pauses for human approval
    # Wait: pauses for next user message (multi-turn)
    interrupt_nodes = []
    if interrupt_on_hitl:
        interrupt_nodes.extend(hitl_nodes)
    interrupt_nodes.extend(wait_nodes)

    # --- Step 5: Compile ---
    if checkpointer is None:
        checkpointer = MemorySaver()

    compiled = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes if interrupt_nodes else None,
    )

    return compiled


# --- Parallel Execution ---


def _detect_parallel_groups(steps: List[Step]) -> List[List[Step]]:
    """Identify consecutive steps that can safely run in parallel.

    Two or more consecutive lookup or tool steps are parallelizable if none of
    them depends on another's output_key. Dependency is checked by looking at
    whether step B's params reference step A's output_key via ${...} syntax.

    Returns:
        A list of groups, where each group is a list of 2+ steps that can run
        concurrently. Steps not in any group run sequentially as before.
    """
    groups: List[List[Step]] = []
    i = 0

    while i < len(steps):
        step = steps[i]

        # Only lookup and tool steps are candidates for parallelization
        if not isinstance(step, (LookupStep, ToolStep)):
            i += 1
            continue

        # Collect a run of consecutive lookup/tool steps
        candidate_run: List[Step] = [step]
        j = i + 1
        while j < len(steps) and isinstance(steps[j], (LookupStep, ToolStep)):
            candidate_run.append(steps[j])
            j += 1

        if len(candidate_run) < 2:
            i += 1
            continue

        # Now determine which steps in the run are independent
        # Build a dependency-free group greedily from the start of the run
        independent_group = _extract_independent_group(candidate_run)

        if len(independent_group) >= 2:
            groups.append(independent_group)
            i += len(independent_group)
        else:
            i += 1

    return groups


def _extract_independent_group(candidates: List[Step]) -> List[Step]:
    """From a run of consecutive lookup/tool steps, extract the longest prefix
    of mutually independent steps.

    Steps are independent if none of them references another's output_key
    in their params.
    """
    group: List[Step] = []
    # Track all output_keys produced by steps already in the group
    produced_keys: set[str] = set()

    for step in candidates:
        # Get this step's param references
        param_refs = _extract_param_references(step)

        # Check if this step depends on any key produced by a step already in the group
        if param_refs & produced_keys:
            # This step depends on a prior step in the group — stop here
            break

        group.append(step)

        # Record what this step produces
        output_key = _get_output_key(step)
        if output_key:
            produced_keys.add(output_key)

    return group


def _extract_param_references(step: Step) -> set:
    """Extract all ${key} references from a step's params."""
    refs: set = set()

    params: Dict[str, Any] = {}
    if isinstance(step, (LookupStep, ToolStep)):
        params = step.params

    for value in params.values():
        if isinstance(value, str):
            # Find all ${key} references
            for match in re.finditer(r"\$\{(\w+)\}", value):
                refs.add(match.group(1))

    return refs


def _get_output_key(step: Step) -> Optional[str]:
    """Get the output_key for a step, if it has one."""
    if isinstance(step, LookupStep):
        return step.output_key
    elif isinstance(step, ToolStep):
        return step.output_key
    return None


def _make_parallel_node(
    node_fns: List[Callable[[ExecutionState], dict]],
    step_names: List[str],
) -> Callable[[ExecutionState], dict]:
    """Create a composite node that runs multiple node functions against the same
    input state and merges their partial state updates.

    Merge strategy:
    - data: union of all data dicts (later steps in the list overwrite on key conflict)
    - traces: concatenated in order
    - steps_executed: concatenated in order
    - Other keys: last-write-wins

    Args:
        node_fns: The individual node functions to run.
        step_names: Names of the steps (for debugging/tracing).

    Returns:
        A single node function with signature (state: ExecutionState) -> dict.
    """

    def parallel_node(state: ExecutionState) -> dict:
        # Run all node functions against the SAME input state
        results: List[dict] = []
        for fn in node_fns:
            result = fn(state)
            results.append(result)

        # Merge results
        merged: Dict[str, Any] = {}
        merged_data: Dict[str, Any] = dict(state.get("data", {}))
        merged_traces: List[Any] = list(state.get("traces", []))
        merged_steps_executed: List[str] = list(state.get("steps_executed", []))

        for result in results:
            # Merge data (union)
            if "data" in result:
                merged_data.update(result["data"])

            # Concatenate traces
            if "traces" in result:
                # Each node returns state["traces"] + [new_trace]
                # We only want the NEW traces (those not already in merged_traces)
                new_traces = result["traces"][len(state.get("traces", [])):]
                merged_traces.extend(new_traces)

            # Concatenate steps_executed
            if "steps_executed" in result:
                new_steps = result["steps_executed"][len(state.get("steps_executed", [])):]
                merged_steps_executed.extend(new_steps)

            # Other keys: last-write-wins
            for key, value in result.items():
                if key not in ("data", "traces", "steps_executed"):
                    merged[key] = value

        merged["data"] = merged_data
        merged["traces"] = merged_traces
        merged["steps_executed"] = merged_steps_executed

        return merged

    return parallel_node


def _find_group_for_step(
    step_name: str, parallel_groups: List[List[Step]]
) -> Optional[List[Step]]:
    """Find which parallel group a step belongs to."""
    for group in parallel_groups:
        for step in group:
            if step.name == step_name:
                return group
    return None


def _resolve_node_name(
    step_name: str,
    parallel_groups: List[List[Step]],
    parallelized_steps: set,
) -> str:
    """Resolve a step name to its graph node name (may be a parallel group node)."""
    if step_name not in parallelized_steps:
        return step_name
    group = _find_group_for_step(step_name, parallel_groups)
    if group is not None:
        return "__parallel__" + "__".join(s.name for s in group)
    return step_name


def _add_sequential_edge_for_node(
    graph: StateGraph,
    node_name: str,
    steps: List[Step],
    last_index: int,
    step_names: List[str],
    jump_targets: set,
    parallelized_steps: set,
    parallel_groups: List[List[Step]],
):
    """Add a sequential edge from a node (could be a parallel group) to the next step."""
    next_index = last_index + 1

    if next_index >= len(steps):
        graph.add_edge(node_name, "__complete__")
    else:
        next_name = steps[next_index].name
        if next_name in jump_targets:
            graph.add_edge(node_name, "__complete__")
        else:
            # Resolve the next step's actual node name
            resolved_next = _resolve_node_name(next_name, parallel_groups, parallelized_steps)
            graph.add_edge(node_name, resolved_next)



def _create_node(step: Step, factory: NodeFactory):
    """Create the appropriate node function for a step."""
    if isinstance(step, LookupStep):
        return factory.make_lookup_node(step)
    elif isinstance(step, ReasonStep):
        return factory.make_reason_node(step)
    elif isinstance(step, RespondStep):
        return factory.make_respond_node(step)
    elif isinstance(step, BranchStep):
        return factory.make_branch_node(step)
    elif isinstance(step, HITLStep):
        return factory.make_hitl_node(step)
    elif isinstance(step, ToolStep):
        return factory.make_tool_node(step)
    elif isinstance(step, WaitStep):
        return factory.make_wait_node(step)
    elif isinstance(step, HandoffStep):
        return factory.make_handoff_node(step)
    else:
        raise ValueError(f"Unknown step type: {type(step)}")


def _add_branch_edges(graph: StateGraph, step: BranchStep, step_names: list[str]):
    """Add conditional edges for a branch node.

    After a branch node executes, state["next_step"] contains the target.
    We route to that target via a conditional edge.
    """
    # Build the possible targets
    targets = {step.if_true: step.if_true, step.if_false: step.if_false}

    # Ensure both targets exist in the graph
    for target in [step.if_true, step.if_false]:
        if target not in step_names:
            targets[target] = "__complete__"

    def route_branch(state: ExecutionState) -> str:
        next_target = state.get("next_step")
        if next_target and next_target in step_names:
            return next_target
        return "__complete__"

    graph.add_conditional_edges(step.name, route_branch, targets)


def _add_hitl_edges(
    graph: StateGraph,
    step: HITLStep,
    steps: list[Step],
    index: int,
    step_names: list[str],
    jump_targets: set[str],
):
    """Add edges for a HITL node.

    If HITL escalates → route to __complete__ (execution is interrupted).
    If HITL condition not met → continue to next sequential step.
    """
    def route_hitl(state: ExecutionState) -> str:
        if state.get("waiting_for_human"):
            return "__complete__"
        # Continue to next step
        next_index = index + 1
        if next_index < len(steps):
            next_name = steps[next_index].name
            # Don't fall through to jump targets
            if next_name in jump_targets:
                return "__complete__"
            return next_name
        return "__complete__"

    # Build possible targets
    possible: dict[str, str] = {"__complete__": "__complete__"}
    next_index = index + 1
    if next_index < len(steps):
        next_name = steps[next_index].name
        if next_name not in jump_targets:
            possible[next_name] = next_name

    graph.add_conditional_edges(step.name, route_hitl, possible)


def _add_sequential_edge(
    graph: StateGraph,
    step: Step,
    steps: List[Step],
    index: int,
    step_names: List[str],
    jump_targets: set,
    parallelized_steps: Optional[set] = None,
    parallel_groups: Optional[List[List[Step]]] = None,
):
    """Add a sequential edge from one step to the next.

    Implements the same terminal endpoint detection as the legacy executor:
    if the next step is a jump target (only reachable via branch), don't
    fall through to it — go to __complete__ instead.
    """
    if parallelized_steps is None:
        parallelized_steps = set()
    if parallel_groups is None:
        parallel_groups = []

    next_index = index + 1

    if next_index >= len(steps):
        # Last step → complete
        graph.add_edge(step.name, "__complete__")
    else:
        next_name = steps[next_index].name
        if next_name in jump_targets:
            # Next step is a jump target — don't fall through
            graph.add_edge(step.name, "__complete__")
        else:
            # Resolve the next step's actual node name (might be a parallel group)
            resolved_next = _resolve_node_name(
                next_name, parallel_groups, parallelized_steps
            )
            graph.add_edge(step.name, resolved_next)
