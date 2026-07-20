"""
FlowStrix Simulation Runner — AI-driven testing for non-deterministic agents.

The agent-native equivalent of Flow's Test Framework, designed for the
core problem: how do you give enterprises confidence in an LLM-powered
agent when the same input can produce different outputs?

Answer: run each scenario N times, evaluate outcomes with an LLM judge,
report pass rates and confidence intervals.

Architecture:
1. Load agent spec + simulation definitions
2. For each scenario, run the journey N times
3. After each run, evaluate against criteria:
   - expected_steps: were these steps executed?
   - must_not: were these steps avoided?
   - expected_outcome: LLM judge evaluates if outcome was achieved
4. Aggregate results: pass rate, failures, non-determinism score
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from flowstrix.engine.context import ExecutionContext, StepStatus
from flowstrix.engine.executor import JourneyExecutor, ToolRegistry
from flowstrix.gateway import GatewayConfig, create_client, resolve_model
from flowstrix.schema.models import AgentSpec, Simulation, SimulationScenario


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


@dataclass
class CheckResult:
    """Result of a single evaluation check."""

    check_name: str
    verdict: Verdict
    detail: str = ""


@dataclass
class RunResult:
    """Result of a single scenario execution."""

    run_number: int
    verdict: Verdict
    checks: list[CheckResult] = field(default_factory=list)
    execution_time_ms: float = 0.0
    steps_executed: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.verdict == Verdict.PASS


@dataclass
class ScenarioResult:
    """Aggregated result for a scenario across N runs."""

    scenario_name: str
    description: str
    runs: list[RunResult] = field(default_factory=list)
    pass_threshold: float = 0.8

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.runs if r.passed)

    @property
    def total_runs(self) -> int:
        return len(self.runs)

    @property
    def pass_rate(self) -> float:
        if not self.runs:
            return 0.0
        return self.pass_count / self.total_runs

    @property
    def verdict(self) -> Verdict:
        if self.pass_rate >= self.pass_threshold:
            return Verdict.PASS
        return Verdict.FAIL

    @property
    def is_deterministic(self) -> bool:
        """True if all runs had the same verdict (no flakiness)."""
        if not self.runs:
            return True
        verdicts = set(r.verdict for r in self.runs)
        return len(verdicts) == 1


@dataclass
class SimulationResult:
    """Full simulation suite result."""

    suite_name: str
    scenarios: list[ScenarioResult] = field(default_factory=list)
    total_time_ms: float = 0.0

    @property
    def scenarios_passed(self) -> int:
        return sum(1 for s in self.scenarios if s.verdict == Verdict.PASS)

    @property
    def scenarios_total(self) -> int:
        return len(self.scenarios)

    @property
    def overall_verdict(self) -> Verdict:
        if all(s.verdict == Verdict.PASS for s in self.scenarios):
            return Verdict.PASS
        return Verdict.FAIL

    @property
    def total_runs(self) -> int:
        return sum(s.total_runs for s in self.scenarios)

    @property
    def total_passes(self) -> int:
        return sum(s.pass_count for s in self.scenarios)

    @property
    def flaky_scenarios(self) -> list[str]:
        """Scenarios that sometimes pass and sometimes fail."""
        return [s.scenario_name for s in self.scenarios if not s.is_deterministic]


class SimulationRunner:
    """Runs simulation suites against an agent spec.

    Usage:
        runner = SimulationRunner(spec, tools=tools)
        result = runner.run_suite("refund_scenarios")
        print(f"Passed: {result.scenarios_passed}/{result.scenarios_total}")
    """

    def __init__(
        self,
        spec: AgentSpec,
        tools: ToolRegistry | None = None,
        gateway_config: GatewayConfig | None = None,
        model: str | None = None,
        knowledge_base_path: Optional[Path] = None,
    ):
        self.spec = spec
        self.tools = tools or ToolRegistry()

        if gateway_config is None:
            gateway_config = GatewayConfig.from_env()

        self.gateway_config = gateway_config
        self.model = resolve_model(model or gateway_config.model)
        self.knowledge_base_path = knowledge_base_path

        # Separate client for the LLM judge (same gateway, could be different model)
        self.judge_client = create_client(gateway_config)

    def run_suite(
        self,
        suite_name: str | None = None,
        num_runs_override: int | None = None,
    ) -> SimulationResult:
        """Run a simulation suite (or all suites if name not specified).

        Args:
            suite_name: Which simulation to run. If None, runs all.
            num_runs_override: Override num_runs_per_scenario from spec.

        Returns:
            SimulationResult with full details.
        """
        suites = self._find_suites(suite_name)
        suite_start = time.time()

        all_scenario_results = []

        for suite in suites:
            num_runs = num_runs_override or suite.num_runs_per_scenario

            for scenario in suite.scenarios:
                scenario_result = self._run_scenario(
                    scenario,
                    num_runs=num_runs,
                    pass_threshold=suite.pass_threshold,
                )
                all_scenario_results.append(scenario_result)

        total_time = (time.time() - suite_start) * 1000

        return SimulationResult(
            suite_name=suite_name or "all",
            scenarios=all_scenario_results,
            total_time_ms=total_time,
        )

    def _find_suites(self, name: str | None) -> list[Simulation]:
        """Find simulation suites by name."""
        if name is None:
            return self.spec.simulations

        for sim in self.spec.simulations:
            if sim.name == name:
                return [sim]

        available = [s.name for s in self.spec.simulations]
        raise ValueError(f"Simulation '{name}' not found. Available: {available}")

    def _run_scenario(
        self,
        scenario: SimulationScenario,
        num_runs: int,
        pass_threshold: float,
    ) -> ScenarioResult:
        """Run a single scenario N times and aggregate results."""
        scenario_result = ScenarioResult(
            scenario_name=scenario.name,
            description=scenario.description,
            pass_threshold=pass_threshold,
        )

        for i in range(num_runs):
            run_result = self._execute_single_run(scenario, run_number=i + 1)
            scenario_result.runs.append(run_result)

        return scenario_result

    def _execute_single_run(
        self,
        scenario: SimulationScenario,
        run_number: int,
    ) -> RunResult:
        """Execute one run of a scenario and evaluate it."""
        start_time = time.time()

        # Determine which journey to run (infer from trigger keywords)
        journey_name = self._infer_journey(scenario)

        # Build context from scenario description
        context_data = self._build_scenario_context(scenario)

        # Get user message
        user_message = scenario.user_messages[0] if scenario.user_messages else scenario.description

        # Execute the journey
        try:
            executor = JourneyExecutor(
                self.spec,
                tools=self.tools,
                gateway_config=self.gateway_config,
                model=self.model,
                knowledge_base_path=self.knowledge_base_path,
            )
            ctx = executor.run(
                journey_name,
                user_message=user_message,
                context_data=context_data,
            )
        except Exception as e:
            return RunResult(
                run_number=run_number,
                verdict=Verdict.ERROR,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        # Evaluate the run
        checks = self._evaluate_run(ctx, scenario)
        execution_time = (time.time() - start_time) * 1000

        # Overall verdict: pass only if ALL checks pass
        all_passed = all(c.verdict == Verdict.PASS for c in checks)

        steps_executed = [t.step_name for t in ctx.traces]

        return RunResult(
            run_number=run_number,
            verdict=Verdict.PASS if all_passed else Verdict.FAIL,
            checks=checks,
            execution_time_ms=execution_time,
            steps_executed=steps_executed,
        )

    def _evaluate_run(
        self,
        ctx: ExecutionContext,
        scenario: SimulationScenario,
    ) -> list[CheckResult]:
        """Evaluate a run against all scenario criteria."""
        checks = []
        steps_executed = [t.step_name for t in ctx.traces]

        # Check 1: Expected steps were executed
        if scenario.expected_steps:
            missing_steps = [s for s in scenario.expected_steps if s not in steps_executed]
            if missing_steps:
                checks.append(CheckResult(
                    check_name="expected_steps",
                    verdict=Verdict.FAIL,
                    detail=f"Missing steps: {missing_steps}",
                ))
            else:
                checks.append(CheckResult(
                    check_name="expected_steps",
                    verdict=Verdict.PASS,
                    detail=f"All expected steps executed: {scenario.expected_steps}",
                ))

        # Check 2: must_not steps were NOT executed
        if scenario.must_not:
            violated = [s for s in scenario.must_not if s in steps_executed]
            if violated:
                checks.append(CheckResult(
                    check_name="must_not",
                    verdict=Verdict.FAIL,
                    detail=f"Forbidden steps executed: {violated}",
                ))
            else:
                checks.append(CheckResult(
                    check_name="must_not",
                    verdict=Verdict.PASS,
                    detail=f"No forbidden steps executed",
                ))

        # Check 3: Execution didn't error out
        if ctx.status == StepStatus.FAILED:
            checks.append(CheckResult(
                check_name="execution_status",
                verdict=Verdict.FAIL,
                detail=f"Execution failed",
            ))
        else:
            checks.append(CheckResult(
                check_name="execution_status",
                verdict=Verdict.PASS,
                detail=f"Status: {ctx.status.value}",
            ))

        # Check 4: LLM Judge — did the expected outcome occur?
        if scenario.expected_outcome:
            judge_result = self._llm_judge(ctx, scenario)
            checks.append(judge_result)

        return checks

    def _llm_judge(
        self,
        ctx: ExecutionContext,
        scenario: SimulationScenario,
    ) -> CheckResult:
        """Use LLM-as-judge to evaluate if the expected outcome was achieved.

        This is the key innovation for non-deterministic testing:
        instead of exact string matching, we ask an LLM to judge whether
        the conversation achieved the intended outcome.
        """
        # Build the judge prompt
        steps_executed = [t.step_name for t in ctx.traces]
        conversation = "\n".join(
            f"{m['role']}: {m['content']}" for m in ctx.messages
        )

        judge_prompt = f"""You are an objective test evaluator. Determine if the agent achieved the expected outcome.

