# Plan — 40+ Loop-Engineer Improvements to the AI-Marketing Agents

> Multi-loop program for a **new session** in Loop Engineer mode. Bootstrap: read
> `CLAUDE.md §0` + `progress.md` + `docs/LOOP_ENGINEER.md` + this file, then run the
> waves below one verified loop at a time. Approved 2026-07-06.

## Context

**Why:** The LeadGenAI AI-Marketing product is run by a roster of AI "staff" agents. An audit found the agents' *creation* path largely works and is default-on, but there is a cluster of **reliability fail-open holes, LLM-cost/429 burn, missing observability, thin tests, and a dormant "last mile"** (publishing/feedback). Goal: **40+ concrete improvements** to these agents, one verified Loop-Engineer loop each.

**Roster reality (note):** "32 agents" = **31 code-defined agents** in `app/platform/team.py` `STAFF` (platform 13 / voice 8 / **marketing 10**; agents serving marketing = 10 marketing + 13 shared platform = **23**). The extra "1" is a round-up / next-hire. This program targets the marketing-serving agents + the engines/jobs they run.

**Decisions locked:**
- **Scope:** run the ~25 *safe self-contained code loops* autonomously; **PAUSE and ask the user** before any gated item (creds, prod-data, policy, enabling a send/publish path).
- **First wave:** Reliability + Cost + Observability.
- **Deploy:** each wave **merged to `main` via PR**; the **user runs the VPS deploy** via the gated `leadgen-ops` runbook (agent/scheduler code ⇒ recreate `worker`+`worker-heavy`+`scheduler`, not just `app`).

## Agent system (orientation)

- **Roster:** `app/platform/team.py` `STAFF` (31). Marketing: Dev, Rohan, Isha, Ravi, Neha, Kiran, Priya, Zara, Anika, Ira + shared platform staff.
- **Orchestration:** dual scheduler — in-process `app/platform/team_scheduler.py` (`_run_job_inner` ~178, gated `TEAM_AUTOMATION`) + durable Celery beat `app/worker.py:199` / `app/tasks/staff_jobs.py`. Marketing jobs: `content` (07:00), `blog` (06:30), `email_outreach` (hourly 9–19). On-demand: `POST /api/agents/*`.
- **Engines:** `app/marketing/*`, `app/platform/auto_outreach.py`, `app/agents/staff.py`, `app/agents/self_improve.py`, `app/voice_agent/free_ai.py` (LLM chain + cache).

## How the new session runs this

1. **Read first:** `CLAUDE.md` (§0, §5, §6, §8), `progress.md`, `docs/LOOP_ENGINEER.md`, this file.
2. **One improvement = one loop:** pick next item (wave order) → smallest additive change → verify (targeted pytest + `scripts/prod_check.py`) → append `## Loop Run` to `progress.md` → next.
3. **PRs:** wave onto branch `chore/agents-wave-N-*`; PR per wave; **merge via `gh pr merge` (GITHUB_TOKEN= unset)** — never `git push origin main` (blocked). Stage explicit paths only (never `git add -A`).
4. **Verify per loop (DoD §6):** targeted pytest (new behaviour ⇒ new test) + `prod_check.py` PASS + `check_secrets.py` clean. No in-session deploy.
5. **Guardrails (hard):** stay inside §5/§6/§8. **Never autonomously** flip a compliance/prod-send gate, add creds, mutate prod data, edit `.env`, deploy, or weaken 2FA/DND — those are **Wave 4 pause points**.
6. **Stop rule:** wave loops pass + recorded, or budget near limit with `progress.md` updated, or user stops.

---

## Backlog (≈43 items) in waves

Legend: `type · size(S/M/L)`. Waves 1–3 = **SAFE self-contained loops**. Wave 4 = **GATED** (pause & ask).

### WAVE 1 — Reliability + Cost + Observability (autonomous) — do first

- **W1.1** Scheduler single-instance lock fail-**OPEN** on lock-FS error → both workers double-fire jobs. Fail-closed. `team_scheduler.py:82-85` · reliability·S
- **W1.2** `_run_job_inner` swallows sub-job exceptions ⇒ dead-man switch records success forever. Thread real status into `automation_health.record_run`. `team_scheduler.py:164-175,862-863` · reliability·M
- **W1.3** `content` mega-job chains ~12 engines with no per-engine try-wrap → one throw silently skips later engines. Wrap each. `team_scheduler.py:389-432` · reliability·M
- **W1.4** Follow-up outreach still per-send full-file JSONL rewrite (O(N²) OOM pattern; only initial path got the bulk fix). Apply `set_prospect_fields_bulk`. `auto_outreach.py:930` · reliability·S
- **W1.5** `self_improve.acquire_tick_slot` fail-opens when Redis down → duplicate self-requeue chains. Fail-closed. `self_improve.py:98-99` · reliability·S
- **W1.6** Module-import-time network call `_AUDIT_URL_TRACKED = _track_url(...)` (is.gd) → lazy. `auto_outreach.py:110-111` · reliability·S
- **W1.7** In-memory `_last_ran` resets on restart → hourly jobs re-fire same window. Persist last-run / extend grace. `team_scheduler.py:98-137,882-916` · reliability·S
- **W1.8** Unbounded JSONL growth, no prune for `content_queue/*`, `self_improve_runs.jsonl`, `content_feedback.jsonl`, `reply_drafts.jsonl`. Add rotation (kavya prune pattern). `staff.py:308-362`, `auto_content.py:544-575` · reliability·S
- **W1.9** Outreach reads whole prospect store + in-memory sort each run (11×/day, 7.6k rows). Stream/index. `auto_outreach.py:563-567` · reliability·M
- **W1.10** `LLM_CACHE` default OFF → bulk content/blog/SEO uncached. Turn on for content profile. `free_ai.py:489-490` · cost·S
- **W1.11** LLM cache eviction full `.clear()` at bound → LRU/TTL. `free_ai.py:521-522` · cost·S
- **W1.12** LLM cache per-process dict (not shared) → Redis-backed. `free_ai.py:501-523` · cost·M
- **W1.13** Core marketing/agent engines emit zero Prometheus metrics → per-job success/duration/items counters. `auto_content.py:448`, `auto_outreach.py:525`, `staff.py:82-621` · observability·M
- **W1.14** Staff jobs signal failure only via `{"error":…}` → metrics + ntfy alert (ties to W1.13). `staff.py:142-148,296-302,433-439` · observability·S
- **W1.15** Daily digest no push channel → ntfy/WhatsApp fallback. `staff.py:551-561` · observability·S

