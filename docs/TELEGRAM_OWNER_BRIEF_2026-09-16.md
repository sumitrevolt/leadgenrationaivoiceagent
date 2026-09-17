# Telegram Enterprise Coordination — Owner Briefing
**Date:** 2026-09-16 20:17 IST  
**Role:** Project Admin (LeadGen AI)  
**Scope:** STRICTLY coordination — NO marketing, NO personal use

---

## TL;DR

Telegram infrastructure is **85% built**. 10 of 13 chats exist (2 channels + 8 supergroups). **3 are missing** (the coordination layer). Bot is only admin in 1/13. Runbook is ready — owner action required to complete.

**Full details:** [`docs/TELEGRAM_ENTERPRISE_GRID_SETUP_2026-09-16.md`](docs/TELEGRAM_ENTERPRISE_GRID_SETUP_2026-09-16.md)

---

## Current State

| Metric | Value |
|--------|-------|
| Existing chats | 10 / 13 |
| Wired (bot as admin) | 1 / 13 (Marketing-Community only) |
| Missing chats | **3** (all coordination) |
| Bot identity | `@Leadsgenai1_bot` (id 8889560331) |
| Bot token | In prod `.env` (never exposed) |
| Setup spec | `config/telegram/setup_spec.yaml` (13 entities) |

---

## The 3 Missing Coordination Chats

These are the ONLY Telegram surfaces for agent/worker coordination:

| # | Name | Purpose | Topics |
|---|------|---------|--------|
| 11 | **Worker Coordination** | 9-bot fleet task handoffs + status | worker-status, task-handoffs, urgent |
| 12 | **Agents Coordination** | 31-agent Boss-led coordination | agent-status, assignments, verdicts, skill-share |
| 13 | **Admin Command Center** | Owner/deploy/kill-switch/revenue | deploys, revenue, kill-switch, metrics, system-health |

---

## What You Need to Do (5 minutes)

### Option A — Manual (recommended)
1. **Create 3 private supergroups** in Telegram Desktop with exact names above
2. **Enable Topics** → create the forum topics listed
3. **Add @Leadsgenai1_bot as admin** to each
4. **Copy chat_id** for each → paste into `config/telegram/setup_spec.yaml`
5. **Run:** `TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply`

### Option B — Programmatic (if you have TELEGRAM_API_ID + TELEGRAM_API_HASH)
```bash
export TELEGRAM_API_ID=...
export TELEGRAM_API_HASH=...
python scripts/telegram_create_chats.py --apply --write-spec
TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply
```

---

## After Creation — Verify

```bash
# Dry-run (no network)
python scripts/telegram_setup.py --plan

# Live apply (needs TELEGRAM_SETUP_ENABLED=1 + TELEGRAM_BOT_TOKEN)
python scripts/telegram_setup.py --apply

# Test egress (dry-run first, then live)
docker exec leadgen_app python3 -c "
from app.utils.owner_notify import send_owner
r = send_owner('Test: enterprise grid', severity='P0', evidence='manual-verify', dry_run=True)
print('OK' if r else 'FAIL')
"
```

---

## Compliance (Hard Gates — Never Weaken)

- ✅ Opt-in only (no scraping, no bulk-add)
- ✅ AI disclosure (bot labels itself)
- ✅ Secret-free (no tokens/OTPs in chat)
- ✅ Tenant isolation (no cross-customer PII)
- ✅ Coordination-only (no marketing posts)

---

## Files Reference

| File | Role |
|------|------|
| `config/telegram/setup_spec.yaml` | **CANONICAL** — all 13 entities |
| `scripts/telegram_setup.py` | Bot-API bootstrap (descriptions/topics/pins) |
| `scripts/telegram_create_chats.py` | Userbot creation (Path B) |
| `scripts/telegram_wire_bot.py` | Userbot admin promotion (Path C) |
| `app/utils/telegram_egress.py` | Send helpers (TEST-PROVEN) |
| `app/utils/owner_notify.py` | L1 egress with routing/dedupe/rate-limit |
| `docs/TELEGRAM_ENTERPRISE_GRID_SETUP_2026-09-16.md` | Full runbook |
| `docs/HANDOFF_TELEGRAM_2026-09-13.md` | Previous handoff |

---

## What's NOT in Scope (for later)

- ❌ Auto-publishing workforce/agent status (blocked by T-05 probe fix)
- ❌ Boss verdict streaming (blocked by `AGENT_HARNESS` arm)
- ❌ Product community/support wiring (separate owner decision)

---

**Next step:** Create the 3 missing chats → fill chat_ids → run `--apply` → verify egress.

🐦 pelican
