# Agent Harness Engineering Standard — Full Reference

> Condensed-but-faithful extraction from *Agent Harness Engineering Standard & Reference Architecture* (AI Platform Engineering — Office of the CTO, 22 Jul 2026, Draft for ARB approval). This file preserves the normative tables and RFC-2119-worded contracts; narrative framing/business-case sections are summarized. See `SKILL.md` in this same folder for the working, repo-mapped summary. Original source: the uploaded `Agent_Harness_Engineering_Standard.docx`.

## Thesis

The same model, given the same task, can succeed cheaply or fail expensively. The deciding variable is the **harness** — the runtime control loop wrapping the model that decides what context is assembled, which tools are exposed, where model-directed actions execute, how state survives, and when to stop. Reliability, cost, and auditability are properties of the harness, not the model weights. "Enterprise-grade" means **governability plus measurability** — never "a working demo": behavior bounded by testable controls, quality proven by golden-task measurement, every run traceable, every control auditable.

## The five harness responsibilities (R1–R5) — why identical inputs diverge

The model never operates on the raw task; it operates on whatever the harness constructs and permits. Two runs on an identical model/prompt/task diverge because of these five responsibilities:

- **R1 — Assemble** the working context (task, conventions, relevant files, prior attempts, tool schemas).
- **R2 — Expose** a deliberately narrow, contract-bound tool set; the model never touches assets directly, only emits structured requests.
- **R3 — Validate & execute**: check the request against schema, permissions, and budget, then run it in an isolated sandbox, capturing stdout/stderr/exit code/diffs.
- **R4 — Record**: write the observation into durable state and checkpoint progress.
- **R5 — Decide**: call the model again, halt on success, halt on budget/step cap, or pause for human approval.

Diagnostic discipline this standard institutionalizes: **when an agent fails, inspect context, tool contracts, permissions, stopping conditions, and recovery logic before considering a model change.**

## Three-layer vocabulary and seams

- **Framework ↔ Harness seam** — a framework provides a loop primitive; the harness decides the stopping conditions that primitive enforces. A convergence failure is (almost always) a harness-configuration bug, not a framework bug.
- **Harness ↔ Sandbox seam** — the harness validates and dispatches; the sandbox executes and contains. "The agent deleted a file it shouldn't have" resolves to exactly one side: harness admitted an out-of-contract action, or sandbox failed to contain a validly-dispatched one.
- **Harness ↔ Model seam** — the model returns structured requests, never side effects. Every model-requested action is mediated, hence inspectable, permissionable, budgetable, loggable.

## Stakeholder / concern register (ISO/IEC/IEEE 42010 alignment)

| Stakeholder | Primary concerns | Addressed by |
|---|---|---|
| Harness / agent engineer | Control-loop structure; extension points; state survival | C4 Container view; Component register |
| Tools & sandbox engineer | Execution location; isolation/egress boundaries; permission model | Sandbox execution, tool routing/permits |
| Eval / QA engineer | Golden-task linkage; per-turn signals captured | Evaluation hooks, tracing |
| Security & governance | Untrusted-output validation; least-privilege/HITL; auditability | Request validation, approvals/HITL; Control Matrix |
| SRE / operations | Budget/step caps; kill switch; checkpoint/rollback; observability | Stopping conditions, state/checkpointing, tracing |
| CTO / sponsor & ARB | Cost-of-success vs cost-of-failure; model-neutrality; durability | Context view; standard's thesis |
| Compliance / audit | Human oversight, logging, containment, decision traceability | HITL, tracing, control mapping |

## Logical component register (10 normative components)

