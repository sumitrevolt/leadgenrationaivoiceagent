# Telegram Single Source of Truth — LeadGen AI
**Date:** 2026-09-20  
**Status:** CLEANED UP → Ready for owner action

---

## 1. Architecture (Single Source of Truth)

```
┌─────────────────────────────────────────────────────────────┐
│  OWNER (sumitrevolt)                                        │
│  Direct chat: @Sumits_jarvis_bot (Telegram)                 │
└──────────────┬──────────────────────────────────────────────┘
               │
       ┌───────▼────────┐     ┌──────────────────────────────┐
       │  JARVIS BOT    │     │  LEADGEN AI EGRESS BOT       │
       │  (@Sumits_jar- │     │  (@Leadsgenai1_bot)          │
       │  vis_bot)      │     │  (TELEGRAM_NOTIFY_BOT_TOKEN) │
       │  (Jarvis)      │     │  (Broadcast/alerts)          │
       │  T-01 token    │     │                              │
       └───────┬────────┘     └───────────────┬──────────────┘
               │                               │
       ┌───────▼────────┐             ┌────────▼──────────────┐
       │  telegram_bot  │             │  telegram_egress.py   │
       │  .py (ingress) │             │  (Bot API egress)     │
       │  + Typesafe    │             │  → setup_spec.yaml    │
       │  classifier    │             │  → 10 enterprise      │
       └───────┬────────┘             │    chats              │
               │                       └──────────────────────┘
       ┌───────▼────────────────────────────────────────────────┐
       │  AutomationOrchestrator (9-worker / 31-agent)          │
       │  DurableTaskStore + Governor + SkillRegistry           │
       └────────────────────────────────────────────────────────┘
```

**Two bots, clear separation:**
- **Jarvis** (`TELEGRAM_JARVIS_BOT_TOKEN`) — Interactive command bot. Owner sends `/status`, `/tasks`, `/agents`, `/pause`, `/resume`. TypeSafe-classified natural language → routed to 9 Hermes supervisory bots.
- **LeadGen AI Admin** (`TELEGRAM_NOTIFY_BOT_TOKEN` / `TELEGRAM_BOT_TOKEN`) — Broadcast/alert egress bot. Sends P0/P1 owner alerts, deploy notices, video deliverables to enterprise groups.

---

## 2. Canonical Config

**Single source of truth:** `config/telegram/setup_spec.yaml`

Contains all 13 entities (10 existing + 3 coordination groups pending creation).

**Routing map:** `config/telegram/owner_notify_routing.yaml`

Maps severity → destination group.

---

## 3. Live Code (Active)

| File | Purpose | Status |
|------|---------|--------|
| `app/integrations/telegram_bot.py` | Jarvis bot ingress, TypeSafe classification, orchestrator connection | ✅ LIVE |
| `app/integrations/telegram_typesafe.py` | Intent classifier, bot coordinator, response validator | ✅ LIVE |
| `app/utils/telegram_egress.py` | Bot-API egress to enterprise groups | ✅ LIVE |
| `app/api/telegram_bot_api.py` | `/api/telegram/bot/*` REST endpoints | ✅ MOUNTED |
| `app/api/telegram_typesafe.py` | `/api/telegram/typesafe/*` router (alias) | ✅ MOUNTED |
| `app/api/telegram_setup.py` | `/telegram/setup/*` enterprise grid setup API | ✅ MOUNTED |
| `app/platform/telegram_ingress.py` | Headless ingress scaffold (fail-closed, TODO poll loop) | ⚠️ SCAFFOLD |

---

## 4. Cleanup Completed (2026-09-20)

**Deleted (orphaned/duplicate):**
- `app/telegram/multi_tenant.py` — legacy multi-tenant bot, no production import
- `app/api/telegram_bot.py` — tenant management API, unused
- `app/tasks/telegram.py` — Celery tasks for orphaned multi_tenant
- `config/telegram/enterprise_groups.yaml` — merged into setup_spec.yaml
- `scripts/run_telegram_setup.{ps1,sh}` — referenced non-existent script
- `scripts/telegram_web_create_groups.py` — duplicate Selenium script
- `scripts/telegram_create_groups_README.md` — referenced wrong script name
- `scripts/TELEGRAM_SETUP_PHASES.txt`, `telegram_setup_plan.json`, `telegram_recovery_plan.json` — stale

