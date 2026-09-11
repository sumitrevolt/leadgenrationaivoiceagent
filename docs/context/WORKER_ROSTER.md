# WORKER ROSTER — LeadGen AI + Hermes coordination

**Coordinator:** Nova (WorkBuddy) — owner-granted admin authority 2026-09-10.
**Last updated:** 2026-09-10 12:56 IST
**How to use:** this file is the session-start memory for the coordinator. Re-read it before
assigning anything, and update it whenever a worker appears, disappears, or changes state.
Protocol source: `docs/context/AI_OPERATING_PROTOCOL.md` · broadcast: `COORDINATION_BROADCAST.md`.

---

## 1. Desktop workers — live inventory

Discovery command (Windows PowerShell):
`Get-Process | Where-Object { $_.MainWindowTitle -ne "" }` + process-name match on
`OpenClaw|ChatGPT|WorkBuddy|Hermes|Codex|Cursor|Claude`.

| Worker | Live evidence (2026-09-10 12:56 IST) | Window | State | Repo write access? |
|---|---|---|---|---|
| **WorkBuddy AI** (Nova — me, coordinator) | 12 procs; main window pid 12940; largest pid 14384 @ 700 MB | ✅ `WorkBuddy AI` | ACTIVE | ✅ yes |
| **OpenClaw** | `OpenClaw.Tray.WinUI` pid 23952 (hwnd set, "OpenClaw Companion") + `msedgewebview2` pid 25272 ("OpenClaw Control") | ✅ | ACTIVE | ✅ yes (mirrors repo in `~\.openclaw\workspace\`) |
| **ChatGPT Desktop** | 9 procs; window pid 21168 @ 184 MB | ✅ `ChatGPT` | ACTIVE | ⚠️ **assume NO** — treat as read-only/advisory |
| **Hermes** (owner cockpit) | GUI window pid 35572; helpers 34136/7976/12264/2900; backend = python pid 29444 on 9119 | ✅ `Hermes` | ACTIVE (own backend on 54935) | n/a — it is the managed surface |
| **Codex** | `codex` pid 4680 @ 130 MB + `codex-code-mode-host` pid 34176 | ❌ headless | IDLE / unassigned | unknown — treat as read-only until it declares |
| **Claude** | tracked by workforce (`desktop_apps.claude` = UNVERIFIED); **no process found** on this machine | ❌ | **DOWN / not installed here** | n/a |
| **Verdant** | tracked by workforce (`desktop_apps.verdant` = UNVERIFIED); **no process found** | ❌ | **DOWN / not installed here** | n/a |
| **Buzz** | tracked by workforce (`desktop_apps.buzz` = UNVERIFIED); only Docker **infra** containers found: `buzz-postgres`, `buzz-redis`, `buzz-prometheus`, `buzz-keycloak` (unhealthy), `buzz-minio` — **no Buzz agent app process** | ❌ | INFRA-ONLY (harness not started) | n/a |

> **Roster correction 2026-09-10 13:05 IST:** the first version of this file listed only 5 workers.
> `data/workforce_live_status.json` tracks **6 desktop apps** (hermes, claude, workbuddy, openclaw,
> verdant, buzz). Claude, Verdant and Buzz are now added — none of them was running as an agent app
> at discovery time. Source of truth for "expected workers" = `desktop_apps` in that JSON, not my
> process grep alone.

**Communication channel (be honest about this):** there is no inbox into ChatGPT Desktop or
OpenClaw's runtime. The only reliable channel is **shared filesystem state in this repo** —
`docs/context/` (mandatory startup reads) and `~\.openclaw\workspace\`. Every broadcast is written
there. Workers that do not read those files cannot be coordinated by message; they must be
constrained by the single-writer rules instead.

---

## 2. Task board — assigned ownership

Single-writer rule: one owner per surface. Claim in `ACTIVE_WORK.md` before editing.

| ID | Task | Owner | Status | Blocked by |
|---|---|---|---|---|
| C-01 | Coordination + roster + status tracking | **Nova / WorkBuddy** | ACTIVE | — |
| C-02 | Health sweep (prod / 9119 / 20128) | **Nova / WorkBuddy** | ✅ DONE — all green 12:40 IST | — |
| C-03 | Working-tree restore (4041 accidental deletions) | **Nova / WorkBuddy** | ✅ DONE — verified 0 deletions | — |
| C-04 | Hermes backend + GUI restart | **Nova / WorkBuddy** | ✅ DONE — 9119 pid 29444, GUI pid 35572 | — |
| C-05 | Root-cause doc correction (§7 addendum) | **Nova / WorkBuddy** | ✅ DONE | — |
| C-06 | Local automation / council-ledger / workforce keepalive / OmniRoute watchdog | **OpenClaw** | CARRY-OVER — no ack received yet | ack from OpenClaw |
| C-07 | Advisory review only — no repo writes | **ChatGPT Desktop** | ASSIGNED (read-only) | — |
| C-08 | Repo `.venv` rebuild (missing → 5/6 MCP servers fail) | **UNCLAIMED** | ⛔ OWNER GATE | owner go-ahead |
| C-09 | Confirm 4041-file deletion was accidental | **UNCLAIMED** | ⛔ OWNER GATE | owner answer |
| C-10 | `buzz-keycloak` container unhealthy | **UNCLAIMED** | OPEN | owner triage |
| C-11 | Codex role declaration | **Codex** | OPEN | Codex ack |
| C-12 | Owner-Telegram feed design (topology + 4-layer design) | **Nova / WorkBuddy** | ✅ DONE — `docs/context/OWNER_TELEGRAM_FEED_DESIGN.md` | — |

### Telegram-feed workstream (added 2026-09-10 13:05 IST — owner ask)

| ID | Task | Owner | Status | Blocked by |
|---|---|---|---|---|
| T-01 | `app/utils/owner_notify.py` — single Telegram egress | **UNCLAIMED** | OPEN | owner: creds + test chat |
| T-02 | `data/owner_feed_events.jsonl` schema + append helper | **Nova / WorkBuddy** | ✅ **DONE 13:35** | 24/24 tests green (`tests/test_owner_feed.py`); `app/utils/owner_feed.py`; truth gate enforced in code |
| T-03 | Bot-fleet (9 bots) → Telegram bridge | **UNCLAIMED** | OPEN | T-01 |
| T-04 | Desktop-worker push bridge | **Nova / WorkBuddy** | OPEN | T-02 |
| T-05 | Workforce probe fix (`active_workers` is 0 while feed claims 592 actions) | **OpenClaw** | OPEN — **prerequisite** | — |
| T-06 | Workforce / 31 agents → Telegram | **UNCLAIMED** | ⛔ GATED | T-05 verified |
| T-07 | Hourly digest + P0 routing + dedupe | **UNCLAIMED** | OPEN | T-03 |

---

## 3. Last known state per worker

- **Nova / WorkBuddy** — completed C-02…C-05. Uncommitted: `progress.md`,
  `docs/HERMES_DESKTOP_ROOT_CAUSE_2026-09-03.md` modified; new `docs/context/COORDINATION_BROADCAST.md`,
  `docs/context/WORKER_ROSTER.md`. No commit/push (owner rule).
- **OpenClaw** — historically owns `scripts/council_ledger_sync.py`, workforce orchestrator,
  `omniroute_self_healing_watchdog.py` (per `SESSION_HANDOFF.md`). Last recorded work 2026-09-07.
  **No acknowledgement of today's broadcast yet.**
- **ChatGPT Desktop** — running with a live window; no declared task; no evidence of repo activity.
- **Hermes** — cockpit up; machine backend 9119 (pid 29444) is the health-check endpoint; GUI runs
  its own child backend on 54935 (expected — see `COORDINATION_BROADCAST.md` §4).
- **Codex** — headless processes present, no declared task.
- **Claude / Verdant / Buzz** — expected by `data/workforce_live_status.json:desktop_apps` but **not
  running as agent apps** on this machine (Claude + Verdant: no process; Buzz: Docker infra only).
  Do not report them as "active".
- **Owner-Telegram feed (owner ask 2026-09-10):** nothing reaches owner Telegram today — Telegram is
  wired only for marketing video publish; owner alerts go via **ntfy**. Full topology, truth gap and
  4-layer design in `docs/context/OWNER_TELEGRAM_FEED_DESIGN.md`.
- **Truth gate:** `workforce_live_status.json` reports `status=RUNNING_24_7_PARALLEL`,
  `actions_today=592`, but `active_workers=0`, `active_members=0`, `task_execution_verified=false`,
  `evidence_kind=inference_probe_only`, and all 6 desktop apps `UNVERIFIED`. **Do not pipe this to
  Telegram until T-05 lands.**
- **Someone else is editing this repo right now (13:15 IST, confirmed via `git status`).** Two files
  changed that I did not touch: `HERMES_CONTROL_PLANE.md` (+27) and
  `docs/coordination/desktop_registry.json` (+3 app entries: openclaw / workbuddy / chatgpt-desktop,
  all `observed-not-attested`). **These are real, consistent with existing code, and I accept them**
  — full reconcile in `OWNER_TELEGRAM_FEED_DESIGN.md` §6.
- **E-01 (ledger conflict):** canonical source is `command_center/data/tasks.json` (44 tasks) +
  `docs/coordination/CENTRAL_LEDGER.md`, which forbids a second ledger. My C-01…C-12 / T-01…T-08
  boards are therefore **demoted to coordination-scratch** and must be synced into the canonical
  file via `scripts/council_ledger_sync.py --apply` — which I will NOT run without an owner ask.
- **E-02 (enrolment blocker, CODE-PRESENT):** `app/platform/coordination_hub_auth.py:23` has
  `_KNOWN_TOOLS = ("cursor","claude","monkeycode","opencode","bolt","buzz","hermes")` and line 169
  rejects anything else. `openclaw`/`workbuddy`/`codex` are **absent**, so the three new registry
  entries can never reach `buzzlock_enrolled: true`. Owner decision needed.
- **Telegram ingress ownership settled:** `HERMES_CONTROL_PLANE.md` now says Hermes is the ONLY
  `getUpdates` consumer. `grep -rn "getUpdates" --include=*.py .` → 0 hits (none exists today).
  Our T-01 design is **egress-only**, so no conflict. Also: `owner_bot.py` is **WhatsApp**, not
  Telegram — do not conflate the two.

---

## 4. Session-start checklist (coordinator runs this every session)

1. Re-read this roster + `COORDINATION_BROADCAST.md` + `ACTIVE_WORK.md` + `SESSION_HANDOFF.md`.
2. Re-run the process discovery above; diff against §1 (new worker? gone worker?).
3. Re-probe the three health checks (prod `/health`, `:9119`, `:20128`).
4. `git status --short` — confirm no worker left surprise edits.
5. Post a short status summary: who is doing what / pending / next step.
6. Update this file if anything in §1–§3 changed.

---

## 5. Escalation rules

Escalate to the owner immediately when:
- Two workers claim the same file or surface.
- Any worker proposes weakening a compliance gate (DND / TRAI / DPDP / consent ledger).
- Any worker issues `git add -A`, `git reset --hard`, or a commit/push without owner ask.
- A worker kills Hermes/Docker processes, or restarts `leadgen_omniroute`, without coordinator sign-off.