| # | Component | Core responsibility | Failure mode it prevents |
|---|---|---|---|
| 1 | Context Assembler | Build working context per turn (task, conventions, files, prior attempts, tool schemas) | Model acting on missing/irrelevant context; hallucinated tool signatures |
| 2 | Compaction Engine | Summarize/evict context before window overflow | Context overflow; loss of earlier findings mid-task |
| 3 | Request Validator | Validate every request vs. schema/permissions/budget | Malformed, out-of-scope, or budget-busting actions reaching the sandbox |
| 4 | Tool Router & Permit Broker | Resolve tool, bind least-privilege permit | Over-broad capability (read task gaining write/network rights) |
| 5 | Sandbox Executor | Execute in isolation, capture output/errors/diffs | Uncontained side effects; exfiltration; host compromise |
| 6 | State & Checkpoint Store | Durable state, diffs, per-step checkpoints | Irrecoverable runs; can't roll back a bad edit |
| 7 | Approval / HITL Gateway | Pause for human sign-off on gated actions | Autonomous execution of risky changes without oversight |
| 8 | Tracing & Observability | OTel span per model/tool call, correlated by run ID | Unauditable behavior; no post-hoc diagnosis |
| 9 | Evaluation Hooks | Connect runs to golden-task suite | "Enterprise-grade" as an untested adjective |
| 10 | Stopping Conditions | Success/caps/error/kill switch | Runaway loops; expensive failures; infinite retries |

## Architectural invariants

Structured-request · Validate-before-execute · Contained-execution · Observability · Harness-owned termination. (Definitions in SKILL.md — restated here as the load-bearing minimum distinguishing a governed harness from a demo wrapper.)

## Module map and contracts (M1–M7)

| ID | Module | Owns | Binds to worked example |
|----|---|---|---|
| M1 | Agent-Loop Core | Turn cycle, stop conditions, budgets, orchestration | Drives read→edit→run_test to a verdict |
| M2 | Tool Registry & Contract Layer | Tool schemas, request validation, permissioning, versioning | Declares/gates read_file, edit_file, run_test |
| M3 | Sandboxed Executor | Isolation, capture, timeouts, egress, secret injection | Runs the test suite; captures diffs, stdout/stderr |
| M4 | Context Assembly & Compaction | Working-set construction, summarization, prior attempts | Assembles task, repo rules, files, prior tries, schemas |
| M5 | Durable State & Checkpoint | Turn journal, checkpoint/resume, idempotency | Records each observation; enables resume after crash |
| M6 | Observability Plane | Tracing, metrics, spans per call | Traces every model and tool call |
| M7 | Evaluation Harness | Golden tasks, scoring, go/no-go gate | Scores "tests pass at acceptable cost" |

### M1 — Agent-Loop Core

One iteration = a turn. Ordered phases: **Assemble** (from M4/M5) → **Invoke** (model + M2 tool contracts) → **Parse** (typed actions or terminal finish; anything else = `MalformedResponse`, never silently dropped) → **Authorize & Validate** (via M2; rejections feed back as observations) → **Execute** (dispatch to M3) → **Observe** (write to M5) → **Evaluate stop conditions** (halt on first that fires).

The completion predicate MUST be explicit and machine-checkable, never inferred from model prose (e.g. "most recent `run_test` observation reports exit 0 and zero failing tests" — a model *claiming* success in prose while tests still fail MUST NOT satisfy `TaskComplete`).

Budgets (both mandatory): **turn budget** (`max_turns`, caps iterations) and **cost budget** (`max_cost` — projected post-turn cost checked *before* invoking the model, refuse rather than discover after spending).

Failure modes: `MalformedResponse` → surfaced as next observation, counts against turn budget up to a `max_malformed` sub-cap, then halt failed. `PartialActionBatch` → execute valid ones, feed rejections back, never fail the whole turn for one bad action. `StateWriteFailure` → `HardError`; an unrecorded turn MUST NOT be considered to have happened.

### M2 — Tool Registry & Contract Layer

Every tool has a JSON Schema/MCP-aligned contract with `permissions`, `danger_class` (safe | reversible | dangerous), `scope` (path/size/target bounds), `sandbox_tier`. Semantic versioning: breaking changes = major bump, old major stays resolvable during a deprecation window; a run pins the tool's major version.

Error taxonomy (loop treatment):

