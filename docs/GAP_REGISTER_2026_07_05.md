# GAP REGISTER — living tracker (seeded 2026-07-05)

> **Kya hai:** `docs/SYSTEMATIZATION_AUDIT_2026_07_05.md` ke saare gaps ka LIVING tracker.
> Status YAHAN update hota hai (audit doc frozen snapshot hai). Har fix apne phase ki approval pe.
> Rules: surgical-only (additive/flag-gated), har item = alag commit, verify gates green
> (`prod_check.py` + `check_secrets.py` + targeted pytest), full pytest KABHI nahi (team_pulse hang).

**Status values:** `OPEN` · `IN-PROGRESS` · `DONE (sha)` · `USER-CONFIRM` (owner decision chahiye) · `WONT-FIX (reason)`

## Phase 1 — zero-behaviour-change hygiene (approved 2026-07-05)

| ID | Gap | Files | Risk | Status |
|---|---|---|---|---|
| R-01 | 6 registry-invisible flags flags-UI me untoggleable (`LLM_COUNCIL`, `CUSTOMER_OFFICE`, `ADMIN_OFFICE`, `SESSION_MEMORY`, `DLT_APPROVED`, `PROMETHEUS_HTTP_METRICS`) | `app/api/automation_flags.py` | LOW (list-append only) | IN-PROGRESS |
| R-02 | Duplicate-route runtime check flag-OFF mounts nahi dekh sakta — static guard missing | NEW `scripts/route_collision_audit.py` + `scripts/prod_check.py` wiring | LOW (FAIL sirf exact static dup pe; prefix overlap = INFO) | IN-PROGRESS |
| R-03 | `.env.example`: ~45 dead removed-stack keys + critical keys (`ADMIN_API_KEY`, `ADMIN_TOTP_SECRET`, …) undocumented | `.env.example` | LOW (example file; compose `.env` use karta hai) | IN-PROGRESS |
| R-04 | 3 competing doc indexes; HANDOFF.md = single master banana | `docs/ENTERPRISE_DOC_INDEX.md` + `docs/RESEARCH_DOCS_INDEX.md` banners; `docs/archive/` | LOW (banners additive) | IN-PROGRESS |
| R-05 | Root stale reports (`FIX_PLAN.md`, `PRODUCTION_AUDIT_REPORT.md`, `TEST_RESULTS.md`) | `git mv` → `docs/archive/` (grep-gated) | LOW | IN-PROGRESS |

## USER-CONFIRM — owner ka decision chahiye (koi action nahi hua)

| ID | Gap | Options | Status |
|---|---|---|---|
| R-06 | **`prospect_leads_export.csv` 238KB lead-PII git-tracked (history me bhi)** | (A) `git rm` + .gitignore — HEAD saaf, history me PII rahega · (B) `git filter-repo` history purge + force-push — POORA saaf par har clone + VPS coordinate karna padega | USER-CONFIRM |
| R-07 | Root `.xlsx` ×2 (`LeadGen_Costing_Model`, `Niche_Pricing_Research`) — business assets repo me | (A) rehne do · (B) Drive me le jao + `git rm` | USER-CONFIRM |
| R-08 | `debug_signup.py`, `test_phase7_inline.py` root pe | Phase-2 attic list me propose honge — abhi untouched | USER-CONFIRM |
| R-09 | `TASKS.md` root pe — agent-workflow surface ho sakta hai | Verify-first; grep-gate ke baad hi archive propose | USER-CONFIRM |

## Phase 2 — guards + consolidation (approval pending)

