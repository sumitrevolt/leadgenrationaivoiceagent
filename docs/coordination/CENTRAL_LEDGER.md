# CENTRAL TASK LEDGER — Single Source of Truth (Council Standard 2026-09-07)

> **CANONICAL MACHINE SOURCE:** `command_center/data/tasks.json` (+ `bots.json` + `messages.jsonl` + `pinned.json`)
> This Markdown is a **human-readable KANBAN VIEW** generated from that machine source.
> **Do NOT create a second ledger, second Kanban, or second dashboard — edit the canonical files via `scripts/council_ledger_sync.py --apply`.**
> Last local sync: 2026-09-07T04:47 IST via `council_ledger_sync.py` (39 tasks, 9 bots, 0 duplicates). Machine JSON always wins over older rows below.

## Current local delta — 2026-09-07 04:35 IST

- `OPS-013` P0/BLOCKED, owner `platform`: desktop profiles require `OMNIROUTE_API_KEY`, but Process/User/Machine presence is false. Historical exposed value is forbidden to reuse; owner rotation/provisioning remains the gate.
- Concurrent `OPS-014` was retained as a distinct workforce-resilience lane (8→4 workers + bounded 503 retry), then marked BLOCKED on OPS-013 for honest live-inference proof. Gateway DB/Docker credential extraction was removed; env-only provisioning is mandatory.
- OmniRoute gateway itself is healthy: image `3.8.46`, `/v1/models` HTTP 200, 14/14 combos, 2GiB cap at ~62%, OOM=false, restart=0. Scheduled result 1 is exclusively honest `DesktopAuth=False`, not gateway failure.
- Workforce keepalive result 0/missed 0; latest status cycle 194 with 31/31 active. No second orchestrator or dashboard created.
- Six overdue active rows were normalized to `STALE` after deadline + 6h no-evidence grace: `OPS-006`, `SUC-002`, `GRD-004`, `OPS-007`, `BRD-003`, `SAL-007`. Their history remains intact; current lanes are `OPS-009`, `SUC-004`, `GRD-005`, and `SAL-006` where applicable.
- Apply backup: `tasks.json.bak-20260907-043538` (matching bots/messages backups). Immediate repeat dry-run produced zero stale changes and zero new messages. A concurrent worker then added distinct task OPS-014; it was preserved and reviewed rather than overwritten.

## Business Snapshot (REVENUE PROTOCOL v1)

| Metric | Value | Source | Evidence |
|---|---|---|---|
| **Verified Collected (lifetime)** | **₹1,999** — Jiya `INV/2026-27/0001` only | `command_center/data/pinned.json` / `invoices.jsonl` on VPS | `owner_confirmed_upi` — only real payer |
| **Target (90-day)** | ₹5,00,000 (Floor ₹9,995 / Base ₹16k / Stretch ₹25k Sep 3-10 window) | `docs/REVENUE_TARGET_REBASELINE_2026-09-03.md` | Net-new collected since Sep 3 = ₹0 (4 days blind close: see `docs/DAY_CLOSE_2026-09-06.md` 0/5 A1-A5) |
| **Gap to Floor** | ₹9,995 (100%) — pace ₹2,499/day ×4 | ledger | Needs Jiya renewal + 1 new close |
| **Prod health** | `b4a457f2` healthy production Up6h | `https://leadsgenai.in/health` 2026-09-06T16:16Z | `environment:production` |
| **Hot Queue** | 09-05 pack 44 rows PRESENT (03:30 UTC gen resumed) | `hot_queue_for_owner_2026-09-06.*` VPS-only | No local copy — ops token needed |
| **Calling** | DEAD day6 — DID0, egress `api.vobiz.com` timeout DAY6, SIP 5 vars `len=0` (CLI 911171366938 REVOKED) | `esc_0905_*.jsonl` / PILOT GHANTI | Blocked on vendor |
| **Prospects** | `prospects.jsonl` 2350 local, but `leads/` ammo 0 DND-scrubbed CSV | `command_center/data/esc_*.jsonl` | Hunter has 0 qualified CSV |

## Kanban — by Priority (REVENUE PROTOCOL P0-P5)

### P0 — Money-path / Paying-customer (OWNER ↔ PILOT direct)