| Class | Meaning | Loop treatment |
|---|---|---|
| ValidationError | Schema/argument check failed | Not executed; observation; retryable |
| PermissionDenied | Not in permission set | Not executed; not retryable without escalation |
| BudgetDenied | Would breach budget | Not executed; typically triggers a stop condition |
| ExecutionError | Ran but failed (non-zero exit/exception) | Executed; error captured; retryable |
| Timeout | Exceeded `timeout_s` | Terminated by M3; captured |
| InfraError | Registry/sandbox unavailable | HardError; not the model's fault |

Only "not executed" classes (ValidationError/PermissionDenied/BudgetDenied) guarantee no side effect — this is what M5 idempotency relies on.

### M3 — Sandboxed Executor

Isolated per-run environment (container/microVM/equivalent), destroyed at run end: isolated filesystem seeded only with the task repo, isolated process namespace, no ambient credentials, default-deny egress. Mutating actions MUST capture a structured diff (path, before-sha, after-sha, unified diff); writes escaping the repo root are rejected even if M2's check were bypassed (defense in depth). stdout/stderr captured separately, size-bounded with explicit truncation markers (never silent). Every execution carries a `timeout_s`; on expiry the process tree is terminated and a `Timeout` observation returned. Egress default-deny; a tool needing network access declares it in its contract and gets an allow-listed destination set for that action's duration only. Secrets injected at execution time as short-lived, least-privilege tokens — never baked into the image, always redacted from captured output/traces.

### M4 — Context Assembly and Compaction

Working set MUST include: task statement; repo/agent conventions; relevant files selected by relevance (not the whole repo); prior-attempt outcomes in this run; the tool contracts for the run's permission set. Compaction MUST trigger before overflow (e.g. at 70% of window), never after a hard failure: retain task/conventions/tool-contracts verbatim, retain the most recent K turns verbatim, summarize older turns preserving load-bearing facts (files changed, tests moved red↔green, dead ends ruled out). What's compacted and when MUST be recorded in state and traced.

### M5 — Durable State, Checkpoint and Idempotency

Every turn appends an **immutable, append-only** journal record: context ref, raw model response, parsed actions, validation verdicts, observations (incl. diffs/error classes), resolved tool versions, cumulative budget, stop-condition evaluation. Checkpointing at least every turn boundary (sandbox diff-set + journal + budget counters) enables resume-from-crash and rollback. Idempotency key = `run_id + turn + action_index + argument_hash`; a replayed already-applied `edit_file` returns the recorded observation rather than re-applying.

### Extension-point register (deliberately stubbed — honest foundation, not a hidden gap)

| Stubbed capability | Owning module | Why deferred |
|---|---|---|
| Full secrets management (vault, dynamic leasing, rotation) | M3 | Reference task needs no secrets |
| Dynamic RBAC per calling principal | M2 | Static named permission sets suffice for the reference |
| Horizontal scaling / sandbox pooling | M3 | One-sandbox-per-run is correct/simplest for a single run |
| Multi-agent orchestration | M1 | Single-agent loop is the honest primitive to standardize first |
| Retrieval-augmented / long-term memory | M4 | Rule-based relevance is deterministic and auditable |
| Distributed / HA state | M5 | Single durable store meets single-node needs |

Moving a stub to "implemented" is how a team advances maturity levels.

## Security, Governance and the Control Matrix

### Control stages (S1–S6, one-to-one with harness modules)

| Stage | Module | Trust boundary | Question answered |
|---|---|---|---|
| S1 Context Assembly | Context Builder | Enterprise data → prompt | Anything sensitive/poisoned/out-of-tenant entering context? |
| S2 Model Invocation | Orchestrator | Model → harness | Is the returned action well-formed and within declared intent? |
| S3 Action Authorization | Tool Router / Policy | Harness → tool contract | Is this action permitted, for this task, within budget? |
| S4 Execution | Sandbox | Tool → environment | Is the blast radius bounded and reversible? |
| S5 Observation | Tracer / State | Environment → state → next prompt | Logged immutably and scrubbed before re-entering context? |
| S6 Termination | Stop Controller | Loop → outside world | Continue, pause for approval, or halt? |

### Threat model (T1–T7)

