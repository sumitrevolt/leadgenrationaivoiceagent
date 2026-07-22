# Kavya — Third-Agent Production Canary Proof

**Classification:** `PRODUCTION-CANARY-PROVEN` for Kavya `ops_health_check` only (read-only Ops Watchdog diagnostic).  
**Date:** 2026-07-22  
**Deployed SHA:** `3fe74095` (`3fe740958dac14eba2ac27d8ce91104aa7e90389`)  
**Authorization:** Owner — Kavya-only third canary (runtime flags; no production code change).  
**Outcome:** COMPLETE for this loop. Overall 31-agent mission remains **incomplete**.

Kavya is **not** `production_enabled` — all workforce flags restored OFF after proof.

---

## 1. Candidate comparison (10 canary-ready)

| Agent | Capability (runtime) | Engine | Reads | Possible writes | External side effects | Flag | Lane | Canary eligible |
|---|---|---|---|---|---|---|---|---|
| **Kavya** | `ops_health_check` | `automation_health.health()` via `kavya_ops_health_check` | beats, queues, dead markers | audit/runtime/idem only | none for this capability | `OPS_WATCHDOG` | GREEN L0 | **YES (chosen)** |
| Isha | `draft_content_brief` | LLM/template draft | client/topic | draft proposal only | LLM call if `AGENT_RUNTIME_LLM=1` | `AFTERNOON_CONTENT` | GREEN L1 | hold — reasoning / content |
| Zara | `publish_approved_content` | `social_engine.enqueue_publish` | approval record | **publish queue write** | social publish hand-off | `SOCIAL_ENGINE` | **AMBER** | NO |
| Hermes | owned infra snapshot | infra_handler snapshot | infra signals | proposal path risk | infra tooling surface | `INFRA_HANDLER` | GREEN L1 | later — infra adjacency |
| Vidya | owned finops | finops scan | cost metrics | none (adapter marks read_only) | billing-adjacent reads | `FINOPS_AGENT` | GREEN L0 | next-tier RO |
| Arnav | owned security | security scan | compliance signals | proposal | security tooling | `SECURITY_AGENT` | GREEN L1 | **recommended next** |
| Kabir | owned dbre | DB reliability scan | DB metrics | prohibited write_prod_db | DB adjacency | `DBRE_AGENT` | GREEN L0 | later |
| Diya | owned data quality | integrity scan | data quality | dedupe prohibited | customer-data adjacency | `DATA_INTEGRITY_AGENT` | GREEN L0 | later |
| Aryan | owned deps | supply-chain scan | deps lockfiles | upgrade prohibited | package surface | `DEPS_AGENT` | GREEN L1 | **recommended next** |
| Arya | owned MCP health | MCP health | MCP endpoints | expose prohibited | MCP surface | `MCP_ENGINEER` | GREEN L1 | later |

**Why Kavya:** lowest-risk real execution pattern already registered as GREEN L0 deterministic read-only (`side_effect=none`), no customer/publish/billing/infra mutation in the selected capability, useful ops diagnostic.

**Dual-path caveat (documented, mitigated):** `OPS_WATCHDOG=1` also arms legacy scheduler `ops_watchdog.run_watchdog()` (hourly ~:35) which can retry outbound webhooks and email alerts. Agent Runtime canary used **only** `ops_health_check` (never `run_watchdog`). Arm window kept outside :30–:40 UTC; post-canary `dead=7` unchanged; flags OFF before next :35.

---

## 2. Verified Kavya contract

```yaml
agent_id: kavya
capability: ops_health_check
adapter: kavya_ops_health_check  # app/platform/agent_runtime_pilots.py
engine: automation_health.health()
feature_flag: OPS_WATCHDOG
flag_default: false
safety_lane: GREEN
autonomy: L0_OBSERVE
mode: read_only
tenant_scope: false
writes_allowed: false   # for ops_health_check
customer_communication: false
automatic_remediation: false
timeout_s: 120
max_concurrency: 1
remediation_capability_on_runtime: absent  # run_watchdog → capability_not_registered
```

Registration: `ensure_pilots_registered()` → `AgentCapability(side_effect="none")`.  
Primary flag confirmed via `agent_registry.primary_flag="OPS_WATCHDOG"` + canary preflight census.

---

## 3. Pre-canary snapshot

| Item | Value |
|---|---|
| `/health` | healthy / production / `3fe74095` |
| App images (5) | `ghcr.io/...:3fe74095` |
| Migration | `022_add_request_depth (head)` |
| Workforce flags | **all OFF** in app/worker/scheduler/heavy/video |
| OpenClaw | `0` |
| Calling | `PLATFORM_DIAL_DAILY=0` |
| Queues | celery=0 failed=0 **dead=7** (unchanged; not replayed) |
| Eligible (runtime OFF) | `[]` |
| Ungated | `0` |
| Idempotency | Redis, fallback false |
| Cancellation | Redis, fallback false |

Disabled Kavya submit: `skipped` / `runtime_flag_disabled:AGENT_RUNTIME` — no lease / no engine.

---

## 4. Eligibility proofs

### Empty (all flags OFF)
```yaml
agent_runtime_enabled: false
eligible_agents_if_enabled: []
ungated_dispatchable_agents: []
unexpected_agents: []
```

