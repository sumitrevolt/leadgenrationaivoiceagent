# Enterprise Readiness Scorecard — 31 agents + Agent-OS control plane (honest)
<!-- 2026-07-19 (ADR-126): title corrected 32->31. Code truth = 31 STAFF personas (manager=Boss is one of them). Agent-OS (registry+owner_os control plane) is the coordinating layer, NOT a 32nd persona. Canonical contract: app/platform/agent_registry.py. -->

_Date: 2026-07-19 · Source: `app/platform/team.py` STAFF (31 personas) + flag map + guard/test evidence · Verdict = code state, NOT aspiration_

## Legend
✅ = ready/yes · ⚠️ = partial/conditional · ❌ = no/missing

**6 dimensions (enterprise-agent criteria):**
1. **Run24/7** — periodic/continuous schedule + flag ON by default (on-demand/gated-off = ❌/⚠️)
2. **Autonomous** — genuine LLM reasoning (✅) vs deterministic scheduled job (⚠️) vs human/event-triggered only (❌)
3. **Guarded** — budget/rate/kill-switch/compliance guard present
4. **Observed** — dead-man heartbeat coverage (`automation_health` EXPECTED_GAP_MIN)
5. **Lane** — 🟢 GREEN (internal/draft, safe autonomous) · 🟡 AMBER (customer outreach, caps+review) · 🔴 RED (calling/bulk, HITL/mandate)
6. **Tested** — contract/unit test evidence

> **Key truth:** "Guarded" is ✅ almost everywhere because guardrails are GLOBAL (owner_os kill-plane, agent_budget, dead-man, compliance gates). The real differentiators are **Run24/7** (mostly gated OFF) and **Autonomous** (mostly deterministic jobs, not reasoning agents).

---

## PLATFORM team (13) — infra/ops/eng
| Agent | Role | Run24/7 | Autonomous | Guarded | Observed | Lane | Tested |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Boss (manager) | Supervisor/coordinator | ❌ gated `AGENT_STANDUP` | ✅ LLM | ✅ rate-cap | ⚠️ standup only | 🟢 | ✅ |
| Kavya | Ops Monitor | ✅ hourly | ⚠️ | ✅ | ✅ | 🟢 | ⚠️ |
| Hermes | Infra Handler | ⚠️ gated `INFRA_HANDLER` | ⚠️ | ✅ | ✅ | 🟢 | ⚠️ |
| Nikhil | Revenue Ops | ✅ daily | ⚠️ | ✅ | ✅ | 🟢/🟡 dunning | ⚠️ |
| Vikram | Code Upgrader | ❌ gated `CODE_UPGRADER` | ✅ LLM proposals | ✅ approval-gated | ✅ | 🟢 | ⚠️ |
| Guru | Skill Trainer | ⚠️ gated `SKILL_PACK` | ⚠️ | ✅ | ⚠️ | 🟢 | ⚠️ |
| Pranav | SRE/Reliability | ❌ gated `SRE_AGENT` | ⚠️ | ✅ | ✅ | 🟢 | ✅ |
| Vidya | FinOps/Cost | ❌ gated `FINOPS_AGENT` | ⚠️ | ✅ | ✅ | 🟢 | ✅ |
| Arnav | Security/Compliance | ❌ gated `SECURITY_AGENT` | ⚠️ | ✅ | ✅ | 🟢 | ✅ |
| Kabir | DB Reliability | ❌ gated `DBRE_AGENT` | ⚠️ | ✅ | ✅ | 🟢 | ✅ |
| Diya | Data Integrity | ❌ gated `DATA_INTEGRITY_AGENT` | ⚠️ | ✅ | ✅ | 🟢 report-only | ✅ |
| Aryan | Dependency/Supply-chain | ❌ gated `DEPS_AGENT` | ⚠️ | ✅ | ✅ | 🟢 proposal-only | ✅ |
| Arya | MCP Engineer | ❌ gated `MCP_ENGINEER` | ⚠️ | ✅ | ✅ | 🟢 | ⚠️ |

## MARKETING team (10) — growth/outreach
| Agent | Role | Run24/7 | Autonomous | Guarded | Observed | Lane | Tested |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Dev | Data Analyst (RAG seed) | ⚠️ per-client event | ⚠️ | ✅ | ⚠️ | 🟢 | ⚠️ |
| Rohan | Leads Manager | ❌ on-demand | ⚠️ | ✅ | ❌ | 🟡 | ⚠️ |
| Isha | Marketing Exec (content) | ❌ on-demand | ⚠️ LLM draft | ✅ | ⚠️ | 🟢 draft | ⚠️ |
| Ravi | SEO Scout | ✅ daily+Mon | ⚠️ | ✅ | ✅ | 🟢 | ⚠️ |
| Neha | Pipeline Ops | ✅ daily 11:00 | ⚠️ | ✅ | ✅ | 🟢 | ⚠️ |
| Kiran | Campaign Optimizer | ❌ gated `CAMPAIGN_OPTIMIZER` | ⚠️ | ✅ eval-gate | ✅ | 🟡 | ⚠️ |
| Priya | CRM Sync | ⚠️ gated `CRM_SYNC` | ⚠️ | ✅ | ⚠️ | 🟢 client-CRM | ⚠️ |
| Zara | Social Media Mgr | ⚠️ gated `SOCIAL_ENGINE` | ⚠️ | ✅ | ✅ social_drain | 🟢 own / 🟡 client | ⚠️ |
| Anika | Cadence Manager | ⚠️ gated `CADENCE_ENGINE` | ⚠️ | ✅ 25/day cap | ⚠️ | 🟡 | ⚠️ |
| Ira | Journey Automation | ⚠️ gated `JOURNEY_ENGINE` | ⚠️ | ✅ | ⚠️ | 🟡 | ⚠️ |

