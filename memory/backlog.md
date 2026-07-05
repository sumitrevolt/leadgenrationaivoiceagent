# Backlog — parked ideas WITH the why (so context isn't lost)

Schema: `[DATE parked] Idea — WHY it matters | what unblocks it`

[2026-06-2X] **Own telephony stack (P3)** — cost ladder Plivo ₹0.60 → Vobiz ₹0.45 → operator-direct ₹0.30-0.40/min; at scale = biggest COGS lever | Plan in `docs/superpowers/plans/PENDING_PLANS.md`; needs volume + DLT.
[2026-06-1X] **Missed-call auto-callback** — classic Indian lead-capture pattern, zero-DLT inbound | Vobiz DID + webhook (user paperwork).
[2026-06-1X] **GBP API auto-post** — Google Business posts = highest-ROI local-marketing channel | Google ~60-din API approval (user applied?).
[2026-06-1X] **Meta FB/IG auto-posting** — completes social automation promise | Meta app-review (user action).
[2026-06-1X] **HA / 2nd server** — single-VPS SPOF; warm-DR probe already wired | user spend decision.
[2026-07-02] **Enterprise-audit follow-ups** — k6 load run, SLO burn-rate slice, live alembic verify, trivy enforce | audit scored SLO 3/Capacity 2/DB-mig 5/Supply 5 — these lift the weak domains.
[2026-07-03] **Enable-everything Tier 3+4** — remaining flags council-reviewed, value on the table | user go-ahead only (Tier 1+2 already LIVE).
[2026-07-03] **Office HQ Tier-2/3 ideas (22-item ranked)** — engagement/ops value | spec in `docs/superpowers/specs/` (office action batch).
[2026-06-29] **RL flywheel graduation** — Thompson/contextual/OPE deferred behind gate; Phase-0 logging running | needs reward-volume + eval_gate-live.
[2026-06-29] **Voice fine-tune pipeline ramp (50→200→1500/day)** — own telecaller data flywheel (~45k recs/mo at scale) | DLT + Vobiz balance + platform_dial re-enable conditions (ADR-019).
[2026-06-20] **vobiz_stream refactor** — last god-file, deferred as voice-unsafe | needs live-call regression harness first.
[2026-06-21] **P4-3 eval_gate-live + ear-test** — last SWARA roadmap item | manual listening session.
[2026-07-04] **WAHA QR scan** — self-host WhatsApp engine ready, session dormant | user scans QR once.
[2026-06-16] **payment.received / subscription.* webhook emits** — customer-webhook hooks documented, not wired | wire after billing webhook handlers stabilize.
[2026-07-04] **STUDIO_ENTITLEMENT_GATE flip** — studio tools entitlement enforcement | user go-ahead.
[2026-07-05] **`.env.example` + `pyproject.toml` drift cleanup** — ~~.env.example~~ SHIPPED 2026-07-05 (ADR-023 Phase 1: dead keys removed + 6 critical added); bacha: `pyproject.toml` stale paid-stack pins | small PR; keep requirements.lock.txt authoritative.
[2026-07-05] **Systematization Phase 2-4** — MOSTLY SHIPPED same-day (ADR-024, PR #28): R-10/13-tier1/14/15/16/17/18-partial/26/27/28/29 DONE. BACHA: R-11 tests.yml demote (owner: branch-protection required-checks pehle dekho) · R-12 deploy hard-gate flip (ci tests job ke pehle green ke baad; timeout 15→30 bhi) · R-13 tier-2 attic (~110 files, `docs/SCRIPTS_ATTIC_PLAN.md` approve karo) · R-19..24 router UI-or-deprecate (VPS access-log data + UI sessions) · R-25 webhook emits (billing-stabilization precondition) · R-34 legacy 19 tasks idempotent (per-queue batches) · R-37 gap_analyzer synonym-normalise fix (chhota) · R-38 niche_db docstring · R-06 history purge (owner op) · Phase 4 R-30..33 PARKED (ADR-backed) | tracker `docs/GAP_REGISTER_2026_07_05.md`.
[2026-07-05] **Make full pytest CI-blocking** — currently continue-on-error; regressions can reach main | fix team_pulse-area hang first, then flip gate in `deploy-vps.yml`.
[2026-07-05] ~~**Prospect-store purge + harvester ingest gating**~~ — SHIPPED 2026-07-05 (ADR-022): `HARVEST_INGEST_VALIDATION` gate DEFAULT ON + `scripts/purge_junk_prospects.py`. Bacha: VPS pe purge run (deploy ke baad, `--apply`; home_loans ke liye `--niche home_loans` consider).
[2026-07-04] **POSTHOG_API_KEY + .codex key rotate** — analytics wired-but-off; old stitch key revoke provider-side | user actions.
