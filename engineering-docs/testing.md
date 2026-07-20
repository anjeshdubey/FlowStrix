# Testing Strategy & Simulation

FlowStrix features a robust testing suite consisting of standard unit/integration tests (`pytest`) and an AI-driven test simulator.

---

## 🧪 AI-Driven Test Simulation

In traditional deterministic programming, unit tests assert exact output matches. However, AI agents behave non-deterministically. 

FlowStrix addresses this by implementing an **AI-Driven Simulation Runner** directly into the spec definition. 

### Defining a Simulation Scenario
In `customer_support.yaml`, you define scenario test suites:
```yaml
simulations:
  - name: refund_scenarios
    scenarios:
      - name: eligible_small_refund
        description: "Customer bought 3 days ago, item arrived damaged, wants refund"
        user_messages:
          - "Hi, I received my order yesterday but the item is damaged. I'd like a refund."
        expected_outcome: "Refund processed successfully"
        expected_steps:
          - fetch_order_history
          - determine_eligibility
          - process_refund_action
        must_not:
          - escalate_high_value
```

### The LLM-as-a-Judge Evaluation Pipeline
When you execute `flowstrix simulate`, the runner performs the following steps:
1.  **Multiple Run Cycles:** Executes each scenario $N$ times (default: 5) to check for flaky outputs and non-determinism.
2.  **Step Assertions:** Asserts that the agent executed all required steps (e.g. `process_refund_action`) and did not touch forbidden steps (e.g. `escalate_high_value`).
3.  **Outcome Evaluation:** Feeds the final conversation logs and execution context into a separate LLM connection acting as the Judge. The Judge evaluates the semantic outcome against the `expected_outcome` (ignoring trivial phrasing changes) and issues a strict `PASS` or `FAIL`.

---

## 💻 Running the Application Locally

Follow these instructions to run the tests, check simulations, and start the local workspace stack.

### 1. Prerequisite Setup
Ensure you have Python 3.9+ and Node.js 18+ installed on your system.

```bash
# Clone the repository and install dependencies
cd /Users/anjeshdubey/projects/flowstrix
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Configure your environment keys:
```bash
cp .env.example .env
# Open .env and add your GEMINI_API_KEY or GROQ_API_KEY
```

### 2. Running Unit & Integration Tests
We use `pytest` for codebase tests:
```bash
# Run the complete test suite
pytest
```

### 3. Running CLI Simulations
Execute the AI-driven test simulations to evaluate model behavior and pass rates:
```bash
# Run the refund simulation suite
flowstrix simulate examples/customer_support.yaml --suite refund_scenarios --runs 3
```

### 4. Running the Local API & UI Stack
Start the server and React application to interact with your agents via the web interface.

**Terminal A (API Backend):**
```bash
source .venv/bin/activate
flowstrix serve
```

**Terminal B (Vite + React Frontend):**
```bash
cd ui
npm install
npm run dev
```

Open your browser to: **`http://localhost:3001`** (or the port specified by Vite in Terminal B) to start experimenting with FlowStrix!