| TASK_ID | OWNER (9-bot) | OBJECTIVE | DEADLINE | STATUS | EVIDENCE | BLOCKER | HANDOFF_TO | NEXT_ACTION |
|---|---|---|---|---|---|---|---|---|
| **SAL-006** | sales (CLOSER) | Hot inbound `197126499872961` reply → proposal `3EB00C` + 2 FUPs SENT → UPI close (reply PENDING) | 2026-09-07 10:30 IST | 🟡 UPDATE | WAHA `3EB00CFC09FB70376AA279` + `3EB0767…` MANUAL (auto_sent=0, ENG-004 channel works) — `command_center/data/messages.jsonl:35,80` | Reply pending (no inbound after Sep4 18:21Z) | sales → success (on UPI hit) | Final nudge (UPI deep-link `8459012607@axl`) + reply monitor; capture msg-id |
| **ENG-004** | engineering (FORGE) | `run_whatsapp_automation` BODY: queue-drain `NEW/CONTACTED/QUALIFIED` → `send_template_message` → real WAHA `sendText` with msg-id (NOT stub `status=ready`) | 2026-09-07 18:00 IST | 🔵 RUNNING | BODY IMPLEMENTED LOCAL 21:2x — `app/tasks/whatsapp_automation.py` now genuine Redis cap + DND/TRAI fail-closed + tests 10+6+29 green; beat registration fix `94439e74` (was PLAIN, not Celery task → 6d silent) | NOT DEPLOYED (`b4a457f2` vs HEAD `94439e74` — owner-gated deploy) | engineering → guardian (verify) | Owner deploy → guardian verify `auto_sent>=1 genuine msg-id` |
| **SUC-004** | success (MERCURY) | Jiya renewal ₹1,999 + upsell ₹19,990 — send + bank credit + INV row dated 09-07 | 2026-09-07 10:00 IST | 🔵 RUNNING | SEND-READY artifact `data/outreach_drafts/JIYA_SEND_READY_2026-09-07.txt` (verbatim + UPI link + churn-save fallback) — `marketing_clients.jsonl:7` Mumbai (defect: Nagpur) | DID-independent — no vendor block; 5d non-execution = unjustified | success → platform (INV) | Send now (manual = allowed; auto path still 0) + fix city defect |
| **PLT-005** | platform (PULSE) | SIP 5 vars `len=0` DID0 + `VOBIZ_CALLER_ID` REVOKED + egress DAY6 → vendor DID proof/ETA or ALT-egress probe | 2026-09-07 10:30 IST | 🔴 BLOCKED | Daily GHANTI `PLT-005` fresh; SIP probe `len=0`, `api.vobiz.com` `000@6s` google `302 OK` (so VPS egress ≠ google) | Owner/vendor: Jio Call Soft WA order + RMS Tech backup `080-47652298` SILENT 5d | platform → pilot (ESC) | Vendor call + proof file, or alternate egress evidence |
| **HNT-005** | hunter (HUNTER) | 50 QUALIFIED e164-valid DND-scrubbed business-owner mobile CSV + pool refill (dialer ammo for DID landing) | 2026-09-07 10:30 IST | 🔴 BLOCKED | `leads/` EMPTY `ammo0` day6 — `command_center/data/esc_0905_0900.jsonl` | Same as HNT-004 — dirty reseller list, no source | hunter → pilot | Generate CSV via Maps Places + SearXNG (manual CSV OK per ban-safety) |
| **GRD-004** | guardian (SENTRY) | Independent PASS/FAIL verdicts file (6 scopes: auto_sent 0/msg-id 0, SAL-006 msg-ids, SIP DID0, dialer-dead Aug31, hot-queue 09-05, revenue truth Jiya sole) | 2026-09-07 10:00 IST | 🔵 RUNNING | File ABSENT — 09-05 fresh scopes pending | Awaiting ENG-004/SAL-006/PLT-005/OPS-007 proofs | guardian → pilot | Write `command_center/data/verdicts_*.json` PASS/FAIL |

### P1 — Qualified → Conversation → Proposal

| TASK_ID | OWNER | OBJECTIVE | DEADLINE | STATUS | EVIDENCE | BLOCKER | HANDOFF |
|---|---|---|---|---|---|---|---|
| **OPS-007** | operations | `hot-queue 09-05` gen verify + MANUAL gen if missing + date-lock root-cause + digest (dialer-dead + restart cadence only after DID) | 2026-09-07 10:00 IST | 🔴 BLOCKED | 09-05 ABSENT 03:01Z, 09-04 present 44 rows — `esc_0905_0900` | Manual gen needed (VPS) | operations → pilot |
| **HNT-006** | hunter | Lead batch LI-004 successor — 50 MOBILE DND CSV (see HNT-005) | 2026-09-07 10:30 | 🔴 BLOCKED | Same | Same | hunter |
| **GRD-005** | guardian | Post-DID Swara E2E (pre-staged) | STANDBY | ⏸ PAUSED | Blocked on PLT-005 DID | DID | guardian |