**Remaining scripts (all verified):**
- `scripts/telegram_setup.py` — Bot-API bootstrap (descriptions/topics/pins)
- `scripts/telegram_create_chats.py` — Telethon userbot chat creation (Path B)
- `scripts/telegram_wire_bot.py` — Telethon bot admin wiring (Path B)
- `scripts/test_telegram_dual_bot.py` — Dual-bot coordination verification
- `scripts/telegram_owner_canary.py` — Production canary (owner alerts)
- `scripts/telegram_readonly_probe.py` — Read-only wiring probe

---

## 5. Current State (Verified)

| Entity | Kind | chat_id | Status |
|--------|------|---------|--------|
| Marketing - Announcements | Channel | -1004485447096 | ✅ Wired |
| Marketing - Community | Supergroup | -1004475752582 | ✅ Wired |
| Marketing - Support | Supergroup | -1004464035633 | ✅ Wired |
| Marketing - Feedback | Supergroup | -1003932745917 | ✅ Wired |
| Voice Agent - Announcements | Channel | -1003935454293 | ✅ Wired |
| Voice Agent - Community | Supergroup | -1004421485309 | ✅ Wired |
| Voice Agent - Support | Supergroup | -1003906410254 | ✅ Wired |
| Voice Agent - Feedback | Supergroup | -1004376116363 | ✅ Wired |
| Internal Ops | Supergroup | -1004460536807 | ✅ Wired |
| Owner Alerts | Supergroup | -1003878635977 | ✅ Wired |
| **Worker Coordination** | Supergroup | **EMPTY** | ❌ NEEDS CREATION |
| **Agents Coordination** | Supergroup | **EMPTY** | ❌ NEEDS CREATION |
| **Admin Command Center** | Supergroup | **EMPTY** | ❌ NEEDS CREATION |

---

## 6. Owner Action Required (3 Missing Groups)

**Step 1:** Create 3 private supergroups in Telegram (manual, ~2 min):
1. `LeadGen AI - Worker Coordination` (private)
2. `LeadGen AI - Agents Coordination` (private)
3. `LeadGen AI - Admin Command Center` (private)

**Step 2:** For each group:
- Enable **Topics** (⋯ → Manage → Topics)
- Add `@Leadsgenai1_bot` as admin (Manage → Administrators → Add Admin → search bot → Add)
- Copy the `chat_id` (forward a message to @userinfobot or check bot's getUpdates)

**Step 3:** Fill `chat_id` in `config/telegram/setup_spec.yaml` for:
- `workers_coordination`
- `agents_coordination`  
- `admin_command_center`

**Step 4:** Run bootstrap:
```bash
TELEGRAM_SETUP_ENABLED=1 TELEGRAM_BOT_TOKEN=<token> \
  python scripts/telegram_setup.py --apply
```

**Alternative (Path B — fully automated):**
```bash
export TELEGRAM_API_ID=30160587
export TELEGRAM_API_HASH=5a6af325bc59e9da130999f2ccda1674
python scripts/telegram_create_chats.py --apply --write-spec
python scripts/telegram_wire_bot.py --apply
TELEGRAM_SETUP_ENABLED=1 TELEGRAM_BOT_TOKEN=<token> \
  python scripts/telegram_setup.py --apply
```

---

## 7. Tests

```
tests/test_telegram_bootstrap.py  ..............  [14/14 pass]
tests/test_telegram_setup.py        .......       [7/7 pass]
tests/test_telegram_webhook.py      .....         [5/5 pass]
tests/test_telegram_integration_2026.py  16/18   [2 pre-existing TypeSafe mock failures]
```

---

## 8. Compliance

- ✅ Opt-in only, no scraping, no cold-DM
- ✅ Bot labels itself as automated in every reply
- ✅ No PII/tokens in chat
- ✅ Tenant isolation enforced
- ✅ Fail-closed: disabled without `TELEGRAM_BOT_TOKEN`
- ✅ DPDP Act 2023 + TRAI TCCCPR compliant

---

**Next:** Once owner creates the 3 groups and fills chat_ids, run `--apply` to complete the enterprise grid.
