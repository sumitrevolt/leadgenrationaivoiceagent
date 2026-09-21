# Telegram Enterprise Groups — Manual Creation Runbook

**Status:** AUTO-CREATE FAILED — account `spamreported` (Telethon limitation)
**Date:** 2026-09-20
**Action Required:** Owner manual creation (5 minutes)

---

## Why Automation Failed

`scripts/telegram_create_chats.py --apply` tried to create groups via Telethon user API but received:
```
FAILED: You're spamreported, you can't create channels or chats.
```

Telegram restricts accounts that have been reported for spam. This is a **platform-level** restriction — no script can bypass it. The only path is manual creation via Telegram Desktop app.

---

## Step 1: Create 3 Groups (Telegram Desktop)

### Group 1: Worker Coordination
1. Open **Telegram Desktop**
2. Click **⋮ (More)** → **New Group**
3. Select **Create New Group** → Next
4. Add any 1-2 contacts (can remove later) → Next
5. **Group Name:** `LeadGen AI - Worker Coordination`
6. **Description:** `Cross-worker coordination, task handoffs, status updates between the 9 worker CLI agents.`
7. Click **Create**
8. **Enable Topics:** Click group name → ⋮ → **Manage Group** → **Topics** → Toggle ON
9. **Create Topics:**
   - `worker-status` — daily standup, blockers
   - `task-handoffs` — handoff between workers
   - `urgent` — P0 escalations
10. **Add Bot as Admin:** ⋮ → **Administrators** → **Add Admin** → Search `@Leadsgenai1_bot` → Grant: change_info, delete_messages, ban_users, invite_users, pin_messages

### Group 2: Agents Coordination
1. Same process as above
2. **Group Name:** `LeadGen AI - Agents Coordination`
3. **Description:** `31-agent coordination, Boss verdict, hierarchical runs, skill sharing, agent health.`
4. **Topics:**
   - `agent-status` — health checks
   - `assignments` — task delegation
   - `verdicts` — Boss decisions
   - `skill-share` — knowledge transfer
5. Add `@Leadsgenai1_bot` as admin (same rights)

### Group 3: Admin Command Center
1. Same process as above
2. **Group Name:** `LeadGen AI - Admin Command Center`
3. **Description:** `Owner/admin operational commands, deployment notices, kill-switch status, revenue truth, system health.`
4. **Topics:**
   - `deploys` — deployment notices
   - `revenue` — daily/weekly revenue
   - `kill-switch` — automation kill status
   - `metrics` — KPI dashboard
   - `system-health` — infra alerts
5. Add `@Leadsgenai1_bot` as admin (same rights)

---

## Step 2: Get Chat IDs

For each group:
1. Right-click the group → **Copy Link**
2. Link format: `https://t.me/c/1234567890/1`
3. Extract numeric ID: `1234567890`
4. Add `-100` prefix: `-1001234567890`

**Example:** If link is `https://t.me/c/1001234567890/1` → chat_id is `-1001001234567890`

---

## Step 3: Reply With These Values

```
workers_coordination: -100XXXXXXXXXXX
agents_coordination: -100XXXXXXXXXXX
admin_command_center: -100XXXXXXXXXXX
```

---

## Step 4: What I Will Do After

1. Update `config/telegram/setup_spec.yaml` with chat_ids
2. Run `TELEGRAM_SETUP_ENABLED=1 TELEGRAM_BOT_TOKEN=... python scripts/telegram_setup.py --apply`
3. Verify egress to all 3 groups
4. Commit all changes
5. Run full test suite

---

## Alternative: Wait for Spam Restriction Lift

If you believe the spamreported flag is erroneous:
1. Contact Telegram support: https://telegram.org/support
2. Once lifted, re-run: `python scripts/telegram_create_chats.py --apply --write-spec`

---

## Current State (2026-09-20)

| Group | Status | chat_id |
|-------|--------|---------|
| LeadGen AI Marketing - Announcements | ✅ CONFIGURED | -1004485447096 |
| LeadGen AI Marketing - Community | ✅ CONFIGURED | -1004475752582 |
| LeadGen AI Marketing - Support | ✅ CONFIGURED | -1004464035633 |
| LeadGen AI Marketing - Feedback | ✅ CONFIGURED | -1003932745917 |
| LeadGen AI Voice Agent - Announcements | ✅ CONFIGURED | -1003935454293 |
| LeadGen AI Voice Agent - Community | ✅ CONFIGURED | -1004421485309 |
| LeadGen AI Voice Agent - Support | ✅ CONFIGURED | -1003906410254 |
| LeadGen AI Voice Agent - Feedback | ✅ CONFIGURED | -1004376116363 |
| LeadGen AI - Internal Ops | ✅ CONFIGURED | -1004460536807 |
| LeadGen AI - Owner Alerts | ✅ CONFIGURED | -1003878635977 |
| LeadGen AI - Worker Coordination | ⏳ PENDING | (empty) |
| LeadGen AI - Agents Coordination | ⏳ PENDING | (empty) |
| LeadGen AI - Admin Command Center | ⏳ PENDING | (empty) |

**10/13 groups configured. 3 pending owner action.**
