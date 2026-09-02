# `app/agents/harness/` — the control tier

A thin, wire-first harness that unifies the controls your engines already
half-implement. It does **not** replace `dag_engine`, `coordinator`, or the
LangGraph supervisors — they call into it. INERT until `AGENT_HARNESS=1`.

## Why

The audit (see `docs/HARNESS_STANDARD_IMPLEMENTATION_PLAN.md`) found the safety
primitives already exist but are default-OFF, unwired, and spread across 5
incompatible loops. This package is the single ordered pipeline every tool call
passes through, so a control is enforced in exactly one place.

## Modules

| File | Responsibility | Wires your existing |
|---|---|---|
| `contracts.py` | Typed `ToolCall`/`ToolResult`/`RunContext`, risk classes | — (new spine) |
| `tool_registry.py` | Tool catalog + arg-schema validation (VA-01/02) + fail-closed permit (PM-01) | `agent_permissions.can` |
| `stop.py` | Unified budget/iteration/wall-clock caps, no-progress, live kill switch (ST-01/02/03) | `dev_control.gateway.admit_cost`, `budgets`, `budget_guard` |
| `sandbox.py` | Real isolation for model code: rlimits + scrubbed env + backend hook (SB-01/02/03) | replaces `code_exec` executor |
| `audit.py` | One `run_id` threaded to trace + eval + ledger; `replay()` (OB-01/02) | `observability_llm` |
| `loop.py` | The ordered pipeline `step()` + `run()` driver | `risk_approve`, `agent_checkpoints` |

## The pipeline (every `step()`)

`kill? → VA-01/02 validate → PM-01 permit → ST-01 admit → PM-03 approve (if dangerous)
→ SB-04 checkpoint (if mutating) → DL-01 egress scan → execute (sandbox if code) →
OB-01 trace/audit → ST-02 progress/stop`

## Register a tool

```python
from pydantic import BaseModel, field_validator
from app.agents.harness import REGISTRY, RiskClass


class SendWhatsAppArgs(BaseModel):
    to: str
    body: str

    @field_validator("to")
    @classmethod
    def _india(cls, v):
        assert v.startswith("+91"), "domestic only"  # VA-02
        return v


REGISTRY.register(
    "send_whatsapp",
    send_whatsapp_impl,
    SendWhatsAppArgs,
    RiskClass.EXTERNAL_SEND,  # -> PM-03 approval + SB-04 checkpoint + DL-01 scan
    profiles=["outreach"],  # PM-01 least-privilege
    allowed_egress=["graph.facebook.com"],  # SB-02
)
```

## Drive a run

```python
from app.agents.harness import Harness, RunContext, Budget

h = Harness(budget=Budget(max_iterations=8, max_usd=0.50, max_wall_clock_s=120))
ctx = RunContext(task_id="t123", tenant_id="client:jiya", agent="sales")


async def propose(ctx):
    # your model call -> a validated ToolCall via app.llm.structured, or None when done
    return await plan_next_action(ctx)


reason = await h.run(ctx, propose, profile="outreach")
# reason in {GOAL_MET, BUDGET_EXHAUSTED, WALL_CLOCK, NO_PROGRESS, KILL_SWITCH, ...}
```

## Kill a run (no redeploy)

```python
from app.agents.harness import StopController

StopController.request_kill("all")  # fleet-wide
StopController.request_kill(run_id)  # one run
```

## Rollout

`AGENT_HARNESS=1` canary → route `dag_engine.execute_step` and `coordinator._TOOLS`
through `Harness.step()` → expand tool-by-tool. Phase order in the plan doc.
Start at **Phase 0** (sandbox + fail-closed budget) — that closes the RCE.

## Tests

`pytest tests/test_harness_smoke.py -q` — runs standalone (no app deps needed).


---

## Shadow slice — Nikhil real-agent observation (Stage A)

**Selected path (Graphify):** `app/agents/staff.py:run_member` (the manual "Run now"
dispatcher, `POST /run/{member}`) → `"nikhil": run_nikhil` (Revenue Ops: revenue
digest + client health + usage alerts, internal/read-only). Interception is a
guarded call after `result = await fn()` and in the `except` — agent_id, latency,
and result/error are all available there, and eligibility keeps it Nikhil-only so
no peer agent is touched. The other four loops (coordinator, dag_engine,
supervisor, staff_supervisor, batch_harness) are NOT hooked in this slice.

**Contract:** legacy stays authoritative and runs exactly once; the adapter feeds
a COPY to `Harness.observe(...)` which is RECORD-ONLY — it validates, evaluates
policy/permission/budget/approval/stop, records what enforcement WOULD decide,
compares proposed-vs-actual, and NEVER executes the tool, mutates, retries,
approves, or consumes the legacy idempotency key. Observer failures are audited
(`kind="shadow_error"`) but never break the legacy run.

**Flags (all INERT by default).** Shadow eligibility requires ALL of:
`AGENT_HARNESS=1 AND AGENT_HARNESS_SHADOW=1 AND AGENT_HARNESS_ENFORCE=0 AND
normalized agent_id in AGENT_HARNESS_CANARY_AGENTS`. Empty allowlist = nobody
eligible; no wildcard. Canary run config:
`AGENT_HARNESS=1 AGENT_HARNESS_SHADOW=1 AGENT_HARNESS_ENFORCE=0 AGENT_HARNESS_CANARY_AGENTS=nikhil`.

**Shadow record schema** (audit `kind="shadow"`, bounded + redacted): agent,
tenant_id (`__system__` for internal), source_loop, mode, enforcement=False,
requested_tool, args_hash, risk_class, would_validate, predicted_lane,
would_allow, would_require_approval, would_checkpoint, would_deny_reason,
budget_decision, stop_decision, legacy_tool, legacy_status, legacy_error,
legacy_result_summary, latency_ms, side_effect_class, comparison_verdict
(MATCH/POLICY_MISMATCH/ARGUMENT_MISMATCH/TOOL_MISMATCH/MISSING_CONTEXT/
SHADOW_ERROR/LEGACY_ERROR), run_id, shadow_run_id (`shadow:<run_id>:<idx>`, never
the legacy key).

**Explain:** `harness.explain <run_id>` (Kavach GREEN) reconstructs the timeline
from `audit.replay(run_id)`.

**Tests:** `python -m pytest tests/test_harness_shadow.py -q` (23 shadow tests +
integration through real run_member). Full harness+Kavach: 40 focused tests.

**Live proof (2026-07-22):** one real `run_member("nikhil")` with flags on →
1 shadow record, verdict MATCH, lane GREEN, enforcement False, latency 4531ms,
`harness.explain` OK; STAFF=31, Kavach not in registry, no peer eligible. Flags
off → 0 shadow records, legacy result unchanged. Calling HARD OFF, CODE_EXEC=0.

**Rollback:** set `AGENT_HARNESS=0` (or `AGENT_HARNESS_SHADOW=0` / empty canary) —
the adapter becomes a no-op with no code removal.

