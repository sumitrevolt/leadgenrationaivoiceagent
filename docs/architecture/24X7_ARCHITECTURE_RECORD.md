# 24×7 CANONICAL ARCHITECTURE RECORD — PHASE 1 FREEZE

**Compiled:** 2026-09-10 · **By:** team-lead (Qi) · **Source:** architect design (Gao), built on the QA-verified PHASE 0 baseline
**Status:** FROZEN for design — no code change may start until the owner gates in §7 are cleared.

> ⚠️ **Tooling caveat from the architect:** Bash/PowerShell stdout capture failed mid-session. Everything in
> this record derives from Read/Grep/Glob. Two items are explicitly **UNVERIFIED** and are marked as such.
> Do not restate them as fact.

---

## 1. LINEAGE — BASE COMMIT

**BASE = `0b848b34`.** Decision: **(a)-minimal** — cut `migration/24x7` from `0b848b34` and cherry-pick
**ZERO** of the 30 local HEAD commits by default.

Each of the 30 is admitted only via an individually-tested, owner-approved cherry-pick. Rationale: they are
unreleased local work not required for the migration; forcing them in converts a lineage fix into a
30-commit regression risk.

**Risks of the rejected options**
| Option | Risk |
|---|---|
| (b) merge prod → HEAD | HEAD carries 30 never-run-in-prod commits; conflict resolution on the Smartflo pair can silently drop prod's fix → **live call-drop regression on a revenue system**. |
| (c) leave HEAD alone | The 30 rot and get force-merged later; local stays divergent, so any future deploy-from-local silently reverts prod. |

**Conflict #1 — PROVEN:** voice/Smartflo.
`d0183bf1` = *fix(smartflo): keep playback alive and persist cleanup metering* (09-08 21:49 IST) **vs**
`0b848b34` = *fix(voice): Smartflo call-drop root cause — TTS silent failure + stream_sid validation*
(09-09 14:01 IST) — same subsystem, adjacent days, divergent.

**Conflicts #2 / #3 — UNVERIFIED.** Resolve with:
```
git log --oneline 79291e2b..d0183bf1
git log --oneline 79291e2b..0b848b34
# intersect by touched path
```
Highest-probability areas (UNVERIFIED, do not assume): `app/telephony/*` and `app/platform/agent_runtime.py`-adjacent
(ADR-179/180/181/182/183 churn).

> **No branch has been created.** Branch creation itself awaits owner approval.

---

## 2. SINGLE CONTROL PLANE — CANONICAL = **DevTask**

`app/models/dev_task.py:10` · Postgres `dev_tasks` · 18 states (`app/dev_control/service.py:10-28`).
Chosen because it already has atomic claim, heartbeat and a 600 s lease.

| Implementation | Disposition |
|---|---|
| **DevTask** | **CANONICAL** — extended per gap table below |
| AgentTask `app/platform/agent_task_queue.py` | **SHIM → canonical.** Stays the *scheduler routine ledger* (its documented job, `:557+`); add nullable `dev_task_id`; no orchestration logic |
| CC ledger `command_center/data/tasks.json` | **FREEZE-readonly → MIGRATE.** Gitignored + unversioned → **export/version it FIRST**, one-time reviewed import into DevTask, then regenerate as a read-only export |
| `command_center/state.js` | **DELETE-AS-SOURCE.** Committed and the *only* task view the UI serves, but frozen at 08-24/09-02. Remove the tasks array or regenerate from DevTask |
| `agent_runtime` JSON `app/platform/agent_runtime.py` | **SHIM → canonical.** Keep heartbeat/backoff/DLQ as *liveness* only; task identity = `dev_task.id`. Its lease is in-process only → **not truth** |
| `HERMES_CONTROL_PLANE.md` | **SUBORDINATE (not DELETE).** Delete the Dsh/Cordis-plugin + own-Redis-bus sections (second control plane). **KEEP** §Desktop Worker Coordination Contract + §Bot-to-Bot Event System (single `getUpdates` consumer, one lease owner per task) as normative rules |

### DevTask gap-closure contract

