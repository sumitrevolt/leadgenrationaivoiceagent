# Admin Manual Customer Call

## Goal
Owner `/app/admin` par customer ka number daal kar canonical conversational Vobiz call safely place kar sake, bina SSH/manual script ke.

Approach: existing admin-authenticated `POST /api/telephony/vobiz/stream-call` reuse hoga. Admin UI explicit phone, pitch/niche, call type aur authorization confirmation lega; request in-flight aur short cooldown me duplicate click block hoga.

## Risk
**High-risk — telephony/outbound.** Existing backend compliance chokepoint untouched rahega: promotional calls par DND/DLT/window fail-closed, AI disclosure aur opt-out existing stream path se hi. Transactional option sirf owner ke explicit known/consented confirmation ke saath.

Named rollback: `frontend/admin_dashboard.html` se `manualCallCard` + `placeManualCustomerCall` slice revert karke container hard-recreate. Koi migration/env flip nahi.

## File map
- `frontend/admin_dashboard.html` — owner form, validation, canonical API call, visible result.
- `tests/test_admin_manual_customer_call.py` — static UI contract + mocked API happy/compliance-block path.
- `docs/context/ACTIVE_WORK.md` — completed memory stream ko current GTM UI slice se replace.
- `docs/context/SESSION_HANDOFF.md` — local verification evidence and deployment status.

## Tasks
1. Add `#manualCallCard` near daily owner actions and one Customers-nav anchor.
2. Add E.164 normalization, explicit call type, consent/authority checkbox, confirm step, 20s timeout, in-flight lock and 60s same-number cooldown.
3. POST `{to,niche,call_type}` with admin bearer auth to the existing stream-call route; display placed, compliance-blocked, auth and provider errors in Hinglish.
4. Test exact route reuse, safe defaults, required controls, duplicate guard, and mocked endpoint propagation.
5. Run:
   - `.venv\Scripts\python.exe -m pytest tests\test_admin_manual_customer_call.py tests\test_vobiz.py -q`
   - `.venv\Scripts\python.exe scripts\prod_check.py`
   - `.venv\Scripts\python.exe scripts\check_secrets.py`

## Wiring
No new FastAPI route, scheduler, worker, flag, store or provider. UI calls the existing `require_admin` route; backend remains the single compliance and Vobiz placement path.
