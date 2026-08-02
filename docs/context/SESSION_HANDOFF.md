# SESSION_HANDOFF - overwrite every session end

## Session objective
Launch-readiness audit → fixes execution. **3 fixes done locally (UPI guest 401, pricing lie, golden eval suite) + FULL CAMPAIGN calling unblocked LIVE on prod.**

## Live truth (probed 2026-08-02 ~08:05Z)
- `/health` = `cc88efbd` healthy production (app/worker/scheduler all `cc88efbd`, no skew after env-only recreate).
- **Calling = FULL CAMPAIGN LIVE (owner go-ahead 2026-08-02)**: `VOICE_LAUNCH_KILL=0` (was 1) · `DIAL_TEST_MODE=0` (was 1) · `VOICE_DAILY_CALL_CAP=100` (was 5) · `PLATFORM_DIAL_DAILY=100` (was 10). **LIVE proof: 3 real Vobiz calls placed** (session `S20260802-a280d841`, state `running`, call_attempts+1 on 3 leads). Daily 11:30 IST scheduler auto-dials up to 100/day (niche=all, 122 fresh-with-phone leads). Rollback = `/opt/leadgen/.env.bak-fullcampaign-20260802075851` (restore + recreate).
- Compliance spine UNTOUCHED: DND fail-closed · TRAI window 10–19 IST · AI-disclosure · consent · DLT_APPROVED=1 · phone-type gate · learned IVR blocklist · circuit breaker · 30-call training pause · recording gate (recording_ok=true) · concurrency=1. launch_status: `admin_kill_engaged=false`, `daily_cap=100`, `remaining_today=97`, `circuit_open=false`.
- Guest UPI 401 → **FIXED locally** (`optional_customer` in `customer_auth.py`, `upi_payments.py` swapped, `index.html` sends Bearer if token). Tests green. NOT deployed.
- Pricing lie → **FIXED locally** (`pricing.html:184` → "UPI; card — international customers"). Tests green. NOT deployed.
- Golden eval suite (`scripts/eval_golden.py` + `tests/test_eval_golden.py` + deploy-vps.yml step) → local verified. NOT committed/deployed.
- Key env (unchanged this session): `EVAL_GATE_HARD=1`, `ENABLE_LLM_OBS=1`, `WHATSAPP_AUTO_SEND=0`, `UPI_AUTO_ACTIVATE=1` (memory said 0 — STALE), `VOICE_LAUNCH_CAMPAIGN=1`, `REPLY_AUTO_SEND=1` (guarded).

## Owner decisions pending
1. Commit+PR local fixes (golden suite + UPI fix + pricing fix) — user kenot karna hai
2. Estique ledger proof vs reopen
3. Feed 10–30 consented prospects (autopilot queue empty)
4. Whether to enable STUDIO_ENTITLEMENT_GATE

## Safety
Compliance gates untouched. WhatsApp stays 1-click human. DLT_APPROVED=1 confirmed. Calling rollback path documented.
