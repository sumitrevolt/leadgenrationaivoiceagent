# 31-Agent Runtime & Orchestration Truth Audit Report

**Date:** 2026-08-31  
**Status:** Completed (Empirically Verified & Non-Destructive)

---

## 1. 31/31 Agent Registry Inventory & Status Matrix

| ID | Name | Team | Lane | Mode | Concurrency | Status | Hermes Bot | Primary Execution Path |
|---|---|---|---|---|---|---|---|---|
| **manager** | Boss | platform | GREEN | live | 1 | `READY_IDLE` | board / pilot | Boss Coordinator / Agent-OS Engine |
| **swara** | Swara | voice | RED | hard_off | 1 | `DISABLED_RED` | sales (Red Voice) | Celery Beat -> leadgen_worker / worker-heavy |
| **ananya** | Ananya | voice | RED | hard_off | 1 | `DISABLED_RED` | sales (Red Voice) | FastAPI Event / Lifespan Hook |
| **riya** | Riya | voice | AMBER | inbound_ready | 4 | `ACTIVE` | operations (Inbound Voice) | FastAPI Event / Lifespan Hook |
| **dev** | Dev | marketing | GREEN | live | 1 | `READY_IDLE` | operations | FastAPI Event / Lifespan Hook |
| **rohan** | Rohan | marketing | AMBER | draft | 2 | `STAGED_SHADOW` | sales / hunter | Celery Beat -> leadgen_worker / worker-heavy |
| **arjun** | Arjun | voice | GREEN | live | 1 | `READY_IDLE` | operations | Celery Beat -> leadgen_worker / worker-heavy |
| **meera** | Meera | voice | GREEN | live | 1 | `READY_IDLE` | engineering | Celery Beat -> leadgen_worker / worker-heavy |
| **lekha** | Lekha | voice | GREEN | live | 1 | `ACTIVE` | board | Celery Beat -> leadgen_worker / worker-heavy |
| **raksha** | Raksha | voice | AMBER | inbound_ready | 4 | `ACTIVE` | operations | FastAPI Event / Lifespan Hook |
| **kavya** | Kavya | platform | GREEN | live | 1 | `READY_IDLE` | guardian | Celery Beat -> leadgen_worker / worker-heavy |
| **hermes** | Hermes | platform | GREEN | proposal | 1 | `STAGED_SHADOW` | platform | Embedded Specialist Sub-engine |
| **isha** | Isha | marketing | GREEN | draft | 2 | `STAGED_SHADOW` | operations | Celery Beat -> leadgen_worker / worker-heavy |
| **tara** | Tara | voice | GREEN | live | 1 | `READY_IDLE` | platform | Embedded Specialist Sub-engine |
| **nikhil** | Nikhil | platform | GREEN | live | 1 | `READY_IDLE` | operations / success | Celery Beat -> leadgen_worker / worker-heavy |
| **vikram** | Vikram | platform | GREEN | proposal | 1 | `STAGED_SHADOW` | engineering | Embedded Specialist Sub-engine |
| **guru** | Guru | platform | GREEN | live | 1 | `READY_IDLE` | engineering | Embedded Specialist Sub-engine |
| **pranav** | Pranav | platform | GREEN | live | 1 | `READY_IDLE` | platform / engineering | Celery Beat -> leadgen_worker / worker-heavy |
| **vidya** | Vidya | platform | GREEN | live | 1 | `READY_IDLE` | guardian | Celery Beat -> leadgen_worker / worker-heavy |
| **arnav** | Arnav | platform | GREEN | proposal | 1 | `STAGED_SHADOW` | guardian | Celery Beat -> leadgen_worker / worker-heavy |
| **kabir** | Kabir | platform | GREEN | live | 1 | `READY_IDLE` | platform | Celery Beat -> leadgen_worker / worker-heavy |
| **diya** | Diya | platform | GREEN | live | 1 | `READY_IDLE` | guardian | Celery Beat -> leadgen_worker / worker-heavy |
| **aryan** | Aryan | platform | GREEN | proposal | 1 | `STAGED_SHADOW` | engineering | Celery Beat -> leadgen_worker / worker-heavy |
| **arya** | Arya | platform | GREEN | live | 1 | `READY_IDLE` | platform | Celery Beat -> leadgen_worker / worker-heavy |
| **ravi** | Ravi | marketing | GREEN | live | 1 | `READY_IDLE` | operations | Embedded Specialist Sub-engine |
| **neha** | Neha | marketing | GREEN | live | 1 | `ACTIVE` | sales | Celery Beat -> leadgen_worker / worker-heavy |
| **kiran** | Kiran | marketing | AMBER | proposal | 1 | `STAGED_SHADOW` | sales | Embedded Specialist Sub-engine |
| **priya** | Priya | marketing | AMBER | shadow | 2 | `STAGED_SHADOW` | operations | FastAPI Event / Lifespan Hook |
| **zara** | Zara | marketing | AMBER | shadow | 1 | `STAGED_SHADOW` | operations | Celery Queue (DLQ / Cadence) |
| **anika** | Anika | marketing | AMBER | draft | 2 | `STAGED_SHADOW` | sales / hunter | Celery Beat -> leadgen_worker / worker-heavy |
| **ira** | Ira | marketing | AMBER | draft | 2 | `STAGED_SHADOW` | sales | FastAPI Event / Lifespan Hook |

