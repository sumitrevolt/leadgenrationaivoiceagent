# Telegram Enterprise Grid — Phase 1: Send SMS Code

**Status:** Ready to execute  
**Script:** `scripts/telethon_create_groups.py`  
**Credentials:** Provided by owner (api_id=30160587, api_hash=5a6af325bc59e9da130999f2ccda1674)

---

## Phase 1: Send SMS Code (ONE TIME)

```bash
python scripts/telethon_create_groups.py \
  --api-id 30160587 \
  --api-hash "5a6af325bc59e9da130999f2ccda1674" \
  --phone +91XXXXXXXXXX
```

**Expected output:**
```
[OK] SMS code sent to +91XXXXXXXXXX
[INFO] phone_code_hash saved to data/telethon_code_hash.json
[NEXT] Run again with --code <SMS_CODE>
```

**Action:** Check your Telegram app (or SMS) for the 6-digit code.

---

## Phase 2: Verify Code + Create Groups

```bash
python scripts/telethon_create_groups.py \
  --api-id 30160587 \
  --api-hash "5a6af325bc59e9da130999f2ccda1674" \
  --phone +91XXXXXXXXXX \
  --code 123456
```

**Replace `123456` with the actual code from your phone.**

**Expected output:**
```
[telethon] Logged in as: sumit daryanani (+91XXXXXXXXXX)

--- Creating: LeadGen AI - Worker Coordination ---
  [OK] Created: LeadGen AI - Worker Coordination
  [OK] Added @Leadsgenai1_bot
  [OK] Made @Leadsgenai1_bot admin
  [OK] chat_id: -1001234567890

--- Creating: LeadGen AI - Agents Coordination ---
  [OK] Created: LeadGen AI - Agents Coordination
  [OK] Added @Leadsgenai1_bot
  [OK] Made @Leadsgenai1_bot admin
  [OK] chat_id: -1001234567891

--- Creating: LeadGen AI - Admin Command Center ---
  [OK] Created: LeadGen AI - Admin Command Center
  [OK] Added @Leadsgenai1_bot
  [OK] Made @Leadsgenai1_bot admin
  [OK] chat_id: -1001234567892

============================================================
RESULTS -- chat_ids for setup_spec.yaml:
============================================================
  workers_coordination: -1001234567890
  agents_coordination: -1001234567891
  admin_command_center: -1001234567892

Saved to: data/new_group_chat_ids.json
```

---

## Phase 3: Update Spec + Apply

```bash
# Update setup_spec.yaml with new chat_ids
# (Manual: copy from data/new_group_chat_ids.json)
# OR use --write-spec flag in Phase 2

# Validate spec
python scripts/telegram_setup.py --validate

# Apply descriptions, topics, pins
TELEGRAM_SETUP_ENABLED=1 \
  TELEGRAM_BOT_TOKEN=<from_prod_env> \
  python scripts/telegram_setup.py --apply
```

---

## Files Created/Modified

| File | Action |
|------|--------|
| `data/telethon_setup.session` | Created (user auth session) |
| `data/telethon_code_hash.json` | Created (SMS code hash) |
| `data/new_group_chat_ids.json` | Created (output) |
| `config/telegram/setup_spec.yaml` | Updated (chat_ids) |

---

## Next Steps

1. **Enable forum topics** in each group (Telegram Desktop UI)
2. **Create topics** per spec:
   - Worker Coordination: worker-status, task-handoffs, urgent
   - Agents Coordination: agent-status, assignments, verdicts, skill-share
   - Admin Command Center: deploys, revenue, kill-switch, metrics, system-health
3. **Verify egress:** `send_owner('Test', severity='P0', evidence='verify')`
4. **Update runbook:** `docs/TELEGRAM_ENTERPRISE_GRID_SETUP_2026-09-16.md` with verified chat_ids

---

**Ready to execute?** Provide your phone number (+91XXXXXXXXXX) and I'll run Phase 1.
