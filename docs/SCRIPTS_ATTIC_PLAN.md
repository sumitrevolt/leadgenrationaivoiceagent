# scripts/ Attic Plan (R-13) — 2026-07-05

`scripts/` = 278 files ka junk drawer tha. Cleanup 2 tiers me:

## Tier-1 — DONE (is PR me, har file grep-gated zero-reference)
23 files → `scripts/attic/` (list: `git log --diff-filter=R -- scripts/attic` ya attic dir):
9× `_`-prefix temp, 3× `ci_repro*.bat`, `push_exotel_ws.bat` (removed-stack),
7× one-off repro/probe (`where2/noob_repro/probe_double_lifespan/first_call/conv_test/pro_test/brain_test`),
`deploy_si_bg.sh`, root ke `test_phase7_inline.py` + `debug_signup.py` (R-08),
aur `app/config_production.py` (R-15 — imported-nowhere dead config, DEEPGRAM refs samet).

**Kept despite test_/junk-looking naam (LIVE references mile):**
- `scripts/ws_test.py` — `leadgen-ops` skill references it
- `scripts/test_phase6_safety_gates.py` — `verify_phase6_integration.py` + phase6 docs
- `scripts/test_phase7_deterministic_loops.py` — PHASE7 guide references
- `scripts/test_features.py`, `test_gemini_key.py`, `test_gemini_paid.py`, `test_nvidia_key.py` — ops key-probes/self-tests (VPS pe manually chalte hain; pytest inhe collect nahi karta, `testpaths=tests`)

## Tier-2 — OWNER LIST-APPROVAL PENDING (bulk, ~110 files)
Categories (move karne se pehle har file same grep-gate):
- `vps_*` one-off deploy/hotfix scripts (~64) — surgical-deploy era ke artifacts
- `.bat` Windows wrappers (~50 bache) — Linux VPS/CI pe useless; par Windows-dev SOP kuch use karta hai (`run_tests.bat`, `graphify_refresh.bat` EXCLUDED — CI/skills refs)
- `deploy_*` duplicates (~12) — `deploy_now.sh` + hostinger-deploy skill = canonical; baaki candidates
- one-off `*audit*`/`smoke_*`/`check_*` jo kisi skill/prod_check se referenced nahi

**KABHI attic nahi (prod_check/CI imports):** `deep_wiring_audit`, `automation_wiring_audit`,
`cross_path_audit`, `explorer_sync`, `sync_api_docs`, `route_collision_audit`,
`env_reference_sync`, `data_store_inventory`, `queue_idempotency_audit`, `check_secrets`,
`security_scan`, `prod_check`, `run_tests.bat`.

Execute: owner bole "tier-2 attic chalao" → per-category grep-gate → batched `git mv` → prod_check green.
