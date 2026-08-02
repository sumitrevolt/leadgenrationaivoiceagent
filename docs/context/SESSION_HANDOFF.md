# SESSION_HANDOFF - overwrite every session end

## Session objective
Launch-readiness audit → fixes execution → **SHIPPED + DEPLOYED**. 3 fixes (UPI guest 401, pricing lie, golden eval suite) now LIVE on prod via PR #215, deploy `3cbf1164`.

## Live truth (probed 2026-08-02 ~10:40Z)
- `/health` = `3cbf1164` healthy production (app/worker/scheduler/worker-heavy/worker-video all `3cbf1164`, no skew after deploy + env-only recreate).
- **Calling = FULL CAMPAIGN LIVE (owner go-ahead 2026-08-02)**: `VOICE_LAUNCH_KILL=0` · `DIAL_TEST_MODE=0` · `VOICE_DAILY_CALL_CAP=100` · `PLATFORM_DIAL_DAILY=100` (all confirmed inside container). LIVE proof: 3 real Vobiz calls placed 2026-08-02 (session `S20260802-a280d841`). Daily 11:30 IST scheduler auto-dials up to 100/day.
- **Deploy gate note (2026-08-02)**: `prod_check.py --deployment` requires `VOICE_LAUNCH_KILL=1` (TRUE_TOKEN) — FULL CAMPAIGN kill=0 pe deploy REFUSED by design (commit `cb5e19a7`). Safe flow used: `.env` backup → kill=1 → deploy → verify → kill=0 restore + env-only recreate. Backups: `/opt/leadgen/.env.bak-predeploy-kill0-20260802_102240` (kill=0 pre-deploy) · rollback env `/opt/leadgen/.env.bak-fullcampaign-20260802075851`.
- Compliance spine UNTOUCHED: DND fail-closed · TRAI window 10–19 IST · AI-disclosure · consent · DLT_APPROVED=1 · phone-type gate · learned IVR blocklist · circuit breaker · 30-call training pause · recording gate · concurrency=1. launch_status: `admin_kill_engaged=false`, `daily_cap=100`, `circuit_open=false`.
- UPI guest 401 → **DEPLOYED** (`optional_customer` in `customer_auth.py`, `upi_payments.py` swapped, `website/index.html` sends Bearer if token).
- Pricing lie → **DEPLOYED** (`pricing.html` → "UPI; card — international customers").
- Golden eval suite (`scripts/eval_golden.py` + `tests/test_eval_golden.py` + advisory deploy-vps.yml step) → **DEPLOYED**.
- Key env: `EVAL_GATE_HARD=1`, `WHATSAPP_AUTO_SEND=0`, `UPI_AUTO_ACTIVATE=1`, `VOICE_LAUNCH_CAMPAIGN=1`, `REPLY_AUTO_SEND=1` (guarded).

## Owner decisions pending
1. WAHA session restart + QR scan → `WAHA CONNECTED`.
2. Estique ledger proof vs reopen.
3. Feed 10–30 consented prospects (autopilot queue empty).
4. Whether to enable STUDIO_ENTITLEMENT_GATE.

## Safety
Compliance gates untouched. WhatsApp stays 1-click human. DLT_APPROVED=1 confirmed. Calling rollback path documented. Deploy kill-gate bypass NOT performed — safe kill=1/0 cycle used instead.
