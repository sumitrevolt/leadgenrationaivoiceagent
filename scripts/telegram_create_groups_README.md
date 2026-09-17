# Telegram Enterprise Grid — Auto-Create Script
# Creates 3 missing coordination groups + wires bot as admin

**Purpose:** Programmatic creation of 3 missing enterprise coordination groups via Telethon (user API).

**Prerequisites:**
- `TELEGRAM_API_ID` = 30160587 (provided by owner)
- `TELEGRAM_API_HASH` = 5a6af325bc59e9da130999f2ccda1674 (provided by owner)
- Owner's phone number for SMS auth
- Telethon installed (`pip install telethon`)

**What it creates:**
1. `LeadGen AI - Worker Coordination` (private supergroup, forum topics: worker-status, task-handoffs, urgent)
2. `LeadGen AI - Agents Coordination` (private supergroup, forum topics: agent-status, assignments, verdicts, skill-share)
3. `LeadGen AI - Admin Command Center` (private supergroup, forum topics: deploys, revenue, kill-switch, metrics, system-health)

**What it does:**
- Authenticates with owner's Telegram account via Telethon
- Creates 3 supergroups with exact names from `config/telegram/setup_spec.yaml`
- Adds @Leadsgenai1_bot as member
- Promotes bot to admin with rights: change_info, delete_messages, ban_users, invite_users, pin_messages, manage_call, other
- Returns chat_ids in `data/new_group_chat_ids.json`
- Updates `config/telegram/setup_spec.yaml` if --write-spec flag used

**Usage:**
```bash
# Phase 1: Send SMS code (one-time)
python scripts/telethon_create_groups.py --api-id 30160587 --api-hash "5a6af325bc59e9da130999f2ccda1674" --phone +91XXXXXXXXXX

# Phase 2: Verify code + create groups
python scripts/telethon_create_groups.py --api-id 30160587 --api-hash "5a6af325bc59e9da130999f2ccda1674" --phone +91XXXXXXXXXX --code 123456

# Or if session already authed:
python scripts/telethon_create_groups.py --api-id 30160587 --api-hash "5a6af325bc59e9da130999f2ccda1674" --phone +91XXXXXXXXXX --create
```

**Output:**
- `data/telethon_setup.session` — user auth session (binary)
- `data/telethon_code_hash.json` — SMS code hash (temporary)
- `data/new_group_chat_ids.json` — chat_ids for each group
- `config/telegram/setup_spec.yaml` — updated with new chat_ids (if --write-spec)

**Next steps after creation:**
1. Enable forum topics in each group (Telegram UI)
2. Create topics per spec (Telegram UI or via Bot API)
3. Run `TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply` to set descriptions + pins
4. Verify egress: `send_owner('Test', severity='P0', evidence='verify')`

**Compliance:**
- ✅ Coordination-only (no marketing, no personal use)
- ✅ Opt-in only (private groups, invite links)
- ✅ Bot labels itself as automated
- ✅ No PII/tokens in chat
- ✅ Tenant isolation (private groups)

**Risks:**
- Session file (`data/telethon_setup.session`) contains auth tokens — treat as secret
- SMS code expires in 5 minutes — run Phase 2 promptly after Phase 1
- Bot promotion requires bot to be member first — script handles this automatically

**Files:**
- `scripts/telethon_create_groups.py` — main script
- `scripts/run_telegram_setup.ps1` — Windows wrapper
- `scripts/TELEGRAM_SETUP_PHASES.txt` — step-by-step instructions
