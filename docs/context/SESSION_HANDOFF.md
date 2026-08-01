# SESSION_HANDOFF - overwrite every session end

## Session objective
Fix WAHA QR (provider) + Estique credential compromise + prepare payment. Soak waived. No app redeploy.

## Outcome — WAIT (owner scan + private password reset + PAID)
- Prod SHA `3c843517` (app untouched this wave; WAHA-only stack refreshed)
- UPI (fresh-probed): `UPI_AUTO_ACTIVATE=1`, clients=`81bd0bbe501d` only; jiya/other refuse; Estique unpaid rows=0
- Estique login: treated compromised → prod hash invalidated (random rotate, never printed). Owner must private-reset. Never request password/OTP in chat.
- WAHA: pulled fresh `devlikeapro/waha:latest` (container created 2026-08-01), session wiped once, status **`SCAN_QR_CODE`**, real PNG QR 5398 bytes (292×292). `/app/whatsapp`=200. `WHATSAPP_AUTO_SEND=0`. restart=0 oom=false. No STARTING/FAILED flap after fix.
- Post-connect canary dest: `***4977`. Suppressed: `***2607`.

## Owner actions (exact)
1. Pre-open phone WhatsApp → Linked devices → Link a device (scanner waiting). Then open https://leadsgenai.in/app/whatsapp → scan QR → reply `WAHA CONNECTED`.
2. Privately reset Estique portal password (Forgot password on `/app/login` or admin set-password). Do not paste password/OTP in chat.
3. After reset only: log in Estique portal → Billing ₹1,999 → real UPI ref → reply `PAID`. Do not share password or OTP.

## After owner replies
- WAHA CONNECTED → WORKING verify → unlisted+suppressed zero provider → AUTO=1 temp → one `***4977` canary + WAHA msg id → leave AUTO only if boundaries pass else restore 0.
- PAID → signed ref + activate `81bd0bbe501d` only + one invoice/ledger + replay no dup + browser paid. Never manual-mark paid.

## Safety
Soak waived. No app redeploy unless code change. Do not raise dial. Credential never stored/logged/committed.
