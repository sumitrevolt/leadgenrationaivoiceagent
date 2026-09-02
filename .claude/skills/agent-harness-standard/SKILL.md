---
name: agent-harness-standard
description: |
  The org's governed Agent Harness Engineering Standard & Reference Architecture — a vendor/model-neutral blueprint (control matrix, self-certification checklist, L1-L5 maturity ladder) for building reliable, auditable agent loops. Use when designing or reviewing ANY agent loop in this repo (self_improve, coordinator, process_engine, dag_engine, sales_team, engineer agents, or a brand-new staff agent) for containment, least-privilege, stopping conditions, or observability; when the user says "self-certify", "conformance check", "harness audit", "is this agent governed/enterprise-grade", "control matrix", "maturity level", or before requesting the next build/funding tranche for an agent capability. Full detail: reference.md. Scoring agent: `harness-conformance-auditor`.
---

# Agent Harness Engineering Standard (LeadGenAI)

> Source: *Agent Harness Engineering Standard & Reference Architecture* (AI Platform Engineering — Office of the CTO, 22 Jul 2026), condensed for this repo. Full tables (control matrix, checklist, maturity ladder, threat model, module contracts, regulatory mapping): `reference.md`. To actually SCORE an existing loop against this standard, dispatch the `harness-conformance-auditor` agent — this file is the reference, not the scorer.

## Thesis (read this first)

Same model + same task can succeed cheap or fail expensive — the deciding variable is the **harness**, not the model. When an agent misbehaves (loops forever, takes an unapproved action, burns budget, "succeeds" but is wrong), the defect almost always lives in context assembly, tool contracts, permissions, stopping conditions, or recovery logic. Inspect those before reaching for a bigger/different model.

## Four-layer vocabulary (don't blur these — every downstream control attaches to one)

| Layer | Supplies | Question it answers |
|---|---|---|
| Model | intelligence | "What should be done?" |
| Tools | capabilities | "What is it able to do?" |
| Sandbox | containment | "Where does it run, and what if it's wrong?" |
| **Harness** | **control** | "Who is in charge?" — context assembly, tool routing, state, stopping, recovery |

## Five architectural invariants (non-negotiable; restated as pass/fail controls below)

1. **Structured-request** — the model MUST NOT mutate any asset directly; it only emits schema-conformant requests the harness executes. No exceptions for "trusted" tools.
2. **Validate-before-execute** — no request reaches the sandbox until it clears schema + permission + budget validation.
3. **Contained-execution** — all model-directed work runs sandboxed, least-privilege, egress-controlled.
4. **Observability** — every model call + tool execution produces a correlated trace; a run with trace gaps is non-conformant.
5. **Harness-owned termination** — stopping (success / caps / error / kill) is the orchestrator's decision, never inferred from the model's own prose claim of success.

## Module map (M1–M7) — buildable units, mapped onto this repo

