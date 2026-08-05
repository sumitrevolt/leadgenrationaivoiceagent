# SESSION_HANDOFF — 2026-08-05 admin manual customer call

## Production truth carried forward
- **Prod `/health` = `3235b9bc`** (`environment:production`) — PR #252 memory stack/OKF lineage.
- `VOICE_LAUNCH_KILL=0` · `PLATFORM_DIAL_DAILY=1` · `PLATFORM_DIAL_LIMIT=100`; memory/OKF ingest flags stay OFF.
- This session did **not** commit, push, deploy, flip env, or place a real call.

## Local slice
- `/app/admin` now shows **📞 Customer ko AI se call karayein** near the daily owner flow plus Customers-nav shortcut.
- Fields: phone; pitch (`ai_marketing` default); explicit transactional/promotional relation; owner confirmation.
- Canonical `POST /api/telephony/vobiz/stream-call` reused with admin bearer auth. No second route/provider/scheduler.
- Safety: phone normalization; explicit consent choice; confirmation dialog; 20s timeout; no automatic retry; in-flight lock; persisted 60s same-number cooldown; visible auth/provider/compliance errors.
- Files: `frontend/admin_dashboard.html`, `tests/test_admin_manual_customer_call.py`, `docs/plans/2026-08-05-admin-manual-customer-call.md`.

## Evidence
- `pytest tests/test_admin_manual_customer_call.py tests/test_vobiz.py -q` → **22 passed**.
- `pytest tests/test_admin_nav_ia_groups.py tests/test_admin_nav_ia_cleanup.py -q` → **19 passed**.
- `scripts/prod_check.py` → **PASS**, 1266 routes, 49 pages / 0 gaps, automation 0 gaps.
- `scripts/check_secrets.py` → **PASS**, no secrets detected.
- `git diff --check` scoped files → **PASS**.
- Browser snapshot + screenshot confirmed visible, responsive form and accessible labels at local `/app/admin`.

## Next exact action
Owner review → explicit commit/PR/deploy request → canonical `deploy_vps.sh` under kill fence → `/health` + admin-login canary. Do not live-test with a phone until voice health is known good.
