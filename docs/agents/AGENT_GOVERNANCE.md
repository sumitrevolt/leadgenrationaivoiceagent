# Agent Governance — LeadGen AI

> **Purpose:** Satisfy the Enterprise Playbook's `04_AGENT_GOVERNANCE.md` +
> `AGENT_READINESS_CHECKLIST.md` with the project's **real** agent roster — not
> generic C-suite templates. Source of truth for the roster = `app/platform/team.py`
> (`STAFF` dict, code-defined). Multi-agent layer = `app/agents/` + `app/platform/`.
>
> **Scope note:** The Playbook frames agents as a literal C-suite (CEO/CTO/COO…).
> This project does **not** ship those as standalone agents. Their *function*
> (cross-domain strategy, go/no-go, conflict resolution) is delivered by the
> **LLM Council** (`POST /api/agents/council`, `app/platform/llm_council.py`,
> Karpathy 3-stage) and the **Coordinator** hierarchical/debate modes
> (`app/agents/coordinator.py`). The mapping is documented in §4 — no agent is
> claimed that does not exist in code.

---

## 1. Fleet-wide governance (the 14 readiness fields)

Most readiness-checklist fields are satisfied **uniformly by shared infrastructure**,
not re-implemented per agent. This table is the fleet baseline; §3 lists per-agent
deltas (identity, trigger, flag, KPI, escalation).

| Checklist field | How it is satisfied (fleet-wide) | Code / evidence |
|---|---|---|
| **Role defined** | Every staff member has a fixed `title` + `duties` | `team.py` `STAFF[*]` |
| **Inputs defined** | KB context (Qdrant `kb_main`, per-niche/client namespaces), `agent_events`, lead/CRM state, job payloads | `voice_agent/free_ai.py`, `platform/skill_pack.py` |
| **Outputs defined** | Drafts / proposals / scores / events — **draft-only by default** (no unsolicited side effects) | `agent_events` table, per-engine return values |
| **Tools allowed** | Free-stack LLM chain, KB retrieval, `skill_pack.find/snippet_for`, that agent's own engine module | `free_ai.py`, `skill_pack.py` |
| **Forbidden actions** | See §2 (hard limits) | compliance gates, flag gating |
| **Memory scope** | `agent_memory` (per-agent, DPDP-purgeable) + KB namespaces (`niche:`/`client:<id>`/`skills`); customer memory separated from global; Guru runs Mem0 hygiene | `voice_agent/agent_memory.py`, Qdrant namespaces |
| **Prompt versioned** | Prompts are code-defined (git-versioned); voice scripts in `niche_scripts.py`; system prompts in `app_platform_agent_system_prompts.py` | git history |
| **Fallback model** | Multi-provider chain with circuit-breaker = automatic per-call fallback (Mistral→Groq→Cerebras→Gemini→SambaNova→NVIDIA→OpenRouter) | `free_ai.py` ~L420 |
| **Confidence threshold** | `eval_gate` median-baseline regression signal; low-confidence / ambiguous → escalate to Council | `platform/eval_gate.py`, `llm_council.py` |
| **Escalation path** | LLM Council (`/api/agents/council`) for ambiguity; **Sumit approval** for core-code apply + high-risk/destructive | `coordinator.py` hierarchical mode |
| **Health check** | Dead-man trio (heartbeat `data/job_heartbeats.json` + revive-beat */20min + watchdog) + `automation_health` overdue/failed detection + `team_pulse` live monitors (Kavya/Tara/Hermes) | `platform/automation_health.py`, `team_scheduler.py` |
| **Metrics** | `agent_events` (every action), `llm_metrics` per-provider, per-engineer-agent KPIs (§3) | `platform/llm_metrics.py` |
| **Evaluation tests** | `scripts/agent_tester.py` (voice scorecard), `eval_gate` close-the-loop reward, DeepEval CI, `tests/test_*` suites | `tests/test_eval_gate.py`, `test_judge_calibration.py` |
| **Rollback prompt/version** | Prompts code-defined → `git revert`; every loop **flag-gated, default OFF** = instant disable without deploy | `AUTOMATION_FLAGS` registry, `growth.py` |

