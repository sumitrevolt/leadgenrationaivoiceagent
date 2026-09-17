# Telegram Manual Creation Guide — 3 Missing Groups

**Status:** Your account has `spamreported` restriction — API blocked. Manual creation required.

**Time:** 5 minutes

---

## Groups to Create

### 1. LeadGen AI - Worker Coordination
- **Type:** Private Super Group
- **Purpose:** Cross-worker coordination, task handoffs, status updates between 9 worker CLI agents
- **Audience:** Worker agents + founder + PM

**Topics to create:**
- `worker-status` — daily standup, blockers
- `task-handoffs` — handoff between workers  
- `urgent` — P0 escalations

---

### 2. LeadGen AI - Agents Coordination
- **Type:** Private Super Group
- **Purpose:** 31-agent coordination, Boss verdict, hierarchical runs, skill sharing, agent health
- **Audience:** Agent operators + founder

**Topics to create:**
- `agent-status` — health checks
- `assignments` — task delegation
- `verdicts` — Boss decisions
- `skill-share` — knowledge transfer

---

### 3. LeadGen AI - Admin Command Center
- **Type:** Private Super Group
- **Purpose:** Owner/admin operational commands, deployment notices, kill-switch status, revenue truth, system health
- **Audience:** Founder + devops + PM

**Topics to create:**
- `deploys` — deployment notices
- `revenue` — daily/weekly revenue
- `kill-switch` — automation kill status
- `metrics` — KPI dashboard
- `system-health` — infra alerts

---

## Step-by-Step Instructions

### Step 1: Create Group
1. Open **Telegram Desktop**
2. Click **⋮ (More actions)** → **New Group**
3. Select **Private Super Group**
4. Enter **Name** (from list above)
5. Add **Description** (from list above)
6. Click **Create**

### Step 2: Enable Topics
1. Click on group name → **⋮** → **Manage Group**
2. Click **Topics**
3. Toggle **Enable Topics** → ON
4. Click **Add Topic** for each topic listed above
5. Set topic icons if desired

### Step 3: Add Bot as Admin
1. Click group name → **⋮** → **Administrators**
2. Click **Add Admin**
3. Search **@Leadsgenai1_bot** → Select
4. Grant these rights:
   - ✅ change_info
   - ✅ delete_messages
   - ✅ ban_users
   - ✅ invite_users
   - ✅ pin_messages
5. Click **Save**

### Step 4: Get Chat ID
**Method A: Copy Link**
1. Right-click group → **Copy Link**
2. Link format: `https://t.me/c/1234567890/1`
3. Extract numeric ID: `1234567890`
4. Add `-100` prefix: `-1001234567890`

**Method B: Send Message**
1. Send any message in group
2. Run: `GET https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find `"chat":{"id":1234567890}`
4. Add `-100` prefix

---

## Reply With Chat IDs

Once all 3 groups are created, reply with:

```
workers_coordination: -100XXXXXXXXX
agents_coordination: -100XXXXXXXXX
admin_command_center: -100XXXXXXXXX
```

I'll then:
1. Update `config/telegram/setup_spec.yaml`
2. Run `telegram_setup.py --apply`
3. Verify egress works

---

## Compliance Notes

✅ **Coordination-only** — No marketing, no personal coding chatter
✅ **Opt-in only** — No scraping, no bulk-add
✅ **AI disclosure** — Bot labels itself as AI
✅ **Secret-free** — No tokens/OTPs in chat
✅ **Tenant isolation** — No cross-customer PII

---

**Questions?** Check [`docs/TELEGRAM_ENTERPRISE_GRID_SETUP_2026-09-16.md`](docs/TELEGRAM_ENTERPRISE_GRID_SETUP_2026-09-16.md)