| ID | Threat | Entry | Rating | Key mitigations |
|---|---|---|---|---|
| T1 | Prompt/context injection — malicious instructions ride in via untrusted data (README, comments, error strings, prior observations) | S1, S5 | High/High | Provenance tagging (trusted-instruction vs untrusted-data); injection can only *request*, never *authorize* (S3 lives outside the model) |
| T2 | Tool over-permissioning — broader/more dangerous surface than the task needs | S3 | Medium/High | Least-privilege contracts per task profile; expiring capability tokens; dangerous-action approval gates |
| T3 | Data exfiltration via context — sensitive data pulled in at S1, leaves via a tool at S4/S5 | S1→S4/S5 | Medium/High | Ingress/egress redaction; egress allow-listing + default-deny; tenant-scoped fetch; diff/output scanning |
| T4 | Sandbox escape / lateral movement | S4 | Low/Critical | Strong containment tiers, no host network, read-only base images, ephemeral envs, control plane never shares a trust zone with sandbox |
| T5 | Runaway cost / non-termination — oscillation, flaky-test retry loop, unbounded context growth | S2, S6 | Medium/Medium | Hard budget caps, monotonic-progress checks, kill switch (halt + checkpoint on breach) |
| T6 | Unauthorized/irreversible side effects — legitimate contract, but the instance needs human judgment | S3, S4 | Low/High | Dangerous-action classification + HITL, checkpoint-before-mutate, rollback/undo |
| T7 | Audit gap / non-repudiation failure — can't reconstruct what/why/on whose authority | S5 | (governance) | Immutable append-only per-call tracing + replayable audit logs + decision records |

### Design principles