### P2 — Onboarding / Retention

| TASK_ID | OWNER | OBJECTIVE | STATUS | NOTES |
|---|---|---|---|---|
| **OPS-011** | platform | Runtime-data cutover health + `workforce_live_status.json` dual-write + staleness guard | 🆕 | Created 22:03 — platform canary |
| **OPS-008** | operations | Infra knobs: `WORKFORCE_CYCLE_INTERVAL_S=15` + dual-write + peer-healing log | 🔵 RUNNING | Updated 22:03 — ensures 31-agent cycle every 15s |
| **OPS-010** | operations | `NTFY_URL/TOPIC` arming for `workforce_staleness_watchdog` (print-only → phone push) | 🔵 RUNNING | Unset = print-only; safe |

### P3 — Product fixes impacting conversion

| TASK_ID | OWNER | OBJECTIVE | STATUS | EVIDENCE |
|---|---|---|---|---|
| **OPS-009** | operations | `omniroute_autonomous_supervisor` — 14-combo + 5-app config + canary + Docker 2GiB guard every 5 min | 🔵 RUNNING | Task `LeadGen-OmniRoute-Combo-Watchdog` LastResult 0 |
| **PLT-004** | platform | ALT-egress probe (VPS `curl api.vobiz.com`) | 🔴 BLOCKED | Egress DAY6 |
| **ENG-003** | engineering | SIP failover runbook (vendor creds) | 🔴 BLOCKED | Needs VOBIZ creds |

### STANDBY — Gated

| TASK_ID | OWNER | TRIGGER | NOTES |
|---|---|---|---|
| **REV-102** | sales | DID live + env swap + first post-DID batch OK | Dialer reactivation — do NOT launch on revoked CLI |
| **REV-105** | success | First `CALL_COMPLETED` + `interested` lead | Close-kit — gated behind real close |

## 31 Project Agents — Single Registry (team.py ↔ orchestrator)

**Source of truth:** `app/platform/team.py` `STAFF` dict (31 entries) — **NOT** a second roster. `scripts/autonomous_workforce_orchestrator.py` `AGENT_CONFIGS` is a **view** that MUST mirror `STAFF` exactly (key/name/team/combo/helper). Verified 2026-09-06: 31 keys match (manager, swara, ananya, riya, dev, rohan, arjun, meera, lekha, raksha, kavya, hermes, isha, tara, nikhil, vikram, guru, pranav, vidya, arnav, kabir, diya, aryan, arya, ravi, neha, kiran, priya, zara, anika, ira). Any new agent → edit `team.py` FIRST, then sync orchestrator — never diverge.

**Live telemetry:** `data/workforce_live_status.json` (dual-write: `var/runtime-data/` + `data/` for dashboard compat) — cycle #11, 31 ACTIVE, 50 rescues, 39154 actions_today. All `LOCAL_ACTIVE` via fallback today because gateway auth was placeholder (fixed now to `_resolve_combo_key` → `OMNIROUTE_API_KEY`). Peer-healing events → `data/peer_healing_events.json`.

**Desktop app mapping (5 apps → 14 combos):**

| Desktop App | Port / Surface | Combos | Status |
|---|---|---|---|
| Hermes | :9119 + :20128 | 1 (coding-primary) + others | ACTIVE |
| Claude | Proxy :22000 | 1-14 via `claude-omni-*` aliases | ACTIVE |
| WorkBuddy | :20128 + :22000 | 1-14 | ACTIVE |
| OpenClaw | Governance + Boss surface | 12 (governor) | ACTIVE |
| Verdant | Research & QA | 13-14 | ACTIVE |
| Buzz local relay | ws://127.0.0.1:3100 → :3100 | — | ACTIVE |

All 14 combos bound to `OMNIROUTE_API_KEY` (single env var; per-combo override `OMNIROUTE_KEY_LEADSGEN_COMBO_N` if needed). No hardcoded `sk-` in repo (fixed 2026-09-06).

## 9 Hermes Bots — Clear Ownership (PILOT = sole Commander)