| Gap | File | Minimal change |
|---|---|---|
| startup reconcile | `app/dev_control/reconcile.py` | expose `reconcile_leases()` as startup-lifespan + beat entry (today admin-POST only, `app/api/dev_tasks.py:392`); idempotent, bounded, runs **before** first claim |
| retry backoff | `app/dev_control/reconcile.py:32,52` | add `next_eligible_at`; curve **60 s × 2ⁿ, cap 15 m + jitter**; `claim_next` predicate adds `next_eligible_at <= now` |
| durable idempotency | `app/dev_control/service.py:72` | **DELETE** the process-local `_IDEMPOTENCY` dict; enforce the existing unique column `dev_task.idempotency_key` (`:14`) by DB upsert; return 200 + existing id on conflict |
| audit history | **NEW** `app/models/dev_task_event.py` | `DevTaskEvent(task_id FK, seq, prev_hash, event_hash, actor, from_state, to_state, payload, created_at)` — hash-chained, reuse the ADR-180 pattern in `app/agents/harness/session.py` |
| parent_id + deps | `app/models/dev_task.py:31` | add `parent_id` FK; a QUEUED task is **not claimable until all `dependencies` are `completed`** — enforce in `claims.claim_next:82` |

---

## 3. WORKER IDENTITY CONTRACT — new table `dev_workers`

**Fields:** `worker_id` (PK) · `kind` (cli / api / desktop) · `supervisor_bot` · `capabilities[]` · `version` ·
`started_at` · `heartbeat_ts` · `lease_id` · `current_task_id` · `queue_depth` · `success_count` ·
`failure_count` · `combo_id` · `health` (healthy / degraded / dead) · `pid_host`.

| Cadence | Value |
|---|---|
| heartbeat interval | **60 s** |
| lease TTL | **600 s** (keep `app/dev_control/claims.py:27`) |
| staleness | `now > lease_until` (= 10 missed beats) |
| reap sweep | **60 s** |
| requeue rule | `retry_count < 3` |
| backoff | 60 s × 2ⁿ, cap 15 m |
| max attempts | **3** |

**Reap:** sweeper moves CLAIMED/RUNNING → BLOCKED → QUEUED (existing legal transition, `reconcile.py:47`),
writes a `DevTaskEvent`, frees the slot.
**Desktop workers** use the same contract but are **advisory until HMAC-attested** — never authoritative.

---

## 4. BOT → AGENT MAPPING (9 bots ← 31 agents, no agent unassigned)

Derived from `app/platform/team.py:49-316` duties.

| Bot | Agents |
|---|---|
| **Pilot** (1) | manager |
| **hunter** (4) | rohan, dev, ravi, neha |
| **sales** (4) | nikhil, priya, anika, ira |
| **platform** (4) | hermes, kavya, tara, arya |
| **engineering** (5) | vikram, guru, pranav, kabir, aryan |
| **success** (3) | isha, zara, kiran |
| **guardian** (4) | arjun, meera, arnav, diya |
| **operations** (4) | riya, raksha, ananya, **swara** |
| **board** (2) | lekha, vidya |

**12 pilots distribute:** platform 3 (kavya, hermes, arya) · engineering 3 (pranav, kabir, aryan) ·
success 2 (isha, zara) · guardian 2 (arnav, diya) · sales 1 (nikhil) · board 1 (vidya).

### The 19 non-dispatchable — explicit disposition

| Disposition | Agents | Condition |
|---|---|---|
| **PROMOTE NOW (1)** | `priya` | Evidence exists: `AGENTS.md:137` CRM LIVE, provider=hubspot, auto_sync, recent_pushes=5 |
| **PROMOTE AFTER CANARY (8)** | dev, rohan, neha, kiran, anika, ira, lekha, ravi | Each needs ≥1 green canary with a stored evidence artifact + `task_execution_verified=true` |
| **MANUAL / ADVISORY (3)** | manager (Boss = orchestrator surface, never a worker — ADR-165), guru (skill curation, owner-curated), vikram (mutating code; duty text requires owner approval) | Stay non-dispatchable by design |
| **PERMANENTLY NON-DISPATCHABLE (7)** | swara, ananya, riya, raksha, tara, arjun, meera | Voice RED + customer AMBER + voice-adjacent QA stay OUT (`agent_runtime.py:90-93`) |

> 🔒 **`swara` is FROZEN (voice, modification permission NONE)** and must stay non-dispatchable
> regardless of any future rollout decision.

