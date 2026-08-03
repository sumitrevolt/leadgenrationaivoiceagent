# SESSION_HANDOFF - overwrite every session end

## Session objective
Cursor session: beat launch gaps after Claude/OpenCode shipped UPI+pricing+golden. **No deploy** this session unless owner asks. Avoided dirty files owned by parallel agents where possible.

## Live truth (probed ~2026-08-02 evening IST)
- `/health` = `3cbf1164` healthy (prior PR #215 deploy).
- Guest UPI LIVE: POST `/api/upi/submit` no-auth → `ok:true status:pending`.
- Pricing copy LIVE (UPI; card international).
- Calling FULL CAMPAIGN still live per prior handoff (owner go-ahead) — this session did NOT touch dial/WA flags.
- Autopilot still only Estique=`converted` until new prospects ingested.
- `STUDIO_ENTITLEMENT_GATE=1` already ON in prod container.

## This session SHIPPED (local, uncommitted unless owner commits)
1. **Proposal pricing truth** — `app/marketing/proposal.py`: default `starter` ₹1999; legacy `growth` maps → starter (no ₹2999 leak).
2. **`/login` → `/app/login`** redirect (`app/main.py`) — bare /login was 404.
3. **Inquiry → sales_autopilot feed** — `inquiry_hooks.maybe_ingest_sales_autopilot` + optional email on InquiryIn + homepage form email field. Platform leads only; `consent_basis=website_inquiry_form`.
4. **Admin `POST /api/sales-autopilot/prospects`** — operator can fill empty GTM queue with explicit consent_basis.
5. **Tests** — `tests/test_gtm_launch_fixes_2026_08_02.py` (7) + updated `test_proposal`. `prod_check` OK · secrets scan run.

## Owner next (still needed for 2nd customer)
1. Commit/PR/deploy these Cursor fixes when ready.
2. Feed 10–30 consented prospects via `POST /api/sales-autopilot/prospects` OR wait for form inquiries with email.
3. WAHA QR → `WAHA CONNECTED`.
4. Estique ledger proof vs reopen.
5. Do not flip `WHATSAPP_AUTO_SEND`.

## Safety
Compliance gates untouched. No WA auto-send / dial-cap change this session. Parallel agents may still have dirty work in admin_dashboard / sales_autopilot store+eligibility — coordinate before commit.