| ID | Gap | Approach | Status |
|---|---|---|---|
| R-10 | 305 undocumented env keys — koi ENV reference nahi | `scripts/env_reference_sync.py` → autogen `docs/ENV_REFERENCE.md` (template: `sync_api_docs.py` AUTO-markers + `--check`; INFO-drift line prod_check me `check_api_docs_drift` `:261-277` pattern se) | OPEN |
| R-11 | `tests.yml` overlap (10-file narrow gate push/PR pe abhi bhi fire hota hai) | Demote to `workflow_dispatch`-only (`test.yml` ke "Legacy" comment precedent se) — **PEHLE owner GitHub branch-protection required-checks verify kare** warna merges block | OPEN |
| R-12 | Deploy test-gated nahi (`deploy-vps.yml` pytest `continue-on-error`) | Hard-gate flip — separate owner decision (team_pulse hang resolve hone ke baad safest) | OPEN |
| R-13 | `scripts/` 278-file junk drawer | Categorized attic move-list generate (reference-grep column ke saath); execute SIRF owner list-approval pe. Exclusions: prod_check-imported (`deep_wiring_audit`, `automation_wiring_audit`, `cross_path_audit`, `explorer_sync`, `sync_api_docs`), `run_tests.bat`, `graphify_refresh.*` | OPEN |
| R-14 | 7 misplaced test files (6 `scripts/`, 1 root) — pytest collect nahi hote | Per-file: real tests → `network`/`timeout` markers + `tests/` me; live-key probes (`test_gemini_key.py`, `test_nvidia_key.py`, `test_gemini_paid.py`) → attic. Bulk `mv` KABHI nahi (CI blocking suite me add hota hai) | OPEN |
| R-15 | `app/config_production.py` — imported-nowhere dead file (DEEPGRAM refs samet) | Attic candidate (Phase-2 list me) | OPEN |
| R-16 | 38 stale-stack docs; active-ops offenders mislead karti hain (`PRD.md`, `API.md`, `PROJECT_SOP.md`, `PROJECT_HANDOFF.md`, `OPERATIONAL_RUNBOOKS.md`, billing runbook/workflow, `AGENT_SYSTEM_PROMPTS.md`) | Active-ops docs me removed-stack refs fix; historical docs (SESSION_LOG/ADR/CHANGELOG) untouched; zero-reference stale docs → `docs/archive/` (per-file grep gate). ⚠️ `SESSION_ACTIVATION_RUNBOOK_2026_06_16.md` move-PROHIBITED (`runbook_drift.py:24` hardcode) | OPEN |
| R-17 | 164 jsonl data-stores ka koi registry/schema inventory nahi (PII/auth stores samet) | Data-store inventory doc (path, owner module, PII?, retention, backup) — migration NAHI (policy: when-volume) | OPEN |
| R-18 | `ruff` lint non-gating (`\|\| true` in ci.yml) | Baseline-fix + gate flip = separate decision (bade diff ka risk) | OPEN |

## Phase 3 — feature completeness (per-item approval)

| ID | Gap | Approach | Status |
|---|---|---|---|
| R-19 | `app/api/leads.py` — no UI (growth se superseded?) | Decision table: UI tab YA deprecation note. Pehle VPS pe `scripts/route_usage_audit.py --access-log` (≥30 din) | OPEN |
| R-20 | `app/api/campaigns.py` — no UI (admin_ops se superseded?) | same as R-19 | OPEN |
| R-21 | `app/api/niche_db.py` — **no UI + no tests** | same + import-smoke tests | OPEN |
| R-22 | `app/api/widgets.py` 13 endpoints — admin config tab nahi | UI tab (automation-control-center tab pattern) | OPEN |
| R-23 | `app/api/conversion.py` admin widget-form builder — no UI | UI tab | OPEN |
| R-24 | `app/api/booking.py` — admin tab nahi | UI tab ya calendar-page wiring | OPEN |
| R-25 | Customer webhook `payment.received`/`subscription.*` emits documented-not-wired | Additive emit calls behind existing `CUSTOMER_WEBHOOKS` flag (billing-webhook stabilization ke baad) | OPEN |
| R-26 | `lead_scraper/linkedin.py` placeholder | **ToS-REFUSED tombstone** (no-callers verify karke) — KABHI implement nahi | OPEN |
| R-27 | Plivo stub (`carrier_router.py:149-179`) + ARI stub (`sip_handler.py:339`) | Explicit tombstone docstrings | OPEN |
| R-28 | `zoho_crm.py` vs `hubspot.py` duplicate `ZohoCRMIntegration` | Canonical pick + re-export shim (no file moves) | OPEN |
| R-29 | 5 untested dormant engines (`gtm_targeting`, `udyam_pipeline`, `gap_analyzer`, `icp_generator`, `niche_db`) | Import-smoke + flag-OFF-inertness tests minimum | OPEN |

## Phase 4 — deferred structural (EXPLICIT opt-in only — risk notes ke bina start nahi)

| ID | Gap | Risk note | Status |
|---|---|---|---|
| R-30 | `main.py` 78 inline frontend routes → pages-router extraction | Route-registration ORDER change = first-route-wins landmine; before/after route-snapshot diff harness mandatory | PARKED |
| R-31 | 672 `os.getenv` → `settings` migration | 232-file blast radius; getenv=live vs settings=boot-frozen — VPS flag-flip-without-redeploy workflow tod sakta hai | PARKED |
| R-32 | Godfile splits (`vobiz_stream.py` 3023, `telecaller_brain.py` 2811) | Voice-unsafe per existing ADR — deferred hi rahega | PARKED |
| R-33 | jsonl → Postgres (164 stores incl PII/auth) | Policy = migrate-when-volume; R-17 inventory pehle | PARKED |

---
*Seeded: 2026-07-05 session (3-audit consolidation). Update protocol: status change = is file me edit + jis commit se fix hua uska sha.*
