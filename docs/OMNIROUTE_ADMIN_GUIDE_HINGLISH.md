# OmniRoute Admin Guide — Hinglish

_Last verified: 2026-07-14._

## Abhi kya working hai

OmniRoute local WSL gateway v3.8.46 par chal raha hai. Dashboard/API port 20128 aur
LiveWS port 20129 loopback par hai. Groq aur Mistral ke sanitized coding requests verify
ho chuke hain. 2048 MB memory setting aur fresh-tab WebSocket stability bhi verified hai.

Yeh customer production traffic ke liye ON nahi hai. Jiya ya kisi aur customer ka
phone, WhatsApp, payment, lead ya private business data OmniRoute ko nahi bhejna hai.

Operator runbook (daily/weekly + 20 checklists): `docs/AGENT_OS_OMNIROUTE_ADMIN_RUNBOOK.md`.
Per-agent eligibility: `app/platform/agent_os_routing.py` (voice/billing = forbidden).

## Daily start/check

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-leadgen-dev.ps1
powershell -ExecutionPolicy Bypass -File scripts\omniroute-check.ps1
```

Dashboard: `http://127.0.0.1:20128`

Fresh stability check:

```powershell
wsl.exe bash -lc "OMNI_HEALTHGUARD_WINDOW_SECONDS=20 bash /mnt/c/Users/Ratanshila/Documents/leadgenrationaiagent/scripts/omniroute-healthguard.sh"
```

Expected: single process, v3.8.46, normal reconnect count. Dashboard band ho to active
WS clients zero hone chahiye. Reconnect churn aaye to purane OmniRoute tabs close karke
sirf ek fresh tab kholo.

## Provider rules

- Groq/Mistral: sanitized internal coding routes ke liye verified.
- Gemini: connected hai, lekin retired model ID active route mein use nahi hota.
- OpenCode Free/DuckDuckGo: customer PII ke liye blocked; production fallback nahi.
- OAuth/API key/OTP admin khud dashboard mein enter karega—chat mein kabhi nahi.
- `OMNIROUTE_ENABLED` production mein OFF hi rakho.

## Agar gateway down ho

LeadGen app, login, dashboard, billing, scheduler aur workers independent hain. Launcher
dobara chalao; provider/customer routing ko bypass ya force-enable mat karo.

Engineering details: `docs/OMNIROUTE_ENGINEERING_RUNBOOK.md` aur `docs/omniroute/`.