**Next migration candidate:** shadow-wrap one more safe internal loop (e.g. the
`dag_engine` typed executor) — NOT enforcement — before considering Nikhil
shadow→enforce.


---

## Shadow slice #2 — DAG engine (`dag_engine`) real-loop observation

**Selected path (Graphify):** `app/agents/dag_engine.py:advance` — the typed
executor boundary `result = await process_library.execute_step(node, eff_inputs)`
then `ok, reason = process_library.check_gate(node, result)`. Available at the
seam: `run_id`, `nid` (node_id), `eff_inputs` (typed args), `ms` (latency),
`node`/`node.action` (tool), `nodes[nid].retries` / `node.max_retries` (attempt +
retry). Interception is a single guarded block after `check_gate`, before the
`if ok:` branch. `execute_step` dispatches `EXECUTORS[step["action"]]`.

**Interception point:** one record-only call to `observe_dag_action(...)` per
node execution attempt. It never executes the node, invokes the tool, alters
arguments, marks node success/failure, changes retry policy, creates a second
checkpoint, consumes the real idempotency key, or reorders the journal. Failures
are audited (`kind="shadow_error"`) and swallowed — the DAG is never affected.

**Adapter:** `app/agents/harness/adapters/dag_shadow.py:observe_dag_action`.
Eligibility is loop-scoped: `shadow_loop_eligible(agent_id, "dag_engine")` =
agent eligibility AND `"dag_engine" in AGENT_HARNESS_CANARY_LOOPS`. Empty loop
allowlist ⇒ no DAG observation. `run_member` stays agent-only and ignores this.

**Canary run config:**
`AGENT_HARNESS=1 AGENT_HARNESS_SHADOW=1 AGENT_HARNESS_ENFORCE=0
AGENT_HARNESS_CANARY_AGENTS=nikhil AGENT_HARNESS_CANARY_LOOPS=dag_engine`.
The DAG carries the canary identity via run input `_harness_agent_id` (a
harness-side routing label only — it does not dispatch an agent or change STAFF;
absent it, the run defaults to `manager` and is ineligible, so ordinary DAGs are
never observed).

**Correlation fields:** run_id (= dag_run_id), shadow_run_id =
`shadow:<dag_run_id>:<node_id>:<attempt>`, source_run_id, source_node_id,
source_attempt, source_loop=`dag_engine`, agent_id, tenant_id (real for
tenant-bound DAGs, else `__system__`), actor_id=`dag_scheduler`. Each node and
each retry attempt is a distinct, independently traceable record linked to the
same DAG run.

**Success/error/retry semantics:** completed → `MATCH`; gate-fail with retries
left → `dag_node_status=retry_pending`, `retry_scheduled=true`,
`comparison_verdict=RETRY_OBSERVED`; final gate-fail → `dag_node_status=failed`,
`LEGACY_ERROR`. A legacy failure is never auto-classified as a harness mismatch.
Stop/policy decisions are recorded (`would_stop`/`stop_decision`,
`predicted_lane`, `would_allow`, `would_require_approval`) but NEVER applied.

**DAG record schema adds:** dag_run_id, node_id, attempt, declared_tool,
actual_executor (`process_library.execute_step`), actual_arguments_hash,
dag_node_status, retry_scheduled — on top of the base shadow schema.

**Tests:** `python -m pytest tests/test_harness_dag_shadow.py -q` (incl. real
`dag_engine.advance` integration). Full harness suite: 57 focused tests.

**Live proof (2026-07-22):** one real `advance()` over a single task node under
nikhil → DAG completed, real node executions 1, harness tool executions 0,
duplicate journal entries 0, 1 shadow record (MATCH, GREEN, enforcement False),
`harness.explain` OK; observer overhead ≈ 3.3 ms. Flags off → 0 shadow records,
same DAG terminal state. 3 additional real Nikhil `run_member` samples → 3/3
MATCH, 0 errors, avg legacy latency ≈ 4151 ms. STAFF=31, Kavach absent, calling
HARD OFF, CODE_EXEC=0.

**Rollback:** `AGENT_HARNESS=0` (or `AGENT_HARNESS_SHADOW=0` / empty
`AGENT_HARNESS_CANARY_LOOPS`) — the DAG adapter is a no-op, no code removal.

**Coverage now:** staff.run_member (shadow) + dag_engine (shadow) wrapped;
coordinator, supervisor, staff_supervisor, batch_harness still bypass. **Next:**
shadow-wrap the coordinator loop.


---

## Shadow slice #3 — coordinator (`coordinator`) real-loop observation

**Graphify findings.** `app/agents/coordinator.py` has multiple orchestration
entries (`coordinate`, `coordinate_advanced`, `fan_out`, `coordinate_hierarchical`,
`coordinate_agentverse`, `coordinate_engineering`, `debate`, `council`). Actions
are freeform LLM text normalized by `plan()` → `_extract_list()` (heuristic
JSON/regex extraction) into `{agent, task}` steps. There are **two** real
executor boundaries where a normalized action actually runs a `_TOOLS[agent]`:
`_run_agent` (line ~290, shared by coordinate/fan-out/sequential) and
`_expert_contribution` (line ~831, agentverse). The 5 executable tools are
internal: isha→generate_post (draft), dev→hashtags.research, kavya→run_ops,
arjun→run_qa, meera→run_trainer.

**Selected interception point:** `coordinator.py:_run_agent`, immediately after
`res = await _TOOLS[agent](task, goal)`. This observes the **coordinator's own
normalized selection** (`agent` = parsed tool, `res` = real result) — never raw
prose. `_expert_contribution` (agentverse) is a second boundary **not** covered
this slice (documented remaining work). `coordinate()` stamps `_run_id`/`_path`
into the blackboard for correlation.

**Raw-text vs normalized-action boundary.** The raw LLM response is never stored;
only `parser_type=_extract_list` and `parser_confidence=HEURISTIC` (plus an
optional bounded `raw_response_hash`). Executable observation is based solely on
the coordinator's post-parse `{agent, task}`. Unparseable/failed → `MISSING_CONTEXT`
/ `PARSER_AMBIGUITY`, never a guessed tool.

**Identity (honest).** The coordinator has no self agent_id; the genuine identity
is the **delegated** `_TOOLS` agent (isha/dev/kavya/arjun/meera). The canary uses
those real identities — NOT a faked `nikhil`. tenant defaults to `__system__`
(preserved when a tenant-bound coordinator run supplies one).

**Adapter:** `adapters/coordinator_shadow.py:observe_coordinator_action`.
Eligibility: `shadow_loop_eligible(agent_id, "coordinator")`. Verdicts add
`FALLBACK_OBSERVED`, `DELEGATION_OBSERVED`, `PARSER_AMBIGUITY` via a
`verdict_override` honoured only after the structural validate/permit gates pass.