---

## 5. OMNIROUTE CONTRACT + 14 COMBOS

**Canonical id = `leadsgen combo N` (1–14), single scheme.** `_TASK_ROUTES`
(`app/platform/omniroute_client.py:106`) already complies and `tests/test_omniroute_canonical_combos.py`
enforces it.

- **Legacy aliases** (leadgen-free-first, hermes-*, kimi-coding, vps-01/02, claude-code) become **read-only
  aliases** in a new `app/platform/omniroute_aliases.py`. `config/desktop_apps/combo_distribution.yaml`
  loses routing authority (it already has none) and references aliases only, resolved at load.
- **Gateway's 18 → 14** is a gateway-side prune, documented, not code-enforced.

### New per-combo health record

**Module** `app/platform/omniroute_combo_health.py` · **Table** `omniroute_combo_health`

`combo_id` PK · `last_success_at` · `last_failure_at` · `failure_count` · `consec_failures` ·
`circuit_state` · `circuit_open_until` · `quota_remaining` · `quota_reset_at` · `latency_p50_ms` ·
`latency_p95_ms` · `cost_usd_today` · `tokens_today` · `fallback_combo_id`

> All of these are **new except latency**, which already exists (`omniroute_client.py:80,482`).

- **Auto-disable:** `consec_failures >= 5` → `circuit_state=open`, `circuit_open_until = now + cooldown`,
  cooldown 60 s → 30 min escalating (mirror the 429 breaker in `app/voice_agent/free_ai.py`); route to
  `fallback_combo_id`.
- **Re-enable:** after cooldown → half-open single probe; success = closed, fail = reopen + double cooldown.

### Making the SOT reviewable without leaking secrets

Keep `.omniroute-cutover/combos.json` gitignored (`.gitignore:344`). Add
`scripts/omniroute_export_combos.py --redact` emitting a **committed**
`config/omniroute/combos.canonical.json` containing **only** combo id, slot index, providerId, model, label.
**No keys.** Un-ignore only the redacted export.

### Headless replacement for openclaw + verdant

Both are `project_only` in `combo_distribution.yaml:72,82` — re-scope to `vps_and_project` and back them
with CLI/API supervisor bots. **Blocked on the `_KNOWN_TOOLS` owner gate (§7)** — these are the two apps
whose only enrolment path is desktop.

---

## 6. DASHBOARD IA — 4-level progressive disclosure

**L1 Executive (6 tiles) → L2 Module (10) → L3 Detail → L4 Raw (JSONL / hash-chain)**

| # | Module | Data source | Upgrade this existing file |
|---|---|---|---|
| 1 | Executive | DevTask `status_snapshot` + billing truth | `admin-dashboard/src/pages/Dashboard.tsx` |
| 2 | 24×7 worker control | `dev_workers` + heartbeats | `admin-dashboard/src/components/orchestration/OrchestrationView.tsx` |
| 3 | 31-agent view | `team.py` STAFF + `agent_registry.py` + `PILOT_AGENTS` | `frontend/team_dashboard.html` (`/app/team`) |
| 4 | Task ledger | DevTask + DevTaskEvent | `admin-dashboard/src/components/ui/DataTable.tsx` |
| 5 | OmniRoute-14 | `omniroute_combo_health` | `frontend/automation.html` (`/app/automation`) |
| 6 | Automation control | `app/api/automation_flags.py` | `admin-dashboard/src/pages/Automations.tsx` |
| 7 | Approvals | `app/dev_control/governor_reviews.py` + `production_approval_required` | `app/dev_control/governor_reviews.py` |
| 8 | Automation health | `app/platform/automation_health.py` wiring_gaps + dead-man | `frontend/automation.html` |
| 9 | Incidents | `data/agent_runtime_dlq.jsonl` + failed DevTaskEvent + Sentry | `app/dev_control/health.py` |
| 10 | Audit & security | DevTaskEvent hash-chain + `app/platform/admin_audit.py` | `app/platform/admin_audit.py` |

**Reusable surface map:** `docs/FINAL_INFORMATION_ARCHITECTURE.md` (2026-07-09 — stale in date, valid as a surface inventory).

