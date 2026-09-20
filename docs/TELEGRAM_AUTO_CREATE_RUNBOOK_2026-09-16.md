# Telegram Enterprise Grid â€” Auto-Create 3 Missing Coordination Groups
**Date:** 2026-09-16  
**Owner:** sumit daryanani  
**Bot:** @Leadsgenai1_bot (id 8889560331)

---

## Summary
3 coordination groups are MISSING from the enterprise Telegram grid:
1. **Worker Coordination** (9-bot fleet)
2. **Agents Coordination** (31-agent Boss-led)
3. **Admin Command Center** (owner/deploy/kill-switch)

This script creates them via Telethon (user API) and adds the bot as admin.

---

## Prerequisites

You need **TELEGRAM_API_ID** and **TELEGRAM_API_HASH** from https://my.telegram.org/api

If you don't have these:
1. Go to https://my.telegram.org
2. Log in with your phone number
3. Click "API development tools"
4. Create a new application
5. Copy the `api_id` and `api_hash`

---

## Step 1: Get Credentials

```bash
# Get your API credentials from https://my.telegram.org
echo "TELEGRAM_API_ID=<your_id>" > .env.telegram
echo "TELEGRAM_API_HASH=<your_hash>" >> .env.telegram
```

---

## Step 2: Run the Script

```bash
# Phase 1: Send SMS code to your phone
python scripts/telegram_create_chats.py \
  --api-id <your_id> \
  --api-hash <your_hash> \
  --phone +91XXXXXXXXXX

# You'll see: "[OK] SMS code sent to +91XXXXXXXXXX"
# Check your phone for the code

# Phase 2: Verify code and create groups
python scripts/telegram_create_chats.py \
  --api-id <your_id> \
  --api-hash <your_hash> \
  --phone +91XXXXXXXXXX \
  --code 12345

# Or if session already authed:
python scripts/telegram_create_chats.py \
  --api-id <your_id> \
  --api-hash <your_hash> \
  --phone +91XXXXXXXXXX \
  --create
```

---

## Step 3: Verify Creation

```bash
# Check the output JSON
cat data/new_group_chat_ids.json

# Should show:
# {
#   "workers_coordination": "-1001234567890",
#   "agents_coordination": "-1001234567891",
#   "admin_command_center": "-1001234567892"
# }
```

---

## Step 4: Update Spec and Apply

```bash
# The script should have written chat_ids to setup_spec.yaml
# Verify:
python scripts/telegram_setup.py --validate

# Apply descriptions, topics, pins
TELEGRAM_SETUP_ENABLED=1 \
  TELEGRAM_BOT_TOKEN=<token> \
  python scripts/telegram_setup.py --apply
```

---

## What the Script Does

1. **Authenticates** with your Telegram user account (via Telethon)
2. **Creates 3 supergroups** with exact names from spec:
   - "LeadGen AI - Worker Coordination"
   - "LeadGen AI - Agents Coordination"
   - "LeadGen AI - Admin Command Center"
3. **Adds @Leadsgenai1_bot** as a member
4. **Promotes bot to admin** with rights:
   - change_info, delete_messages, ban_users
   - invite_users, pin_messages, manage_call, other
5. **Returns chat_ids** for each group

---

## Compliance

- âœ… Coordination-only (no marketing, no personal use)
- âœ… Opt-in only (private groups, invite links)
- âœ… Bot labels itself as automated
- âœ… No PII/tokens in chat
- âœ… Tenant isolation (private groups)

---

## Troubleshooting

**Error: "Phone code expired"**
- Run Phase 1 again to get a new code

**Error: "Session file corrupted"**
- Delete `data/telethon_setup.session` and run Phase 1 again

**Error: "Bot not found"**
- Verify bot username is `Leadsgenai1_bot` (no @ prefix)

**Error: "Cannot promote bot"**
- Bot must be a member first. Script handles this automatically.

---

## Files Modified

- `data/telethon_setup.session` â€” created (user auth session)
- `data/telethon_code_hash.json` â€” created (SMS code hash)
- `data/new_group_chat_ids.json` â€” created (output)
- `config/telegram/setup_spec.yaml` â€” updated (chat_ids)

---

## Next Steps After Creation

1. **Enable forum topics** in each group (Telegram UI)
2. **Create topics** per spec:
   - Worker Coordination: worker-status, task-handoffs, urgent
   - Agents Coordination: agent-status, assignments, verdicts, skill-share
   - Admin Command Center: deploys, revenue, kill-switch, metrics, system-health
3. **Run telegram_setup.py --apply** to set descriptions + pins
4. **Verify egress:** `send_owner('Test', severity='P0', evidence='verify')`

---

**Ready to run?** Provide your TELEGRAM_API_ID and TELEGRAM_API_HASH, and I'll execute the script for you.

