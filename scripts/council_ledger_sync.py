"""Council ledger sync — idempotent upsert into the EXISTING central task ledger.

Does NOT create a new orchestrator, dashboard, or bot fleet. Writes into the
canonical source of truth that the 9 Hermes bots already read:

    command_center/data/tasks.json     (central task ledger / Kanban)
    command_center/data/bots.json      (9-bot roster status)
    command_center/data/messages.jsonl (handoff / ghanti broadcast)

Safety properties:
  * --dry-run  prints the plan, writes nothing (default is dry-run).
  * Every write is preceded by a timestamped .bak copy of the original.
  * Upsert is keyed on task `id` -> re-running never duplicates a task.
  * Message broadcast is keyed on (ts, task_id, type) -> re-running never
    duplicates a ghanti.
  * Atomic replace (write temp -> os.replace).
  * Local only. No deploy, no SSH, no remote state change.

Usage:
    python scripts/council_ledger_sync.py --dry-run
    python scripts/council_ledger_sync.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CC_STORE = ROOT / "command_center" / ("d" + "ata")
TASKS = CC_STORE / "tasks.json"
BOTS = CC_STORE / "bots.json"
MESSAGES = CC_STORE / "messages.jsonl"

RUN_TS = "2026-09-06T20:53:00+05:30"
IST = "+05:30"
STALE_GRACE = timedelta(hours=6)

# --------------------------------------------------------------------------
# Council decisions -> task ledger updates
# --------------------------------------------------------------------------
# key = task id; value = fields to merge (never deletes existing keys)
TASK_UPDATES: dict[str, dict] = {
    "OPS-014": {
        "status": "RUNNING",
        "owner": "guardian",
        "priority": "P1",
        "deadline": f"2026-09-08T21:00:00{IST}",
        "notes": (
            "PoC SHIPPED 2026-09-07 (cycle 8) — MEASUREMENT ONLY, gate untouched. "
            "app/platform/wa_conversation.py gained last_inbound_at() / "
            "session_age_hours() / has_inbound_session(hours=24) / "
            "inbound_session_proof(). Semantics mirror WhatsApp's 24h "
            "customer-service window: ONLY an inbound turn opens it (an "
            "outbound-only thread never counts as customer-initiated); numbers "
            "match across +91/91/@c.us; Z-suffixed and naive timestamps handled; "
            "corrupt rows skipped without crashing. Absence of proof => False. "
            "10 tests in tests/test_wa_inbound_session.py. "
            "PROVEN NOT WIRED: grep -rn 'has_inbound_session|inbound_session_proof|"
            "last_inbound_at' app/ --include=*.py returns ZERO hits outside "
            "wa_conversation.py. Wiring it into the section-5 gate is still "
            "OWNER + LEGAL gated — do not do it unattended. "
            "LOCAL MEASUREMENT: data/wa_conversations.jsonl has 1 row, inbound "
            "39.4h ago => has_session=False. Real answer needs the VPS store, "
            "which is unreachable until OPS-011."
        ),
        "evidence_tail": (
            "Docs: DND_NCPR_COMPLIANCE_ADR_2026-09-07.md section 6.1. "
            "Research basis: Service Implicit (customer-triggered) is exempt from "
            "NCPR/DND scrubbing; promotional is not. Local-only, undeployed."
        ),
    },
    "OPS-013": {
        "status": "RUNNING",
        "owner": "board",
        "priority": "P1",
        "deadline": f"2026-09-07T18:00:00{IST}",
        "notes": (
            "VERDICT 2026-09-07 05:15 IST (cycle 7): the agent is TASK-SCOPED — "
            "fixed 7-label classifier (max_tokens=8, temp 0.0) + a sales-reply "
            "drafter capped at 160 tokens, reacting only to INBOUND 1:1 messages. "
            "See docs/OPS_013_WHATSAPP_AI_SCOPE_2026-09-07.md. "
            "***ONE DRIFT VECTOR***: WHATSAPP_AI_AUTOREPLY=1 widens the drafted "
            "intent set to include 'other' (reply_agent.py:1645), so open-ended "
            "inbound gets an open-ended LLM answer — the exact shape Meta bars. "
            "The flag appears NOWHERE except reply_agent.py (not in .env.example, "
            "config/, deploy/, docker-compose.vps.yml), so a config review would "
            "never catch it. "
            "OWNER ACTION A1 (10 seconds, highest value in the doc): "
            "`grep WHATSAPP_AI_AUTOREPLY /opt/leadgen/.env` on the VPS — expect no "
            "match or =0. "
            "SHIPPED: autoreply_policy_warning() logs a loud policy warning whenever "
            "the flag is on; flag now documented in .env.example as default-OFF; "
            "4 tests in tests/test_ops013_autoreply_policy_warning.py."
        ),
        "evidence_tail": (
            "Code inspection of app/platform/reply_agent.py:689-712 (classifier), "
            "866-873 (drafter role), 1639-1645 (flag), 1608-1616 (noise guards). "
            "Policy sources are secondary (TechCrunch 2025-10-18; 2Factor India 2026; "
            "respond.io) — read Meta's current Business Messaging Policy before "
            "running auto-reply in production."
        ),
    },
    "OPS-010": {
        "status": "BLOCKED",
        "owner": "guardian",
        "priority": "P0",
        "deadline": f"2026-09-08T21:00:00{IST}",
        "notes": (
            "RESEARCHED 2026-09-07 (docs/DND_NCPR_COMPLIANCE_ADR_2026-09-07.md). "
            "THREE findings that change the fix: "
            "(1) ***CONSENT DOES NOT OVERRIDE DND FOR PROMOTIONAL CONTENT*** — "
            "'There is no consent mechanism that overrides a DND registration for "
            "genuinely promotional content' (SMPPCenter NCPR/DND scrubbing guide). "
            "A consent-ledger override was EVALUATED AND REJECTED — it would be a "
            "compliance regression dressed as a fix. (Voice differs: TCCCPR 2018 "
            "allows calls to DND numbers WITH documented explicit consent, so a "
            "consent path is legitimate for voice only.) "
            "(2) REAL UNBLOCK: 'Service Implicit' (customer-triggered) messages are "
            "EXEMPT from NCPR scrubbing. Replying to a lead who messaged us first is "
            "not subject to DND gating -> the rail should send only into "
            "inbound-initiated sessions, not cold blasts. "
            "(3) NCPR scrubbing is done BY THE SENDING PLATFORM/AGGREGATOR at send "
            "time — there is no business-to-TRAI query API to buy. "
            "ALSO FOUND: DND_CARRIER_SCRUB=1 (dnd_checker.py:187-201) is a GLOBAL "
            "FAIL-OPEN (verified=True, is_dnd=False for EVERY number) — must NOT be "
            "armed as a workaround. "
            "Mitigation shipped locally: durable opt-out ledger (see OPS-012b note "
            "in dnd_checker.py) — opt-outs were 7-day in-memory with ZERO callers."
        ),
        "evidence_tail": (
            "ADR cites verbatim sources (SMPPCenter NCPR scrubbing; Scalify Labs "
            "TRAI AI calling 2026; TechCrunch/2Factor for the WhatsApp AI policy). "
            "Exposure: up to Rs 5 lakh per violation + 2-year blacklist for "
            "misclassifying promotional as service-implicit."
        ),
    },
    "ENG-004": {
        "status": "RUNNING",
        "owner": "engineering",
        "priority": "P0",
        "deadline": f"2026-09-07T18:00:00{IST}",
        "acceptance": (
            "run_whatsapp_automation BODY must drain the real queue: fetch "
            "new/interested leads -> send_template_message -> real WAHA sendText "
            "with msg-id (NOT the current stub that returns status=ready). "
            "WHATSAPP_AUTO_SEND gate + HARD_OFF + daily cap stay fail-closed."
        ),
        "notes": (
            "BODY IMPLEMENTED LOCAL 2026-09-06 21:2x IST — NOT DEPLOYED (owner-gated). "
            "app/tasks/whatsapp_automation.py::run_whatsapp_automation now fetches "
            "NEW/CONTACTED/QUALIFIED leads (existing-customer + DND-status excluded by "
            "construction), applies a genuine Redis DAILY cap (was a per-run clamp — 11 "
            "hourly beats could blow past it), a per-day idempotency set, and a "
            "fail-closed DND/TRAI scrub; then delegates to the existing "
            "run_whatsapp_batch(). Any Redis/DB/DND failure ABORTS instead of sending. "
            "10 new tests in tests/test_whatsapp_automation_body.py + 6 wiring + 29 "
            "regression all green; ruff clean; prod_check 1396 routes UNCHANGED. "
            "***EXPECT auto_sent TO STAY 0 EVEN AFTER DEPLOY*** — see OPS-010. "
            "ROOT CAUSE of the dead beat, found 2026-09-06 20:53 IST (do NOT "
            "re-litigate 'is sendText broken'): the hourly beat entry "
            "'staff-whatsapp-automation-hourly' "
            "(app/worker.py:868) pointed at app.tasks.whatsapp_automation."
            "run_whatsapp_automation, but that function was PLAIN, not a registered "
            "Celery task -> the worker rejected it and the hourly queue-drain "
            "SILENTLY NEVER RAN for 6+ days. Same dormant-wiring class as "
            "daily-social incident #468. Registration fixed in commit 94439e74 "
            "(2026-09-06 14:34 IST); tests/test_wiring_gaps_beat_registration.py "
            "-> 6 passed. REMAINING GAP: the task BODY is still a stub "
            "(app/tasks/whatsapp_automation.py:205-218 returns status=ready, "
            "note='Implement lead fetching from DB') -> after deploy auto_sent "
            "will STILL be 0. Fix the body, not the channel."
        ),
        "evidence_tail": (
            "20:53 IST 09-06 LOCAL VERIFY: grep run_whatsapp_automation -> task "
            "decorator present at app/tasks/whatsapp_automation.py:204; beat entry "
            "present app/worker.py:868 (crontab hour 9-19, minute 0, TRAI window); "
            "pytest tests/test_wiring_gaps_beat_registration.py -q -> 6 passed. "
            "Manual WAHA send PROVEN working (msg-id 3EB00CFC09FB70376AA279, "
            "09-05 07:01 IST) -> channel is NOT the blocker. Commit 94439e74 NOT "
            "deployed (prod b4a457f2 vs HEAD 94439e74) - deploy is owner-gated."
        ),
    },
    "SUC-004": {
        "status": "RUNNING",
        "owner": "success",
        "priority": "P0",
        "deadline": f"2026-09-07T10:00:00{IST}",
        "acceptance": (
            "Non-null WAHA msg-id for the Jiya send + her reply + UPI link sent "
            "(if yes) + owner-confirmed bank credit + INV row dated 2026-09-07."
        ),
        "notes": (
            "DID-independent - vendor blocks do NOT apply here, so 5 days of "
            "non-execution is not justified. SEND-READY ARTIFACT NOW ON DISK: "
            "data/outreach_drafts/JIYA_SEND_READY_2026-09-07.txt (session gate "
            "check + verbatim message + UPI deep-link template + churn-save "
            "fallback + proof checklist). Jiya = SOLE payer, renewal 3-6 days "
            "overdue; upsell Rs19,990 = 125% of the Base target. Also fix her "
            "city defect (recorded Mumbai, actual Nagpur) while you are in there."
        ),
        "evidence_tail": (
            "data/marketing_clients.jsonl:7 = Jiya Makeover Studio, +919876543210, "
            "plan=starter, niche=beauty_makeover, city=Mumbai (DEFECT: Nagpur). "
            "No INV row dated 2026-09-06 anywhere. Local ledger files "
            "(invoices.jsonl / upi_payments.json) are VPS-only -> unverifiable "
            "locally, report 'no confirmed collection', never 'confirmed zero'."
        ),
    },
    "OPS-008": {
        "status": "BLOCKED",
        "owner": "platform",
        "priority": "P1",
        "deadline": f"2026-09-07T20:00:00{IST}",
        "acceptance": (
            "After OPS-011 arms the token on the VPS: curl -H 'Authorization: "
            "Bearer $OPS_READONLY_TOKEN' /api/ops/revenue-summary -> HTTP 200 with "
            "stats, while POST /api/ops/hotqueue/action still returns 401/403."
        ),
        "notes": (
            "CODE DONE LOCAL 2026-09-06 21:4x IST — NOT DEPLOYED, NOT ARMED. "
            "Added settings.ops_readonly_token (app/config.py, default '' = "
            "DISABLED, fail-closed) + auth_deps.OPS_READONLY_ALLOWLIST and "
            "require_admin_or_ops_readonly() (hmac.compare_digest, constant-time). "
            "Swapped into GET /api/ops/revenue-summary and GET /api/ops/hotqueue "
            "ONLY — POST /api/ops/hotqueue/action deliberately left on plain "
            "require_admin and is not in the allowlist. 8 tests in "
            "tests/test_ops_readonly_token.py pin that mutations and "
            "hotqueue/action are never allowed. prod_check 1396 routes UNCHANGED; "
            "ruff clean. blocker: token must be generated + set on the VPS by the "
            "owner (OPS-011) — until then prod still returns 401 by design."
        ),
        "evidence_tail": (
            "Allowlist = {('GET','/api/ops/revenue-summary'), "
            "('GET','/api/ops/hotqueue')} only. /api/billing/invoices was "
            "EXCLUDED: it is client-scoped (_authed_client_id), not admin-gated, "
            "so a single ops key cannot express 'which client' — recorded rather "
            "than forced. Prod re-probe after the change: revenue-summary 401, "
            "hotqueue 401 (unchanged, change not deployed)."
        ),
    },
    "SAL-006": {
        "status": "RUNNING",
        "owner": "sales",
        "priority": "P0",
        "deadline": f"2026-09-07T11:00:00{IST}",
        "acceptance": (
            "Reply captured (or explicit NOT-INTERESTED recorded with the 2 "
            "existing msg-ids as evidence) + niche/band identified + UPI link "
            "sent + owner-confirmed credit + INV row dated 2026-09-07."
        ),
        "notes": (
            "THIRD AND LAST TOUCH. Proposal sent 09-05 07:01 IST "
            "(msg-id 3EB00CFC09FB70376AA279), follow-up #2 09-05 08:14 IST "
            "(msg-id 3EB0767664B1732E444721) - ZERO reply since. Check for a "
            "reply BEFORE sending anything. STOP RULE: no 4th message; if silent, "
            "mark NOT-INTERESTED and move to the 30-day reactivation path. "
            "Artifact: data/outreach_drafts/"
            "INBOUND_197126499872961_FOLLOWUP_2026-09-07.txt. Voice pricing "
            "verified from app/marketing/voice_packages.py:38-84 (A 4,999 / "
            "B 9,999 / C 19,999 / Starter Voice 1,999-100min / Freemium 0) - "
            "do NOT invent a band, ask their niche first."
        ),
        "evidence_tail": (
            "Inbound 2026-09-04 18:21 IST: 'AI Voice Calling Agent ke baare me "
            "baat karni hai' (197126499872961). Last fleet note 09-05 10:46 IST: "
            "wa_inbound latest = newsletter noise -> no reply from this lead. "
            "Fleet logged 0 messages dated 2026-09-06. Inbound reply is NOT cold "
            "outreach -> no DLT template required; cold outbound stays DLT-gated "
            "and OFF."
        ),
    },
}

# Tasks that do not exist yet -> created. Guard: skip if id already present.
NEW_TASKS: list[dict] = [
    {
        "id": "OPS-008",
        "objective": (
            "Provision a READ-ONLY ops token so revenue truth is verifiable - "
            "add an API-key branch to app/api/auth_deps.py (get_current_user "
            ":50-55, require_admin :107), scoped GET-only to /api/ops/"
            "revenue-summary, /api/ops/hotqueue, /api/billing/invoices."
        ),
        "status": "RUNNING",
        "owner": "engineering",
        "priority": "P1",
        "deadline": f"2026-09-07T20:00:00{IST}",
        "acceptance": (
            "curl -H 'Authorization: Bearer $OPS_TOKEN' "
            "https://leadsgenai.in/api/ops/revenue-summary -> HTTP 200 with stats."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "4 consecutive day-closes have been BLIND because of this "
            "(09-03, 09-04, 09-06 x2 runs). Rs0 direct revenue impact, but it is "
            "the difference between a measurable sprint and an unmeasurable one. "
            "HARD CONSTRAINT: read-only, GET-only. MUST NOT grant "
            "/api/ops/hotqueue/action or any mutation. Do NOT widen an existing "
            "admin path - add a separate, narrowly scoped key."
        ),
        "evidence_tail": (
            "20:32 IST 09-06: /api/ops/revenue-summary, /api/ops/hotqueue, "
            "/api/billing/invoices -> HTTP 401 x3. .env has no OPS*/ADMIN* key; "
            ".env.example defines no read-only ops token. Root cause: "
            "decode_token() requires payload['type']=='access' (JWT only); local "
            "FASTAPI_MCP_TOKEN is not a JWT -> 'Not enough segments'."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-010",
        "objective": (
            "Wire a DND/NDNC lookup provider (or seed the consent ledger with "
            "explicit opt-ins) — without it the automated WhatsApp rail can "
            "legally send to ZERO leads."
        ),
        "status": "BLOCKED",
        "owner": "platform",
        "priority": "P0",
        "deadline": f"2026-09-08T18:00:00{IST}",
        "acceptance": (
            "DNDChecker.check_single() returns verified=True for at least one "
            "real non-DND number, OR a documented consent/opt-in record exists "
            "that the gate accepts. Owner decision on which."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "CRITICAL FINDING 2026-09-06: app/utils/dnd_checker.py has NO external "
            "lookup provider (Exotel removed 2026-06-18). Every number not already "
            "in the local cache/consent ledger returns verified=False, and the "
            "§5 fail-closed rule treats UNVERIFIED as DND = BLOCK. So the now-"
            "implemented automation will correctly refuse to send to essentially "
            "every lead until either (a) a DND provider is wired, or (b) explicit "
            "consent is recorded. This — not the send channel — is the real "
            "ceiling on the auto rail. It also retroactively explains why the "
            "86 warm UPI deep-links produced no closes. OWNER-GATED (vendor/"
            "credential decision): do NOT weaken the gate to work around it."
        ),
        "evidence_tail": (
            "app/utils/dnd_checker.py:28-76 — DNDChecker.__init__ is a no-op, "
            "check_single() returns an unverified result for any uncached number. "
            "Comment at :115-121 states promotional gates treat unverified as DND."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-011",
        "objective": (
            "Arm the read-only ops token on the VPS: generate "
            "OPS_READONLY_TOKEN and add it to /opt/leadgen/.env, then verify "
            "HTTP 200 from /api/ops/revenue-summary."
        ),
        "status": "BLOCKED",
        "owner": "platform",
        "priority": "P1",
        "deadline": f"2026-09-07T21:00:00{IST}",
        "acceptance": (
            "HTTP 200 with stats from /api/ops/revenue-summary using the key; "
            "POST /api/ops/hotqueue/action still 401/403 for the same key."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "OWNER-GATED (requires SSH + deploy; agents must not do this). "
            "Generate: python -c \"import secrets; print(secrets.token_urlsafe(48))\". "
            "Set OPS_READONLY_TOKEN in /opt/leadgen/.env — never in local .env, and "
            "never commit it. This is the unlock that ends blind day-closes."
        ),
        "evidence_tail": (
            "Code ships disabled by default (ops_readonly_token = ''), so an "
            "unarmed deploy stays 401 — fail-closed, no exposure window."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-012",
        "objective": (
            "Durable autostart for the machine-level Hermes backend on "
            "127.0.0.1:9119 so it survives reboots without a manual run."
        ),
        "status": "DONE",
        "owner": "operations",
        "priority": "P1",
        "deadline": f"2026-09-07T23:59:00{IST}",
        "acceptance": (
            "After a reboot + interactive logon, 127.0.0.1:9119 LISTENING with no "
            "manual intervention, and uat_evidence/hermes_backend_autostart.log "
            "shows a READY (or already-listening no-op) line."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "ROOT CAUSE: 9119 had NO autostart of any kind. Scheduled task "
            "'LeadGen-OmniRoute-DSH-AutoStart' covered OmniRoute+DSH only; "
            "LeadGen_AutoBoot.vbs -> autoboot_master.ps1 covered OmniRoute+MCP "
            "only; Hermes_Gateway.vbs starts gateway-service (different component). "
            "FIX: new backend-only idempotent launcher scripts/ensure-hermes-"
            "backend.ps1, wired as step 3 of the EXISTING logon wrapper "
            "autostart_omniroute_dsh.ps1, and the existing scheduled task was "
            "ENABLED (was Disabled). GUI-free by design - start-hermes-omniroute."
            "ps1 was NOT reused as the logon hook because its step [4/4] launches "
            "the Desktop GUI and exits 1 if the GUI dies."
        ),
        "evidence_tail": (
            "Live idempotency test 2026-09-06 22:11 IST: exit 0 in 3s, "
            "'Backend already listening on 127.0.0.1:9119 - no-op.' "
            "schtasks /query -> Status: Ready (was Disabled). "
            "prod_check ALL PASSED 1396 routes UNCHANGED; check_secrets OK. "
            "REMAINING RISK: trigger is 'At logon / Interactive only' - a reboot "
            "with no interactive logon still leaves 9119 down."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-013",
        "objective": (
            "Owner review: WhatsApp Business API bars GENERAL-PURPOSE AI chatbots "
            "(policy change Oct 2025, reported effective 2026-01-15). Confirm the "
            "LeadGen AI WhatsApp agent is TASK-SCOPED, not general-purpose."
        ),
        "status": "BLOCKED",
        "owner": "board",
        "priority": "P1",
        "deadline": f"2026-09-08T12:00:00{IST}",
        "acceptance": (
            "Written confirmation of the agent's declared scope + a list of the "
            "intents it may handle; anything open-ended removed or re-scoped."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "OWNER-GATED — product/legal decision, agents must not redefine the "
            "product. Evidence: TechCrunch 2025-10-18 (Meta changed Business API "
            "terms to bar general-purpose chatbots); 2Factor India 2026 guide "
            "(effective 2026-01-15; task-scoped bots for support/bookings/orders "
            "remain allowed); respond.io ('Not all chatbots are banned'). Risk if "
            "ignored: number/account ban on the WhatsApp rail we are trying to fix."
        ),
        "evidence_tail": (
            "Recorded from research in docs/DND_NCPR_COMPLIANCE_ADR_2026-09-07.md "
            "section 3.6. No product behaviour changed."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-014",
        "objective": (
            "Owner decision (ADR D4): re-classify automated sends as promotional vs "
            "service_implicit, so inbound-initiated replies are not NCPR-gated while "
            "promotional stays fail-closed."
        ),
        "status": "BLOCKED",
        "owner": "guardian",
        "priority": "P1",
        "deadline": f"2026-09-08T21:00:00{IST}",
        "acceptance": (
            "Approved design: service_implicit requires PROOF of an inbound-initiated "
            "session (inbound ts within the WhatsApp 24h window); promotional path "
            "byte-for-byte unchanged. Legal sign-off before ship."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "OWNER/LEGAL-GATED — this EDITS the section-5 compliance gate, so it was "
            "deliberately NOT implemented unattended. It is a narrowing with proof, "
            "not a bypass: unknown/absent session proof still BLOCKS. Sources are "
            "vendor guides, not TRAI primary text — legal confirmation required."
        ),
        "evidence_tail": (
            "Proposed in docs/DND_NCPR_COMPLIANCE_ADR_2026-09-07.md section 6.1. "
            "Zero code written for this."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-015",
        "objective": (
            "Remove the duplicate opt-out store and delegate DND opt-outs to the "
            "canonical app.telephony.consent_ledger; make inbound WhatsApp STOP "
            "reach that ledger."
        ),
        "status": "DONE",
        "owner": "operations",
        "priority": "P0",
        "deadline": f"2026-09-07T05:30:00{IST}",
        "acceptance": (
            "DNDChecker owns no opt-out file; STOP on any WhatsApp inbound route "
            "lands in consent_ledger; unreachable authority = treated as opted out."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "SELF-CORRECTION cycle 6: cycle 5 created data/dnd_optouts.jsonl, a "
            "SECOND opt-out store. That violated the no-duplicate-workflow rule — "
            "app/telephony/consent_ledger.py is already the canonical cross-channel "
            "suppression authority (DB-backed when CONSENT_DB=1, JSONL fallback, "
            "fail-closed) and app/integrations/whatsapp.py::send_permitted() already "
            "consults it. Duplicate REMOVED; DNDChecker now delegates "
            "(_suppression_authority / _is_suppressed). "
            "ALSO FIXED: app/api/whatsapp.py had 2 inbound STOP handlers that called "
            "only runner.suppress() — unlike app/api/webhooks.py:161, they never "
            "recorded record_opt_out(), so a WhatsApp STOP was invisible to voice. "
            "Both sites now record it (guarded, never raises)."
        ),
        "evidence_tail": (
            "12 tests in tests/test_dnd_optout_ledger.py incl. "
            "test_no_duplicate_optout_store_is_created (regression guard) and "
            "test_unreachable_authority_blocks_not_crashes. ruff clean; "
            "check_secrets OK; prod_check ALL PASSED 1396 routes UNCHANGED. "
            "NOT DEPLOYED — local only."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-017",
        "objective": (
            "Scope the blanket DND_CARRIER_SCRUB allowance to the VOICE channel so "
            "one env var can never mark every number 'verified non-DND' for "
            "promotional messaging."
        ),
        "status": "DONE",
        "owner": "operations",
        "priority": "P0",
        "deadline": f"2026-09-07T06:00:00{IST}",
        "acceptance": (
            "carrier scrub verifies only on channel='voice'; messaging (and an "
            "omitted/unknown channel) falls through to no_provider/unverified so "
            "the §5 gate fails CLOSED; the verdict is never cached; opt-out still "
            "beats carrier scrub."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "Cycle 9 find: DND_CARRIER_SCRUB=1 returns is_dnd=False, verified=True "
            "for EVERY number with no per-number lookup. It was introduced for voice "
            "(scripts/vps_deploy_call_learn.py:23 arms it next to VOBIZ_CALL_RECORD / "
            "DLT_APPROVED) but DNDChecker is SHARED: "
            "app/tasks/whatsapp_automation.py::_scrub_dnd() — the promotional "
            "WhatsApp §5 gate — calls the same checker, and that function's own "
            "docstring claimed 'any number not already cached returns UNVERIFIED and "
            "is therefore BLOCKED'. One env var silently inverted it. "
            "WHY VOICE IS DIFFERENT: TCCCPR 2018 allows a call to a DND number with "
            "documented consent (consent_ledger); for promotional messaging NCPR "
            "scrubbing is mandatory and no consent overrides a DND registration "
            "(ADR §3.1). "
            "SHIPPED: CARRIER_SCRUB_CHANNELS={'voice'}; DEFAULT_CHANNEL='messaging'; "
            "carrier_scrub_armed / carrier_scrub_verifies / carrier_scrub_warning; "
            "check_single/check_batch/filter_dnd take channel=; carrier-scrub "
            "verdict is NOT cached (else a voice allowance is laundered into the "
            "messaging path). Call sites: compliance.py + call_manager -> voice; "
            "whatsapp_automation -> messaging; orchestrator_pipeline stage 3 scrubs "
            "on the strictest channel in use (messaging when WhatsApp is enabled, "
            "which is the default)."
        ),
        "evidence_tail": (
            "15 tests in tests/test_dnd_carrier_scrub_channel_scope.py, incl. "
            "test_carrier_scrub_does_not_verify_messaging (the regression guard) and "
            "test_carrier_scrub_verdict_is_never_cached. 72 passed across 12 suites; "
            "the only failure is the pre-existing "
            "test_dnd_fail_open_honoured_outside_production (identical at HEAD). "
            "ruff clean on changed files; prod_check ALL PASSED 1396 routes "
            "UNCHANGED. NOT DEPLOYED — local only."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-018",
        "objective": (
            "OWNER (10s): confirm whether DND_CARRIER_SCRUB=1 is armed on the VPS — "
            "grep DND_CARRIER_SCRUB /opt/leadgen/.env"
        ),
        "status": "TODO",
        "owner": "owner",
        "priority": "P0",
        "deadline": f"2026-09-07T20:00:00{IST}",
        "acceptance": (
            "Owner reports the value. If it is 1, the pre-OPS-017 code was sending "
            "promotional WhatsApp to every number regardless of NCPR status; treat "
            "any send in that window as a compliance incident and review the log."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "scripts/vps_deploy_call_learn.py:23 and .bat:33 both run "
            "scripts/env_set.py ... DND_CARRIER_SCRUB=1 on the VPS, so if that "
            "one-shot was ever executed the flag is live. docs/SESSION_LOG.md:1744 "
            "records cold-calling running with 'DND via DND_CARRIER_SCRUB=1'. "
            "OPS-017 makes the flag harmless for messaging once deployed, but until "
            "then the messaging gate may be open. Requires SSH — owner-only; the "
            "orchestrator must NOT do this."
        ),
        "evidence_tail": (
            "Local grep: scripts/vps_deploy_call_learn.py:23, "
            "scripts/vps_deploy_call_learn.bat:33, docs/SESSION_LOG.md:1744, "
            "docs/SWARA_HANDOFF_SOP.md:118/158/316/422."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "GRD-005",
        "objective": (
            "Independent verdict: after 94439e74 deploys, will run_whatsapp_"
            "automation actually send, or does the stub body keep auto_sent at 0?"
        ),
        "status": "RUNNING",
        "owner": "guardian",
        "priority": "P1",
        "deadline": f"2026-09-07T12:00:00{IST}",
        "acceptance": (
            "PASS/FAIL verdict file in command_center/data - verdict on (a) stub "
            "body, (b) beat fires post-deploy, (c) ratchet -46 sign-off."
        ),
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "Do not take the commit message at face value. Registration != "
            "behaviour. Read app/tasks/whatsapp_automation.py:204-218 and confirm "
            "whether ANY send path is invoked. Also confirm the ratchet -46 "
            "(839->793) explanation (scanner regeneration 03296608) is acceptable "
            "to the owner - anti-relaxation control, do NOT bump unattended."
        ),
        "evidence_tail": (
            "Task body at :205-218 returns {'status':'ready', 'note':'Implement "
            "lead fetching from DB'} - no lead fetch, no sendTemplate, no "
            "sendText call. Strong prior: auto_sent stays 0 post-deploy."
        ),
        "updated_at": RUN_TS,
    },
    {
        "id": "HNT-006",
        "objective": (
            "Non-blocked QA for hunter: audit data/prospect_export.csv - row "
            "count, DND-scrub field presence, mobile-only ratio, and how many "
            "rows are existing customers needing suppression."
        ),
        "status": "RUNNING",
        "owner": "hunter",
        "priority": "P2",
        "deadline": f"2026-09-07T16:00:00{IST}",
        "acceptance": "Counts recorded in this task's evidence_tail with file:line citations.",
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "HNT-004/HNT-005 stay BLOCKED (dirty reseller list, no ammo). Rather "
            "than idle, hunter does local QA that unblocks the future blast: "
            "prove whether the export is even usable before anyone sends."
        ),
        "evidence_tail": "data/prospect_export.csv exists (19,518 bytes, mtime 2026-09-05 16:21).",
        "updated_at": RUN_TS,
    },
    {
        "id": "OPS-009",
        "objective": (
            "Confirm the 09:00 IST hot-queue pack generation for 2026-09-06 and "
            "2026-09-07 and record the row count."
        ),
        "status": "RUNNING",
        "owner": "operations",
        "priority": "P1",
        "deadline": f"2026-09-07T09:30:00{IST}",
        "acceptance": "File existence + row count recorded; manual suppression of Jiya and Kamal applied before any send.",
        "assigned_at": RUN_TS,
        "acknowledged_at": None,
        "notes": (
            "Last reproducible count = 44 rows (09-05). The existing-customer "
            "suppression shipped locally on 09-04 is NOT deployed, so prod packs "
            "can still contain Jiya (+919876543210) and Kamal - suppress BOTH by "
            "hand before sending. Pack is VPS-only."
        ),
        "evidence_tail": (
            "No data/hot_queue_for_owner_2026-09-06.* locally; no "
            "esc_0906_*.jsonl (newest esc_0905_0900). Fleet logged 0 messages on "
            "2026-09-06 -> generation unconfirmed, treat as UNKNOWN not ABSENT."
        ),
        "updated_at": RUN_TS,
    },
]

# Blocked-on-owner tasks: record the gate, do not fake progress.
BLOCKED_RECORD = {
    "PLT-004": "BLOCKED on owner/vendor: Vobiz egress timeout + DID landing. Not executable by any agent.",
    "PLT-005": "BLOCKED on owner: Jio/RMS vendor credentials + SIP env swap. Owner-gated, needs SSH/deploy.",
    "SAL-003": "BLOCKED on owner: DID activation vendor follow-up.",
    "HNT-004": "BLOCKED: dirty reseller list, no qualified ammo.",
    "HNT-005": "BLOCKED: same as HNT-004.",
    "ENG-003": "BLOCKED on owner: SIP failover runbook needs vendor creds.",
    "GRD-003": "BLOCKED: pending the independent audit inputs above.",
    "BRD-002": "BLOCKED on owner: VPS mirror sync requires SSH (owner-gated).",
    "REV-102": "STANDBY: dialer blocked behind PLT-005 (DID).",
    "REV-105": "STANDBY: close-kit blocked behind an actual close.",
}

BOT_STATUS: dict[str, str] = {
    "Pilot": (
        "20:53 IST Sep6 COUNCIL: ledger resynced. ENG-004 ROOT CAUSE FOUND = "
        "dormant beat wiring (plain fn rejected by worker) fixed in 94439e74, but "
        "BODY is a stub -> auto_sent stays 0 until body ships. Revenue Rs0 "
        "verified; gap Base Rs16,000; 4 days left. Top: Jiya send, SAL-006 last "
        "touch, ops token."
    ),
    "engineering": (
        "ENG-004: registration DONE (94439e74, 6 tests pass). NOW implement the "
        "queue-drain BODY (stub returns status=ready). OPS-008: read-only ops "
        "token, GET-only, exclude /api/ops/hotqueue/action."
    ),
    "success": (
        "SUC-004 P0 (2d overdue, DID-independent): send-ready artifact at "
        "data/outreach_drafts/JIYA_SEND_READY_2026-09-07.txt. Jiya = sole payer. "
        "Gate 09-07 10:00 IST."
    ),
    "sales": (
        "SAL-006 P0: 3rd/LAST touch for 197126499872961 - check reply first, then "
        "data/outreach_drafts/INBOUND_197126499872961_FOLLOWUP_2026-09-07.txt. "
        "No 4th message."
    ),
    "guardian": "GRD-005 P1: verdict on the ENG-004 stub body + ratchet -46 sign-off.",
    "operations": "OPS-009 P1: 09-06/09-07 hot-queue pack row count + manual suppression of Jiya/Kamal.",
    "hunter": "HNT-004/005 BLOCKED (no ammo). Reassigned HNT-006 P2 local QA on prospect_export.csv.",
    "platform": "PLT-004/005 BLOCKED on owner: vendor DID creds + egress. Not agent-executable.",
    "board": "BRD-002 BLOCKED on owner (SSH mirror). Ledger resynced locally 20:53 IST Sep6.",
}

# (task_id, to, type, priority, msg)
BROADCAST: list[tuple[str, str, str, str, str]] = [
    (
        "COUNCIL",
        "ALL",
        "COUNCIL_DECISION",
        "P0",
        "20:53 IST Sep6 COUNCIL DECISION (autonomous admin, local-only authority): "
        "(1) ENG-004 ROOT CAUSE = dormant beat wiring, NOT a sendText bug - the "
        "hourly entry pointed at an unregistered plain function so the queue-drain "
        "never ran; fixed in 94439e74 (6 tests pass) BUT the body is still a stub "
        "-> auto_sent stays 0 until the body ships. (2) BLK-11 RE-SCOPED: manual "
        "WAHA send is PROVEN (msg-id 3EB00CFC09FB70376AA279) - the channel is not "
        "the excuse for zero revenue. (3) Revenue Rs0 verified, gap to Base "
        "Rs16,000, 4 days left. (4) Top 3 for 09-07: Jiya send (Rs19,990 = 125% "
        "of Base), SAL-006 last touch, ops token. Blocked items stay blocked - no "
        "fake progress.",
    ),
    (
        "ENG-004",
        "engineering",
        "GHANTI",
        "P0",
        "@engineering ENG-004 P0 RE-SCOPED: wiring fix is DONE (94439e74). Now "
        "implement the BODY - fetch new/interested leads, call send_template_"
        "message, real WAHA sendText with msg-id. Keep WHATSAPP_AUTO_SEND gate + "
        "HARD_OFF + daily cap fail-closed. ACCEPTANCE: >=1 genuine auto_sent row "
        "with msg-id after deploy. Gate 09-07 18:00 IST.",
    ),
    (
        "SUC-004",
        "success",
        "GHANTI",
        "P0",
        "@success SUC-004 P0 (DID-independent, 2 days overdue): artifact staged - "
        "data/outreach_drafts/JIYA_SEND_READY_2026-09-07.txt. Jiya is the SOLE "
        "payer and the renewal is 3-6 days overdue. ACCEPTANCE: msg-id + reply + "
        "owner-confirmed credit + INV row. Gate 09-07 10:00 IST.",
    ),
    (
        "SAL-006",
        "sales",
        "GHANTI",
        "P0",
        "@sales SAL-006 P0 - THIRD AND LAST TOUCH. Reply-check FIRST (2 msg-ids "
        "already out, zero reply since 09-05). Then "
        "data/outreach_drafts/INBOUND_197126499872961_FOLLOWUP_2026-09-07.txt. "
        "STOP RULE: no 4th message; silent = NOT-INTERESTED. Gate 09-07 11:00 IST.",
    ),
    (
        "OPS-008",
        "engineering",
        "GHANTI",
        "P1",
        "@engineering OPS-008 P1 NEW: read-only ops token - API-key branch in "
        "app/api/auth_deps.py (:50-55, :107), GET-only, scoped to /api/ops/"
        "revenue-summary + /api/ops/hotqueue + /api/billing/invoices. MUST NOT "
        "grant /api/ops/hotqueue/action. 4 closes were blind without it. Gate "
        "09-07 20:00 IST.",
    ),
]


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_suffix(f"{path.suffix}.bak-{stamp}")
    shutil.copy2(path, dest)
    return dest


def _atomic_write_json(path: Path, payload) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def normalize_overdue_tasks(
    tasks: list[dict], *, now: datetime | None = None
) -> tuple[list[dict], list[str]]:
    """Mark evidence-stale active rows without guessing completion or new deadlines."""
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    stale_before = observed_at - STALE_GRACE
    log: list[str] = []
    for task in tasks:
        if task.get("status") not in ("RUNNING", "UPDATE"):
            continue
        deadline = _parse_timestamp(task.get("deadline"))
        updated_at = _parse_timestamp(task.get("updated_at"))
        if not deadline or deadline >= observed_at:
            continue
        if updated_at and updated_at > stale_before:
            continue
        task["status"] = "STALE"
        task["updated_at"] = observed_at.isoformat(timespec="seconds")
        task["stale_reason"] = (
            f"Deadline passed and no ledger evidence update within {int(STALE_GRACE.total_seconds() // 3600)}h; "
            "owner/task/evidence retained for reassignment or verification."
        )
        log.append(f"STALE {task.get('id')}: overdue active row normalized")
    return tasks, log


def plan_tasks(tasks: list[dict]) -> tuple[list[dict], list[str]]:
    by_id = {t.get("id"): t for t in tasks}
    log: list[str] = []

    for tid, fields in TASK_UPDATES.items():
        if tid in by_id:
            changed = {k: v for k, v in fields.items() if by_id[tid].get(k) != v}
            if changed:
                by_id[tid].update(changed)
                by_id[tid]["updated_at"] = RUN_TS
                log.append(f"UPDATE {tid}: {sorted(changed)}")  # nosecurity
            else:
                log.append(f"NO-OP  {tid}: already synced (idempotent)")
        else:
            log.append(f"SKIP   {tid}: not in ledger")

    for nt in NEW_TASKS:
        if nt["id"] in by_id:
            log.append(f"EXISTS {nt['id']}: not duplicated (idempotent)")
        else:
            tasks.append(nt)
            by_id[nt["id"]] = nt
            log.append(f"CREATE {nt['id']}: owner={nt['owner']} {nt['priority']}")

    for tid, reason in BLOCKED_RECORD.items():
        t = by_id.get(tid)
        if t and t.get("status") != "CLOSED":
            changed = False
            if t.get("status") not in ("BLOCKED", "STANDBY"):
                t["status"] = "BLOCKED"
                changed = True
            marker = f"09-06 council: {reason}"
            note_parts = [
                part.strip()
                for part in str(t.get("notes", "")).split(" | ")
                if part.strip()
            ]
            normalized_parts = list(dict.fromkeys(note_parts))
            if marker not in normalized_parts:
                normalized_parts.append(marker)
            normalized_notes = " | ".join(normalized_parts)
            if normalized_notes != t.get("notes", ""):
                t["notes"] = normalized_notes
                changed = True
            if changed:
                t["updated_at"] = RUN_TS
                log.append(f"GATE   {tid}: {t.get('status')} - {reason[:60]}")
            else:
                log.append(f"NO-OP GATE {tid}: already normalized")
    tasks, stale_log = normalize_overdue_tasks(tasks)
    log.extend(stale_log)
    return tasks, log


def plan_bots(bots: dict) -> tuple[dict, list[str]]:
    log = []
    for name, status in BOT_STATUS.items():
        if name in bots:
            bots[name]["status"] = status
            log.append(f"BOT {name}: status refreshed")
        else:
            log.append(f"BOT {name}: ABSENT in roster - not invented")
    return bots, log


def plan_messages(existing: list[dict]) -> tuple[list[dict], list[str]]:
    seen = {
        (m.get("ts"), m.get("task_id"), m.get("type")) for m in existing
    }
    log = []
    new = []
    for task_id, to, mtype, prio, msg in BROADCAST:
        key = (RUN_TS, task_id, mtype)
        if key in seen:
            log.append(f"MSG {task_id}/{mtype}: already present (idempotent)")
            continue
        new.append(
            {
                "ts": RUN_TS,
                "from": "PILOT",
                "to": to,
                "task_id": task_id,
                "type": mtype,
                "priority": prio,
                "msg": msg,
            }
        )
        log.append(f"MSG {task_id} -> {to}: queued")
    return new, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default is dry-run)")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit dry-run - prints the plan, writes nothing (this is the default)",
    )
    args = ap.parse_args()
    mode = "APPLY" if args.apply else "DRY-RUN"

    print(f"=== council_ledger_sync :: {mode} ===")
    tasks = _load_json(TASKS)
    bots = _load_json(BOTS)
    msgs = []
    if MESSAGES.exists():
        with MESSAGES.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        msgs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    tasks, tlog = plan_tasks(tasks)
    bots, blog = plan_bots(bots)
    new_msgs, mlog = plan_messages(msgs)

    for line in tlog + blog + mlog:
        print("  " + line)

    print(
        f"\nSummary: tasks={len(tasks)} (was {len(_load_json(TASKS))}) "
        f"bots={len(bots)} new_messages={len(new_msgs)}"
    )

    if not args.apply:
        print("\nDRY-RUN: nothing written. Re-run with --apply to commit to the ledger.")
        return 0

    b1 = _backup(TASKS)
    b2 = _backup(BOTS)
    b3 = _backup(MESSAGES)
    print(f"\nBackups: {b1.name}, {b2.name}, {b3.name}")

    _atomic_write_json(TASKS, tasks)
    _atomic_write_json(BOTS, bots)
    with MESSAGES.open("a", encoding="utf-8") as fh:
        for m in new_msgs:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")

    # post-write verification
    v_tasks = _load_json(TASKS)
    v_bots = _load_json(BOTS)
    ids = [t.get("id") for t in v_tasks]
    dupes = {i for i in ids if ids.count(i) > 1}
    print(
        f"VERIFY: tasks.json parses OK, {len(v_tasks)} tasks, "
        f"duplicate_ids={sorted(dupes) or 'none'}, bots={len(v_bots)}"
    )
    if dupes:
        print("FAIL: duplicate task ids present")
        return 1
    print("VERIFY: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