### ⛔ BANNED from every tile
- `data/workforce_live_status.json` — self-refuting (`active_workers=0`, `task_execution_verified=false`,
  `evidence_kind=inference_probe_only`), gitignored.
- The `command_center/state.js` tasks array — frozen 08-24/09-02 snapshot.

### 🔴 OWNER-HOME 10 questions → module → source (1:1)

**Updated 2026-09-10 (PHASE 3):** Q4 and Q5 now have a real backing source (`dev_workers` +
`app/platform/worker_health.py`; `app/platform/omniroute_combo_health.py` reading the existing
TEST-PROVEN watchdog). Both are **CODE-PRESENT / TEST-PROVEN but unpopulated** — a source that exists
is not the same as a source that has data, so their tiles must still render the "not instrumented"
default until a supervisor registers / the watchdog runs. **Q8, Q9, Q10 remain NO** — do NOT ship a
tile for them: Q8 needs `DevTaskEvent` (Phase 2, concurrent worker), Q9 needs the 5 owner gates seeded
as DevTask rows (owner-gated DB write), Q10 needs a populated queue.

| Q# | Question | Module | Backing source | HONEST TODAY? | Default shown when data missing |
|---|---|---|---|---|---|
| 1 | Platform healthy? | 8 → 1 | `app/platform/automation_health.py:100-120` dead-man + `GET /health` | **PARTIAL** — services honest; 24×7 worker plane has no row source | "Services N/M green · 24×7 plane not instrumented" |
| 2 | Customers served? | 1 → 6 | `/api/ops/revenue-summary`, `app/billing/subscription.py`, `/app/delivery-command-center` | **PARTIAL** — revenue honest; per-customer delivery SLA has no table | "1 paying customer · delivery SLA unavailable" |
| 3 | Revenue automations working? | 6 → 8 | `automation_health.py:100-120` dead-man + `app/api/automation_flags.py` | **YES** | "N/M jobs green in window" |
| 4 | Bots/agents stuck? | 2 → 9 | **`dev_workers` table + `app/platform/worker_health.py` + `app/models/dev_worker.py`** (2026-09-10) | **CODE-PRESENT / TEST-PROVEN — but NOT yet populated** (0 rows until a supervisor registers) | "0 workers registered · 24×7 plane not instrumented" |
| 5 | Channels failing? | 5 → 9 | **`app/platform/omniroute_combo_health.py`** reads the already-TEST-PROVEN watchdog state file (2026-09-10) | **CODE-PRESENT / TEST-PROVEN — reads real data once the watchdog has run**; today the state file does not exist, so it honestly reports *not instrumented* | "Combo health not instrumented" |
| 6 | Telephony armed/safe? | 8 → 6 | `app/api/admin_ops.py:660` + `app/api/product_consoles.py:1275-1282` `voice_launch.circuit_open()` | **YES** — best-backed | "Armed · kill OFF · caps ok" |
| 7 | Pending approvals? | 7 → 1 | `app/dev_control/governor_reviews.py` + `app/api/dev_tasks.py:490/509/532` + `production_approval_required` (`service.py:23`) | **PARTIAL** — machinery exists but queue is empty/INERT (`AGENT_RUNTIME` unset) | "0 pending (queue not yet fed)" |
| 8 | What changed recently? | 10 → 4 | **NONE for fleet actions** — code/deploy only: `/health.version` + git | **NO** — `DevTaskEvent` does not exist; `app/agents/harness/session.py` chain is harness-scoped | "Deployed `0b848b34` · fleet event log unavailable" |
| 9 | Needs owner attention? | 7 → 9 | `DevTask.blocked_reason` + `production_approval_required`; today **prose only** | **NO** — gates are prose, not rows | "Owner queue unavailable" |
| 10 | Next highest-value action? | 1 → 4 | `app/dev_control/claims.py:98-102` (priority desc, created_at asc) | **NO** — queue unpopulated; today prose | "No ranked queue yet" |

