# Admin Operating Guide

Status: first edition, written 2026-07-15 during the ADR-104 Phase F/G/H session, from
screens actually browser-tested in production that session (Claude in Chrome against
`https://leadsgenai.in`, `prod` badge visible top-right on every screen). It intentionally
does **not** claim coverage of screens not inspected this session — those are listed at the
bottom under "Not yet walked" so the next session (human or agent) knows exactly what's
proven vs. unproven, per this repo's causal-claim discipline (see `CLAUDE.md` §"Known
Landmines").

Related reading: `CLAUDE.md` (root — always read first), `docs/HANDOFF.md` (infra map),
`docs/LOOP_ENGINEER.md` (engineering-loop spec), `memory/incidents.md` +
`memory/decisions.md` (ADR-091 through ADR-104 cover this same modal/DLQ-truth/deploy-drift
family of fixes).

## 1. Access & safety

- Login: `https://leadsgenai.in/app/admin-login`. Use your saved browser credentials
  (autofill) — do not type or read the password out loud/in logs.
- Every admin screen shows a `● prod` badge top-right — if it's missing or says anything
  else, you are not looking at production.
- **Never** enter API keys, passwords, or OTPs into any admin page yourself. Never approve
  or force-deliver a real customer's content unless you specifically mean to.
- As of this session, every approval/publish/status-change/force-deliver button that
  matters is gated by an in-page confirmation modal (ADR-104) — you will always see a
  popup naming the exact client, the exact action, and whether it can contact a real
  external channel, before anything happens. If a button ever fires an action with no
  such popup, that is a regression — file it the same way ADR-104's four fixes were filed
  (see §7).

## 2. Daily 10-minute routine

Do this every morning before touching anything else:

