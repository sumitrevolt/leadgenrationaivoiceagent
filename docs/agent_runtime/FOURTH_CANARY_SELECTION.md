# Fourth Production Canary Selection — Arnav vs Aryan

**Date:** 2026-07-22  
**Loop type:** selection + local readiness only  
**Production mutation:** **NONE** (flags untouched)  
**Production SHA (verified):** `3fe74095` (`3fe740958dac14eba2ac27d8ce91104aa7e90389`)  
**Decision:** `SELECT ARNAV`  
**Production canary:** `BLOCKED — OWNER AUTHORIZATION REQUIRED FOR FOURTH-AGENT CANARY`

Overall 31-agent mission remains **incomplete**. Rollout counts **unchanged**.

---

## 1. Production baseline (read-only verify)

```yaml
health: healthy
environment: production
version: 3fe74095
workforce_flags: all_off
openclaw: off
calling: hard_off
```

Post-selection `/health` re-check: healthy / production / `3fe74095` (2026-07-22T07:11Z).

---

## 2. Nine remaining canary-ready — risk matrix

| Agent | Capability | Adapter | Engine | Flag | Lane | Read paths | Write paths | External effects | Scheduler coupling | Candidate status |
|---|---|---|---|---|---|---|---|---|---|---|
| Isha | `draft_content_brief` | `isha_draft_content_brief` | LLM/template draft | `AFTERNOON_CONTENT` | GREEN L1 | topic/business | proposal only | optional LLM | content scheduler | hold |
| Zara | `publish_approved_content` | `zara_publish_approved_content` | `social_engine.enqueue_publish` | `SOCIAL_ENGINE` | **AMBER** | approval | **publish queue** | social publish | social drain | **reject** |
| Hermes | `run_owned_workflow` | `hermes_infra_snapshot` | `infra_handler.snapshot` | `INFRA_HANDLER` | GREEN L1 | infra signals | scan JSON | email if `run_watch` | hourly watch | hold |
| Vidya | `run_owned_workflow` | `vidya_finops` | `run_finops` | `FINOPS_AGENT` | GREEN L0 | cost KPIs | team log + ntfy* | ntfy if `OPS_ALERTS` | daily | hold |
| **Arnav** | `run_owned_workflow` | `arnav_security` | `run_security` | `SECURITY_AGENT` | GREEN L1 | ledger meta + secret **presence** bools | team log + ntfy* | ntfy if `OPS_ALERTS` | daily same engine | **SELECTED** |
| Kabir | `run_owned_workflow` | `kabir_dbre` | `run_dbre` | `DBRE_AGENT` | GREEN L0 | pg catalog | team log + ntfy* | ntfy | daily | hold |
| Diya | `run_owned_workflow` | `diya_dataquality` | `run_dataquality` | `DATA_INTEGRITY_AGENT` | GREEN L0 | prospects.jsonl | team log + ntfy* | ntfy | daily | hold |
| **Aryan** | `run_owned_workflow` | `aryan_deps` | `run_deps` | `DEPS_AGENT` | GREEN L1 | lockfile + pip-audit | team log + ntfy* | ntfy; subprocess | weekly same engine | runner-up |
| Arya | `run_owned_workflow` | `arya_mcp` | `mcp_engineer.run_mcp` | `MCP_ENGINEER` | GREEN L1 | MCP surfaces | last.json + alerts | ntfy | hourly | hold |

\* `_maybe_alert` only when `OPS_ALERTS=1` (default OFF).

---

## 3–4. Contracts (summary)

**Arnav:** `SECURITY_AGENT` → `arnav_security` → `engineer_agents.run_security` — read-only posture score; no remediation; scheduler shares **same** RO engine (not Kavya-style mutation coupling).

**Aryan:** `DEPS_AGENT` → `aryan_deps` → `run_deps` — allowlisted `pip_audit` subprocess; no install/upgrade; CVE signal weak when pip-audit absent.

Full call graphs + flag census: see worktree copy `leadgen-dist-idem/docs/agent_runtime/FOURTH_CANARY_SELECTION.md` (canonical long form) and local evidence JSON.

---

## 5. Local proof highlights

- Empty eligible `[]`; Arnav-only and Aryan-only isolation **allowed**
- Arnav engine 0.691s score 42.5 structured KPIs; Aryan 0.14s CVE=null
- Local runtime submit fail-closed without Redis (`cancellation_store_unavailable`) — expected
- Pause/kill inheritance observed; pytest engineer+workforce **32 passed**

---

## 6. Risk totals (weighted)

Arnav **12** · Aryan **23** → **SELECT ARNAV**

---

## 7. Decision

```text
SELECT ARNAV
```

```text
BLOCKED — OWNER AUTHORIZATION REQUIRED FOR FOURTH-AGENT CANARY
```

---

## 8. Kavya backlog

```yaml
kavya:
  flag: OPS_WATCHDOG
  issue: shared_with_scheduler_path
  status: production_canary_proven_but_not_safe_for_persistent_enablement
  required_fix: independent_agent_runtime_flag_or_scheduler_gate
```

---

## 9. Counts unchanged

| State | Count |
|---|---:|
| production_canary_proven | 3 |
| canary_ready | 9 |
| rollout_hold | 17 |
| intentionally_disabled | 2 |
| Total | 31 |

## Exact next action

Owner authorize **Arnav-only** prod canary: `AGENT_RUNTIME=1` + `SECURITY_AGENT=1`, peers/`OPS_WATCHDOG`/`OPS_ALERTS`/`OPENCLAW`/`PLATFORM_DIAL` OFF; full disabled→flag-only→armed→proof→rollback loop.
