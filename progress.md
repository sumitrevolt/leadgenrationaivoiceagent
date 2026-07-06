# progress.md — Loop Engineer Ledger (LeadGenAI)

> Per-loop memory for Loop Engineer mode (see `CLAUDE.md §0` + `docs/LOOP_ENGINEER.md`).
> **Read this + CLAUDE.md before starting any loop** — continue, don't repeat.
> Append a `## Loop Run` block after every loop. Deep knowledge → `memory/`;
> dated narrative → `docs/SESSION_LOG.md`. Newest loop at the bottom.

## Active Program (multi-loop)
**AI-Marketing agents — 40+ improvements** → `docs/superpowers/plans/2026-07-06-agents-marketing-improvement-loops.md`. Run Wave 1 (Reliability + Cost + Observability) first; ~25 safe loops autonomous, PAUSE & ask on Wave-4 gated items. Merge per wave to `main`; user deploys via `leadgen-ops`.

---

## Loop Run
- **Date:** 2026-07-06
- **Goal:** Customer dashboard "user-friendly nahi" → restructure IA (all 3 forks).
- **Files inspected:** `frontend/customer_{dashboard,marketing,voice}.html`, `app/api/customer_dashboard*.py`, `app/main.py` routes, `scripts/prod_check.py`, `deep_wiring_audit.py`, existing frontend test pattern (`tests/test_office_map_frontend.py`).
- **Files changed:** `frontend/customer_{dashboard,marketing,voice}.html` (view engine + tagging + nav + focused Home), `tests/test_customer_{dashboard,marketing,voice}_frontend.py` (new guards), `docs/superpowers/specs/2026-07-05-customer-dashboard-ux-redesign-design.md`, `docs/superpowers/plans/2026-07-05-customer-dashboard-ux-redesign.md`.
- **Tests/checks run:** 38 static frontend+builder guards (green) · `node --check` inline JS (green) · browser-driven verification in Chrome (view isolation, gating per fork, chart redraw, mobile nav) · `prod_check.py` PASS (1030 routes, 0 wiring gaps) · 2× `/health` = `environment:production` 200.
- **Result:** SHIPPED. Long-scroll → focused mobile-first Home + toggle-able views (Home/Leads/Content/Account; voice = 3-view). Merged PR #29 → main (`7854828`), deployed to VPS, redesign baked in live container (all 3 forks).
- **Failures found + fixed:** (1) `.sec-title{display:flex}` leaked section headers across views → view-hide rule needs `!important`. (2) Chart.js 0×0 in hidden container → `resizeCharts()` redraws from `window._VIEW` (also fixed a pre-existing "Pura hisaab"-expand bug). (3) pre-JS blank flash → static `data-active-view="home"`. (4) `prod_check` wiring gate flagged dangling `href="#view-*"` anchors → changed to `href="#"`.
- **Fix applied:** all four fixed + re-verified before ship.
- **Next step:** see Loop Run below.

## Loop Run
- **Date:** 2026-07-06
- **Goal:** Install persistent **Loop Engineer mode** so future sessions self-run inspect→fix→verify→record loops.
- **Files inspected:** existing `CLAUDE.md` (lean, token-disciplined), `AGENTS.md`, `docs/` layout.
- **Files changed:** `docs/LOOP_ENGINEER.md` (new full spec), `CLAUDE.md` §0 (lean pointer section), `AGENTS.md` (re-synced byte-copy), `progress.md` (this ledger).
- **Tests/checks run:** `diff -q CLAUDE.md AGENTS.md` (byte-identical) · `grep LOOP ENGINEER MODE` present in both.
- **Result:** Loop Engineer mode wired. On `/loop`-family triggers, future sessions read `progress.md` + CLAUDE.md, run gated loops, and append here. Harmonized to run INSIDE existing compliance/secrets/no-auto-deploy gates.
- **Failures found:** none.
- **Fix applied:** n/a.
- **Next step / Next Loop candidates** (Planner picks, reconcile with `CLAUDE.md ## Current State` = GTM 0→1 / mid-funnel sprint):
  1. **Onboarding + auth E2E** — drive signup → login → tenant-isolated dashboard load; verify no cross-tenant leak. (top of generic priority order) → **started, see next loop.**
  2. **Office HQ improvement panel** (`2421c47`) — deploy still pending per Current State.
  3. **Scheduler health** — confirm Celery beat + 24 staff jobs + dead-man trio alive; `redis-cli llen celery` sane.

## Loop Run
- **Date:** 2026-07-06
- **Goal:** Onboarding + auth + tenant-isolation — verify end-to-end wiring/safety and close the highest-impact gap.
- **Files inspected:** (read-only audit) `app/api/customer_auth.py`, `app/api/public_site.py` (signup), `app/api/customer_dashboard.py` + `customer_dashboard_builders.py` (`_build_from_db`), `app/middleware/tenant.py`, `app/api/billing.py` (`_authed_client_id`), `customer_marketing_studio.py` (91 routes), `app/utils/auth.py`/`admin.py` (JWT), + existing tests (portal/idor/isolation/ownership/office).
- **Files changed:** `tests/test_customer_dashboard_isolation.py` (NEW — test-only, zero prod risk).
- **Tests/checks run:** new test 2 pass · genuineness proof (both leads seeded, client_a sees only its own) · isolation+auth bundle 52 pass (`test_customer_dashboard_isolation`/`test_customer_portal`/`test_billing_auth_idor`/`test_client_lead_isolation`/`test_lead_override_ownership`/`test_customer_office`) · `prod_check.py` = ALL CHECKS PASSED.
- **Result:** **VERIFIED SAFE.** Onboarding (`/start`→`/pricing`→`/api/public/signup` → auto-login JWT → working dashboard) works; auth = pbkdf2-sha256 + 60-min customer JWT (`sub`=client_id, IDOR-safe); tenant isolation resolves current-customer only from `sub`, never request input, and `_build_from_db` DB-filters leads by `assigned_to==client_id`. **Closed the one real gap:** §5 top invariant ("lead cross-client leak KABHI nahi") had NO read-side dashboard regression test — now guarded with a real-SQLite two-client test.
- **Failures found:** (audit, ranked) 1) no read-side dashboard isolation test → **FIXED (this loop).** 2) 2FA fail-open (`customer_auth.py:253-266`, try/except pass) → deliberate policy, NOT a drop-in fix — revisit decision. 3) auth-store JSONL full-rewrite SPOF (`customer_auth.py:72-81`) → reliability task (atomic tmp+rename), not a quick fix. Also: customer logout is cosmetic (stateless JWT, no revocation) — mitigated by 60-min expiry.
- **Fix applied:** added the read-isolation guard; verified genuine (fails if the filter regresses).
- **Next step / Next Loop candidates:**
  1. **Auth-store atomicity** (#3 above) — replace non-atomic JSONL rewrite with tmp-write + `os.replace`; verify with a crash-mid-write unit test.
  2. **2FA fail-open decision** — surface to user: fail-open (current, availability) vs fail-closed (security); code the chosen one + test.
  3. **`access_token: null` silent-success** on signup (`public_site.py:613-619`) — assert frontend handles null token, or make signup 500 if auto-login token can't be minted.
  4. Office HQ panel `2421c47` deploy · Scheduler health check (carried over).
