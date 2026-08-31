# AGENT BOARD — Live Execution State

> Companion to `docs/MULTI_AGENT_WORKFLOW.md` (CANONICAL spec). Ye file **live state** hai —
> har loop ke baad update hoti hai. Statuses: `QUEUED · ACTIVE · VERIFYING · BLOCKED · DONE`
> **Last sync:** 2026-08-31 13:1x IST · by PILOT

---

## GOAL

₹5,00,000 **verified** revenue in 7 days via existing LeadGen AI products — bina kisi fabricated
revenue/customer/payment/call/test/deploy claim ke. Engineering support karega revenue blockers ko,
P0→P5 order me.

## BASELINE EVIDENCE (2026-08-31 13:13 IST — actually run, not asserted)

| Check | Command | Result |
|---|---|---|
| Production gate | `.venv\Scripts\python.exe scripts/prod_check.py` | **`[OK] ALL CHECKS PASSED - ready to deploy`** |
| Route count | (prod_check 4/6) | **1,346 registered routes** |
| Page wiring | (prod_check 6/6) | **54 pages · 0 gaps** · automation 0 gaps |
| Config | (prod_check 5/6) | `env=production` |
| Explorer graph | (prod_check note) | 362 nodes · 97/97 engine coverage · 0 orphans |
| API index | (prod_check note) | `API.md` in sync (1,373 ops) |
| Git branch | `git branch --show-current` | `main` |
| Working tree | `git status --short` | **10 modified · 13 untracked** (uncommitted owner work — preserve) |

**Verdict: app-level production wiring HEALTHY.** Is liye P0 outage nahi hai — priorities ab
**P1 acquisition/onboarding blockers** aur **working-tree hygiene** hain.

---

## ACTIVE WORKSTREAMS (cap = 3)

### WS-09 · Security / Compliance — `ACTIVE`
**Lead:** arnav · **Reviewer:** pranav

| Task | Objective | Status |
|---|---|---|
| `T-WS09-001` | Review the 13 untracked `scripts/**` desktop-automation files before ANY commit. Risk surface: OS-level persistence (`setup_autoboot.ps1`, `autoboot_master.ps1`, `autoboot_silent.vbs`), keystroke injection (`focus_workbuddy_sendkeys.ps1`, `send_to_workbuddy.py`, `focus_and_submit_workbuddy.py`), window/process enumeration (`find_all_windows.py`, `desktop_action_overlay.py`), admin MCP harness (`leadgen_admin_harness_mcp.py`). Deliverable: `check_secrets.py` clean + written allow/deny verdict per file. | `ACTIVE` |

**Why P1:** ye files `main` par untracked hain aur machine-level persistence + input injection karti hain.
Bina review ke commit = unvetted code production repo me.

---

### WS-06 · Infra / SRE — `ACTIVE`
**Lead:** pranav · **Reviewer:** aryan

| Task | Objective | Status |
|---|---|---|
| `T-WS06-001` | Working-tree hygiene: 10 modified + 13 untracked files `main` par hain (CLAUDE.md §3.4 violation). Produce a scoped branch plan (`ws/09-*`, `ws/06-*`) that preserves 100% of owner work; **no commit/push without owner authorization** (§8/§7). Deliverable: branch plan + `git status` diff summary. | `ACTIVE` |

**Constraint:** read-only until owner says go. `reset --hard` / force-push / stash-drop **forbidden**.

---

### WS-07 · Revenue Ops — `ACTIVE`
**Lead:** nikhil · **Reviewer:** vidya

| Task | Objective | Status |
|---|---|---|
| `T-WS07-001` | Establish the **verified** revenue baseline from ledger/DB: paying customers, invoices (last known: 1 customer `jiya makeover`, invoice `INV/2026-27/0001`), MRR, minute-pack top-ups. Gap to ₹5,00,000/7d. Deliverable: `data/revenue/baseline_2026-08-31.md` + count of verified transactions. | `ACTIVE` |

**Dependency:** read path to prod Postgres (PgBouncer :6432) — SSH `root@72.61.245.204` is an **owner-gated**
action (§7). If unreachable → task goes `BLOCKED` with the precise ask; baseline ko guess **nahi** kiya jayega.

---

## BLOCKED — owner action required

| Task | Owner ask | Status |
|---|---|---|
| `T-WS02-001` | **Vobiz owned caller-ID registration** — per `progress.md` (2026-08-30) ye abhi bhi *THE single unblock* for outbound calling. Needs provider KYC/creds. Voice subsystem stays non-armed until then. | `BLOCKED` |

---

## QUEUED

| WS | Focus | Trigger |
|---|---|---|
| `WS-01` | Engineering / Integrations (`app/**`, `scripts/**`) | new defect or integration gap |
| `WS-02` | Voice / Swara (`app/voice_agent/**`, `app/telephony/**`) | unblocked by `T-WS02-001` |
| `WS-03` | Funnel / Lead Intel (`app/lead_scraper/**`, prospecting) | after revenue baseline |
| `WS-04` | Outreach & Conversation (cadence, WhatsApp, email) | after `WS-03` feed |
| `WS-05` | Content / SEO (programmatic pages, marketing tabs) | parallel-safe, low-risk |
| `WS-08` | QA / Verification (`tests/**`, `evals/**`) | on every integration |

---

## CHANGES MADE (this session)

| File | Change |
|---|---|
| `docs/MULTI_AGENT_WORKFLOW.md` | NEW — canonical multi-agent execution contract (13 sections) |
| `docs/AGENT_BOARD.md` | NEW — live board, seeded from verified repo state |
| `_work/README.md` | NEW — artifact root convention for task deliverables |

**No code changed. No commit. No push. No deploy.** (§8 — owner-gated.)

---

## NEXT ACTION

1. `T-WS09-001` — secrets scan + per-file verdict on the 13 untracked desktop-automation scripts.
2. `T-WS06-001` — scoped branch plan (read-only).
3. `T-WS07-001` — verified revenue baseline; if prod DB unreachable → `BLOCKED` with precise ask.

Owner se ek hi cheez chahiye: **kya main `T-WS06-001` ke liye scoped branches bana doon (local, non-destructive)?**
Push/commit nahi karunga bina permission ke.
