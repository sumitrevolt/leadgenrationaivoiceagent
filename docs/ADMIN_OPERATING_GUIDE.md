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

## Daily 10-minute routine

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
7. **Check disk / build-cache** — SSH `df -h` or read the deploy log's `DISK GUARD` line.
   Current thresholds (`scripts/deploy_vps.sh`): **warn ≥80% used, hard-stop ≥90% used**
   (refuses to build past hard-stop). Build cache retention runs automatically after every
   verified deploy — `docker builder prune -f --filter unused-for=168h --max-used-space 20GB`
   (7-day-unused entries pruned, total cache capped at 20GB regardless of age if it exceeds
   the cap). Tagged image retention keeps the newest 3 app-image tags. Disk was last observed
   at 76→77% used across this session's earlier deploys (below warn) — this reconciliation
   step needs a live SSH session to re-check current numbers; it could not be re-verified
   from an agent sandbox without SSH key access (see §10). The retention *policy* itself is
   sound and doesn't need changing unless a live check finds cache genuinely exceeding the
   20GB cap after the automatic prune ran.
8. **Check customers needing attention** — `/app/clients` client list + each client's
   Delivery Timeline panel (see §5). Look for "Customer delivery SLA breached" or repeated
   "Approval reminder raised" entries.
9. **Check approvals/evidence** — `/app/automation#approvals` shows the pending-approval
   count in the sidebar badge; `/app/clients` → client → Content panel shows per-item
   Draft/Approved/Posted/Skipped state directly.
10. **Agent OS / OmniRoute (30s)** — confirm you are **not** expecting OmniRoute on VPS
    unless you deliberately stood up a gateway. Default = both flags OFF. Full checklist:
    `docs/AGENT_OS_OMNIROUTE_ADMIN_RUNBOOK.md` §1.

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
architecture graph, embedded via `<iframe src="/app/control-center/graph">` —
**classification: root-caused and fixed, commit `5d4b9fe`, see §7a**; the "Old
explorer ↗" link next to it remains a valid fallback if you ever prefer the plain page),
**L3 Workflow** (not walked this session), **L4 Agent** (Root-cause
analysis findings list + an Agent Explorer staff grid with Sab/Marketing/Voice/Platform
tabs — functional, showed real findings including the 4 dead tasks and 6 recent failed
flow-runs with actionable `fix:` text).

**L2 Stack graph troubleshooting (§7a).** If this ever goes blank again: check the response
headers on `/app/control-center/graph` first (`curl -sD - -o /dev/null <url>`) — an
`X-Frame-Options: DENY` or a `frame-ancestors` CSP directive that omits `'self'` will make
the browser silently refuse to render the iframe, with **no console error at all** (this is
not a JS bug, so `read_console_messages` will look clean even when this is exactly the
cause). The graph's own JS (`control_center_graph.html`) has real error-handling (a loading
spinner, an error banner, try/catch around ELK init) — if you see that error banner instead
of a blank canvas, the problem is genuinely in the graph's data/rendering, not headers, and
is a different bug. The graph itself is fully static (a hardcoded `VIEWS` object with 3 tabs
— Structural/Automation/Products — no backend fetch at all), so "malformed data from the
API" is not a real failure mode here; "blank canvas, no error" almost always means headers.

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

### 3.2b Full Console — `/app/admin` (overview, not daily home)

**Use this page as a map, not as your only workspace.** Daily work lives on Delivery
Cockpit, Automation, Client Actions, and Office HQ (linked from the **“Aaj ka 5-minute
flow”** strip at the top — ADR-110).

How to use (5 minutes):

1. Read **Aaj ka business** — green = automations OK; yellow problems = follow the fix line.
2. Open **Aapke kaam** — do **UPI** first (revenue), then content. Large content queues
   (`>20`) do **not** offer “Sab approve” — go to Client Actions / Mission Control and
   approve paid clients (e.g. Jiya) one by one. Never bulk-approve a 300+ backlog blindly.
