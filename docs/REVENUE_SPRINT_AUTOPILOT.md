# Revenue Sprint Autopilot — ₹5L in 7 days (Hermes Desktop)

> Owner-gated revenue sprint engine. It drives the **owner's Hermes Desktop CLI**
> (`hermes kanban swarm`) to launch one sprint cycle of workers → verifier →
> synthesizer. It only **DRAFTS** outreach for owner 1-click review; it never sends
> and never automates money. Compliance gates are never relaxed.

## What this is

| Key | Value |
|---|---|
| Goal | ₹5,00,000 in 7 days (start 2026-08-22) |
| Day of sprint now | `python scripts/revenue_sprint_engine.py --status` → DAY x/7 |
| Driver | Hermes Desktop CLI (local Windows) → `hermes kanban swarm` |
| Cycle graph | 3 workers (`sales` / `mercury` / `operations`) → verifier (`sentry`) → synthesizer (`commander`) |
| Data probe | `scripts/leadgen_daily_brief.py` (read-only SSH → prod DB/health) |
| State | `data/sprint_state.json` (repo-tracked for the owner machine) |
| Roster/API (repo) | `HERMES_CONTROL_PLANE.md`, `HERMES_AGENT_ROSTER.yaml`, `app/api/revenue_sprint.py` |

## Files

- `scripts/revenue_sprint_engine.py` — the autopilot (cycle manager). Uses
  `HERMES_CLI` / `SPRINT_STATE_FILE` / `SPRINT_BRIEF` env overrides; auto-discovers
  the Hermes CLI under `%LOCALAPPDATA%\hermes`.
- `scripts/leadgen_daily_brief.py` — read-only prod brief (SSH → docker → psql),
  used by the swarm goal so the bots act on live numbers.

## Run (owner's Windows machine, from repo root)

```bat
.venv\Scripts\python.exe scripts\revenue_sprint_engine.py --status    :: state + cycle status
.venv\Scripts\python.exe scripts\revenue_sprint_engine.py --dry-run   :: what would launch (no-op)
.venv\Scripts\python.exe scripts\revenue_sprint_engine.py --tick      :: normal tick (launch if prev cycle done)
.venv\Scripts\python.exe scripts\revenue_sprint_engine.py --force     :: launch next even if current not done (recovery)
```

## Scheduling

The engine is a **no-agent cron job**: it checks whether the previous cycle's
synthesizer is done; if yes it launches the next cycle, if no it waits (~4h).
Schedule it on the owner machine (Hermes cron or Windows Task Scheduler), e.g.
every 4 hours:

```bat
:: example Windows Task Scheduler action (daily-ish cadence)
python C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\scripts\revenue_sprint_engine.py --tick
```

When `day > 7` the engine prints `SPRINT ENDED` and becomes a no-op — that is the
owner-review boundary (final summary with the owner).

## GUARDRAILS (baked into every cycle — never relax)

- NO bulk / cold WhatsApp auto-sends — drafts only, owner 1-click review.
- Email volume max 25/day.
- Outbound calling ONLY via the VPS scheduler (DND fail-closed, TRAI window untouched).
- Payment / UPI confirmations are OWNER-ONLY — never automate money steps.

Changing any of these = **ABORT**, not a fix (existing compliance-gate invariant).

## Owner gates (untouched by this engine)

- Hot Queue `/app/inbox` 1-click UPI follow-ups = owner action (PR #430 UPI cards).
- Jiya combo-upsell / Kamal inputs drafts = owner WhatsApp 1-click (WAHA live).
- Money state today: see `--status` + `scripts/leadgen_daily_brief.py`.

## Related

- `7_DAY_REVENUE_PLAN.md` — day-by-day plan (Day 0 = truth/repair … Day 7).
- `REVENUE_BLOCKERS.md` — ranked blockers; this engine targets outreach/pipeline.
- `HERMES_CONTROL_PLANE.md` — Hermes orchestration layer + next directives.
