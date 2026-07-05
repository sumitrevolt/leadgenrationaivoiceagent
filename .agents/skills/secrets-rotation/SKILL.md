---
name: secrets-rotation
description: Secrets inventory + rotation cadence + leak-response runbook — .env keys (LLM providers, Gemini 9-key pool, SMTP, Vobiz, Stripe, GMaps), no-restart rotation paths, check_secrets.py, deploy-keys. Use jab key rotate/revoke karni ho, leak suspect ho, naya provider key add ho, ya quarterly security hygiene chale.
---

# Secrets Rotation (static key = ticking liability)

> Enterprise audit skill. Rule of house: **secrets SIRF `.env`** (gitignored), kabhi committed file/CLAUDE.md/scripts me nahi. `scripts/check_secrets.py` `/verify` step-4 me wired (false-positive = line pe `nosecret`). Pehle `context-first`.

## Secrets inventory (rotation cadence)
| Secret | Rotation | Last-rotated | No-restart path? |
|---|---|---|---|
| LLM keys: `MISTRAL/GROQ/CEREBRAS/GEMINI/SAMBANOVA/NVIDIA/OPENROUTER_API_KEY` | 90d ya leak pe | unknown (baseline 2026-07-02) | NAHI — .env + app recreate |
| **Gemini voice pool (9 keys)** | rolling — 429 pe auto `advance_key` | unknown (baseline 2026-07-02) | HAAN — admin "Voice Keys" page / `POST /api/admin/voice/gemini-keys` (per-key Google-validate, `data/voice_gemini_keys.json`) |
| SMTP `admin@leadsgenai.in` (Hostinger) | 180d | unknown (baseline 2026-07-02) | NAHI |
| `VOBIZ_AUTH_ID/TOKEN` | provider dashboard se | unknown (baseline 2026-07-02) | NAHI |
| Stripe keys + webhook secret | 90d (webhook secret SAATH rotate) | unknown (baseline 2026-07-02) | NAHI |
| Google Maps (Places New) | 90d + API-restriction check | unknown (baseline 2026-07-02) | NAHI |
| `FASTAPI_MCP_TOKEN` | 90d — **Arya MCP-engineer hourly :40 me 90d rotation reminder wired** | unknown (baseline 2026-07-02) | NAHI |
| UPI VPA (`upi_config`) | change pe | unknown (baseline 2026-07-02) | HAAN — `POST /api/admin/upi/configure` |
| VPS SSH key (`id_rsa`) + GitHub deploy-key `VPS-LeadsGen` | yearly ya staff change | unknown (baseline 2026-07-02) | NAHI |
| Customer webhook HMAC (H.1) | customer-initiated re-key | unknown (baseline 2026-07-02) | HAAN — customer portal |
| `SENTRY_DSN`, `POLLINATIONS_API_KEY` (`pk_`=client-safe, `sk_`=server-only proxy!) | leak pe | unknown (baseline 2026-07-02) | NAHI |
| `HOSTINGER_API_TOKEN` (DNS API — hPanel→Profile→API; EXPIRE hota hai!) | expiry pe (hPanel se naya) | **2026-07-02** (purana expired mila) | HAAN — sirf `.env` (VPS+local), scripts runtime read karte |

> **Rotation evidence** = jab bhi koi key rotate ho, SESSION_LOG me 1-liner (key naam + date; VALUE kabhi nahi) + is table ka `Last-rotated` column update karo. `unknown (baseline 2026-07-02)` = honest starting state (koi verified rotation-date record nahi tha).

## Rotation loop (per key)
1. Naya key provider console me banao (purana ABHI revoke mat karo — overlap window).
2. `.env` update VPS pe (ssh via Git ka ssh.exe) → app recreate (`up -d --no-deps app`) → smoke: us provider ka ok-rate `free_ai` chain me / feature curl.
3. Purana key revoke. Evidence → SESSION_LOG 1-line (key name, date; VALUE kabhi nahi).
4. `.env` encrypted offsite copy refresh (dr-restore-drill dependency!).

## Leak response (suspect = confirmed jaisa treat karo)
1. Scope: kaunsa key, kahan leaked (git history? log? screenshot?). `git log -S <prefix>` + `check_secrets.py` full-scan.
2. REVOKE first, rotate second (upar loop). Git-committed leak = history me PERMANENT — revoke hi ilaaj, force-push cosmetic.
3. Blast radius: us key se kya access tha (billing? PII? send-email?) → affected surface audit + Sentry/logs me abuse check.
4. Guard ship: naya check_secrets.py pattern add + is skill me row update.

## Enterprise bar
- Har secret ka owner + cadence + no-restart path documented (upar table = source of truth, drift = update karo).
- Quarterly hygiene: table walk-through, 90d+ old keys rotate, unused keys revoke.
- Logs/PII me secrets kabhi na aayein (`llm-security` prompt-injection lens bhi).

## Output
Inventory table current · rotated keys list (names only) · leak-response evidence · check_secrets.py patterns updated.

## Related repo skills
`leadgen-security-rbac` (secrets audit lens) · `dr-restore-drill` (.env offsite) · `mcp-engineer` (MCP token 90d) · `llm-quota-ops` (provider keys health).