---

## 2. Hermes 9-Bot ↔ 31 Agent Supervisory Alignment

| Hermes Bot Profile | Supervisory Role | Assigned Project Agents | Ownership Policy |
|---|---|---|---|
| **`board`** | Executive Oversight & Strategy | `manager` (Boss), `lekha` | Strategic goals, KPI digests |
| **`pilot`** | Operational Coordination | `manager` (Boss) | Task dispatch & mission routing |
| **`guardian`** | Security, Audit & Governance | `kavya`, `arnav`, `vidya`, `diya` | Security posture, compliance, cost tracking |
| **`engineering`**| Code & Infrastructure Build | `vikram`, `guru`, `aryan`, `meera` | Skill packs, dependency audits, quality |
| **`platform`** | SRE & Database Reliability | `hermes`, `pranav`, `kabir`, `arya`, `tara` | Health checks, DBRE, MCP management |
| **`sales`** | Outbound & Growth Pipeline | `neha`, `kiran`, `anika`, `ira`, `swara`*, `ananya`* | Lead scoring, campaign optimization, outbound |
| **`hunter`** | Prospecting & Cold Outreach | `rohan`, `anika` | Email outreach, prospecting lookup |
| **`operations`**| Fulfillment & Customer Delivery | `dev`, `isha`, `ravi`, `priya`, `zara`, `arjun`, `riya`, `raksha` | Content generation, CRM sync, inbound call |
| **`success`** | Customer Retention & Quality | `nikhil` | Delivery assurance, dunning checks |

*\*Note: Outbound voice agents (`swara`, `ananya`) remain strictly gated by `HARD_OFF` and `RED` lane policy.*

---

## 3. Background Process & Router Topology

```
+-----------------------------------------------------------------------------------+
|                                 USER DESKTOP                                      |
|                                                                                   |
|  +--------------------------+   +----------------------+   +-------------------+  |
|  |   Claude Desktop App     |   |  Hermes Desktop App  |   |   WorkBuddy AI    |  |
|  +------------+-------------+   +----------+-----------+   +---------+---------+  |
|               |                            |                         |            |
+---------------+----------------------------+-------------------------+------------+
                |                            |                         |
                v                            v                         v
+-------------------------------+ +---------------------+ +-------------------------+
| Claude Proxy (:22000)         | | Hermes Local Daemon | | DSH Web UI (:3080)      |
| (Header & Format Translation) | | (127.0.0.1:18789)   | | (Local Dev Web Server)|
+---------------+---------------+ +----------+----------+ +------------+------------+
                |                            |                         |
                +--------------------+-------+-------------------------+
                                     |
                                     v
                 +---------------------------------------+
                 | OmniRoute LLM Gateway (WSL :20128)    |
                 | (Model combos & provider failover)    |
                 +-------------------+-------------------+
                                     |
                                     v
                 +---------------------------------------+
                 | Free Upstream LLM Providers            |
                 | (Groq / Mistral / Gemini / Cerebras)  |
                 +---------------------------------------+
```

---

## 4. Single Global Resource & Concurrency Budget

To prevent machine resource exhaustion (RAM/CPU/Pagefile pressure):

1. **Max Concurrency Ceiling:**
   - **Local Dev Total Concurrent LLM Slots:** `4`
   - **Celery Worker Concurrency:** `leadgen_worker` = 4, `worker-heavy` = 1.
2. **Memory Ceiling per Worker:**
   - Celery worker memory limit: `2.0 GB`
   - Heavy worker memory limit: `2.44 GB`
3. **Execution Rule:** One task -> One agent owner -> One execution path. No parallel duplicate dispatch across multiple frameworks.

---

## 5. Verification Evidence

- `tests/test_agent_registry.py`: **PASS** (31/31 agent contracts validated)
- `scripts/audit_31_agent_runtime.py`: **PASS** (Zero broken contracts, zero duplicate dispatches)
- **Port Health:**
  - `:20128` (OmniRoute WSL): `ONLINE`
  - `:22000` (Claude Proxy): `ONLINE`
  - `:3080` (DSH Web): `ONLINE`
- **RAM Headroom:** `3.03 GB` physical free RAM available.