**Smallest additions that would make each honest (one record, not a subsystem):**
- **Q4** → add `heartbeat_ts` + `lease_id` to `dev_workers` *(already specified in §3)*.
- **Q5** → `omniroute_combo_health` *(already specified in §5)*.
- **Q8** → one table `app/models/dev_task_event.py` — nothing smaller is honest. *(Phase 2, in progress.)*
- **Q9** → **CORRECTION to my earlier assumption:** the approvals source is the right *shape* but is
  **inert, not missing** — it needs **seeding, not building**. Seed 5 known gates as DevTask rows:
  C-08 `.venv` rebuild · C-09 deletion confirmation · C-10 `buzz-keycloak` · T-01 Telegram creds ·
  HX-01 hot-queue clearance. ⚠️ Requires DB write → **owner-gated**.
- **Q10** → falls out free once Q9 rows exist and `claim_next` ordering is exposed.

---

## 7. FLAG-ARM ORDER (safe default OFF preserved, each step independently revertible)

1. `AGENT_TASK_LEASE_REAP=1` — safe, terminal-close only, no new dispatch.
2. `DEV_TASK_RECONCILE=1` — startup + beat.
3. `AGENT_RUNTIME=1` — **with `PILOT_AGENTS` untouched (12)**; dispatch begins, bounded.
4. `OMNIROUTE_ENABLED=1` + `OMNIROUTE_API_KEY` + `OMNIROUTE_AGENTS` — **only after the combo-health table exists.**

**Owner-gated only (NOT ours to flip):** `_KNOWN_TOOLS` edit · rollout 12→31 · DSH arm · `.venv` rebuild ·
any commit / push / deploy.

**Kill switches:** `VOICE_LAUNCH_KILL` (voice, existing) + new `DEV_CONTROL_KILL` (orchestration).

**Compliance gates — untouched:** DND fail-closed · TRAI 09:00–19:00 · AI-disclosure · consent ledger ·
cold-WhatsApp ban-safety · manual-UPI payment truth · `VOICE_LAUNCH_KILL` deploy gate · tenant isolation.

### ⚠️ REQUIRES OWNER APPROVAL — trust-boundary change

`app/platform/coordination_hub_auth.py:23` — add `"openclaw", "workbuddy", "codex"` to `_KNOWN_TOOLS`.
Without it, headless bots can never reach `buzzlock_enrolled: true`. Each new tool also needs
`_configured_secret()` set, otherwise it fails closed as `secret_unconfigured` (`:173`).

---

## 8. NEXT FILES TO TOUCH (Phase 2)

1. `app/models/dev_task.py` — add `parent_id`, `next_eligible_at` columns.
2. `app/dev_control/reconcile.py` — startup/beat-safe `reconcile_leases()` + exponential backoff on requeue.
3. `app/models/dev_task_event.py` — **NEW**, hash-chained audit model.
4. *(blocked on owner)* `app/platform/coordination_hub_auth.py`.

---

## 8A. PHASE 3 — HEADLESS MIGRATION

### 🚨 CRITICAL: OmniRoute CANNOT be the 24×7 central gateway today

`deploy/compose/docker-compose.omniroute.yml:21-22` — *"OmniRoute must stay absent from production per
ADR-111"*. Confirmed by `memory/decisions.md:2855` and `progress.md:291` (ADR-189): it is a **local-only
desktop gateway** on the owner's Windows box (Docker Desktop, `127.0.0.1:20128`).

This **directly conflicts with the owner's mandated architecture** ("CENTRAL OMNIROUTE GATEWAY" sitting
between 31 agents and 14 combos). Resolution adopted as the safe default:

> **OmniRoute = an OPTIMIZATION LANE, NOT a 24×7 DEPENDENCY.** All 24×7 correctness must hold with it
> **absent**. `app/voice_agent/free_ai.py` free-stack remains the 24×7 path; combo routing is best-effort.
> `decisions.md:2855` already states the safe position: *"Graceful degrade → `free_ai.py` fallback; no
> customer/revenue path depends on OmniRoute."*

**Moving OmniRoute to the VPS = OWNER GATE** (overrides ADR-111 / ADR-189). If it is made critical while
still living on the desktop host, "24×7" is false and the migration silently re-creates a desktop dependency.

**Spine decision:** reuse the existing Celery `worker` + `scheduler` services (`docker-compose.vps.yml:317,539`)
for supervisor bots. They already satisfy every 24×7 requirement — `restart: unless-stopped`,
`json-file 50m×5` logging, healthcheck, resource limits, graceful shutdown, no terminal windows.
A new container would duplicate all of it. Add a dedicated `bot-supervisor` service later **only if Celery
contention is measured**.