### Flag-only (`AGENT_RUNTIME=0`, `OPS_WATCHDOG=1`)
```yaml
agent_runtime_enabled: false
expected_agent: kavya
eligible_agents_if_runtime_enabled: [kavya]
unexpected_agents: []
allowed: true
```

### Armed (`AGENT_RUNTIME=1`, `OPS_WATCHDOG=1`, peers OFF)
```yaml
agent_runtime_enabled: true
eligible_agents: [kavya]
unexpected_agents: []
allowed: true
enabled_workforce_count: 1
```

---

## 5. Real runtime proof

| Field | Value |
|---|---|
| Owner command | `ocmd_5ed79850efc2` |
| Idempotency key | `kavya-prod-canary-3fe74095-v1` |
| Runtime run | `art_c913cdb95326` |
| Lifecycle | `queued → leased → running → succeeded` |
| Duration | 465 ms |
| Engine | real `automation_health.health()` (no mock) |
| Output quality | PASS — `check`, `read_only:true`, status/ok, queue keys, overdue/never_ran lists, `dead_tasks_present` |
| Observed diagnostic | `status=degraded`, `ok=false`, `dead_tasks_present=true` (reflects existing dead=7; **no remediation**) |
| Intentional 2nd key | `...-v2` → `art_4046992f8c98` succeeded |

Unauthorized mutations: **0** (SHA unchanged, dead=7, no peer agents, OpenClaw/calling OFF).

---

## 6. Redis idempotency (cross-process)

```text
KEY = kavya-prod-canary-3fe74095-concurrent-v1
A = leadgen_app   → succeeded art_ef928b06c206
B = leadgen_worker → skipped duplicate_in_progress original=art_ef928b06c206
```

```yaml
atomic_claim_winners: 1
runtime_runs_created: 1
engine_call_count: 1
duplicate_responses: 1
```

Restart-process duplicate (worker half, key `...-v1`): `duplicate_suppressed` → original `art_c913cdb95326`.

Finite Redis TTL observed on Kavya idem keys (~`1209197`–`1209389` s remaining ≈ 14d schema default).

---

## 7. Cancellation & control inheritance

| Control | Result |
|---|---|
| Pause | `blocked:agent_paused` → resume once → dup suppressed |
| Stop claims | `blocked:agent_claims_stopped` |
| Drain new work | `blocked:agent_draining` |
| Kill (`owner_schedulers`) | `blocked:kill_switch_engaged:owner_schedulers` |
| Pre-engine cancel | `cancelled:cancel_requested` (`art_465391e7aa81`); dup suppressed; future unique succeeded |
| In-flight drain finish | **not observed** (honest: partially_proven globally) |
| Cross-container cancel race | **not re-proven** for Kavya (engine ~465ms); Redis cancel backend still active (`fallback_active:false`) |

---

## 8. Policy refusals

| Case | Result |
|---|---|
| Unknown capability | `blocked:capability_not_registered` |
| `run_watchdog` remediation | `blocked:capability_not_registered` |
| Pranav | `skipped:flag_disabled:SRE_AGENT` |
| Nikhil | `skipped:flag_disabled:DELIVERY_ASSURANCE_AGENT` |
| Isha peer | `skipped:flag_disabled:AFTERNOON_CONTENT` |
| Swara | `blocked:red_lane_hard_off_mandate_required` |

Controlled failure (`kavya_fail_probe`): `failed` then same-key `duplicate_suppressed`.

---

## 9. Rollback (mandatory)

All listed flags forced `0` in app/worker/scheduler/heavy/video:

`AGENT_RUNTIME`, `OPS_WATCHDOG`, peers, `OPENCLAW_ENABLED`, `PLATFORM_DIAL_DAILY`.

Final preflight: eligible `[]`, ungated `0`.  
Final `/health`: healthy / production / `3fe74095`.  
Queues: celery=0 failed=0 **dead=7**.  
Idempotency + cancellation: Redis, fallbacks false.

---

## 10. Updated 31-agent state

| State | Count |
|---|---:|
| production_canary_proven | **3** — Pranav, Nikhil, Kavya |
| canary_ready | **9** |
| rollout_hold | 17 |
| intentionally_disabled | 2 |
| **Total** | **31** |

```yaml
production_canary_patterns:
  deterministic_read_only_sre:
    agent: pranav
    proven: true
  platform_global_delivery_diagnostic:
    agent: nikhil
    proven: true
  operational_watchdog_diagnostic:
    agent: kavya
    proven: true
```

---

## 11. Unresolved limitations

- In-flight drain completion remains **partially_proven**.
- Kavya cross-container cancel race not separately timed (engine too fast); Redis cancel store inherited from prior proof.
- `OPS_WATCHDOG` dual-path (scheduler `run_watchdog`) remains a flag-coupling risk — keep arm windows short / off after canary.
- Stale idempotency claims need explicit recovery if re-keying same strings.
- Inherited CI segfault / Jiya failures unchanged (out of scope).
- Future mutation-capable agents require AMBER approval proof.

---

## 12. Exact next action

Do **not** immediately activate a fourth agent. Review remaining nine canary-ready agents and select **Arnav** or **Aryan** as the next pure-read security/supply-chain pattern under a **separate** owner authorization.