| ID | Module | Owns | LeadGenAI mapping (approx — verify, don't assume) |
|----|--------|------|------------------------------|
| M1 | Agent-Loop Core | turn cycle, explicit stop conditions, turn/cost budgets | `self_improve.py` tick, `process_engine.py`, `dag_engine.py`, `coordinator.py` |
| M2 | Tool Registry & Contract Layer | tool schemas, request validation, least-privilege permissioning, versioning | function/tool-call schemas, `mcp_engineer.py` |
| M3 | Sandboxed Executor | isolation boundary, diff/output capture, timeouts, egress control, secret injection | wherever agent-directed code/tool exec actually runs |
| M4 | Context Assembly & Compaction | working-set construction, prior-attempt legibility, pre-overflow compaction | context builders feeding each LLM call |
| M5 | Durable State & Checkpoint | append-only turn journal, checkpoint/resume, idempotency | jsonl run logs, `dlq_retry.py`, `data/<loop>_state.json` heartbeats |
| M6 | Observability Plane | per-call trace spans (OTel-aligned), metrics | `team.log_event`, `automation-health`, OTel (if wired) |
| M7 | Evaluation Harness | golden-task suite, success/cost/latency/turns, go/no-go gate | `eval_gate.py` |

Conformant = M1–M5 at MUST-level; M6/M7 are cross-cutting and bind into all five.

## Sandbox containment tiers — assign the MINIMUM tier that safely contains the action

`T0` in-process validation only (schema/permission/budget check, no execution) · `T1` container, read-only base + ephemeral repo copy, default-deny net (read-only actions, static analysis) · `T2` hardened runtime / gVisor-class, allow-listed egress (run_test, edit_file, dependency install) · `T3` microVM, egress-proxied+logged (untrusted third-party code, anything touching secrets).

## Control Matrix (condensed — stable IDs used in traces/ADRs/checklist; full table + pass/fail tests in reference.md)

- **AC-01..03** context provenance tagging (trusted-instruction vs untrusted-data) · PII/secret redaction on context ingress · tenant/residency scoping of context fetch.
- **VA-01/02** schema validation on every model-requested action · intent/argument bounds check (path traversal etc.) against declared scope.
- **PM-01..03** least-privilege tool contract bound to task profile · per-run capability tokens expired at termination · dangerous-action HITL approval gate (delete / external send / protected-branch push / payment).
- **SB-01..04** sandbox tier matches the action's trust level · default-deny egress with per-run allow-list · ephemeral per-run env destroyed at termination · checkpoint before any state-mutating action.
- **DL-01** output/diff scan before any externally visible write (secret-leak block).
- **OB-01/02** immutable per-call trace (WORM/hash-chained) · replayable audit log linking run → trace → evals → approvals.
- **ST-01..03** hard budget caps (tokens/cost/wall-clock/tool-calls/iterations), halt+checkpoint on breach · progress/stall detector (oscillation, repeated identical calls) · operator kill switch (per-run + fleet-wide).
- **GV-01** no tool entry point bypasses VA-01/02 — any direct model→side-effect path is a fail.

Four principles bind the matrix: **default deny** (absence of a grant = denial, not ambiguity) · **authorization is never delegated to the model** (it may request, only harness policy code may authorize) · **fail closed, checkpoint, preserve evidence** on any breach · **every control is pass/fail testable**, or it isn't a control.

## Self-certification checklist (C-01..C-15 — condensed; full evidence/test columns in reference.md)

C-01 every invocable tool has a machine-readable contract · C-02 malformed/off-schema requests are rejected, never coerced · C-03 least-privilege (granted scope ⊆ scope actually exercised) · C-04 model-directed work executes only inside the sandbox · C-05 default-deny egress · C-06 budget caps enforced, loop halts on breach · C-07 explicit non-trivial stop conditions — no infinite loop, no reliance on an external watchdog kill · C-08 high-impact actions are HITL-gated · C-09 context compacts before window overflow, no silent truncation · C-10 checkpointing enables rollback/resume to a known-good state · C-11 every call/action/observation is traced with run-correlation, no gaps · C-12 wired to a golden-task eval suite scoring success/cost/latency/turns · C-13 documented, drilled kill switch · C-14 prompts/contracts/permissions/policies are versioned and change-controlled · C-15 one representative end-to-end task passes with all controls active.

Attestation without an attached evidence artifact = fail. An item marked N/A needs a written justification, not silence.

## Maturity ladder (L1 → L5, cumulative — a level requires every lower level's criteria too)

**L1** Prototype loop — schema-validated + sandboxed + hard step/token cap as the only stop condition. **L2** Contained agent — + least-privilege tools, enforced budgets, default-deny egress. **L3** Observable & recoverable — + full-fidelity tracing, checkpoint/rollback, a drilled kill switch. **L4** Eval-gated — + golden-task suite blocks regressions, HITL on high-impact actions. **L5** Governed platform — continuous audit + drift alerting + inherited by other teams/projects.

L3→L4 is the hard pivot: no eval suite, no L4 claim ("reliable" is otherwise unfalsifiable). L5 is a platform designation (independently audited + inherited elsewhere), not a per-loop claim.

## Workflow — applying this standard to a LeadGenAI loop

1. **Locate the stage.** S1 context assembly / S2 model invocation / S3 action authorization / S4 execution / S5 observation / S6 termination (full stage table in reference.md §5.1).
2. **Run the checklist.** Before adding or changing a loop, walk C-01..C-15 against it. Cite `file:line` evidence — "looks fine" is not a pass.
3. **Score the level.** State the current maturity level (L1-L5) and what's missing for the next one — don't claim a level without every lower level's criteria holding too.
4. **Propose the minimal fix.** Any gap → name the control ID, propose the smallest closing change, flag-gated per this repo's own `agent-loop-design` guards checklist. Don't gold-plate past what the workload needs (a throwaway dev-sandbox loop doesn't need L4).
5. **Gate dangerous actions.** Delete / external-send / protected-branch-push / payment / money-moving actions route through this repo's approvapapattern (e.g. `SELF_IMPROVE_APPROVAL`-style gate) before execution — never on the model's say-so alone (PM-03).

## Related repo skills — cross-reference, don't duplicate

`agent-loop-design` (this repo's own loop-anatomy: pick/execute/learn/requeue + dead-man trio) — this standard's M1 and ST-01..03 are the SAME guards, formalized with control IDs; read both together. `leadgen-automation-reliability` (Celery durable/DLQ/idempotency) → maps to M5/SB-03/C-10. `leadgen-security-rbac`, `security-review` → maps to PM-01..03/SB-01..04/GV-01. `leadgen-observability` → maps to M6/OB-01/02/C-11. `self-improve-loop`, `self-improve-control` → the highest-blast-radius existing loop; run the checklist against it first. `teach-agent-loop` → use when the gap found is "no clean way to add a new staff agent" (C-14 territory).

## Regulatory mapping (why this is more than engineering taste)

Every control group maps to at least one of NIST AI RMF, ISO/IEC 42001, ISO/IEC 27001, SOC 2 (TSC), and EU AI Act (Art. 9/10/12/13/14/15) — full crosswalk in reference.md §5.10. Passing the Control Matrix is, by construction, evidence toward all five; a control with no mapping is incomplete.

## Output (when applying this standard to a review or design)

Report: harness stage(s) reviewed → C-01..C-15 pass/fail with `file:line` evidence → current maturity level (L1-L5) claimed and justified (or the honest lower level) → gaps ranked by control ID with minimal fix + risk tier + flag → one-line certifiable-at-L_-or-not verdict. Never claim a level you didn't evidence.