### Headless replacement design (6 desktop dependencies)

| # | Mechanism | Where | Heartbeat | Rollback | Owner gate? |
|---|---|---|---|---|---|
| 1 `_KNOWN_TOOLS` | config change + Celery-supervised enrolment task | `app/platform/coordination_hub_auth.py:23` (+`_configured_secret()` `:173`) | `dev_workers.heartbeat_ts` via `POST /api/dev_tasks/{id}/heartbeat` (`dev_tasks.py:265`) | revert tuple → fail-closed `tool_unknown`; `DEV_CONTROL_KILL=1` | **YES** (trust boundary) |
| 2 openclaw + verdant `project_only` | config change | `config/desktop_apps/combo_distribution.yaml:72,82` → `worker_scope: vps_and_project` | n/a | `git revert` the YAML | YAML: **NO** · OmniRoute→VPS: **YES** |
| 3 Buzz / Comb `BUZZ_AUTH_TAG` | **ACCEPT OWNER-MANUAL-ONLY — out of 24×7 scope** | `AGENTS.md:122` | — | — | No (explicit decision, below) |
| 4 Hermes sole Telegram `getUpdates` | new scheduled ingress task (**no code exists today**; `WORKER_ROSTER.md:111` grep = 0) | NEW `app/platform/telegram_ingress.py` + Celery beat | `dev_workers` + `DevTaskEvent` | `TELEGRAM_INGRESS_ENABLED=0` → fail-closed, Hermes can re-poll | Code: **NO** · Creds: **YES** (T-01) |
| 5 Hermes GUI child-backend exits | **ACCEPT OWNER-MANUAL-ONLY** (cockpit) | `scripts/start-hermes-omniroute.ps1` | advisory | restart script | No |
| 6 `.venv` missing | **ACCEPT AS LOCAL-ONLY — DOES NOT BLOCK PROD** | `mcp` is a container (`docker-compose.vps.yml:121-174`) | — | — | **YES** (C-08) |

**Accepted as owner-manual-only — decisions, not defaults:**
- **#3 Buzz** — no proven value (ADR-167: ₹0 marginal, preview-only, Lane C UNVERIFIED); no CLI mint path
  exists (cred store / relay / port all checked). Building a headless replacement for an unproven lane is waste.
- **#5 Hermes** — cockpit by mandate; not on the orchestration path.
- **#6 `.venv`** — blocks *local pytest only*; prod MCP is containerised. Route local proof to Docker/prod
  probes rather than blocking the programme.

### Decommission proof checklist — 🔴 only 3 of 13 provable locally

| Proof | Command / endpoint | Local? |
|---|---|---|
| a CLI/API worker exists | `docker compose -f docker-compose.vps.yml ps worker` | Docker only |
| b starts without GUI | `… up -d worker` + `logs worker` | **DEPLOY** |
| c survives terminal close | container still `Up` after shell exit | **DEPLOY** |
| d restart policy | `… inspect worker --format '{{.HostConfig.RestartPolicy.Name}}'` = `unless-stopped` | **DEPLOY** |
| e heartbeat visible | `GET /api/dev_tasks/status` (`dev_tasks.py:348`) + `dev_workers.heartbeat_ts` | **DEPLOY** |
| f task claim works | `POST /api/dev_tasks/{id}/claim` (`:238`) / `claim-next` (`:222`) | **DEPLOY** |
| g retry works | expire lease → `POST /api/dev_tasks/reconcile` (`:392`) → requeued, `retry_count+1` | **DEPLOY** |
| h bot/agent assignment visible | registry + `PILOT_AGENTS` render | static ✅ |
| i OmniRoute works | `GET 127.0.0.1:20128/v1/models` = 200 | local Docker ✅ |
| j result returns to ledger | `POST /api/dev_tasks/{id}/report` (`:291`) → `worker_report` persisted | **DEPLOY** |
| k dashboard displays it | OWNER-HOME tile renders from DevTask | **DEPLOY** |
| l logs / metrics | `… logs worker`; `automation_health.py:100-120` dead-man | **DEPLOY** |
| rollback | `DEV_CONTROL_KILL=1` + flag-only revert | config ✅ |

