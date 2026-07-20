# FlowStrix

**Agent-native workflow engine — what traditional low-code Flow would look like if rebuilt for the AI era.**

FlowStrix is a proof-of-concept that explores the intersection of low-code automation and AI agents. It answers the question: *what if we kept Flow's strengths (declarative, auditable, enterprise-grade) but replaced the execution primitive from "deterministic steps" to "intelligent agents with guardrails"?*

---

## The Thesis

| Traditional Flow | FlowStrix |
|---|---|
| Drag elements onto a canvas | Describe workflows in natural language |
| Decision elements with explicit conditions | LLM reasoning bounded by guardrails |
| Deterministic execution (same input → same output) | Probabilistic execution with deterministic gates |
| Screen flows for user interaction | Conversational agents across any channel |
| Test coverage metrics | AI-driven simulation suites |
| Debug logs | Full execution traces with LLM call auditing |

**The key insight:** The hard problems are the same (failure handling, human approval gates, auditability, testing). The abstraction level is different.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    YAML Agent Spec                    │
│  (persona + journeys + knowledge + simulations)      │
└────────────────────────┬────────────────────────────┘
                         │ parse & validate
                         ▼
┌─────────────────────────────────────────────────────┐
│              Pydantic Schema Models                   │
│  (typed, validated, serializable)                     │
└────────────────────────┬────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────┐
│   Executor   │ │  Simulator  │ │  Ghostwriter │
│  (LangGraph) │ │  (Testing)  │ │  (Compiler)  │
│              │ │             │ │  NL → YAML   │
│ • lookup     │ │ • scenario  │ │              │
│ • reason     │ │ • multi-run │ │ • describe   │
│ • respond    │ │ • LLM-judge │ │ • emit spec  │
│ • branch     │ │ • coverage  │ │ • validate   │
│ • hitl       │ │             │ │              │
│ • tool       │ │             │ │              │
└──────────────┘ └─────────────┘ └──────────────┘
       │                                  │
       ▼                                  ▼
┌─────────────────────────────────────────────────────┐
│              Knowledge Layer (Qdrant RAG)             │
│  documents • URLs • APIs • databases                 │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# Install
pip install -e .

# Validate a spec
flowstrix validate examples/customer_support.yaml

# Inspect (visual overview)
flowstrix inspect examples/customer_support.yaml

# Run a journey
flowstrix run examples/customer_support.yaml \
  --journey handle_refund_request \
  --message "I want a refund for my damaged item" \
  --context '{"customer_id": "cust_123"}'
```

---

## The Schema: YAML as the Agent Contract

Every agent is defined by a single YAML file. This is the **core design artifact** — it's what the Ghostwriter compiler emits, what the executor consumes, and what the simulator tests against.

```yaml
agent: customer_support

persona:
  name: "Alex"
  tone: "Friendly, concise, empathetic"
  guardrails:
    - "Never promise refunds before verifying eligibility"
  off_limits:
    - "Competitor pricing"

journeys:
  - name: handle_refund_request
    trigger:
      description: "Customer asks for a refund"
    steps:
      - type: lookup          # Deterministic: fetch data
        name: fetch_orders
        tool: get_orders_by_customer_id

      - type: reason          # Probabilistic: LLM decides
        name: check_eligibility
        prompt: "Is this eligible per our policy?"
        knowledge: [refund_policy]

      - type: branch          # Deterministic: route
        condition: "${eligible}"
        if_true: process_refund
        if_false: explain_why_not

      - type: hitl            # Gate: human approval
        condition: "${amount} > 500"
        escalate_to: senior_agent

knowledge:
  - id: refund_policy
    source_type: document
    uri: "docs/refund-policy.md"

simulations:
  - name: refund_scenarios
    scenarios:
      - name: eligible_small_refund
        expected_outcome: "Refund processed"
      - name: too_old_for_refund
        expected_outcome: "Denied with alternatives"
```

---

## Step Types: The Agent Primitives

| Step | Deterministic? | Flow Equivalent | Purpose |
|------|:---:|---|---|
| `lookup` | ✅ | Get Records | Fetch data from tools/APIs |
| `reason` | ❌ | Decision (but smarter) | LLM evaluates context against knowledge |
| `respond` | ❌ | Screen element | Generate user-facing message |
| `branch` | ✅ | Decision element | Conditional routing |
| `hitl` | ✅ | Pause + Approval | Human gate before destructive actions |
| `tool` | ✅ | Apex Action | Execute a deterministic action |
| `wait` | ✅ | Pause element | Wait for event/timeout |

**Design principle:** Deterministic where possible, probabilistic where necessary. Every LLM call is explicitly marked, bounded by temperature + token limits + output schema.

---

## Roadmap (9-Month Learning Plan)

### Phase 1: Foundation ← **YOU ARE HERE**
- [x] YAML schema design
- [x] Pydantic model parsing
- [x] Basic executor (step-by-step)
- [x] CLI (validate, inspect, run)
- [ ] Demo video / leadership walkthrough

### Phase 2: Knowledge & RAG
- [ ] Qdrant integration for knowledge sources
- [ ] Document ingestion pipeline
- [ ] Context-aware retrieval during `reason` steps
- [ ] Knowledge gap detection

### Phase 3: LangGraph Executor
- [ ] Migrate executor to LangGraph state machine
- [ ] Parallel step execution
- [ ] Persistent state (resume after HITL)
- [ ] Multi-turn conversation support

### Phase 4: Ghostwriter (NL Compiler)
- [ ] Natural language → YAML compilation
- [ ] SOP document parsing
- [ ] Iterative refinement ("make it also handle exchanges")
- [ ] Schema validation in the loop

### Phase 5: Simulation Runner
- [ ] AI-driven conversation generation
- [ ] LLM-as-judge evaluation
- [ ] Regression suite management
- [ ] Non-determinism quantification (N runs per scenario)

### Phase 6: API & UI
- [ ] FastAPI server for real-time agent execution
- [ ] WebSocket support for streaming responses
- [ ] Simple React UI for conversation testing
- [ ] Deployment dashboard

---

## Why This Matters

1. **Flow's ceiling is process definition.** When the logic gets complex enough, admins hit a wall. Agents reason through complexity instead of requiring every path to be pre-defined.

2. **The builder's job changes.** From "architect every possible path" to "provide the right context, goals, and guardrails." This is more natural for domain experts.

3. **Testing gets harder but more realistic.** You can't just unit-test deterministic paths. You need simulation suites that run many conversations and evaluate outcomes. This is a harder engineering problem but produces more realistic confidence.

4. **The same hard problems remain.** HITL gates, auditability, failure handling, safe rollout — these don't go away with agents. They just need different primitives.

5. **Sierra proved the market.** $4.5B valuation, 40% of Fortune 50, built by former enterprise tech leaders. This isn't hypothetical — it's the direction the industry is moving.

---

## Technical Decisions

- **Python + FastAPI**: Fastest path to working demo, rich LLM ecosystem
- **Anthropic Claude**: Primary LLM for reasoning/response steps
- **Pydantic**: Schema validation with clear error messages
- **YAML**: Human-readable agent definitions (the "source code")
- **Qdrant** (Phase 2): Vector DB for knowledge retrieval
- **LangGraph** (Phase 3): State machine for complex journey execution
- **Instructor** (Phase 4): Structured LLM output for Ghostwriter

---

*Built by Anjesh Dubey as a POC exploring agent-native automation.*
