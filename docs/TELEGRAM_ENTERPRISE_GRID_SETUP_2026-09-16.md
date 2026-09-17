# Telegram Enterprise Grid — Missing Chats & Setup Runbook
**Date:** 2026-09-16 · **Owner:** sumit daryanani · **Bot:** @Leadsgenai1_bot (id 8889560331)
**Purpose:** Strictly project coordination + agent coordination. NO marketing. NO personal coding chatter.

---

## 1. Current State (as of 2026-09-16 probe)

| Entity | Status | chat_id | Bot as admin? |
|--------|--------|---------|---------------|
| LeadGen AI Marketing - Announcements | ✅ Created | `-1004485447096` | ❌ MISSING |
| LeadGen AI Marketing - Community | ✅ Wired | `-1004475752582` | ✅ YES |
| LeadGen AI Marketing - Support | ✅ Created | `-1004464035633` | ❌ MISSING |
| LeadGen AI Marketing - Feedback | ✅ Created | `-1003932745917` | ❌ MISSING |
| LeadGen AI Voice Agent - Announcements | ✅ Created | `-1003935454293` | ❌ MISSING |
| LeadGen AI Voice Agent - Community | ✅ Created | `-1004421485309` | ❌ MISSING |
| LeadGen AI Voice Agent - Support | ✅ Created | `-1003906410254` | ❌ MISSING |
| LeadGen AI Voice Agent - Feedback | ✅ Created | `-1004376116363` | ❌ MISSING |
| LeadGen AI - Internal Ops | ✅ Created | `-1004460536807` | ❌ MISSING |
| LeadGen AI - Owner Alerts | ✅ Created | `-1003878635977` | ❌ MISSING |
| **LeadGen AI - Worker Coordination** | 🔴 **MISSING** | *(empty)* | ❌ N/A |
| **LeadGen AI - Agents Coordination** | 🔴 **MISSING** | *(empty)* | ❌ N/A |
| **LeadGen AI - Admin Command Center** | 🔴 **MISSING** | *(empty)* | ❌ N/A |

**Total:** 10 exist (1 wired), **3 MISSING** (all cross-product coordination). 9/10 need bot-as-admin.

---

## 2. Required Telegram Grid (enterprise coordination)

### 2.1 Cross-Product Coordination (the 3 missing)
These are the ONLY Telegram surfaces for agent/worker coordination — no marketing, no customer-facing.

| # | Name | Purpose | Access | Forum Topics |
|---|------|---------|--------|--------------|
| 11 | **Worker Coordination** | 9-bot fleet task handoffs, status, urgent escalation | private | worker-status, task-handoffs, urgent |
| 12 | **Agents Coordination** | 31-agent Boss-led coordination, assignments, verdicts, skill-share | private | agent-status, assignments, verdicts, skill-share |
| 13 | **Admin Command Center** | Owner/deploy/kill-switch/revenue truth + system health | private | deploys, revenue, kill-switch, metrics, system-health |

### 2.2 Why these 3 only?
- `workers_coordination` → mirrors the 9-bot fleet ledger (`command_center/data/tasks.json`)
- `agents_coordination` → mirrors the 31-agent Boss coordination (ADR-165/167)
- `admin_command_center` → mirrors the owner operational surface (MCP tools, deploy notices, kill-switch status)
- **Not needed:** product-level community/support/feedback for agents (those stay in the existing product groups if at all)

---

## 3. Owner Action Required (choose one path)

### Path A — Manual (recommended, 5 minutes)
**Create the 3 missing chats in Telegram Desktop:**

1. Open Telegram Desktop → click **New Group** (or **New Channel** for channels — all 3 are supergroups).
2. For each, give the **exact name** from the table above → enable **Topics** (⋯ → Manage → Topics).
3. Create the forum topics listed in the table.
4. Set to **Private** → copy the invite link → paste into `config/telegram/setup_spec.yaml` `invite_link`.
5. Add **@Leadsgenai1_bot** as admin (⋯ → Manage → Administrators → Add Admin → search "Leadsgenai" → Add).
6. Right-click the chat → **Copy Chat ID** (or forward a message to @userinfobot).
7. Paste each `chat_id` into `setup_spec.yaml` under the corresponding entity.

### Path B — Programmatic (owner has TELEGRAM_API_ID + TELEGRAM_API_HASH)
```bash
# 1. Get credentials from https://my.telegram.org (API development tools)
export TELEGRAM_API_ID=<your_id>
export TELEGRAM_API_HASH=<your_hash>

# 2. Dry-run to see what would be created
python scripts/telegram_create_chats.py --dry-run

# 3. Create + wire bot as admin + write chat_ids back to spec
python scripts/telegram_create_chats.py --apply --write-spec

# 4. Apply descriptions + topics + pins
TELEGRAM_SETUP_ENABLED=1 TELEGRAM_BOT_TOKEN=<token> \
    python scripts/telegram_setup.py --apply
```