> **10 of 13 proofs require a deployed environment.** No desktop responsibility may be marked MIGRATED on
> local evidence alone.

### Unblocked now (no owner approval) vs blocked

**START NOW:** (1) DevTask schema + `reconcile.py` backoff/startup + `DevTaskEvent` · (2) `dev_workers` table ·
(3) `omniroute_combo_health` + `omniroute_aliases.py` · (4) `combo_distribution.yaml` re-scope (YAML only) ·
(5) Telegram ingress behind `TELEGRAM_INGRESS_ENABLED=0` · (6) seed the 5 owner gates as DevTask rows (Q9 fix).

**BLOCKED ON OWNER:** `_KNOWN_TOOLS` (#1) · rollout 12→31 · OmniRoute→VPS · `.venv` (C-08) · Telegram creds.

---

## 9. STATUS

- [x] PHASE 0 — baseline (QA-verified)
- [x] PHASE 0b — feature inventory + no-loss matrix + diffable snapshots
- [x] PHASE 1 — architecture freeze (this record)
- [ ] OWNER-HOME 10-question → module 1:1 mapping
- [ ] PHASE 2 — control plane (DevTask gap closure)
- [ ] PHASE 3 — headless migration
- [ ] PHASE 4 — Owner Command Center
- [ ] PHASE 5 — automation E2E
- [ ] PHASE 6 — harden
- [ ] PHASE 7 — handoff

---

## 12. TELEPHONY PROVIDER DIAL INVARIANT (owner-approved 2026-09-10)

**Approved by:** owner (Ratanshila) via Nova's coordinator authority — this is the invariant the
architect flagged as needing an owner decision. Recorded so it is no longer a verbal convention.

> **No code path may dial without a valid Dial Ticket, and no provider client may expose a dial
> method that skips one.**

A Dial Ticket is produced by the single gated choke point and carries:
`to` · resolved `client_id` (billable identity) · `CallType` · `campaign_id` · `lead_id` ·
`idempotency_key` · `issued_at` / `expires_at`.

### Rules (all four are binding)
1. **Single choke point.** Every dial (Vobiz, Tata SmartFlo, SIP, future providers) passes through
   one gate that runs, in order and **fail-closed**:
   `dial_gate.check()` → `ComplianceGate.check()` (DND fail-closed, TRAI 09:00–21:00 clamped to
   09:00–19:00 for promo, opt-out/suppression, consent ledger) → `admin_kill_engaged()`
   (`app/telephony/voice_launch.py:380`).
2. **Provider clients accept a ticket, not a phone number.** `VobizClient.place_call`,
   `TataSmartfloClient.place_call` and `SIPHandler.place_call` must not be reachable with a bare
   `to=` in production. `enforce_compliance=True` is the default and must not be flipped off by a
   production caller.
3. **Billing identity is mandatory.** A call with no resolvable `client_id`/`client_name` is
   unbilled revenue. It must be **logged at WARNING**, never silently dropped
   (`app/billing/usage.py:185` returns `False` with no log — the caller must therefore log).
4. **No second orchestrator, no second gate.** Do not add a parallel dial path. Adding a provider
   means implementing the client, not re-implementing compliance.

### Why this exists (evidence, not theory)
Before 2026-09-10 `TataSmartfloClient.place_call` had **zero** gates — calling it directly could
cold-dial any number. `POST /api/telephony/smartflo/test-call` called it directly. Both are now
gated. Separately, `app/telephony/smartflo_webhooks.py:_meter_call` called
`meter_call_completion(client_id=, call_duration_s=, metadata=)` against the real signature
`meter_call_completion(call_id, *, client_id, client_name, duration_seconds, campaign_id)` —
`call_id` is a required positional, so **every** metering call raised `TypeError` and was swallowed
at `logger.debug`. Net effect: no metered SmartFlo minute was ever billed, silently.

### Rollout (deliberately staged — do not skip)
1. Ship gated path **shadow/warn-only** on SmartFlo: log `would_block=<reason>` without refusing,
   watch for false positives on real traffic.
2. Then arm `TATA_SMARTFLO_ENABLED=1` hard-enforcement.
3. Only then consider failover Vobiz → SmartFlo. **Never** make an ungated provider a failover
   target — a provider outage would silently become a compliance outage.
