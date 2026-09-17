# Telegram Enterprise Setup - Complete Documentation
# ==================================================
# This document outlines the full end-to-end setup for LeadGen AI's Telegram enterprise presence.

## Overview
- **Platform**: LeadGen AI (2 products: Marketing + Voice Calling Agent)
- **Bot**: @Leadsgenai1_bot (ID: 8889560331)
- **Total Groups**: 13 (10 existing + 3 new)
- **Webhook**: https://leadsgenai.in/api/webhooks/telegram
- **Secret**: TELEGRAM_WEBHOOK_SECRET configured

## Groups Structure

### Product 1: AI Automated Marketing (4 groups)
1. **LeadGen AI Marketing - Announcements** (Channel, Public)
   - chat_id: -1004485447096
   - Bot admin: ✅
   - Purpose: One-way updates, releases, pricing, compliance

2. **LeadGen AI Marketing - Community** (Supergroup, Public)
   - chat_id: -1004475752582
   - Bot admin: ✅
   - Topics: intros, use-cases, wins, how-to, updates-mirror

3. **LeadGen AI Marketing - Support** (Supergroup, Private)
   - chat_id: -1004464035633
   - Bot admin: ✅
   - Invite: https://t.me/+RFUpYWGZvT5lODQ1
   - Topics: open-tickets, billing-UPI, bugs, incidents

4. **LeadGen AI Marketing - Feedback** (Supergroup, Private)
   - chat_id: -1003932745917
   - Bot admin: ✅
   - Invite: https://t.me/+Qes7Yj-g3G43Njll
   - Topics: requests-P0-P1-P2, beta, polls

### Product 2: AI Voice Calling Agent (4 groups)
5. **LeadGen AI Voice Agent - Announcements** (Channel, Public)
   - chat_id: -1003935454293
   - Bot admin: ✅
   - Purpose: Voice releases, DLT updates, compliance

6. **LeadGen AI Voice Agent - Community** (Supergroup, Public)
   - chat_id: -1004421485309
   - Bot admin: ✅
   - Topics: intros, scripts, niche-bands, how-to, updates-mirror

7. **LeadGen AI Voice Agent - Support** (Supergroup, Private)
   - chat_id: -1003906410254
   - Bot admin: ✅
   - Invite: https://t.me/+ZQVr02PewhcyNGM1
   - Topics: open-tickets, billing-UPI, DLT-templates, bugs, incidents

8. **LeadGen AI Voice Agent - Feedback** (Supergroup, Private)
   - chat_id: -1004376116363
   - Bot admin: ✅
   - Invite: https://t.me/+0TR9sLVyt_IxNjY1
   - Topics: requests-P0-P1-P2, beta-voices, polls

### Cross-Product (5 groups)
9. **LeadGen AI - Internal Ops** (Supergroup, Private)
   - chat_id: -1004460536807
   - Bot admin: ✅
   - Invite: https://t.me/+FTKorPoHfDswOTE1
   - Topics: incidents, deploys, bot-status, decisions

10. **LeadGen AI - Owner Alerts** (Supergroup, Private)
    - chat_id: -1003878635977
    - Bot admin: ✅
    - Invite: https://t.me/+FbbUvbVEQ_8zZWI1
    - Topics: payments, health, incidents

11. **LeadGen AI - Worker Coordination** (Supergroup, Private) ⚠️ NEEDS CREATION
    - chat_id: (pending)
    - Purpose: Cross-worker coordination for 9 worker CLI agents
    - Topics: worker-status, task-handoffs, urgent

12. **LeadGen AI - Agents Coordination** (Supergroup, Private) ⚠️ NEEDS CREATION
    - chat_id: (pending)
    - Purpose: 31-agent coordination, Boss verdict, hierarchical runs
    - Topics: agent-status, assignments, verdicts, skill-share

13. **LeadGen AI - Admin Command Center** (Supergroup, Private) ⚠️ NEEDS CREATION
    - chat_id: (pending)
    - Purpose: Owner/admin operational commands, kill-switch, revenue truth
    - Topics: deploys, revenue, kill-switch, metrics, system-health

## Admin Roles
- **founder**: Full access to all chats
- **pm**: announcements, feedback, internal_admin, workers_coordination, agents_coordination, admin_command_center
- **community_manager**: community, feedback
- **support_lead**: support
- **support_agent**: support
- **devops**: internal_admin, owner_alerts, admin_command_center
- **bot_broadcast**: announcements, workers_coordination, agents_coordination, admin_command_center

## Compliance Gates (NEVER weaken)
- **DPDP Act 2023**: Lawful purpose, consent, data minimization, erasure on leave
- **TRAI TCCCPR**: No UCC; opt-in; honor DND + 09:00-21:00 for any outbound
- **AI Disclosure**: Every automated reply labels itself as a bot
- **Payment Truth**: Manual UPI only; never claim 'auto-paid'
- **No Cold Outreach**: No cold Telegram/WhatsApp adds
- **Tenant Isolation**: No cross-customer PII leakage

## Webhook Configuration
- **Endpoint**: POST /api/webhooks/telegram
- **Secret**: TELEGRAM_WEBHOOK_SECRET=59edea328eb17786d2b995badd1872a466bbe24b891dfa55
- **Status**: ✅ LIVE and verified
- **Inbox**: data/telegram_inbox.jsonl

## Pending Actions
1. Create 3 new groups in Telegram Desktop (Worker Coordination, Agents Coordination, Admin Command Center)
2. Add @Leadsgenai1_bot as admin to each new group
3. Get chat_ids for new groups
4. Update config/telegram/setup_spec.yaml with chat_ids
5. Run TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply

## SpamBot Restriction
- Owner's personal Telegram account is limited
- Appeal already submitted (2026-09-14 08:03)
- Bot account is NOT restricted
- This is a Telegram review process, not a platform issue