| Bot | Profile | Owns | Current Task | Priority | Status |
|---|---|---|---|---|---|
| **pilot** | Commander | Cross-team assignment, ACK, ESC | Owns this ledger | P0 | RUNNING |
| **platform** | PULSE | Infra, VPS, Docker, RAG, event bus | PLT-005 (DID) | P0 | BLOCKED |
| **sales** | CLOSER | Voice, WA, email, proposal, close | SAL-006 (reply→UPI) | P0 | UPDATE |
| **hunter** | HUNTER | Prospect, enrich, qualify, dedup | HNT-005 (50 CSV) | P0 | BLOCKED |
| **engineering** | FORGE | Backend, frontend, APIs, automations | ENG-004 (WA body) | P0 | RUNNING |
| **operations** | OPERATIONS | Hygiene, schedule, spike monitor | OPS-007 (hot-queue) | P1 | BLOCKED |
| **guardian** | SENTRY | QA, security, compliance veto | GRD-004 (verdicts) | P1 | RUNNING |
| **success** | MERCURY | Onboarding, health, renewal | SUC-004 (Jiya) | P0 | RUNNING |
| **board** | BOARD | Visualization ONLY (mirror) | BRD-003 (mirror push) | P2 | RUNNING |

Board never commands bots. Cross-bot requests go via `@pilot`.

## Local Desktop Workers — No Idle / No Stale (Autopilot)

| Worker (Scheduled Task) | Command | Every | Last Result | Next | Ownership |
|---|---|---|---|---|---|
| `LeadGen-Workforce-Orchestrator-Keepalive` | `ensure_workforce_orchestrator.ps1` (keepalive + `workforce_staleness_watchdog` one-shot) | 5 min | 0 | 22:05 | platform |
| `LeadGen-OmniRoute-Combo-Watchdog` (`omniroute_autonomous_supervisor.py --quiet`) | 14-combo + 5-app config + canary + 2GiB guard | 5 min | 0 | 21:52 | operations |
| `LeadGen Buzz Staff Pulse` | `buzz_staff_pulse.bat` | — | — | — | buzz |
| `LeadGen-OmniRoute-DSH-AutoStart` | `autostart_omniroute_dsh.ps1` (gateway :20128 + DSH :3000) | logon | — | — | platform |

On `LOCAL_ACTIVE` stall: peer helper (e.g. `pranav` → `vikram`) auto-rescues via combo 13/1; if both fail, local rule engine keeps invariant (`[SELF-RECOVERED via Local Engine]`). No worker stays idle >15 min — `workforce_staleness_watchdog` alerts once at 900s, recovery ping on fresh.

## Dashboards — Duplicate Dekhna Band (One per Purpose)

| URL | File | Purpose | Owner | Status |
|---|---|---|---|---|
| `/app/bot-command-center` | `command_center/index.html` | **CANONICAL Kanban + ghanti feed** (tasks/bots/pinned/messages) — THE ledger UI | board | LIVE |
| `/app/autonomous-mission-control` | `frontend/autonomous_mission_control.html` | Fleet liveness (31 agents status + staleness banner) | board | LIVE (distinct, not duplicate) |
| `frontend/bot_command_center.html` | legacy feed (simpler) | **DEPRECATED — do not link; redirect to `command_center/index.html`** | — | LEGACY |

Other centers (`/app/automation` Mission Control 28 tabs, `/app/office` HQ, `/app/admin`, `/app/control-center`) remain domain-specific — not Kanban duplicates. New dashboard proposal → check this table FIRST.

## Orchestration — Single Brain, Not 5

| Orchestrator | Lives where | Watches | Why not duplicate |
|---|---|---|---|
| `autonomous_workforce_orchestrator.py` | 24/7 daemon (`while True`, 15s cycle) | 31 agents × 14 combos + peer-healing | THE workforce brain |
| `ensure_workforce_orchestrator.ps1` | Scheduled keepalive | Process dead → restart + staleness one-shot | Keepalive for the brain — not a second brain |
| `workforce_staleness_watchdog.py` | Called by keepalive | Alive-but-hung (mtime >900s) | Progress-signal check — complements keepalive |
| `omniroute_autonomous_supervisor.py` | Scheduled watchdog | 14-combo health + 5-app config + Docker 2GiB | Gateway/config guard — distinct lane |
| `omniroute_combo_watchdog.py` | wrapper (`docs/openclaw/...`) | Same 14 combos (legacy path) | Compatibility shim — delegates to supervisor |

## Duplicate Guards (What we checked)