**Correlation:** run_id (= coordinator_run_id), shadow_run_id =
`shadow:<coordinator_run_id>:<orchestration_path>:<action_index>`,
orchestration_path, action_index, parent_action_id, delegated_agent/
delegated_run_id (when delegation occurs), source_loop=`coordinator`.
**Delegation/recursion safety:** the executable `_TOOLS` call staff functions
directly (e.g. `run_ops`), NOT `run_member`/`dag_engine`, so a coordinator record
and any downstream record stay distinct — no double observation; the adapter
never calls the coordinator.

**Canary run config:**
`AGENT_HARNESS=1 AGENT_HARNESS_SHADOW=1 AGENT_HARNESS_ENFORCE=0
AGENT_HARNESS_CANARY_AGENTS=isha,dev,kavya,arjun,meera AGENT_HARNESS_CANARY_LOOPS=coordinator`.

**Tests:** `python -m pytest tests/test_harness_coordinator_shadow.py -q` (incl.
real `coordinate()` integration). Full harness suite: **76 focused tests**.

**Live proof (2026-07-22):** real `coordinate("...", execute=True)` with the REAL
`plan()`/LLM (`USED_DETERMINISTIC_PLAN=False`) → plan chose hermes(draft)+dev
(executed); `dev`→`run_dev` executed once, harness executions 0, 1 coordinator
shadow record (MATCH, GREEN, enforcement False, parser `_extract_list`/HEURISTIC),
downstream duplicates 0, `harness.explain` OK, observer overhead ≈ 3.6 ms. Flags
off → 0 records, same coordinator result shape.

**Enforcement readiness: NOT READY** — the coordinator normalizes via a HEURISTIC
`_extract_list` parser with no stable structured action contract; `_expert_contribution`
is a second un-wrapped boundary. Shadow-only until a structured action contract exists.

**Coverage now:** staff.run_member + dag_engine + coordinator (shadow) wrapped;
supervisor, staff_supervisor, batch_harness still bypass. **Next:** shadow-wrap
supervisor / staff_supervisor as one execution family.


---

## Shadow slice #4 — supervisor family (`supervisor` / `staff_supervisor`)

**Graphify findings.** `app/agents/supervisor.py` is a LangGraph `StateGraph`:
START → `supervisor_node` (router; `semantic_route_for_task` LLM → `route_for_task`
keyword fallback) → conditional edge → `data_agent_node`|`leads_agent_node` → END.
NO native tool-calls — nodes call an LLM brain and return a result string; the
normalized action is the **routing decision** (`out["route"]`) + the executed
node. `app/agents/staff_supervisor.py` uses `langgraph-supervisor`
(`create_react_agent` with `tools=[]`) — routing among STAFF via messages; opt-in
(`USE_LANGGRAPH_SUPERVISOR`). Both mapped to one family `source_loop=supervisor`
with a `supervisor_implementation` field. `file:symbol`: `supervisor.run_supervisor_task`
(L280), `_execute` (L242), `supervisor_node` (L138); `staff_supervisor.StaffSupervisor.run` (L111).

**Interception points.** `supervisor.py:run_supervisor_task` after `out = await
_execute(...)` (normalized route → worker dev/rohan, result). `staff_supervisor.py:
StaffSupervisor.run` after `g.invoke(...)` (delegated agent from message `name`
metadata; INERT unless enabled). Neither infers actions from prose.

**Identity (honest).** Supervisor **actor** = `manager`; **delegated agent** =
the executed worker (`data_agent`→`dev`, `leads_agent`→`rohan`). Canary keys on
the genuine **delegated** identity — NOT a faked nikhil. tenant `__system__` unless
a client-bound run supplies one.

**Adapter:** `adapters/supervisor_shadow.py:observe_supervisor_action`. Eligibility
`shadow_loop_eligible(delegated_agent, "supervisor")`. **Replay/checkpoint dedup:**
a bounded in-memory key `supervisor:<graph_run_id>:<graph_step>:<tool_call_id|idx>:<attempt>`
suppresses duplicate shadow WRITES only (records a `shadow_dedup` diagnostic);
legacy execution is never affected and a genuine retry (distinct attempt) records
separately.

**Correlation:** run_id, shadow_run_id=`shadow:<graph_run_id>:<graph_step>:<tool_call_id|attempt>`,
supervisor_implementation, graph_run_id (thread_id), graph_step, tool_call_id
(None here — no native calls), actor_id, delegated_agent, parent_action_id.
**Parent/child:** the supervisor's graph nodes call staff/LLM directly (NOT
run_member/dag), so a supervisor run produces a parent-only event — reported
honestly (`DOWNSTREAM_SHADOW: 0`); a real delegation into run_member/dag would be
a separate correlated child event, never a duplicate.

**Canary run config:**
`AGENT_HARNESS=1 AGENT_HARNESS_SHADOW=1 AGENT_HARNESS_ENFORCE=0
AGENT_HARNESS_CANARY_AGENTS=rohan,dev AGENT_HARNESS_CANARY_LOOPS=supervisor`.

**Tests:** `python -m pytest tests/test_harness_supervisor_shadow.py -q` (incl. real
`run_supervisor_task` LangGraph integration). Full harness suite: **93 focused tests**.

**Live proof (2026-07-22):** real `run_supervisor_task` (real graph; keyword router
+ fixtured leaf brain) — leads route→rohan and data route→dev, each node executed
once, harness executions 0; shadow records MATCH/GREEN/enforcement False, actor
manager, delegated rohan/dev; downstream duplicates 0; **replay dedup**: rerunning
the same thread_id added 0 shadow records + 1 `shadow_dedup` diagnostic while legacy
still ran once; `harness.explain` OK; observer overhead ≈ 6.6 ms. Flags off → 0
records, same graph result. STAFF=31, Kavach absent, calling HARD OFF, CODE_EXEC=0.

**Enforcement readiness: NOT READY** — supervisor.py has no native structured
tool-calls (routing only; tool_call_id absent), staff_supervisor is opt-in/
unexercised, tool identity is `unregistered_internal_action`, and the router can
fall back to keyword matching. Shadow-only.

**Coverage now:** run_member + dag_engine + coordinator + supervisor (shadow)
wrapped; only `batch_harness` remains. **Next:** shadow-wrap batch_harness.


---

## Shadow slice #5 — batch_harness (`batch_harness`) — final family

**Graphify findings.** `app/agents/batch_harness.py:run_batch` runs an arbitrary
`async fn(item)->dict` over items with bounded concurrency (`asyncio.Semaphore`
[1,16]) via `asyncio.gather`. Item boundary = `_run_one` → `res = await fn(item)`
(L139, never-raise). Checkpoint = append-only JSONL (`_append_ckpt`, one line per
completed index); resume = `_done_indices` skips already-checkpointed indices
(ok AND failed are checkpointed → **no automatic retry**; resume skips them).
Item identity: index (+ `_item_key` human key). No agent_id originally.
`file:symbol`: `run_batch` (L96), `_run_one` (L130), `_done_indices` (L62),
`_append_ckpt` (L85), `asyncio.Semaphore` (L125).