## VOICE team (8) — telephony
| Agent | Role | Run24/7 | Autonomous | Guarded | Observed | Lane | Tested |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Swara | Telecaller | ✅ on-demand; cold=`platform_dial` LIVE (supersedes HARD-OFF, 2026-08-02 — `PLATFORM_DIAL_LIMIT`=100 cap) | ✅ LLM convo | ✅ | ⚠️ call logs | 🔴 calling | ✅ agent_tester |
| Ananya | Appointment Booker | ❌ on-demand | ⚠️ | ✅ | ⚠️ | 🔴/🟡 outbound | ⚠️ |
| Riya | AI Receptionist | ⚠️ inbound event (always-ready) | ✅ LLM | ✅ | ⚠️ | 🟡 inbound | ⚠️ |
| Arjun | Voice QA | ✅ daily 2:30 | ⚠️ | ✅ | ✅ qa | 🟢 | ✅ |
| Meera | Voice Trainer | ✅ daily 3:00 | ⚠️ | ✅ | ✅ trainer | 🟢 | ⚠️ |
| Lekha | Call Analytics | ✅ daily | ⚠️ | ✅ | ✅ call_kpi | 🟢 | ⚠️ |
| Raksha | Human Escalation | ⚠️ on-demand live, gated `CALL_TRANSFER` | ⚠️ | ✅ | ❌ | 🟢 routes-to-human | ⚠️ |
| Tara | Voice Infra Ops | ✅ hourly | ⚠️ | ✅ | ✅ telephony_readiness | 🟢 | ⚠️ |

---

## Rollup — kaun sach me ready hai

**🟢 Running 24/7 NOW (built + guarded + observed + GREEN + flag-on): ~8**
Kavya, Nikhil, Ravi, Neha, Arjun, Meera, Lekha, Tara. → Ye abhi bhi chal rahe hain (jab scheduler up ho). Internal ops/growth/voice-infra. **Enterprise-grade + live.**

**⚙️ One-flag-away (built + guarded + GREEN, sirf gated OFF): ~10**
Hermes, Vikram, Guru, Pranav, Vidya, Arnav, Kabir, Diya, Aryan, Arya. → Ek `.env` flip = ON. Zero risk (internal/report/proposal-only). **Aaj enable kar sakta.**

**🟡 AMBER — customer outreach (caps + review + decision chahiye): ~7**
Rohan, Isha, Kiran, Priya, Zara, Anika, Ira. → Built, gated. Enable karo GREEN stable hone ke baad; email 25/day cap + bounce/complaint watch. Mostly draft/own-channel = manageable.

**🔴 RED — calling/HITL (mandate + human-in-loop): ~4**
Swara, Ananya, Riya, Raksha. → Cold outbound `platform_dial` LIVE since 2026-08-02 (supersedes this file's 2026-07-19 HARD-OFF; per-run cap `PLATFORM_DIAL_LIMIT`=100, TRAI window + DND fail-closed still enforced in `run_campaign_task`). Inbound (Riya/Raksha) safe. **"24/7 autonomous cold-calling" = ab LIVE par gated (caps + compliance spine), intentionally naive nahi.**

**Boss (coordinator)** = orchestrator; on-demand + `AGENT_STANDUP`-gated daily. Ye tera ekmatra genuine autonomous-reasoning agent hai.

---

## Do sabse important honest points

1. **"Autonomous" column mostly ⚠️ hai** — 31 me se sirf ~4 (Boss, Swara, Riya, Vikram) genuine LLM-reasoning karte hain. Baaki = **persona-naam wale deterministic scheduled jobs**. Ye enterprise OPS ke liye bilkul sahi hai, par "autonomous AI agent workforce" nahi. True autonomy chahiye to Phase 3 (coordinator ko har agent ka brain banao) build karna padega.

2. **Enterprise 24/7 SLA ka #1 blocker = single VPS (SPOF).** Guardrails/audit/kill-switch sab enterprise-grade hain, par ek server down = poora agent-OS down. True enterprise = 2nd server/HA (abhi EXTERNAL-blocked).

## Ready banane ka order (is scorecard se)
1. **Phase 0** (health alerts + scheduler-alive proof) → 🟢 wale 8 provably-live.
2. **⚙️ 10 one-flag-away** ON (Batch G1/G3 runbook) → 18 agents live, zero risk.
3. **🟡 7 AMBER** ek-ek, caps watch → 25 agents.
4. **🔴 4 RED** = HITL rakho (mandate).
5. **Phase 2 (real-time)** + **HA 2nd server** = true enterprise SLA.

**Aaj ka realistic max: ~18/31 agents 24/7 GREEN-autonomous** (8 live + 10 flag-away). Baaki customer-facing/calling ko governance chahiye — jo enterprise me hona bhi CHAHIYE (blind autonomy nahi).