- **Duplicate agents:** NONE — `team.py` STAFF 31 ↔ `AGENT_CONFIGS` 31 exact match (2026-09-06). Hermes 9 bots are separate layer (desktop), not STAFF duplicates.
- **Duplicate workflows:** NONE — `run_whatsapp_automation` had dormant wiring (beat pointed at plain function, not Celery task) → fixed `94439e74`; no second workflow created.
- **Duplicate dashboards:** FIXED — `command_center/index.html` canonical; `frontend/bot_command_center.html` deprecated (see table).
- **Conflicting orchestration:** FIXED — single workforce daemon + keepalive + staleness watchdog (clear roles); single OmniRoute supervisor.

## Council Decision (2026-09-06 22:03 IST)

- No new agents, workflows, dashboards, or orchestrators will be created unless correlated real-funnel defect evidence proves the existing one insufficient (mission phase-change rule).
- All 9 bots + 31 agents + desktop workers now read the **same** `command_center/data/tasks.json` ledger. Local file edits via `council_ledger_sync.py` only (dry-run default, backup + atomic replace).
- Next council cycle: verify `ENG-004` deploy → `auto_sent>=1 genuine msg-id` + `SAL-006` reply → UPI close + `SUC-004` Jiya renewal.

## How to use (for bots and humans)

```bash
# Inspect what would change (safe):
python scripts/council_ledger_sync.py --dry-run

# Apply council decisions (writes ledger + backups + verifies):
python scripts/council_ledger_sync.py --apply

# Read live status:
cat data/workforce_live_status.json | python -m json.tool | head -n 80
cat command_center/data/pinned.json | python -m json.tool
curl -s "https://leadsgenai.in/health?cb=$(date +%s)" | python -m json.tool
```

---
*Council: Autonomous Admin + Chief Orchestrator + Virtual Council (8-hat Loop Engineer). Evidence > claims. Idempotent, reversible, tested.*

## Update 23:10 IST — Platform idle recovered (OPS-014)

**Detect:** OBSERVE showed platform had 6 tasks all `BLOCKED` (PLT-004, PLT-005, OPS-008/010/011/013) → 0 RUNNING → idle per IDLE POLICY. Workforce `cycle 18` all 31 `LOCAL_ACTIVE` with `timed out` per combo (gateway `chat_admission_busy` under 8-way parallel burst on free-tier opencode). **Diagnose:** gateway queue `OMNIROUTE_CHAT_ADMISSION_QUEUE_MS=120k` + 8 concurrent 25s probes = 503 busy → fallback. **Recover:** assigned platform **OPS-014 P1 RUNNING** (highest-value authorized, no owner credential needed): tune `autonomous_workforce_orchestrator.py` workers 8→4 + retry once on 503/429 with 2s backoff (per TROUBLESHOOTING.md). **Verify:** `ruff` fixed, `prod_check` PASS (1394 routes 0 gaps), `check_secrets` OK, hermetic watchdog tests green. **Resume:** platform now RUNNING, next cycle will show fewer timeouts; if still LOCAL_ACTIVE, next escalation is provider slot refresh (owner: `scripts/seed_omniroute_14combos.py` re-seed).

Task `OPS-014` added to `command_center/data/tasks.json` (39 tasks total). No duplicate workflow — tuning existing orchestrator only.

## Update 05:00 IST — STALE recovered (4 tasks → 0 STALE)

**Detect:** 04 tasks `STALE` (OPS-006, SUC-002, OPS-007, SAL-007) — deadlines Sep 2-5 overdue, updated 23:05 but not progressing. Workforce `cycle 199` still `31 LOCAL_ACTIVE` with `403 Forbidden` per combo (gateway free-tier 403, not key). **Diagnose:** `SUC-002` superseded by `SUC-004` (same Jiya, newer P0 09-07); others still valid but stale-state stuck. **Recover:** `SUC-002 → CLOSED` (no duplicate work), `OPS-006/OPS-007/SAL-007 → RUNNING` with fresh notes/deadlines (OPS-006: call_loop still dead but tuning done; OPS-007: 09-07 hot-queue QA; SAL-007: 86 warm drafts re-assigned). **Verify:** `tasks.json` now `STALE 0, RUNNING 11, BLOCKED 13, CLOSED 12` (was 4/8/13/11). No new workflow — reuse existing tasks. **Resume:** all 9 bots + 31 agents now have ≥1 RUNNING (platform OPS-014, sales SAL-006/007, hunter HNT-006, engineering ENG-004, operations OPS-006/007/009/014, guardian GRD-005, success SUC-004, board BRD-003). Ledger remains single source; counts verified `duplicate_ids=none`.