**Runtime rules (Playbook §"Agent Runtime Rules"):** agent actions logged to
`agent_events` with timestamp + member id; outputs validated before any external
side effect; **agents do not auto-mutate production state** unless a flag + workflow
grants it (default draft-only); task history + (where applicable) confidence recorded.

---

## 2. Hard limits — forbidden actions (apply to ALL agents)

These are enforced by code/compliance gates, **never** by agent discretion:

1. **No unsolicited bulk auto-send** — WhatsApp bulk auto = number ban → 1-click human send only (`WHATSAPP_AUTO_SEND` OFF + approved-template gate).
2. **No cold AI calls without DLT** — TRAI gate. Calling-window 9am–7pm, AI-disclosure at greeting, DND **fail-closed** (`dnd_lookup_failed` = block).
3. **No core-code auto-apply** — Vikram (Code Upgrader) emits *proposals* only; core code applies on Sumit approval (safe skills may auto-apply).
4. **No opt-out contact** — consent-ledger suppression is cross-channel + instant + 90-day retention.
5. **No PII / secret leakage** — secrets only in `.env` (gitignored), `check_secrets.py` CI gate; DPDP purge available.
6. **Draft-by-default** — outreach/cadence/lifecycle/winback engines produce drafts; auto-send is per-engine flag-gated and ban-risk-reviewed.
7. **Never crash the host** — every loop is `try/except` (never-raise) + bounded awaits + deadline; failure degrades gracefully, does not take down the web process.

---

## 3. The roster (per-agent spec, grounded in `team.py`)

23 code-defined staff, split by `product`. Trigger = schedule; Flag = enable switch
(OFF = inert). All inherit §1 fleet governance + §2 limits.

### Platform (shared infra & ops)
| Agent | Title | Trigger | Flag / gate | KPI / signal |
|---|---|---|---|---|
| Boss (manager) | Supervisor | on-demand (`/api/agents/run`) | — | routing success |
| Kavya | Ops Monitor | hourly + on-demand | always-on | health score, provider/DB/disk |
| Hermes | Infrastructure Handler | hourly watchdog + pulse | `INFRA_HANDLER` | infra readiness 0-100 |
| Tara | Voice Infra Ops | hourly | always-on | telephony readiness (Vobiz/DND/TTS/STT) |
| Nikhil | Revenue Ops | daily | — | dunning recovery, MRR, churn-risk |
| Vikram | Code Upgrader | hourly watchdog | `CODE_UPGRADER` | proposal quality (approve-gated) |
| Guru | Skill Trainer / Memory steward | daily | `SKILL_PACK` | skill coverage, Mem0/agent_memory drift |
| Pranav | SRE / Reliability | hourly + daily DR summary | `SRE_AGENT` | `backup_pass_rate`, `mttr_seconds`, `capacity_headroom_pct` |
| Vidya | FinOps / Cost | daily margin digest | `FINOPS_AGENT` | `gross_margin_per_tenant` |
| Arnav | Security / Compliance | daily + on-demand | `SECURITY_AGENT` | `compliance_posture_score` |
| Kabir | DB Reliability Engineer | daily 10:00 IST | `DBRE_AGENT` | `db_reliability_score` (read-only pg-catalog) |
| Diya | Data-Integrity Engineer | daily 10:30 IST | `DATA_INTEGRITY_AGENT` | `data_integrity_score` (report-only) |
| Aryan | Dependency / Supply-chain | weekly Sun 04:30 IST | `DEPS_AGENT` | `supply_chain_score` (pip-audit, never auto-upgrade) |

