---
name: godmode
description: Single-run checklist to verify production readiness, clear pending approvals, and safely launch/monitor outbound calling using the Admin Dashboard God Mode + Automation Hub + Mission Control. Use when user says "god mode", "calling start", "launch campaign", "production ready hai?", "automation approvals clear karo", or "kal calling se pehle".
---

# God Mode (Production Readiness + Calling Launch)

Ye skill ek hi goal ke liye hai: **kal/abhi calling start karne se pehle** sab safety checks + approvals + workflows **UI se** complete karna.

Scope:
- Admin Dashboard (`/app/admin`) → **God Mode** + **Automation Hub**
- Mission Control (`/app/automation`) → **ClientOps approvals + process breakpoints + self-improve**
- Campaign launch/stop/status + recordings

Non-goals:
- `.env` keys invent karna (user-action)
- DLT paperwork / provider KYC (external)

## Preconditions (fast)
- Site health: `GET /health` → `environment: production`
- Admin access token set (admin pages use `localStorage.accessToken`)
- **Code gate (dev/VPS pull ke baad):** `python scripts/final_integration_check.py` → PASS (0 handler gaps, 0 route gaps, tests green)

## Step 0 — Automated wiring gate (optional but recommended)
```bash
python scripts/final_integration_check.py
```
Ye chalata hai: `wiring_audit.py` + `deep_wiring_audit.py` + `production_ready.py` + parity/portal pytest.
FAIL = kal se pehle fix karo (dead button ya missing API).

## Step 1 — God Mode readiness snapshot (P0)
Open: `/app/admin` → section **⚡ God Mode**

Verify:
- **Readiness probes** mostly green (db/redis/etc.)
- **Telephony score ≥ 70** (calling ready)
- **TRAI window open** (10:00–19:00 IST) for promotional calling
- **UPI/Razorpay** only matters for paid activation (calling ke liye secondary)

If telephony score low:
- Provider creds missing (Exotel/Vobiz)
- `CALLER_ID` missing
- STT key missing (GROQ)
- Balance/KYC issues

Action:
- God Mode me “gap” messages ko follow karo; fir page refresh.

## Step 2 — Clear pending approvals (content + self-improve + process)
### 2A Content approvals (client posts)
Option A (Admin Dashboard quick):
- `/app/admin` → **Automation Hub** → “Pending Approvals” card
- Jo content approvals dikh rahe hain unpe **✓ / ✕** decide karo

Option B (Mission Control Approvals tab):
- `/app/automation` → tab **📥 Approvals**
- “Pending load” under **Content Approvals** → **✓ / ✕**

Option C (Mission Control ClientOps):
- `/app/automation` → tab **🤝 ClientOps**
- “Pending load” → list me **✓ / ✕**

Backend reference:
- List: `GET /api/clientops/approvals?status=pending&client_id=...`
- Decide: `POST /api/clientops/approvals/{approval_id}/decide` `{action: approve|reject, note}`

### 2B Self-improve approvals (if approval gate ON)
- `/app/admin` → **Automation Hub** → “Pending Approvals”
- Self-improve approvals pe ✓ (approve) / ✕ (reject)

Backend reference:
- `GET /api/growth/selfimprove/approvals-pending`
- `PATCH /api/growth/selfimprove/approval/{id}/approve|reject`

### 2C Process breakpoints (WAITING)
- `/app/automation` → tab **⚙️ Processes**
- Runs list → WAITING run ko **Approve/Reject** karo

Backend reference:
- `GET /api/growth/process/runs`
- `POST /api/growth/process/run/{run_id}/approve|reject`

## Step 3 — Automation workflows (manual run buttons)
Open: `/app/admin` → **Automation Hub**

Use-case driven:
- **Prospects/Scrape**: “Scrape Prospects”
- **Email outreach**: “Email Outreach” (SMTP warmup + daily cap respected)
- **Followups**: “Email Followups”
- **Reply triage**: “Reply Triage” (draft-only; auto-send gated)
- **Harvest**: “Lead Harvest” (multi-source; keys absent ho to graceful)
- **Cadence**: “Cadence Run” (draft steps)
- **Lifecycle**: “Lifecycle”
- **Content/Blog**: “Daily Content” / “SEO Blog”
- **Growth pulse**: “Growth Pulse”
- **Reviews**: “Review Monitor”
- **Journeys**: “Journeys Emit” (test event; `JOURNEY_ENGINE=1` chahiye)
- **Sales team**: “Sales Team” (BANT deep-dive drafts)
- **Upgrader**: “Upgrader Scan” (code patch proposals)
- **QA**: “QA Run” (Arjun)
- **Prospects**: “Prospects Run” (Rohan scrape batch)

Note:
- Ye actions **idempotent-ish** hain, par spam avoid: ek hi cheez 2-3 baar back-to-back mat run karo.

## Step 4 — Launch calling campaign (safe)
Open: `/app/admin` → **🚀 Launch Campaign**

Before clicking “Fire Campaign”:
- God Mode me **CALLING READY** (score ≥ 70)
- TRAI window open
- DND/DLT compliance: promotional cold-calling tabhi jab allowed

After launch:
- “Status” pe monitor
- “Stop” available
- Recordings: `/app/admin` → “Call Recordings”

Backend reference:
- Ready leads: `GET /api/admin/leads/ready`
- Launch: `POST /api/admin/campaign/launch`
- Status: `GET /api/admin/campaign/status`
- Stop: `POST /api/admin/campaign/stop`
- Recordings: `GET /api/admin/call-recordings`

## Step 5 — If something fails (triage fast)
Checklist:
- 401/403 everywhere → admin token missing/expired (re-login)
- Buttons respond but no effect → open browser console (network) and verify endpoint response
- Calling errors → God Mode telephony actions list

## User-action blockers (cannot be coded away)
- Razorpay keys / webhook secrets
- UPI_VPA
- Exotel/Vobiz KYC/balance/DID
- DLT approval for cold promotional calling