### Path C — Wire existing 10 (if bot not yet admin anywhere except Community)
If you've already created the 3 missing chats manually and filled in chat_ids:
```bash
# Add bot as admin to ALL 10 (requires TELEGRAM_API_ID/HASH)
python scripts/telegram_wire_bot.py --apply
```

---

## 4. Post-Creation Verification

```bash
# 1. Verify spec parses
python scripts/telegram_setup.py --validate

# 2. Dry-run plan (no network)
python scripts/telegram_setup.py --plan

# 3. Check bot can see all chats
docker exec leadgen_app python3 -c "
import os, json, urllib.request
t = os.environ['TELEGRAM_BOT_TOKEN']
r = json.loads(urllib.request.urlopen(
    f'https://api.telegram.org/bot{t}/getUpdates?limit=100', timeout=20).read())
for u in r.get('result', []):
    m = u.get('message') or u.get('channel_post') or u.get('my_chat_member')
    if m:
        c = m.get('chat') or {}
        print(f\"{c.get('id')} | {c.get('title')} | {u.get('update_type')}\")
"

# 4. Verify bot is admin (replace <ID> with each chat_id)
docker exec leadgen_app python3 -c "
import os, json, urllib.request
t = os.environ['TELEGRAM_BOT_TOKEN']
r = json.loads(urllib.request.urlopen(
    f'https://api.telegram.org/bot{t}/getChatAdministrators?chat_id=<ID>', timeout=15).read())
print(r['ok'], [a['user']['username'] for a in r.get('result', [])])
"
```

---

## 5. Post-Setup: Egress Verification

```bash
# Test owner_notify send (dry-run — no network)
docker exec leadgen_app python3 -c "
from app.utils.owner_notify import send_owner
r = send_owner('Test: enterprise grid setup', severity='P0', evidence='manual-verify', dry_run=True)
print('dry_run OK' if r else 'dry_run FAIL')
"

# Test live (UNCOMMENT only after verified)
# docker exec leadgen_app python3 -c "
# from app.utils.owner_notify import send_owner
# r = send_owner('🟢 Enterprise grid LIVE — 13 chats wired', severity='P0', evidence='grid-setup-20260916')
# print('sent' if r else 'failed')
# "
```

---

## 6. Compliance & Guardrails (NEVER break)

| Rule | Enforcement |
|------|-------------|
| Coordination-only | No marketing posts, no customer PII, no cold outreach |
| AI disclosure | Bot labels itself in every automated reply |
| Secret-free | No tokens, OTPs, passwords in any chat |
| Tenant isolation | No cross-customer data in shared groups |
| Opt-in only | No scraping member lists, no bulk-add |
| Failure-safe | `TELEGRAM_BOT_TOKEN` missing → every send returns `{"sent": False}` |

---

## 7. File Inventory

| File | Purpose |
|------|---------|
| `config/telegram/setup_spec.yaml` | **CANONICAL** — 13 entities (10 existing + 3 new), chat_ids, topics, admins |
| `scripts/telegram_create_chats.py` | Userbot chat creation (Path B) |
| `scripts/telegram_wire_bot.py` | Userbot bot-wire + admin promotion (Path C) |
| `scripts/telegram_setup.py` | Bot-API bootstrap (descriptions, topics, pins, invites) |
| `app/utils/telegram_egress.py` | TEST-PROVEN send helpers (sendMessage, sendVideo, sendPhoto) |
| `app/utils/owner_notify.py` | L1 egress: severity-routing, dedupe, rate-limit, evidence gate |
| `config/telegram/owner_notify_routing.yaml` | Routing map: severity→group, source→group, quiet hours |
| `docs/TELEGRAM_ENTERPRISE_SETUP.md` | Human-facing design + runbook |
| `docs/HANDOFF_TELEGRAM_2026-09-13.md` | Previous handoff (bot identity + 10-chat status) |
| `docs/context/OWNER_TELEGRAM_FEED_DESIGN.md` | 4-layer design (L1-L4) |

---

## 8. Next Steps After Owner Action

1. **Owner creates 3 chats** (Path A or B).
2. **Owner adds @Leadsgenai1_bot as admin** to all 13 (or runs Path B/C).
3. **Owner fills chat_ids** into `setup_spec.yaml` (if Path A).
4. **Run:** `TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply`
5. **Verify:** all 13 show `OK` in output, 0 `FAIL`.
6. **Test egress:** uncomment the live test in §5, confirm owner gets the message.
7. **Update this doc** with verified chat_ids.

---

**Not done (out of scope for this task):**
- ❌ Auto-publishing workforce/agent status to these groups (requires T-05 probe fix first)
- ❌ Boss verdict streaming (requires `AGENT_HARNESS` arm)
- ❌ Product-level community/support wiring (separate owner decision)
