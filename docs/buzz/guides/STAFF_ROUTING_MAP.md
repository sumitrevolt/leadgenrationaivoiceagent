---
title: "31-Agent Routing Map — canonical"
tags: [buzz, staff, routing, boss, 31]
status: active
created: 2026-08-05
---

# 31-Agent Routing Map

Source of truth = `app/platform/team.py` (`STAFF` dict). **Code wins.** Verified
against code 2026-08-05: 31/31 names match, division split confirmed by the
`product` field.

No duplicate bots exist on Buzz for these agents. Buzz mirrors them in
`#staff-pulse` and commands them only through Boss.

## Division counts

| Division | Count | Buzz home channel |
|----------|-------|-------------------|
| Coordination | 1 | `#admin` |
| Platform | 12 | `#ops` |
| Marketing | 10 | `#gtm` |
| Voice | 8 | `#ops` (voice infra) / `#gtm` (call outcomes) |
| **Total** | **31** | |

## Coordination (1)

| Agent | Title | Owns |
|-------|-------|------|
| Boss 🧑‍💼 | Manager (Supervisor) | Priority, routing, conflict resolution, retry/reassign/defer/rollback |

## Platform (12) — `#ops`

| Agent | Title | Owns |
|-------|-------|------|
| Kavya 🛡️ | Ops Monitor | Service/provider/DB/disk liveness, telephony balance |
| Hermes 🛰️ | Infrastructure Handler | Infra scan 0-100, dead-man jobs, queue backlog, backup freshness |
| Nikhil 💰 | Revenue Ops | Dunning recovery, nurture funnel, churn risk, MRR digest |
| Vikram 🛠️ | Code Upgrader | Upgrade proposals from observability signals; core code owner-gated |
| Guru 📚 | Skill Trainer | Skill/KB curation, Mem0 hygiene, agent_memory drift |
| Pranav 🔧 | SRE / Reliability | DR drills, backup-restore integrity, capacity headroom, SLO |
| Vidya 💹 | FinOps / Cost | Per-tenant unit economics, margin-negative niche flags |
| Arnav 🛡️ | Security / Compliance | DPDP + TRAI posture, secret rotation, CVE triage, DSAR |
| Kabir 🗄️ | DB Reliability | Slow queries, index bloat, pool pressure, DB size trend |
| Diya 🧹 | Data Integrity | Duplicate phone/email, missing contacts, prospect-store integrity |
| Aryan 📦 | Dependency / Supply-chain | pip-audit CVEs, lockfile hygiene, upgrade proposals only |
| Arya 🔌 | MCP Engineer | 3-layer MCP surface, gate audit, key quota, rotation watch |

## Marketing (10) — `#gtm`

| Agent | Title | Owns |
|-------|-------|------|
| Isha 📣 | Marketing Executive | Client social posts, GBP tips, festival/offer content |
| Dev 📚 | Data Analyst | Client profile + niche KB seeding, RAG grounding |
| Rohan 🎯 | Leads Manager | Outreach plans, qualification criteria, campaign targeting |
| Ravi 🌐 | SEO Scout | Programmatic SEO pages, IndexNow ping, rank sweep |
| Neha ♻️ | Pipeline Ops | Lead rescore, hot-lead surfacing, journey rule seeding |
| Kiran 📊 | Campaign Optimizer | Per-100-interaction analysis, A/B proposals behind eval_gate |
| Priya 🔗 | CRM Sync Specialist | Qualified-lead push to client Zoho/HubSpot |
| Zara 📱 | Social Media Manager | Approved-content queue drain to client channels |
| Anika 🔁 | Cadence Manager | Per-day omnichannel sequence progression |
| Ira 🧩 | Journey Automation | Event-trigger rules to journey actions/drafts |

## Voice (8)

| Agent | Title | Owns |
|-------|-------|------|
| Swara 📞 | Telecaller | Outbound + web demo calls, niche scripts, objections — **FROZEN path** |
| Tara 🎙️ | Voice Infra Ops | Vobiz auth, caller-ID, webhooks, DND, TTS/STT/LLM chain |
| Arjun 🧪 | QA Engineer | Scripted conversation tests, repeat/slow/long bug capture |
| Meera 🎓 | Trainer | Transcript quality analysis, tuning suggestions |
| Ananya 📅 | Appointment Booker | Slot booking, calendar, reminders |
| Riya 🛎️ | AI Receptionist | Inbound greet, route, message, book — no sales pitch |
| Lekha 📊 | Call Analytics Lead | Duration, qualified/booking rate, p50/p95 latency, dead-air |
| Raksha 🆘 | Human Escalation | Route to human on confusion/anger, context handover, handback |

## Routing rules

1. Owner or Boss posts the mission in the channel that **owns the outcome**, not
   the channel that happens to be open.
2. Boss picks the division, then the agent, then posts the assignment.
3. Cross-division work gets one owning agent plus named consultees — never two owners.
4. Conflicts resolve at Boss. Ties break toward the compliance-safer option.
5. Voice work touching Swara's path: propose only. That surface is FROZEN.
6. Pulse lines land in `#staff-pulse` as
   `[PULSE] <division> | <agent> | <last_run> | <ok|warn|fail> | <note>`.

## Never

- Add a 32nd persona to `team.py` from Buzz.
- Create a Buzz duplicate bot for any of the 31.
- Route a command to a STAFF agent without passing through Boss.