1. **Login** at `/app/admin-login` — confirms your session/token is alive (a red "Login"
   nav link on `/app/automation` instead of a token dot means you're logged out).
2. **Confirm the deployed SHA** — any page's `/health` call, or SSH
   `curl 127.0.0.1:8000/health`, must show `"version"` as an 8-char git SHA, never
   `"latest"`. If it says `latest`, the running code's provenance is unknown (ADR-097) —
   escalate immediately, do not assume it's fine.
3. **Check retryable/dead/overdue tasks** — open `/app/office#reliability` (Reliability
   Console) or the "Problems" panel on `/app/control-center` (L1 Executive). Both now read
   the same authoritative `automation_health.health()` snapshot (`queue.dlq` = retryable,
   `queue.dead` = exhausted). Zero of both is healthy; `dead > 0` needs your attention even
   if `dlq == 0` — a queue can look "clean" on old dashboards while tasks are quietly dead.
4. **Check default vs heavy worker** — `/app/automation#schedule` lists every scheduled job
   with cadence, last-run time, duration, and `ok`/`issue` status. `worker-heavy` runs the
   KB/niche-refresh jobs (why: they're memory-heavy, kept off the shared default worker to
   avoid OOM — see `memory/incidents.md`).
5. **Check queue depths** — `celery`/`heavy` counts on the same panels; a large or growing
   number with `0 running` on Recent Runs is a stuck-worker sign.
6. **Check scheduler health** — "Jobs alive" tile (`/app/control-center`, top strip,
   "HEARTBEAT") should read `N/N`, not less.
7. **Check disk / build-cache** — SSH `df -h` or read the deploy log's `DISK GUARD` line;
   warn at 80% used, hard-stop at 90%. Build cache is capped at 20GB reclaim-eligible but
   the *total* cache has been trending up across this session's three deploys
   (91.58GB total, 70GB+ reclaimable, disk 76→77% used) — not urgent, but worth a monthly
   `docker builder prune` review if it keeps climbing.
8. **Check customers needing attention** — `/app/clients` client list + each client's
   Delivery Timeline panel (see §5). Look for "Customer delivery SLA breached" or repeated
   "Approval reminder raised" entries.
9. **Check approvals/evidence** — `/app/automation#approvals` shows the pending-approval
   count in the sidebar badge; `/app/clients` → client → Content panel shows per-item
   Draft/Approved/Posted/Skipped state directly.

## 3. Screen-by-screen guide (screens actually tested this session)

### 3.1 Operating HQ — `/app/office`
Single long page; the top nav (War Room/Priorities/Map/Replay/Pipeline/Approvals/
Improve/Health/Scheduler/Reliability) smooth-scrolls to anchored sections, it does not
navigate between pages. The "System health" widget now (ADR-104 Phase F, `0f0e4af3`) shows
both `celery=`, `retry-failed=` (dlq), and `dead=` counts on one line, e.g.
`Queue: celery=0 · retry-failed=0 · dead=4`, with the dead count clickable straight to
the Reliability Console. Before this fix it silently ignored `dead`, so it could say
"sab healthy hai" while 4 tasks sat exhausted — classification: **was misleading, now
fixed and truthful.**

### 3.2 Control Center — `/app/control-center`
Four levels via the left sidebar: **L1 Executive** (Problems/Staff pulse/Aaj ke jobs/Flags
OFF cards + a bottom Live Log/Recent Runs/DLQ-Queue tab strip), **L2 Stack** (an
architecture graph — **classification: broken/incomplete this session**, the canvas
rendered an empty broken-image placeholder with no console error captured; the "Old
explorer ↗" link next to it is the known-working fallback — use that until L2 Stack's
graph is fixed), **L3 Workflow** (not walked this session), **L4 Agent** (Root-cause
analysis findings list + an Agent Explorer staff grid with Sab/Marketing/Voice/Platform
tabs — functional, showed real findings including the 4 dead tasks and 6 recent failed
flow-runs with actionable `fix:` text).

Header tiles: STAFF, JOBS AAJ, RUNS, QUEUE/DLQ, HEARTBEAT, LLM BRAIN — all `● live`. The
QUEUE/DLQ tile and its DLQ/Queue detail tab both now read `dead` alongside `dlq`
(ADR-104 Phase F, `22ff63ec`) — before this fix both showed "DLQ 0" / "Queue clean" while
4 tasks were dead/exhausted, contradicting the Reliability Console's truthful count on the
exact same underlying data. Root cause was 3 separate frontend read-gaps plus 2 backend gaps
(`/api/control-center/overview` and `/rca`, and the shared `today_overview.build()` that
also feeds `/app/automation`'s "Aaj" tab) — all now read `queue.dead` /
`dead_tasks_present` / `retryable_failed_present`, the same fields the Reliability Console
already used. **Classification: was misleading, now fixed and truthful; L2 Stack graph
still needs a follow-up fix.**

Auth note: your admin token/session can expire while you're actively looking at this page
— if it suddenly shows all-zero "fallback" data, don't assume something broke; check
Network tab for a 401 on `/api/control-center/overview` and re-login first.

### 3.3 Automation Mission Control — `/app/automation`
Left nav: Aaj / Flow Explorer / Launch / Schedule / Agents / Training / Scraping /
Approvals / Events / Harvester / Prospects / Cadence / Sales Team AI / Processes /
Self-Improve / Code Upgrader / RL Flywheel (only Aaj/Approvals/Schedule were actually
opened and verified this session — the rest are listed under §8 as not yet walked).

- **Aaj tab**: plain-Hinglish daily snapshot (headline, Problems, Staff pulse, Scheduled
  automations). Fed by the same `today_overview.build()` fixed in §3.2 — confirmed live
  that this tab now also correctly surfaces the 4 dead/exhausted tasks as a Problem.
- **Approvals tab**: badge shows a live pending count (e.g. "Approvals (39)"). Contains
  Self-Improve Cost Tracking (daily LLM-heavy budget cap), Self-Improve Approval Queue
  (gated by `SELF_IMPROVE_APPROVAL` flag, currently OFF so nothing queues there), and
  Content Approvals (client posts) — a flat table across **all** clients with columns
  Client / Content / When / Action. **Known UX gap (not fixed this session, logged for
  follow-up):** the Client column shows the raw opaque client id (e.g. `105a5a749a81`),
  not the business name — you have to cross-reference `/app/clients` to know which real
  customer a row belongs to. Approve/Reject here are already gated by the ADR-104
  confirmation modal (fixed earlier this session, commit `1f87ae3`).
- **Schedule tab**: every scheduled job (`ops`, `reply_triage`, `watchdog`, `onboard`,
  `mcp_engineer`, `engineer_sre`, `meter_watch`, `email_outreach`, `email_followup`, etc.)
  with cadence, last-run timestamp, duration, `ok` status, an ON/OFF toggle, and a manual
  ▶ run button. **Classification: complete and truthful.**

### 3.4 Customer Management — `/app/clients`
Left panel: "+ Naya client" form, then the live Clients list (7 active: Jiya Makeover
Studio, Test Biz, Fresh Test Biz 42, LeadGen AI, Sharma Solar ×3 synthetic variants).
Click a client to load its Content queue (right, filterable Sab/Draft/Approved/Posted/
Skipped) and Delivery Timeline (further down — client-scoped event log + a **Deliver Now**
button).

Two real safety gaps were found and fixed here this session (see §7 for full detail):
1. Content-item Approve/Posted/Skip buttons fired their status-change API call on click
   with **zero** confirmation of any kind (worse than a native `confirm()`) — fixed,
   commit `1b2a412`.
2. The **Deliver Now** button calls `deliver_client_value(force=True)` — a real forced
   delivery to a real customer that bypasses normal gating — also with zero confirmation.
   This was the single highest-severity gap found this entire session. Fixed, commit
   `5f65979`, reusing the same modal with a red "dangerous" variant.

Both are now gated exactly like automation.html/delivery_command_center.html's approval
actions: named client, named action, accurate description of real-world effect, explicit
Confirm-button click required, Escape/backdrop/Cancel always safe, Enter never confirms,
opening the modal makes no network call. **Classification: was two real safety gaps
(one high-severity), now fixed and verified.**

**Known gap found but not fixed this session (logged for follow-up):** two other
consequential admin endpoints exist in `app/api/admin_ops.py` —
`POST /clients/{id}/password-reset` and `POST /clients/{id}/onboard/scrape` — that were
not found wired into `clients.html`'s UI (they may be used from a different admin page not
inspected this session). Worth a follow-up grep across `frontend/*.html` before assuming
they're unreachable or already safe.

## 4. Automation / task state — what each label means

- **dispatched / running** — task handed to a worker, executing now.
- **logic completed** — the task's own code finished without raising, but this is **not**
  the same as "succeeded" — a step can complete its logic and still be flagged
  retryable/failed by an outer wrapper (e.g. a partial result). Don't read "completed" on
  its own as "safe to ignore."
- **succeeded** — the terminal good state.
- **retrying** — failed once, an automatic retry is scheduled (see `dlq_retry.py`'s sweep).
- **retryable failed (`queue.dlq`)** — sat in the retry queue; the automatic sweep hasn't
  drained it yet, or it needs a manual nudge.
- **dead/exhausted (`queue.dead`)** — retry budget ran out; the automatic sweep gave up.
  **This needs a human**, even when `dlq == 0` — that's precisely the bug this whole
  session's fixes were about: multiple dashboards showed "queue clean" while `dead` sat
  non-zero on the exact same data.
- **overdue** — a scheduled job that should have run by now and hasn't.
- **cancelled/revoked** — deliberately stopped, not a failure.

Safe-retry conditions: retry a dead task manually from the Reliability Console
(`/app/office#reliability`) once you've confirmed the underlying cause (provider outage,
transient network) is resolved — retrying into a still-broken dependency just burns budget
again. Escalate (don't retry) if the same task keeps dying repeatedly, or if `dead` count
keeps climbing after a retry attempt.

## 5. Worker routing

- **Default worker** (`leadgen_worker`) — general Celery queue.
- **Heavy worker** (`leadgen_worker_heavy`) — KB/niche-refresh and other memory-heavy jobs,
  deliberately isolated after an earlier OOM incident on the shared worker (see
  `memory/incidents.md`).
- **Video worker** (`leadgen_worker_video`) — video-render jobs (seen in Sharma Solar's
  Delivery Timeline: "Video render started/succeeded, pending approval").
- **Scheduler** (`leadgen_scheduler`) — Celery beat, drives every job on the Schedule tab.
- Escalation sign: a worker's restart count climbing, or queue depth rising with
  `0 running` on Recent Runs (stuck, not busy).

## 6. Deployment / rollback

- Deploys are immutable-SHA only: `APP_VERSION=<git-sha> bash scripts/deploy_vps.sh`. The
  script itself enforces skew-free rollout (all 5 app-image containers get the same tag),
  refuses `:latest`, and only reports `OK` after health + per-container skew + smoke tests
  all pass.
- `/health`'s `"version"` field is the drift detector — it must equal the SHA you just
  deployed on every container. If any container shows a different SHA, that's version skew
  (ADR-097) — do not assume it's cosmetic.
- Rollback = redeploy the previous known-good SHA the same way (the script keeps the newest
  3 image tags on the box for exactly this reason — this session's deploys retired
  `1f87ae36` then `0f0e4af3` in turn, keeping 3 always available).
- This session deployed 4 SHAs in sequence, each independently verified: `1f87ae36` →
  `0f0e4af3` → `22ff63ec` → `1b2a4128` → `5f65979c` (final).

## 7. What was fixed this session (Phase F evidence log)

All four fixes follow the identical pattern: a consequential admin action fired its real
API call directly on click with no confirmation (or, for the DLQ-truth bugs, a dashboard
silently under-counted an already-correct backend truth). Every fix reused existing
authoritative data/components rather than inventing new ones, per this session's explicit
"reuse existing architecture" instruction.

| # | Surface | Problem | Fix | Commit | Deployed SHA | Verified |
|---|---|---|---|---|---|---|
| 1 | `automation.html` / `delivery_command_center.html` | Approve/reject/publish/deliver actions used native `confirm()`/`prompt()`, proven to auto-accept in a browser-automation context before a permission interceptor could block it | In-page modal, explicit Confirm click only, Escape/backdrop=cancel, Enter never confirms | `1f87ae3` | `1f87ae36` | Browser: modal shown, zero network calls on open, Cancel verified |
| 2 | `office_map.html` (Operating HQ System health widget) | Read only `queue.dlq`, ignored `queue.dead` — could show "sab healthy hai" with 4 dead tasks | Read + display both counts, gate health-dot and empty-state on both | `0f0e4af` | `0f0e4af3` | Browser: exact text `celery=0 · retry-failed=0 · dead=4` confirmed live |
| 3 | `control_center.py` + `today_overview.py` + `control_center.html` (3 frontend sites + 2 backend endpoints) | Same dead-count blind spot, 6th instance of the bug family, spanning `/overview`, `/rca`, the shared Aaj-tab builder, and 3 separate JS render sites | All read `dead_tasks_present`/`retryable_failed_present`/`queue.dead` off the same `automation_health.health()` call | `22ff63e` | `22ff63ec` | Browser: header tile, Problems panel, and DLQ/Queue detail tab all confirmed showing `dead 4` correctly, after correctly diagnosing an unrelated 401 session-expiry false-negative first |
| 4 | `clients.html` — content Approve/Posted/Skip | Zero confirmation of any kind (worse than native `confirm()`) on a real customer's content status | Same modal pattern, wired into `markItem()`'s click handler | `1b2a412` | `1b2a4128` | Browser: modal shown on synthetic "Fresh Test Biz 42", zero network call confirmed, Cancel verified |
| 5 | `clients.html` — **Deliver Now** | Zero confirmation on a real forced customer delivery (`deliver_client_value(force=True)`) — highest severity found this session | Same modal, red "dangerous" variant, accurate real-world-effect copy | `5f6597` | `5f65979c` | Browser: modal shown on synthetic "Sharma Solar", zero network call confirmed, Cancel verified |

No real Jiya Makeover Studio content or delivery action was ever clicked/confirmed during
any of this work — every browser verification used Cancel only, and where a real click was
needed to prove the gate, it was performed on synthetic test clients (Fresh Test Biz 42,
Sharma Solar), never Jiya.

## 8. Not yet walked this session (do not assume these are fine or broken)

Named in the original Phase F scope but not individually opened/tested this session:
Agent Tools / Training / Scraping / Events / Harvester / Prospects / Cadence / Sales Team AI
/ Processes / Self-Improve / Code Upgrader / RL Flywheel tabs on `/app/automation`; Social
Setup; a dedicated Integration Health page (own-brand social/WhatsApp/Meta facts cited in
§3 come from `CLAUDE.md`'s already-dated, already-verified entries, not a fresh click-
through this session); OmniRoute in the sense of LLM-provider routing/fallback (L4 Agent's
staff/agent grid was seen, but that is agent routing, not necessarily the same thing);
Deployment/rollback UI (the mechanism was verified via 5 real deploys this session, but no
dedicated rollback *button* in the admin UI was located or tested). Treat these as unknown,
not as confirmed-safe.

## 9. Escalation

- Dead/exhausted tasks, version skew, disk ≥80%, or a confirmation modal missing on a
  consequential action → fix or escalate same-day, don't let it ride.
- Anything that would require entering a password/OTP/API key, approving/publishing real
  Jiya (or any other real customer) content without an exact explicit go-ahead, or a
  destructive data operation (Qdrant cleanup, DB reset) → stop and ask the person, do not
  proceed unilaterally, per this repo's standing safety rules.