### Marketing (Product 1)
| Agent | Title | Trigger | Flag / gate | KPI / signal |
|---|---|---|---|---|
| Dev | Data Analyst | per new client (auto) | `AUTO_ONBOARD` | KB seed coverage |
| Rohan | Leads Manager | on-demand + daily 10:30 outreach | `AUTO_EMAIL_OUTREACH` | sends (cap 25/day, MX-verified) |
| Isha | Marketing Executive | on-demand | — | content packs (social/GBP) |
| Ravi | SEO Scout | daily + Monday batch | — | programmatic SEO pages, IndexNow ping |
| Neha | Pipeline Ops | daily 11:00 IST | — | lead rescore, hot-lead surface |
| Kiran | Campaign Optimizer | weekly + threshold | `CAMPAIGN_OPTIMIZER` | A/B win-rate (eval_gate-promoted) |

### Voice (Product 2 — code-ready, commercially DLT/Vobiz-blocked)
| Agent | Title | Trigger | Flag / gate | KPI / signal |
|---|---|---|---|---|
| Swara | Telecaller | on-demand (calls/demos) | telephony provider | qualify rate, objection handling |
| Ananya | Appointment Booker | on-demand | — | slots booked |
| Riya | AI Receptionist | on-demand (inbound) | — | route/message accuracy |
| Arjun | QA Engineer | daily 02:30 + on-demand | always-on | scorecard (double/repeat/slow/long) |
| Meera | Trainer | daily 03:00 + on-demand | always-on | STT-failure/latency analysis |

---

## 4. Playbook C-suite → project mapping (honest)

The Playbook ships CEO/CTO/COO/CIO/CMO/CRO/CFO/Security/QA/Reliability/Voice/CRM
agent specs. This project delivers their **function** without standalone C-suite agents:

| Playbook agent | Project equivalent | Where |
|---|---|---|
| CEO / strategy / go-no-go / conflict resolution | **LLM Council** (3-stage: opinions → peer-review → Chairman verdict) | `llm_council.py`, `POST /api/agents/council`, UI `/app/agents` |
| CTO / Architecture / Performance | Coordinator hierarchical/debate + `engineer_agents` (Pranav/Kabir/Aryan) | `coordinator.py`, `platform/engineer_agents.py` |
| Security | **Arnav** + `security-review` skill + `check_secrets.py` | `team.py`, CI gates |
| Reliability / DevOps / Infra | **Pranav + Hermes + Kavya** + dead-man trio + self-heal | `automation_health.py`, `vps_selfheal.sh` |
| QA | **Arjun** + `eval_gate` + DeepEval CI | `agent_tester.py` |
| Billing / CFO | **Nikhil + Vidya** + billing-truth test | `revenue_digest.py`, `test_billing_truth_2026.py` |
| Marketing / CMO | **Isha + Rohan + Ravi + Kiran** | `team.py` |
| CRM | `crm_sync` (Zoho/HubSpot) + **Neha** pipeline ops | `platform/crm_sync.py` |
| Voice | **Swara/Tara/Arjun/Meera** + `telecaller_brain` | `voice_agent/` |
| Domain expert / debate | Coordinator `debate`/`critic`/`Reflexion` modes | `coordinator.py` |

**Decision recording (ADR):** Council/coordinator decisions are logged to
`agent_events`, mirrored to the Obsidian "Decisions/" vault (`OBSIDIAN_SYNC`), and
strategic ones recorded as `docs/ADR_*.md`. This is the project's ADR path.

---

## 5. Readiness verdict

- **Fleet governance:** ✅ all 14 checklist fields satisfied via shared infra (§1).
- **Per-agent identity/trigger/flag/escalation:** ✅ code-defined (§3).
- **Hard limits / forbidden actions:** ✅ compliance-gated, not discretionary (§2).
- **C-suite parity:** ✅ delivered as Council + Coordinator + named staff (§4) — documented, not faked.
- **Open delta vs Playbook letter:** the project intentionally uses **one governance
  doc + a code-defined roster** instead of N standalone C-suite agent files. This is
  a deliberate shape choice (fewer moving parts on a single-VPS free-stack), not a
  capability gap.
