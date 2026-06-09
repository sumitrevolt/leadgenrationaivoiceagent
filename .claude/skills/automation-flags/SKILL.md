---
name: automation-flags
description: The gated env-flag catalog for LeadGen AI automation engines — what each flag does, ban/cost risk, and the safe enable→verify procedure. Use when the user says "flag on/off karo", "enable automation", mentions JOURNEY_ENGINE / CADENCE_ENGINE / SALES_ENGINE / NICHE_ROTATION / AUTO_ONBOARD, "kaunsa flag safe hai", or before flipping any automation switch.
---

# Automation Flags (default OFF · additive · safe-to-flip)

Har engine ek env-flag pe gated hai (default OFF = ZERO behaviour change). Set in `.env` (VPS `/opt/leadgen/.env`, gitignored) → **container recreate** (`docker compose -f docker-compose.vps.yml up -d app`, NOT sirf `restart` — env_file reload ke liye recreate chahiye) → verify.

## Safe to enable (free, ban-safe)
| Flag | Engine | Notes |
|---|---|---|
| `NICHE_ROTATION=1` | all-42-niche scrape rotation | warna 4-niche |
| `AUTO_EMAIL_OUTREACH=true` | Rohan daily cold-email | cap 25/day, MX-verified, SPF/DKIM/DMARC set |
| `REPLY_AGENT=1` | inbox reply triage (draft-only) | IMAP creds reuse SMTP |
| `JOURNEY_ENGINE=1` | event→rule→action drafts | inquiry/signup triggers |
| `AUTO_QUALIFY_CALLS=1` | post-call AI qualifier | latency-safe (post-call) |
| `CADENCE_ENGINE=1` | omnichannel cadence advance | drafts; channel-gate pe hi send |
| `SALES_ENGINE=1` | deal pipeline next-actions | drafts/links |
| `OPS_WATCHDOG=1` | hourly health + email-alert | needs `NOTIFY_EMAIL` |
| `AUTO_ONBOARD=1` | paid-client done-for-you setup | website→KB + content pack |

## RISKY — bina readiness flip MAT karo
| Flag | Risk |
|---|---|
| `WHATSAPP_AUTO_SEND=1` | number BAN — sirf official Cloud API + approved template + opt-in |
| `MISSED_CALL_CALLBACK=1` | Vobiz/Exotel DID + inbound webhook chahiye |
| `SMS_DLT_ENABLED=1` | DLT templates + BSP creds (MSG91/AiSensy/Fast2SMS) |
| cold-calling | DLT (₹10L TRAI penalty) — Udyam pending |

## Procedure
1. **Backup**: `cp .env .env.bak_$(date +%s)`.
2. `.env` me flag add (base64-over-ssh se — secret kabhi plain argv pe nahi).
3. `docker compose -f docker-compose.vps.yml up -d app` (recreate = env reload).
4. `docker exec leadgen_app printenv <FLAG>` → confirm value.
5. Smoke: manual API trigger ya next scheduled run → `data/*.jsonl` output.
6. Rollback: `.env.bak_*` restore + recreate.

## Verify
`python scripts/setup_status.py` saare flags + readiness dikhata hai. USER-PENDING env (Claude fabricate nahi kar sakta): `UPI_VPA`, `POLLINATIONS_TOKEN`, Exotel KYC/DLT, R2/B2 offsite creds.