**Interception point:** in `_run_one`, observe **after the semaphore is released**
(does not extend the critical section / reduce concurrency). Resume-skip branch
emits a RESUME_SKIPPED **diagnostic**, never an executed-action record.

**Identity (honest).** Added backward-compatible optional `agent_id` / `tenant_id`
kwargs to `run_batch` (default `""` → existing callers stay inert). Canary keys on
the genuine batch agent identity (`nikhil` in the proof, passed explicitly — not
fabricated). Operation identity = `fn.__name__` → `batch.execute.<name>`; a
lambda/anonymous fn → `MISSING_CONTEXT` (never a memory-address/repr guess).

**Concurrency safety.** Observation is called from asyncio tasks (never threads);
`Harness.observe`→`audit.record` is fully **synchronous** (no `await`), so asyncio
cannot interleave two JSONL writes — line-atomic without a lock. The dedup
`OrderedDict` is mutated synchronously. No global lock is held during item
execution; the batch workload is never serialized.

**Checkpoint/resume/dedup.** Fresh item → 1 action record (checkpoint_state
completed/failed). Resume → completed items skipped by legacy → RESUME_SKIPPED
diagnostic, **0 false execution observations**. Duplicate callback for the same
`batch_harness:<batch_run_id>:<item_id>:<attempt>:<op>` → `shadow_dedup` diagnostic
(write suppressed; legacy untouched). A genuine retry (distinct attempt) records
separately. Dedup is in-memory/bounded (process-restart resets it; the durable
batch checkpoint remains the legacy source of truth).

**Correlation:** run_id=batch_run_id, shadow_run_id=`shadow:<batch_run_id>:<item_id>:<attempt>`,
batch_name, item_id, item_index, attempt, operation_name, actual_executor,
checkpoint_state, resumed, actor_id=`batch_runner`.

**Canary run config:**
`AGENT_HARNESS=1 AGENT_HARNESS_SHADOW=1 AGENT_HARNESS_ENFORCE=0
AGENT_HARNESS_CANARY_AGENTS=nikhil AGENT_HARNESS_CANARY_LOOPS=batch_harness`.

**Tests:** `python -m pytest tests/test_harness_batch_shadow.py -q` (incl. real
`run_batch` success/failure/resume/concurrency integration). Full harness suite:
**112 focused tests**.

**Live proof (2026-07-22):** real `run_batch` (5 items, concurrency 3, safe
`safe_calc`) — each item executed once, observed max concurrency 3 (= configured),
5 action records (4 MATCH + 1 LEGACY_ERROR), harness executions 0; `harness.explain`
5 events; **resume** rerun skipped all 5, legacy re-ran nothing, 0 new actions, 5
resume diagnostics; observer overhead ≈ 5.7 ms; flags off → 0 records, same batch
result. STAFF=31, Kavach absent, calling HARD OFF, CODE_EXEC=0.

---

## Five-family shadow-coverage matrix (2026-07-22)

| family | real entry | adapter | samples | MATCH | mismatch | shadow_err | identity | tenant | tool-contract | dedup/replay | overhead | readiness |
|---|---|---|--:|--:|--:|--:|---|---|---|---|--:|---|
| staff.run_member | `run_member` | shadow.py | 4 | 4 | 0 | 0 | agent (nikhil) | `__system__` | unregistered | idempotency-key | ~n/a | NOT READY |
| dag_engine | `advance/execute_step` | dag_shadow.py | 1 | 1 | 0 | 0 | run-input | `__system__`/tenant | unregistered | run:node:attempt | instant | NOT READY |
| coordinator | `_run_agent` | coordinator_shadow.py | 1 | 1 | 0 | 0 | delegated (_TOOLS) | `__system__` | unregistered; HEURISTIC parse | path:index | ~3.6ms | NOT READY |
| supervisor | `run_supervisor_task` | supervisor_shadow.py | 3 | 3 | 0 | 0 | delegated (dev/rohan) | `__system__` | no native tool-calls | graph:step:attempt | ~6.6ms | NOT READY |
| batch_harness | `run_batch/_run_one` | batch_shadow.py | 5 | 4* | 0 | 0 | agent kwarg (nikhil) | `__system__`/tenant | `fn.__name__` (stable) | run:item:attempt | ~5.7ms | NOT READY |

*batch: 4 MATCH + 1 honest LEGACY_ERROR (an intended item failure, not a harness mismatch).
**Cumulative real observations: 14 — matches 13, legacy-error 1, mismatches 0, shadow errors 0.**

**Enforcement readiness: NOT READY (whole project).** Blockers: coordinator heuristic
parser + unwrapped `_expert_contribution`; supervisor has no native structured
tool-calls; tool identities are `unregistered_internal_action` across families
(batch is the exception with a stable `fn.__name__`); the real sandbox backend is
not built and `CODE_EXEC` cannot be safely enabled. Batch_harness is the strongest
structured candidate (stable operation identity, clean concurrency/resume proof)
but still needs a canonical tool registry before any owner-approved enforcement
canary. **All five families are shadow-covered; enforcement remains OFF.**

---

## Canonical Tool Registry + Structured Action Contracts (2026-07-22)

`registry.py` is now the **single canonical, versioned tool registry** and the sole
authority on how dangerous an action is. It is layered ON TOP of the existing shadow
observation — it does not replace or weaken the `execution_comparison` (MATCH-family)
verdict, it adds a separate `registry_comparison` verdict beside it.

**Identity standard:** `<domain>.<capability>.<action>` — lowercase, dot-separated,
regex `^[a-z][a-z0-9]*(?:\.[a-z0-9_]+){1,}$`. No lambdas, memory addresses, or paths.
Versions are strict semver `MAJOR.MINOR.PATCH`. `run_dev`, `a.b.c` + `v1` → rejected.

**`ToolDefinition`** (frozen, `extra="forbid"`): name, version, input_schema,
`risk_class` (GREEN/AMBER/RED), `side_effect_class` (NONE…CODE_EXECUTION), `authority`
(INTERNAL_AUTONOMOUS / OWNER_OS_REQUIRED / APPROVAL_REQUIRED / ALWAYS_REFUSED),
allowed_agents, allowed_tenant_scopes, requires_approval, requires_idempotency,
timeout_s, sandbox_required, executor_ref, enabled_by_default. Unknown enum → validation
error. `public_view()` omits raw callables (listing-safe).

**Registry APIs:** register (idempotent on identical def; `RegistryConflict` on a
conflicting redefinition) · get / resolve (version None → latest by semver) ·
list_versions · list_tools · is_agent_allowed · is_tenant_scope_allowed ·
`manifest_hash()` (sha256[:16], deterministic) · `evaluate_action(...)`.