**Default deny** (absence of a grant is a denial, not an ambiguity) · **authorization never delegated to the model** (only harness policy code authorizes) · **fail closed, checkpoint, preserve evidence** on any breach (halting is always safe) · **every control is testable** (a non-testable control is a policy, not a control, and doesn't appear in the matrix).

### The Control Matrix (full)

| ID | Control | Stage | Owner | Evidence artifact | Pass/fail test |
|---|---|---|---|---|---|
| AC-01 | Context provenance tagging (trusted-instruction vs untrusted-data) | S1 | Harness Eng | Context assembly manifest per run | Inject a benign marker instruction into an untrusted file; run must NOT act on it |
| AC-02 | PII/secret redaction on context ingress | S1 | Data Gov | Redaction policy + sampled context dumps | Seed a synthetic PAN + secret into source data; assert both masked in the assembled prompt |
| AC-03 | Tenant/data-residency scoping of context fetch | S1 | Data Gov | Access-scope query logs | Request an out-of-tenant record; fetch returns empty and logs a denied-access event |
| VA-01 | Schema validation on every model-requested action | S2 | Harness Eng | Rejected-request log + schema version | Submit malformed + unknown-tool action; both rejected before execution, logged with reason |
| VA-02 | Intent/argument bounds check (paths, sizes, targets within declared scope) | S3 | Harness Eng | Policy-decision log | Request `edit_file` outside the working tree; denied. Fail if path traversal succeeds |
| PM-01 | Least-privilege tool contract bound to task profile | S3 | Security | Signed tool-permission manifest | Diff granted tools against task profile; any tool not in profile fails |
| PM-02 | Per-run capability tokens, expired at termination | S3 | Platform/SRE | Token issuance & revocation ledger | Replay a post-run token; must be rejected as expired/revoked |
| PM-03 | Dangerous-action approval gate (delete, external send, protected-branch push, payment) | S3/S6 | Security | Approval records with approver identity | Trigger a classified dangerous action; loop pauses, requires human approval |
| SB-01 | Sandbox isolation at the tier required by trust level | S4 | Platform/SRE | Sandbox config + tier assignment | Attempt host fs/network access from untrusted-tier sandbox; blocked and logged |
| SB-02 | Default-deny egress with per-run allow-list | S4 | Security | Egress firewall ruleset + connection logs | Attempt connection to a non-allow-listed host; refused and alerted |
| SB-03 | Ephemeral, per-run environment destroyed at termination | S4 | Platform/SRE | Environment lifecycle log | Inspect for reused environments across runs; any persistence = fail |
| SB-04 | Checkpoint before any state-mutating action | S4 | Harness Eng | Checkpoint store index | Force a failure mid-mutation; confirm rollback restores pre-action state |
| DL-01 | Output/diff scan before any externally visible write | S5 | Data Gov | Egress-scan report | Attempt to commit a file with a seeded secret; write blocked |
| OB-01 | Immutable per-call trace (model input, action, observation, decisions) | S5 | SRE/Obs | Append-only trace store (OTel) | Attempt to alter a trace record; storage rejects mutation (WORM/hash-chain) |
| OB-02 | Replayable audit log linking run → trace → evals → approvals | S5 | SRE/Obs | Run manifest with linked IDs | Select any completed run; reconstruct full decision path from logs alone |
| ST-01 | Hard budget caps (tokens, cost, wall-clock, tool calls, iterations) | S6 | Harness Eng | Budget-config + enforcement events | Configure a low cap; confirm loop halts at cap and checkpoints |
| ST-02 | Progress/stop condition (no monotonic progress → halt) | S6 | Harness Eng | Stop-controller decision log | Induce an oscillation loop; controller detects stall and terminates |
| ST-03 | Kill switch (operator-invoked immediate halt, per run and fleet-wide) | S6 | SRE/Platform | Kill-switch invocation log | Invoke kill switch mid-run; loop halts within SLA, state preserved |
| GV-01 | Model-output-untrusted assertion enforced across all tool entry points | All | Security | Static/dynamic policy conformance report | Confirm no tool path bypasses VA-01/VA-02; any direct model→side-effect path = fail |

Conformant only when every control has a green pass with a dated evidence artifact.

### Sandbox containment tiers (full)

| Tier | Isolation mechanism | Filesystem | Network | Use in worked example |
|---|---|---|---|---|
| T0 In-process validation | No code execution; harness-side only | none | none | Schema/permission/budget checks |
| T1 Container | Namespaced container, read-only base image, dropped capabilities | Ephemeral working copy of repo | Default-deny | `read_file`, static analysis |
| T2 Hardened runtime | gVisor / seccomp-BPF / user-namespace sandbox | Ephemeral, no host mounts | Allow-list only | `run_test`, `edit_file`, dependency install |
| T3 MicroVM | Firecracker/Kata-class, separate kernel | Ephemeral, encrypted | Egress-proxied, logged | Untrusted third-party code, secrets |

Blast-radius limits independent of tier: working env is always an ephemeral repo copy, never source of truth; writes land on a scratch branch, reach protected branches only via PM-03; env destroyed at termination (SB-03); harness control plane runs in a separate trust zone from the sandbox.

### Regulatory and framework mapping

| Control group | NIST AI RMF | ISO/IEC 42001 | ISO/IEC 27001 | SOC 2 (TSC) | EU AI Act |
|---|---|---|---|---|---|
| Context governance & redaction (AC-01/02/03, DL-01) | MAP-1, MEASURE-2 | A.7 | A.5.34, A.8.10, A.8.12 | CC6.1, CC6.7; Confidentiality; Privacy | Art. 10, 13 |
| Schema/intent validation (VA-01/02, GV-01) | MANAGE-1 | 8.1 | A.8.28, A.8.16 | CC7.1, CC8.1 | Art. 15 |
| Least-privilege & approval gates (PM-01/02/03) | GOVERN-2, MANAGE-2 | A.3, A.9 | A.5.15, A.5.18, A.8.2 | CC6.1, CC6.2, CC6.3 | Art. 14 |
| Sandbox & blast radius (SB-01..04) | MANAGE-2, MANAGE-3 | A.6 | A.8.22, A.8.23, A.8.20 | CC6.6, CC6.8, A1.2 | Art. 15, 9 |
| Observability & audit (OB-01/02) | MEASURE-1, MEASURE-3; GOVERN-4 | 9.1, A.6 | A.8.15, A.8.16, A.5.28 | CC7.2, CC7.3, CC4.1 | Art. 12 |
| Stopping, budget, kill switch (ST-01..03) | MANAGE-4 | 10.2, A.6 | A.5.24–A.5.26, A.8.16 | CC7.4, CC7.5, A1.1 | Art. 14, 9 |

Indicative — confirm current clause citations with the accountable compliance owner before an audit.

## Observability and Evaluation

### Span taxonomy (OTel-aligned; one trace per run, `run_id`-keyed)

| Span type | Emitted by | Represents |
|---|---|---|
| `agent.run` (root) | Orchestrator | Whole task; run_id, task_id, model_id, budget caps, terminal stop_reason |
| `agent.turn` | Control loop | One model→action→observation iteration; turn_index, checkpoint_id |
| `context.assemble` | Context builder | Context assembly for a turn; source manifest, token budget, eviction decisions |
| `model.call` | Model adapter | One inference call; tokens, cached_tokens, cost_usd, latency_ms, finish_reason |
| `tool.validate` | Policy/guard layer | Schema+permission+budget check; schema_valid, permission_decision, rejection_reason |
| `tool.execute` | Sandbox executor | Execution; exit_code, duration_ms, egress_attempted, files_changed[] |
| `approval.gate` | HITL gate | Human-approval pause; approver, decision, wait_ms |
| `state.write` | State store | Observation written to state; state_version, checkpoint_id |

Every span carries: `run_id`, `parent_span_id`, `tenant_id`, `harness_version`, `model_id`, `prompt_template_hash`, `tool_registry_hash`, `wall_clock_ts` — pinning which harness *configuration* produced a behavior, so regressions bisect to a prompt/tool-contract change rather than "model nondeterminism."

## Conformance, Maturity Model and Adoption Roadmap

### Self-certification conformance checklist (C-01..C-15, full)

| # | Requirement | Control ID | Pass/fail test |
|---|---|---|---|
| C-01 | Every invocable tool has a registered machine-readable contract | CTL-TOOL-01 | 100% of exposed tools resolve to a schema; unschemed tool can't register |
| C-02 | Every model-requested action is schema-validated before execution | CTL-VAL-01 | Fuzz/negative test → rejection event, not execution |
| C-03 | Tools are permissioned least-privilege | CTL-PERM-01 | Granted scopes ⊆ scopes exercised in evals; excess scope fails |
| C-04 | Model-directed work executes only inside the sandbox | CTL-SBX-01 | Attempted host write/unlisted egress is blocked and logged |
| C-05 | Sandbox egress is default-deny with an explicit allowlist | CTL-SBX-02 | Connection to non-allowlisted host fails closed |
| C-06 | Per-run budget caps enforced, halt the loop on breach | CTL-STOP-01 | Run engineered to exceed step cap terminates with `budget_exceeded` |
| C-07 | Explicit, non-trivial stopping conditions; no indefinite loop | CTL-STOP-02 | Every eval run terminates with a classified stop reason; none hits an external watchdog kill |
| C-08 | High-impact actions pause for human approval | CTL-HITL-01 | A gated-action run blocks pending approval in the trace |
| C-09 | Context compacted/summarized before window overflow | CTL-CTX-01 | Long-horizon eval task completes without a context-overflow error |
| C-10 | State checkpointed for rollback/resume | CTL-REC-01 | Killing a run mid-task and resuming reproduces state to last checkpoint |
| C-11 | Every call/action/observation emits a structured trace span | CTL-OBS-01 | A run is fully reconstructable end-to-end from spans, no gaps |
| C-12 | Runs wired to a golden-task eval suite (success/cost/latency/turns) | CTL-EVAL-01 | Suite executes on demand/CI, emits the four metrics per task |
| C-13 | Documented kill switch halts all runs of the harness | CTL-KILL-01 | Drill demonstrates in-flight runs stop within stated SLO |
| C-14 | Prompts/tool contracts/permissions/policies versioned + change-controlled | CTL-GOV-01 | Every policy artifact resolves to a version and an approving ADR |
| C-15 | The worked example passes end-to-end with all controls active | CTL-E2E-01 | Reference task reaches a passing outcome via the full loop, sandboxed/budgeted/traced |

Checklist-conformant only when every applicable item passes with attached evidence. N/A items need a written, ARB-accepted justification.

### Maturity ladder (full)

| Level | Name | Loop & control state | Governance state | Permitted workloads |
|---|---|---|---|---|
| L1 | Prototype loop | Structured requests validated vs schema; sandboxed; hard step/token cap only; manual trace inspection | None formal; single owner | Dev sandboxes, throwaway experiments; no real data |
| L2 | Contained agent | Per-run budget caps; sandbox egress allowlisted; basic structured tracing; explicit stop reasons | Tool contracts/permissions versioned; risk register started | Internal non-production tasks, non-sensitive data |
| L3 | Observable & recoverable | Every call/action/observation traced with correlation; context compaction; checkpoint/rollback; drilled kill switch | ADRs for key decisions; control matrix populated; incident runbook | Production-adjacent w/ human review; limited sensitive data w/ approval |
| L4 | Eval-gated | Golden-task suite scores success/cost/latency/turns; regressions block release; HITL on high-impact; recovery fault-tested | Eval-gated change control; ARB sign-off; control matrix fully evidenced | Production on sensitive data behind approval + eval gates |
| L5 | Governed platform | All of L4 continuous; drift/regression alerting; automated conformance re-checks; kill-switch/rollback under SLA | Full audit trail mapped to NIST/ISO/SOC2/EU AI Act; independent audit passed; inherited by downstream projects | Enterprise-critical, regulated, multi-team workloads |

### Phased adoption / funding gates

| Phase | Target level | Objective | Exit/gate criteria |
|---|---|---|---|
| P0 Prototype | L1 | Prove the loop on a worked example | Loop runs the read/edit/run_test cycle sandboxed with schema-validated actions + hard cap |
| P1 Containment | L2 | Safe to run on internal data | Least-privilege + full budget caps + default-deny egress enforced and negative-tested; risk register live |
| P2 Observability & Recovery | L3 | Every run reconstructable/recoverable | End-to-end tracing, compaction, checkpoint/rollback, drilled kill switch; incident runbook signed off |
| P3 Evaluation Gate | L4 | "Reliable" becomes a pass/fail gate | Golden-task suite green above threshold; approval gates on high-impact actions live; regression gate blocks bad deploys |
| P4 Governed Platform | L5 | Certify as durable, inheritable org IP | Continuous eval/cost/drift monitoring; independent audit passed; ≥1 downstream team inheriting the standard |

Suggested ratified thresholds: golden-task success ≥ 90%, median cost within the phase's budget envelope, no eval regression vs. last signed baseline, zero unresolved High-severity risk-register items. A phase whose evals pass but whose cost/latency exceeds budget still fails the gate — remediate the harness, not a model swap.

## Cost model — the core economic argument (Section 8, summarized)

Sensitivity analysis ranks levers by influence on expected cost per task: **first-pass success rate** is the most influential lever (funded directly by eval-driven harness tuning); the **failure-run turn cap** bounds the tail (a tuned cap, not an aggressive one); **human-fallback cost** sets the value of avoided escalations; **model price** is the *weakest* lever — confirming the standard's core claim that swapping to a pricier model is the least cost-effective response to agent failure. Spend on harness quality (context assembly, tool contracts, permissions, stopping conditions, checkpoint/recovery) dominates spend on a bigger model.

## Acceptance criteria for the standard itself (9.4)

Completeness (all sections present, appendices attached and version-stamped) · Traceability (every component maps to a module and, where applicable, a control with ID/owner/evidence/test) · Framework mapping (every control mapped to ≥1 external obligation) · Demonstrability (worked example runs end-to-end, recorded as evidence, C-15) · Governability (revision history, ADRs, change control) · Inheritability (vendor/model-neutral, adoptable by a future project without rework).