## Scenario
{scenario.description}

## Expected Outcome
{scenario.expected_outcome}

## What Actually Happened

### Steps Executed
{', '.join(steps_executed)}

### Execution Status
{ctx.status.value}

### Conversation
{conversation if conversation else '(no conversation — execution may have paused at HITL)'}

### Context Data
{self._summarize_context(ctx)}

## Your Task
Did the agent achieve the expected outcome? Consider:
1. Were the right actions taken (steps match expectations)?
2. Was the user communicated with appropriately?
3. Was the outcome functionally correct (even if wording differs)?

Respond with EXACTLY one of:
- PASS: The expected outcome was achieved
- FAIL: The expected outcome was NOT achieved

Then on the next line, provide a brief explanation (one sentence).
"""

        try:
            response = self.judge_client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=0.0,
                messages=[{"role": "user", "content": judge_prompt}],
            )

            judge_text = response.content[0].text.strip()
            lines = judge_text.split("\n", 1)
            verdict_line = lines[0].strip().upper()
            explanation = lines[1].strip() if len(lines) > 1 else ""

            if "PASS" in verdict_line:
                return CheckResult(
                    check_name="outcome_judge",
                    verdict=Verdict.PASS,
                    detail=explanation,
                )
            else:
                return CheckResult(
                    check_name="outcome_judge",
                    verdict=Verdict.FAIL,
                    detail=explanation,
                )

        except Exception as e:
            return CheckResult(
                check_name="outcome_judge",
                verdict=Verdict.ERROR,
                detail=f"Judge failed: {e}",
            )

    def _infer_journey(self, scenario: SimulationScenario) -> str:
        """Infer which journey to run from the scenario.

        Matches scenario description / user messages against journey triggers.
        Falls back to first journey if no match.
        """
        scenario_text = (
            scenario.description + " " + " ".join(scenario.user_messages)
        ).lower()

        best_match = None
        best_score = 0

        for journey in self.spec.journeys:
            score = 0
            # Check trigger keywords
            for keyword in journey.trigger.intent_keywords:
                if keyword.lower() in scenario_text:
                    score += 1

            # Check if expected steps belong to this journey
            journey_step_names = {s.name for s in journey.steps}
            for expected in scenario.expected_steps:
                if expected in journey_step_names:
                    score += 2  # Strong signal

            if score > best_score:
                best_score = score
                best_match = journey.name

        return best_match or self.spec.journeys[0].name

    def _build_scenario_context(self, scenario: SimulationScenario) -> dict[str, Any]:
        """Build initial context data from scenario description.

        Infers customer_id from scenario name/description for demo tool routing.
        """
        context: dict[str, Any] = {}

        desc_lower = scenario.description.lower()

        # Infer customer type for demo tools
        if any(w in desc_lower for w in ["$750", "high value", "expensive", "furniture"]):
            context["customer_id"] = "cust_vip"
        elif any(w in desc_lower for w in ["45 days", "6 weeks", "old", "expired", "outside"]):
            context["customer_id"] = "cust_old"
        else:
            context["customer_id"] = "cust_standard"

        return context

    @staticmethod
    def _summarize_context(ctx: ExecutionContext) -> str:
        """Summarize context data for the judge (truncate large values)."""
        parts = []
        for k, v in ctx.data.items():
            val_str = str(v)
            if len(val_str) > 150:
                val_str = val_str[:150] + "..."
            parts.append(f"- {k}: {val_str}")
        return "\n".join(parts) if parts else "(empty)"