**`registry_comparison` verdicts:** REGISTRY_MATCH · UNREGISTERED_TOOL · VERSION_MISMATCH
· SCHEMA_MISMATCH · AGENT_NOT_ALLOWED · TENANT_NOT_ALLOWED · IDEMPOTENCY_REQUIRED ·
DISABLED. Unknown tool = **fail-closed** (`would_deny`, reason "tool not in canonical
registry"). The registry is authoritative: a model that claims GREEN on a RED-registered
tool gets `risk_class_mismatch=True` and the registry's classification wins — a model
can never downgrade RED→GREEN.

**First registry-backed family = `batch_harness`.** Built-in tool
`batch.internal.safe_calculation` v1.0.0 (GREEN · READ_ONLY · INTERNAL_AUTONOMOUS ·
allowed_agents={nikhil} · tenant {`__system__`} · no approval/idempotency · schema
`{id: string, additionalProperties: false}`). `run_batch(..., tool_name=, tool_version=)`
routes items to canonical identity; legacy `run_batch` callers with no `tool_name` keep
working as `batch.execute.<op>` and are observed as UNREGISTERED_TOOL (backward-compatible).

**Authority boundary preserved:** OWNER_OS_REQUIRED means *route a command to Owner OS*,
not execute — the registry never becomes a second mutation dispatcher. Owner OS stays the
sole mutation authority.

**Kavach / OpenClaw GREEN read commands** (record-only): `harness.tools`, `harness.tool`,
`harness.registry`, `harness.registry.conformance`.

**Live proof (2026-07-22, real `run_batch`):**
- registered `batch.internal.safe_calculation` v1.0.0 (2 items) → `execution_comparison=MATCH`
  **and** `registry_comparison=REGISTRY_MATCH`, GREEN, INTERNAL_AUTONOMOUS, agent+tenant allowed.
- legacy no-`tool_name` (2 items) → `execution_comparison=MATCH` **and**
  `registry_comparison=UNREGISTERED_TOOL` (would_deny, fail-closed) — execution layer NOT
  converted to failure.
- flags off → **0 records**, identical batch result.

**Negative proofs (isolated unit tests, tripwire executor NEVER invoked):** AMBER +
APPROVAL_REQUIRED → `would_require_approval=True`, `would_allow=False`; RED + ALWAYS_REFUSED
→ `would_deny=True`. IDEMPOTENCY_REQUIRED, AGENT_NOT_ALLOWED, TENANT_NOT_ALLOWED, DISABLED,
VERSION_MISMATCH, SCHEMA_MISMATCH, bad-name reject, conflict reject, manifest stability — all covered.

**Tests:** `tests/test_harness_registry.py` — **25 tests**. Full harness suite:
**137 tests green** (8 files). Regressions (owner_agent_execution, workflow_fixes_2026,
workflow_guards, phase2_upgrades) **41 green**.

**Status: enforcement remains OFF (whole project NOT READY).** `batch_harness` is the
first and only registry-backed structured family; the other four families remain
UNREGISTERED_TOOL until they too gain canonical identities. The registry is a
record-only classification layer — nothing is enforced.

---

## Batch Harness Enforcement Path (INERT; canary-prepared, 2026-07-22)

`enforce.py` adds the decision+execution tier that can turn the canonical registry
from a record-only classifier into an enforceable gate — for exactly ONE registered
internal GREEN tool, and ONLY under explicit per-agent/per-loop/per-tool allowlists.
**INERT by default:** `AGENT_HARNESS_ENFORCE` unset/0 ⇒ `resolve_mode()` never returns
ENFORCE. Full canary procedure: `docs/runbooks/BATCH_HARNESS_ENFORCEMENT_CANARY.md`.

**Three modes** (deterministic `resolve_mode`, fail-closed):

| mode | flags | behaviour |
|---|---|---|
| OFF | `AGENT_HARNESS=0` or not eligible | legacy `fn` path; no observation, no harness exec |
| SHADOW | `AGENT_HARNESS=1`,`SHADOW=1`,`ENFORCE=0`+canary | legacy `fn` executes once; harness observes |
| ENFORCE | `AGENT_HARNESS=1`,`SHADOW=0`,`ENFORCE=1`+agent+loop+tool allowlists | **legacy `fn` NEVER runs**; only the registry-BOUND executor runs |

`SHADOW=1`+`ENFORCE=1` = INVALID → fail-closed OFF. No wildcards in the first canary.
Only ONE authoritative executor per mode — legacy `fn` and the harness executor never
both run one item.

**Executor binding** (`ExecutorBindingRegistry`): explicit `(name,version)→async fn`
map. No dynamic import, no dotted-path, no callable scanning; conflicting binding
rejected; callables never exposed by a read API. Built-in: `batch.internal.safe_calculation@1.0.0`
→ deterministic side-effect-free `_safe_calculation_executor`.

**Gate** separates decision from execution: `EnforcementGate.evaluate()` is pure (NEVER
executes) and returns a frozen `EnforcementDecision` (all gate booleans + `denial_reasons`
+ `decision_id` + `execution_key`); `execute_registered()` runs ONLY the bound executor,
re-checks the live kill switch atomically, and enforces exactly-once via a synchronous
claim on `enforce:<batch_run_id>:<item_id>:<attempt>`. Denials execute the executor zero
times. Duplicate callback → replayed, not re-run. Caller-supplied `fn` is never
authoritative in ENFORCE mode (registry-bound executor wins — an attacker passing
`tool_name=batch.internal.safe_calculation, fn=malicious` cannot run `malicious`).

**Denial reasons:** UNREGISTERED_TOOL, VERSION_MISMATCH, SCHEMA_MISMATCH, AGENT_NOT_ALLOWED,
TENANT_NOT_ALLOWED, TOOL_DISABLED, TOOL_NOT_ALLOWLISTED, RISK_NOT_GREEN, APPROVAL_REQUIRED,
OWNER_OS_REQUIRED, ALWAYS_REFUSED, IDEMPOTENCY_REQUIRED, SANDBOX_REQUIRED, BUDGET_DENIED,
KILL_SWITCH, STOP_REQUESTED, EXECUTOR_NOT_BOUND, EXECUTOR_ERROR, INVALID_MODE.
OWNER_OS_REQUIRED/APPROVAL_REQUIRED/ALWAYS_REFUSED/non-GREEN all DENY here — Owner OS stays
the sole mutation authority; the gate never becomes a second dispatcher.

**Controls reused (not re-created):** `StopController.admit` (budget), `.killed` (live
Redis kill), `.check` (stop) — same controllers as `loop.py`.

**Audit events** (`kind="enforce"`, `layer="enforcement"`, `mode="enforce"`, no secrets):
enforcement_requested / evaluated / denied / started / completed / failed /
duplicate_suppressed. `harness.explain` now returns a `layers` breakdown distinguishing
shadow_observation vs enforcement_decision/execution/denial vs legacy_execution. New GREEN
Kavach read command `harness.enforcement` reports config + bindings + resolved mode (OFF).

**Live proof (2026-07-22, real `run_batch`):**
- ENFORCE, 3 items, concurrency 2, tool `batch.internal.safe_calculation@1.0.0`, agent
  `nikhil`, tenant `__system__`: legacy callable **0**, registry executor **3**,
  `enforcement_completed` **3**, duplicates **0**, denied **0**, aggregate done=3 failed=0.
- ROLLBACK (all flags OFF): legacy callable **3**, registry executor **0**, enforcement
  events **0**, shadow events **0**, audit records **0**, identical aggregate.

**Tests:** `tests/test_harness_enforce.py` — **50 tests** (mode resolution ×9, decision
pipeline ×18, execution/exactly-once ×7, batch integration ×11, audit/explain ×6, incl.
concurrency-honoured and kill-prevents-starts). Full harness suite **187 green** (9 files);
touched-loop regressions **41 green**.

**Readiness: `batch_harness` = CONDITIONALLY READY for an OWNER-APPROVED local/internal
enforcement canary. Overall project = NOT READY for global enforcement.** Enforcement flags
end this session OFF; nothing committed/pushed/deployed.

---

## dag_engine = second registry-backed family (SHADOW-only, 2026-07-22)

`dag_engine` is now the **second canonical registry-backed family** — in SHADOW mode only.
Enforcement for `dag_engine` is prohibited until a separate owner-approved plan.

**Selected step:** the process-library action `internal_calculation` maps to canonical
`workflow.dag.internal_calculation@1.0.0` (GREEN · side-effect NONE · INTERNAL_AUTONOMOUS ·
agents {nikhil, manager} · tenant {`__system__`} · schema `{n: integer, required, additionalProperties: true}`
so real DAG orchestration metadata passes · no approval/idempotency/sandbox). It is a NEW,
explicitly-named deterministic read-only step (`process_library._exec_internal_calculation`),
isolated from business behaviour — NOT a promoted business step and NOT the temporary shadow
proof name.

**Explicit mapping** (`dag_shadow.py:DAG_TOOL_MAP`): `{"internal_calculation": ("workflow.dag.internal_calculation","1.0.0")}`.
The DAG **node ID** and arbitrary model-provided step labels are NOT trusted tool identities —
only a stable process-library action listed in the map resolves to a canonical tool; every other
action stays `UNREGISTERED_TOOL`. No dynamic tool-name construction, no callable scanning, no
fallback-to-registered. `process_library.execute_step` dispatches the same action to the same
safe executor, so identity and executor agree (no spoofing).

**Strict DAG action envelope** (`dag_shadow.py:_valid_envelope`): `dag_run_id` mandatory,
`node_id` mandatory + bounded (≤200), `attempt` ≥ 0 — malformed metadata → `MISSING_CONTEXT`
diagnostic, never an executed-action record and never a false legacy failure. Tool argument
validation is the registry's authoritative `_minimal_schema_check` (integer `n` required).

**Layered shadow result** (execution layer unchanged, registry layer added):
- registered step → `execution_comparison=MATCH` + `registry_comparison=REGISTRY_MATCH` (GREEN,
  INTERNAL_AUTONOMOUS, agent+tenant pass, `enforcement_applied=false`).
- unmapped/legacy step → `MATCH` + `UNREGISTERED_TOOL` (backward-compatible; legacy execution unchanged).
- wrong-type / missing `n` → `MATCH` + `SCHEMA_MISMATCH` (execution NOT converted to a failure).
- registry is authoritative — a claimed-GREEN on a RED-registered DAG tool → `risk_class_mismatch`,
  registry wins; AMBER → would_require_approval; OWNER_OS_REQUIRED / RED → would_deny.

**Retry/idempotency preserved:** shadow ref `shadow:<dag_run_id>:<node_id>:<attempt>` — each real
attempt gets one evaluation with a distinct ref; `RETRY_OBSERVED` stays honest; the harness never
consumes the real DAG idempotency and DAG controls whether to retry.

**No DAG enforcement in this slice:** `AGENT_HARNESS_ENFORCE` OFF, `dag_engine` absent from
enforce-loop allowlists, no executor binding for DAG tools (`ExecutorBindingRegistry` unchanged) —
the DAG legacy executor stays authoritative; the registry executor is never invoked.

**Real proof (2026-07-22, real `dag_engine.advance` → `process_library.execute_step`):**
- registered `internal_calculation` node: dag_status `completed`, legacy executions **1**, harness
  executions **0**, shadow records **1**, resolved `workflow.dag.internal_calculation@1.0.0`,
  schema/agent/tenant pass, GREEN/INTERNAL_AUTONOMOUS, `MATCH`+`REGISTRY_MATCH`, `enforcement_applied=false`, journal 1 `node_completed`.
- unregistered `revenue_sweep` node: legacy **1**, harness **0**, `MATCH`+`UNREGISTERED_TOOL`.
- rollback (flags OFF): dag_status `completed`, legacy **1**, shadow records **0**, harness **0**.

**Kavach reads:** `harness.registry.conformance` now reports `dag_engine: registered`;
`harness.tool workflow.dag.internal_calculation` shows the definition (risk/authority/schema/agents/tenant, no callables).

**Tests:** `tests/test_harness_dag_registry.py` — **36 tests** (mapping/definitions, envelope,
registry-shadow verdicts, real `advance` exactly-once + journal + gate + shadow-failure-swallowed,
compatibility). Full harness suite **223 green** (10 files); touched-loop regressions **41 green**.

**Registry-backed families: 2/5** — `batch_harness`, `dag_engine`. staff/coordinator/supervisor
remain UNREGISTERED_TOOL. **`dag_engine`: CONDITIONALLY READY for a future separate canary plan;
enforcement remains OFF.** Nothing committed/pushed/deployed.

---

## staff.run_member / Nikhil = third registry-backed family (SHADOW-only, 2026-07-22)

`staff.run_member("nikhil")` is now the **third canonical registry-backed family** — SHADOW only.
Nikhil enforcement is prohibited until a separate approved plan.

**HONEST composite risk (the important finding):** `run_nikhil()` is a composite of three
independent engines — `revenue_digest.maybe_run_weekly` + `client_health.run_check` +
`usage_alerts.run_check`. Graphify proved `usage_alerts.run_check` **can send customer-facing
upsell emails** (SMTP to the metered client's address, gated by `_enabled()` + threshold + dedupe).
So the composite is classified honestly as **AMBER / EXTERNAL_SEND / APPROVAL_REQUIRED** — NOT a
simple autonomous GREEN. Registry classification is authoritative; risk was **not** lowered to force
a clean MATCH. The prior shadow under-classification (WRITE_LOCAL/GREEN) was corrected to
EXTERNAL_SEND.

**Canonical identity:** `agent.nikhil.revenue_operations@1.0.0` (AMBER · EXTERNAL_SEND ·
APPROVAL_REQUIRED · agents {nikhil} · tenant {`__system__`} · requires_approval=true ·
requires_idempotency=true · cost_class free · budget_scope internal_ops · timeout 120s · schema
`{requested_by?: string≤120, scope?: string, additionalProperties: false}`). Executor ref =
`app.agents.staff.run_nikhil` (legacy authoritative; NO executor binding — not enforcement-wired).

**Explicit mapping** (`shadow.py:STAFF_TOOL_MAP`): `{"nikhil": ("agent.nikhil.revenue_operations","1.0.0")}`.
STAFF membership ALONE never registers a tool — only members listed here map; every other member
stays `UNREGISTERED_TOOL`. No wildcard, no function-name identity, no model-selected identity, no
auto-registration of the 31-agent roster.

**Composite honesty** (`shadow.py:_composite_summary`): the shadow record carries
`composite_action=true`, `components=[client_health, revenue, usage_alerts]`, `component_count`,
`component_status`, `components_ok/failed`, `partial_success`, `full_success`. A component with an
`error` key is a failure — a partial failure is never reported as full success.

**Layered result** (execution unchanged, registry added): registered nikhil →
`execution_comparison=MATCH` + `registry_comparison=REGISTRY_MATCH`, `registry_risk_class=AMBER`,
`authority=APPROVAL_REQUIRED`, `registry_would_require_approval=true`, `registry_would_allow=false`,
`risk_class_mismatch=false` (claimed EXTERNAL_SEND == registry AMBER), `enforcement_applied=false`.
Peer member (kavya/manager/…) → `MATCH` + `UNREGISTERED_TOOL`. Claimed-GREEN vs registry-AMBER →
`risk_class_mismatch=true`, registry wins.

**Identity/tenant:** agent_id `nikhil` only (peer & manager denied → AGENT_NOT_ALLOWED); tenant
`__system__` (Nikhil sweeps internal platform data; a customer tenant → TENANT_NOT_ALLOWED). Registry
never trusts model-provided identity.

**Idempotency/budget:** `requires_idempotency=true` (writes digests/alerts + sends; duplicate would
duplicate effects) — the shadow ref is a non-executable `shadow:<run>:<idx>` reference, never the
real idempotency key. `cost_class=free` (free stack) but `network_policy=restricted` (SMTP send).

**Real proof (2026-07-22, real `staff.run_member("nikhil")` dispatcher → observe → registry; the
3-engine execution safely stubbed so NO customer email is sent):** 3 samples, legacy executions
**3**, harness executions **0**, each `MATCH`+`REGISTRY_MATCH`, AMBER/APPROVAL_REQUIRED,
would_require_approval, agent+tenant pass, enforcement_applied false; sample 3 `partial_success=true`
(usage_alerts error). Peer `kavya` → `UNREGISTERED_TOOL`, legacy **1**. Rollback (flags OFF) → legacy
**1**, **0** new records, result unchanged.

**Kavach reads:** `harness.registry.conformance` → `staff.run_member: registered`;
`harness.tool agent.nikhil.revenue_operations` shows the definition (AMBER/approval/idempotency, no callables).

**Tests:** `tests/test_harness_staff_registry.py` — **48 tests** (mapping, definition/schema,
identity/policy incl. AMBER/approval/OWNER_OS/disabled/version, real `run_member` exactly-once +
REGISTRY_MATCH + exception path + observer-failure-swallowed + peer-unregistered + flags-off,
composite/partial-failure, STAFF=31, conformance). Full harness suite **271 green** (11 files);
regressions + STAFF-count safety **66 green**.

**Registry-backed families: 3/5** — `batch_harness`, `dag_engine`, `staff.run_member`.
coordinator/supervisor remain UNREGISTERED_TOOL. **`staff.run_member/Nikhil`: NOT READY for an
autonomous enforcement canary** — it is AMBER / external-send / approval-required, so it can only
ever be enforced through an approval-gated path, never autonomously. Enforcement remains OFF.
Nothing committed/pushed/deployed.

---

## coordinator = structured action contract + fourth registry-backed family (SHADOW-only, 2026-07-22)

Coordinator ambiguity (raw LLM prose parsed by `_extract_list`) is replaced by ONE strict, versioned
structured action language — SHADOW only. Coordinator enforcement is prohibited.

**Canonical contracts** (`coordinator_contract.py`): `CoordinatorPlanV1` / `CoordinatorActionV1`
(frozen `extra="forbid"`, `schema_version="1.0"`) + `CoordinatorActionResultV1` +
`CoordinatorPlanComparison`. Closed `CoordinatorActionType` enum (DELEGATE_AGENT,
INVOKE_INTERNAL_TOOL, REQUEST_ANALYSIS, REQUEST_REVIEW, SYNTHESIZE, STOP) — arbitrary
model-generated action types fail validation. Rules: unknown enum / extra field / duplicate
action_id / negative sequence / unbounded task (>2000) / non-dict arguments / invalid schema_version
all reject. **Raw LLM prose is never an executable contract.**

**Legacy adapter** (`normalize_legacy_plan`): `_extract_list` output → `CoordinatorPlanV1` with HONEST
provenance (`PlanSource`: STRUCTURED_NATIVE / STRICT_JSON / LEGACY_JSON_EXTRACT / LEGACY_REGEX /
FALLBACK_DEFAULT / FAILED). Heuristic/fallback output is NEVER marked `STRUCTURED_NATIVE`.

**Plan comparator** (`compare_plans`): deterministic structured-vs-legacy → `CoordinatorPlanVerdict`
(PLAN_MATCH / TARGET_MISMATCH / TOOL_MISMATCH / ARGUMENT_MISMATCH / ORDER_MISMATCH /
ACTION_COUNT_MISMATCH / STRUCTURED_INVALID / LEGACY_FALLBACK / UNCOMPARABLE); bounded `differences`.
Never modifies execution. Three layers stay distinct: structured proposal / legacy normalized plan /
actual legacy execution.

**Both executor boundaries covered:** `_run_agent` (existing) + `_expert_contribution` (NEW hook) —
each record-only via `observe_coordinator_action(..., boundary=...)`, distinct `executor_boundary`
identity, never re-runs the tool, preserves result/fallback semantics.

**Delegation identity standard** (`delegation_identity`, `validate_delegation_target`): canonical
`agent.delegate.<agent_id>`; target must be a real STAFF member; **Kavach is never a delegation
target**; unknown agent → invalid; manager is a valid target (not silently a worker) but is NOT
auto-registered. STAFF membership alone never registers a tool.

**ONE honest registration → coordinator is 4/5.** `agent.delegate.dev@1.0.0` (GREEN · READ_ONLY ·
INTERNAL_AUTONOMOUS · agents {dev} · tenant {`__system__`} · no approval/idempotency ·
network_policy restricted). Justified because downstream `_tool_dev` = `hashtags.research` is
read-only research (no publish/mutate/deploy/code-exec/external-send; template fallback). **Every
other delegation/tool stays UNREGISTERED_TOOL** — isha (LLM post-draft), kavya/arjun/meera
(run_ops/qa/trainer internal writes), and all side-effect agents (rohan/swara excluded from `_TOOLS`).
No executor binding — not enforcement-wired.

**Registry authoritative:** claimed-GREEN vs registry-AMBER → `risk_class_mismatch`; AMBER →
would_require_approval; OWNER_OS_REQUIRED / RED → would_deny; unknown → UNREGISTERED. Scoped:
`agent.delegate.dev` allowed_agents {dev} only — another agent context → AGENT_NOT_ALLOWED
(delegation does not grant unrestricted permissions).

**Flags** (`COORDINATOR_STRUCTURED_PLAN`, `COORDINATOR_STRUCTURED_PLAN_SHADOW`) default OFF. Structured
planning in this phase is shadow-only/mocked (no real dual-LLM double cost); provider-native
structured planning is a future step. Coordinator budget/stop/kill reuse the existing StopController.

**Real proof (2026-07-22, real `coordinate(execute=True)` dispatch → `_run_agent`/`_expert_contribution`
→ observe → registry; planner mocked + `_TOOLS` stubbed safe → no real LLM/network/customer effect):**
5 samples, legacy executions dev **3** / isha **1** / kavya **1**, harness executions **0**, dev →
3× `REGISTRY_MATCH` (agent.delegate.dev, GREEN), isha/kavya → `UNREGISTERED_TOOL`, executor boundaries
`{_run_agent: 4, _expert_contribution: 1}` (**2/2**), external effects **0**, enforcement_applied
false. Rollback (all flags OFF) → legacy dev **1**, **0** new shadow records.

**Kavach reads:** `harness.registry.conformance` → `coordinator: registered`;
`harness.coordinator.contract` / `.samples` / `.readiness` (contract version, action types,
boundary coverage 2/2, readiness blockers). `harness.tool agent.delegate.dev` shows the definition.

**Tests:** `tests/test_harness_coordinator_registry.py` — **53 tests** (contract validation ×12,
legacy normalization ×6, plan comparison ×8, execution safety + both boundaries ×9, delegation
identity ×7, registry compat ×7, compatibility ×4). Full harness suite **324 green** (12 files);
regressions + STAFF-count safety **66 green**.

**Registry-backed families: 4/5** — `batch_harness`, `dag_engine`, `staff.run_member`, `coordinator`.
supervisor remains UNREGISTERED_TOOL. **`coordinator`: STRUCTURED CONTRACT STABLE, BUT NOT READY FOR
ENFORCEMENT** (structured planning shadow-only/mocked; most delegations unregistered; no executor
binding). Enforcement remains OFF. Nothing committed/pushed/deployed.

---

## supervisor / staff_supervisor = fifth family, shared contract reuse (SHADOW-only, 2026-07-22)

The supervisor family REUSES `CoordinatorActionV1` (no fork) via `SupervisorDecisionV1`
(`coordinator_contract.py`, `extra="forbid"`, schema_version 1.0): a route label / selected graph
node / structured message identity normalizes into the shared delegation contract. Raw assistant
prose is never an action identity. `to_coordinator_action()` preserves actor_id + supervisor
metadata (graph_run_id/graph_step/route_label/selection_source) in bounded arguments.

**Graphify:** `supervisor.py` = rule/semantic router (`supervisor_node` → route ∈ {data_agent,
leads_agent}) → `data_agent_node` (KB+LLM, read-only) / `leads_agent_node` (niche-config+LLM,
read-only PLAN — no send/CRM/call). `staff_supervisor.py` = langgraph-supervisor graph, selected
agent from message `name` (MESSAGE_NAME), gated by `USE_LANGGRAPH_SUPERVISOR` + `langgraph-supervisor`
/`langchain-openai`. Both unified under `source_loop=supervisor`.

**Selection provenance** (`SelectionSource`): GRAPH_ROUTE (supervisor.py) / MESSAGE_NAME
(staff_supervisor.py) / NODE_IDENTITY / HEURISTIC / UNKNOWN. HEURISTIC → `PARSER_AMBIGUITY`, UNKNOWN
→ `MISSING_CONTEXT` — neither is registry-trusted (blocks readiness). Target inferred from a
structured route/message name, never from result prose. `SUPERVISOR_ROUTE_MAP` route→target agreement
is checked → `route_node_mismatch`.

**Actor vs target:** `actor_id=manager` (who delegated) and `agent_id=target_agent` (who executes)
kept distinct. Manager does not gain every tool; target must be explicitly allowed; **Kavach is never
a delegation target** (validator rejects); tenant not model-settable.

**Two honest registrations (5th family):**
- **data route → REUSES `agent.delegate.dev@1.0.0`** (GREEN, read-only) — one canonical capability
  invoked from BOTH coordinator and supervisor, no duplicate policy (proves §9 cross-orchestrator reuse).
- **leads route → `agent.delegate.rohan@1.0.0` = AMBER / EXTERNAL_SEND / APPROVAL_REQUIRED.** Rohan's
  canonical role is customer OUTREACH; the shared identity is classified by that broadest capability
  even though this specific `leads_agent_node` only drafts a plan. **NOT forced GREEN.** The adapter
  raises the claimed risk to EXTERNAL_SEND so REGISTRY_MATCH is honest (claimed==registry), never lowered.
  No executor binding — not enforcement-wired.

**Real proof (2026-07-22, real `run_supervisor_task` LangGraph; router + `_llm_brain` fixture-stubbed →
no real LLM/customer effect):** supervisor.py 3 samples, node executions **3**, harness executions
**0**, dev → REGISTRY_MATCH (agent.delegate.dev GREEN), rohan → REGISTRY_MATCH AMBER
`would_require_approval=true`, external effects **0**, enforcement_applied false. Rollback (flags OFF)
→ route unchanged, node executions **1**, **0** new shadow records. **staff_supervisor.py real graph
is HONESTLY BLOCKED** (`USE_LANGGRAPH_SUPERVISOR` unset + `langchain-openai`/provider) — its
structured-contract + MESSAGE_NAME selection are wired and unit-proven, but the real graph did not run.

**Replay/dedup:** shadow write dedup on `supervisor:<graph_run_id>:<graph_step>:<tool_call_id|idx>:<attempt>`
(memory-local; documented). Duplicate callback → one shadow write; genuine retry (new attempt) → separate;
the two implementations do not collide (distinct tool_call_id/context). No manufactured downstream child.

**Kavach reads:** `harness.registry.conformance` → `supervisor: registered`;
`harness.supervisor.contract`/`.samples`/`.readiness`; `harness.tool agent.delegate.rohan` shows AMBER.

**Tests:** `tests/test_harness_supervisor_registry.py` — **58 tests** (shared-contract reuse ×10,
supervisor.py mapping ×10, staff_supervisor mapping/selection ×10, registry ×12, real supervisor.py
graph ×5, correlation/replay ×6, compatibility ×5). Full harness suite **382 green** (13 files);
regressions + STAFF-count safety **66 green**.

**Registry-backed: supervisor.py implementation proven (dev reuse + rohan AMBER); staff_supervisor.py
real-graph dep-gated → family migration is PARTIAL.** All five families are shadow-covered and
structured-contract-covered. **supervisor family: STRUCTURED CONTRACT STABLE, BUT NOT READY FOR
ENFORCEMENT** (rohan is AMBER approval-required — never autonomous; staff_supervisor real graph blocked;
no executor binding). Enforcement remains OFF. Nothing committed/pushed/deployed.