3. Jump via the 4 big buttons: Delivery → Automation → Clients → Office.
4. Expand **Technical / Ops** only when something is broken (God Mode, LLM health, social
   queue). Mid-page cards (campaigns, niches, billing lookup, …) stay collapsed by default.
5. Sidebar **Full Console** is the active item on this URL; **Delivery Cockpit** is a
   different page (do not trust a wrong `active` highlight — fixed in ADR-110).

What is *not* “missing setup” on this page: OmniRoute on VPS (flags OFF until a gateway
exists), platform_dial (LIVE — supersedes this file's 2026-07-15 "HARD OFF" claim, 2026-08-02; `PLATFORM_DIAL_DAILY`=boolean, per-run cap `PLATFORM_DIAL_LIMIT`=100 — see `docs/context/CURRENT_STATE.md`), Unity 3D office (local artifacts only).

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
  Client / Content / When / Action. **Client-name fix (§7b, commit `8a64e9c`):** the Client
  column used to show only the raw opaque client id (e.g. `105a5a749a81`) — you had to
  cross-reference `/app/clients` to know which real customer a row belonged to. It now shows
  the business name in bold as the primary label, with the client id kept directly below as
  small muted text (also in the `title` tooltip) — the id is never hidden, just demoted to
  secondary, since the approve/reject buttons and any support conversation still need it. A
  deleted/unknown client shows an honest "(unknown client)" label instead of a blank cell or
  a stale name. Approve/Reject here are already gated by the ADR-104 confirmation modal
  (fixed earlier this session, commit `1f87ae3`), and the confirmation dialog itself now
  also shows the business name instead of the raw id.
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

**Password-reset / onboard-scrape — found, audited, fixed (§7c, commit `2895e97`).** The
two consequential admin endpoints in `app/api/admin_ops.py` —
`POST /clients/{id}/password-reset` and `POST /clients/{id}/onboard/scrape` — are **not**
wired into `clients.html`; they live on a different admin page,
**`/app/admin` → Customer 360 panel → "Manual Action Triggers"** (three buttons: 🚀 Deliver
Value Now, 🌐 Re-Scrape Website, 🔑 Reset Password). Password reset already had a
well-built confirmation modal (password+confirm fields, live strength meter, Loop 27,
2026-07-11) — that one was never a gap. Re-scrape had zero confirmation despite queuing a
real `force=True` website re-scrape + KB/content re-seed that can overwrite already-tailored
content even on an already-set-up client — now gated with the same modal pattern. Both
endpoints previously had **no audit trail at all**; both now write a
`delivery_ledger.log_event(client_id, "admin_manual_action", ...)` entry (visible in that
client's Delivery Timeline) every time an admin uses them — never logging the password
itself. Backend password minimum raised from 4 to 8 chars to match what the UI already
enforced.

**Customer 360 Deliver Value Now is now fixed:** the second UI surface's
`c360DeliverNow()` action opens a red, named-client confirmation modal before it can call
`POST /clients/{id}/deliver-now`; Cancel, backdrop and Escape are safe, while the real
request lives only in `_c360DeliverConfirmed()`. This shipped in the launch baseline
deployed as `972bd74` on 2026-07-15. The older first-edition note that called this surface
"not fixed" was stale and has been removed after source + deployed-SHA reconciliation.

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

### 7a–7c. Follow-up priorities fixed the same session (2026-07-15, ADR-104 continued)

| # | Surface | Problem | Fix | Commit | Tests |
|---|---|---|---|---|---|
| 7a | `app/middleware/__init__.py` (`SecurityHeadersMiddleware`) + `/app/control-center/graph` | Blanket `X-Frame-Options: DENY` (correct default for every other admin page) silently blocked `control_center.html`'s own same-origin `<iframe>`, rendering an empty canvas with **no console error** | New same-origin-only tier (`X-Frame-Options: SAMEORIGIN`, `frame-ancestors 'self'`) scoped to exactly this one path — narrower than the pre-existing fully-public client-widget tier | `5d4b9fe` | `tests/test_l2_stack_graph_frame_headers.py` — pure-logic tests run and passed locally; TestClient integration tests need the full app dependency graph (not exercised in the authoring sandbox) |
| 7b | `app/api/clientops.py` (`GET /clientops/approvals`) + `automation.html` (`apContentList`) | Approvals table showed only the raw client id, no business name | Bulk `list_clients()` id→name enrichment (one call, not per-row); business name as primary label, id kept as secondary/tooltip text, honest "(unknown client)" fallback for deleted clients | `8a64e9c` | `tests/test_parity_clientops.py` — 18/18 passed locally |
| 7c | `app/api/admin_ops.py` (password-reset, onboard/scrape) + `admin_dashboard.html` (Customer 360 panel) | Onboard/scrape fired a real `force=True` re-scrape+re-seed with zero confirmation; both endpoints had zero audit trail; password-reset's backend minimum (4 chars) was weaker than the UI's (8) | Confirmation modal added for re-scrape (matching the password-reset modal's style); `delivery_ledger.log_event` audit entry added to both; backend minimum raised to 8 | `2895e97` | `tests/test_admin_client_actions_audit.py` — 7/7 passed locally |

None of 7a-7c were deployed as of this session's end — see §10 for the push/deploy blocker
and what to do about it.

### 7d. Qdrant scoped duplicate cleanup + Jiya stale-content review (2026-07-15)

**Qdrant:** a dry-run audit found exactly 8 duplicate points in `kb_main` (not the ~215,000
originally assumed — that number no longer matched reality after earlier work this session
already fixed the real large-scale duplication). All 8 were confined to two internal
RAG-quality-gate test namespaces (`ab:ragquality`, `ab:ragtest`), never customer or catalog
data. After explicit approval, the cleanup re-validated the live candidate set matched the
approved 8-point scope exactly, then deleted only those 8 point IDs (`PointIdsList`, never a
filter/namespace-wide delete). Verified: `kb_main.points_count` 1481→1473, 0 duplicate
fingerprints remaining, all 7 canonical copies retained, all 5 real niche/catalog namespaces
and `_global` unchanged, collection status stayed green, no container restart. Full
before/after evidence: `docs/QDRANT_DUPLICATE_CLEANUP_DRYRUN_2026-07-15.md` (appended, not
overwritten). Cleanup script: `scripts/qdrant_dedupe_cleanup_2026-07-15.py` — reusable if a
similar internal test-namespace duplication reappears (re-validates live scope before
deleting anything; safe to re-run, it's a no-op if nothing matches).

**Jiya stale-content review procedure:** to review a client's draft/pending content queue
without changing anything, read `data/content_queue/<client-slug>.jsonl` directly (each line
= one record: `id`, `client_id`, `date`, `type`, `title`, `caption`, `hashtags`, optional
`svg`, `status`, `created_at`) rather than relying only on the admin UI — the raw file
surfaces defects the UI summary can hide (e.g. duplicate captions across differently-labeled
items, a stale/wrong phone number baked into an SVG poster, geography mismatches, malformed
text). Build a per-item table covering: brand correctness, service relevance, area
correctness, duplicate risk, festival/date relevance, quality issues, recommended action,
whether public publishing is even possible yet (check the client's actual connected-channel
status separately — don't assume), then group into 5 buckets: ready for approval after human
review / needs editing / obsolete-or-date-expired / duplicate-redundant / blocked by missing
info. **Never** approve, reject, schedule, or publish anything while building this review —
it is a read-only pass; present the grouped findings and ask for per-item decisions using
the exact record IDs, never a blanket approval request. Example:
`docs/JIYA_CONTENT_DECISION_PACK_2026-07-15.md`.

## 7b. Agent OS + OmniRoute (operator slice — 2026-07-16)

Full runbook (20 checklists): `docs/AGENT_OS_OMNIROUTE_ADMIN_RUNBOOK.md`.
Local OmniRoute start/check: `docs/OMNIROUTE_ADMIN_GUIDE_HINGLISH.md`.

**Hinglish quick training (safe, read-only pehle):**

1. **Agent roster** — 31 AI staff `app/platform/team.py` se aate hain; specs
   `agent-os/agents/` me generated hain. Haath se spec edit mat karo — `gen_agent_os_specs.py`
   re-run karo.
2. **Routing / privacy** — `app/platform/agent_os_routing.py`. Voice, billing, security,
   CRM-PII agents OmniRoute pe **jaate hi nahi**. Marketing bulk eligible, lekin publish
   pehle approval.
3. **OmniRoute flags** — `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` dono OFF default.
   Production Docker Compose me OmniRoute service **nahi** hai (ADR-079). Local WSL
   `127.0.0.1:20128` only.
4. **Provider key** — dashboard me **aap khud** enter karoge; chat/repo me paste mat.
5. **Decision logs** — app logs me `[omniroute_decision] ok=… task=… provider=…` (PII nahi).
6. **Ek agent band** — Office pause ya uska feature gate unset; poora stack band mat karo.
7. **Jiya** — content/delivery/call buttons pe approval modal; Cancel safe; real publish
   bina explicit go-ahead nahi.

Screens: `/app/office` (staff/reliability), `/app/control-center` L4 Agent,
`/app/automation` (flags/schedule/approvals), `/app/agent-tools`. OmniRoute live badge
HTML me abhi nahi — status flags + local dashboard se verify.

## 8. Not yet walked this session (do not assume these are fine or broken)

Named in the original Phase F scope but not individually opened/tested this session:
Agent Tools / Training / Scraping / Events / Harvester / Prospects / Cadence / Sales Team AI
/ Processes / Self-Improve / Code Upgrader / RL Flywheel tabs on `/app/automation`; Social
Setup; a dedicated Integration Health page (own-brand social/WhatsApp/Meta facts cited in
§3 come from `CLAUDE.md`'s already-dated, already-verified entries, not a fresh click-
through this session); OmniRoute **dashboard browser walk** (code+docs+tests updated
2026-07-16 in §7b / `AGENT_OS_OMNIROUTE_ADMIN_RUNBOOK.md`, but live dashboard click-through
still needs the human admin on local `:20128`); Deployment/rollback UI (the mechanism was
verified via real deploys, but no dedicated rollback *button* in the admin UI was located
or tested). Treat unwalked UI tabs as unknown, not as confirmed-safe.

## 9. Escalation

- Dead/exhausted tasks, version skew, disk ≥80%, or a confirmation modal missing on a
  consequential action → fix or escalate same-day, don't let it ride.
- Anything that would require entering a password/OTP/API key, approving/publishing real
  Jiya (or any other real customer) content without an exact explicit go-ahead, or a
  destructive data operation (Qdrant cleanup, DB reset) → stop and ask the person, do not
  proceed unilaterally, per this repo's standing safety rules.

## 10. Agent-session push/deploy blocker (2026-07-15)

Commits `5d4b9fe`, `8a64e9c`, `2895e97` (§7a-7c above) exist only in the local working-tree
repo as of this session's end — they were **not pushed to GitHub and not deployed**. The
agent sandbox that authored them has no stored GitHub credentials and no SSH private key for
the VPS (both live only on the operator's own Windows machine, per this repo's established
workflow — `C:\PROGRA~1\Git\cmd\git.exe` / `C:\Users\Ratanshila\.ssh\id_rsa`). This is also
why Priority 5 (live disk/build-cache reconciliation) could only be verified at the code/
policy level, not against live VPS numbers.

To finish rolling these out: `git push` from the operator's own Windows git, then deploy each
SHA through the normal pipeline (`APP_VERSION=<sha> bash scripts/deploy_vps.sh`), then
browser-verify `/app/control-center` (L2 Stack graph should render), `/app/automation#approvals`
(business names visible), and the Customer 360 panel's Re-Scrape button (confirmation modal
appears) — the same way every earlier fix this session was verified.