### WAVE 2 — Agent output QUALITY (autonomous)

- **W2.1** No output-validation gate before content enters draft queue → caption validator (length/banned) reusing `staff.BANNED`. `auto_content.py:159-169` · quality·S
- **W2.2** QA agent (arjun) tests only 3 hardcoded niches → parametrize + real transcripts. `staff.py:36-63` · quality·S
- **W2.3** Trainer (meera) suggestions hardcoded thresholds → niche weighting / cheap-LLM reflection. `staff.py:237-258` · quality·S
- **W2.4** Daily digest rule-based concat → optional cheap-LLM synthesis (why + next action). `staff.py:522-531` · quality·S
- **W2.5** Client-journey next-step canned "for now" placeholders → agent brain. `client_journey.py:291,433` · feature·M

### WAVE 3 — Tests + CI safety-net (autonomous)

- **W3.1** `team_scheduler.py` (40-job dispatcher) zero tests → job-routing + boot-grace + lock. · test·M
- **W3.2** Staff jobs (`run_qa/run_trainer/run_ops/run_digest`) no tests. `staff.py` · test·M
- **W3.3** `coordinator.py` (Boss planner, 1043 lines) no tests. · test·M
- **W3.4** Fix team_pulse pytest hang → flip full-suite CI gate to blocking. `memory/backlog.md:21`, `CLAUDE.md:67` · test·M
- **W3.5** `payment.received`/`subscription.*` customer-webhook emits documented but not wired → wire + test. `memory/backlog.md:18` · feature·S
- **W3.6** `.env.example`/`pyproject.toml` advertise stale PAID stack → correct to real free stack. `memory/backlog.md:20` · ux·S

### WAVE 4 — GATED (PAUSE & ASK — never autonomous)

Session prepares a one-line recommendation, then waits for the user:
- **Revenue / mid-funnel (live data):** reply-agent intent classifier + bounce/OOO split (`reply_agent.py`); hot-queue warm-lead aging/SLA + founder nudge; content-feedback auto-ingest from UTM/click.
- **Deliverability-sensitive:** cold-email LLM personalization + 42-niche hooks (`auto_outreach.py:57-80`); enable A/B (`OUTREACH_AB`/`OUTREACH_CAMPAIGN_VARIANTS`) + winner auto-promote.
- **Prod behavior / creds:** `DLQ_AUTO_RETRY` backoff; `EMAIL_TRACKING`; global daily LLM-token budget for `content` fan-out; wire `email_finder` refill; full Zoho pull (`crm_sync.py:300`).
- **Publishing last mile (creds + Meta app-review):** `SOCIAL_AUTOPOST`/Postiz, `POLLINATIONS_API_KEY`, customer email lifecycle, `REVIEW_MONITOR`, `campaign_optimizer` auto-apply.
- **Policy:** `STUDIO_ENTITLEMENT_GATE` flip + entitlement fail-open; customer **2FA fail-open** + cosmetic logout (see `progress.md`).
- **Prod data op:** `scripts/purge_junk_prospects.py --apply` (~94 SERP-junk, ADR-022).

---

## Verification

- **Per loop:** targeted pytest green (new behaviour ⇒ new test) + `scripts\prod_check.py` = "ALL CHECKS PASSED".
- **Per wave:** wave tests + existing agent/scheduler suites (`test_customer_office.py`, `test_*staff*`, `test_*outreach*`) + `prod_check.py`; open/merge wave PR.
- **Program done:** Waves 1–3 (~26 loops) merged + each in `progress.md`; every Wave-4 item resolved-or-deferred with the user; user deploys via `leadgen-ops`.

## Critical files (Waves 1–3, pattern-level)

`app/platform/team_scheduler.py` (lock, try-wrap, real status, persisted last-run) · `app/platform/auto_outreach.py` (bulk write, lazy import, streamed read) · `app/agents/self_improve.py` (fail-closed slot) · `app/voice_agent/free_ai.py` (cache on + LRU + Redis) · `app/marketing/auto_content.py` + `app/agents/staff.py` (rotation, metrics+alerts, digest push, validator, QA/trainer/digest quality) · `app/platform/client_journey.py` (brain next-step) · `tests/` (scheduler/staff/coordinator + CI hang) · `.env.example`/`pyproject.toml` · `progress.md` (ledger).
