# OpenClaw + 31-Agent Runtime — implementation-directed research

Date: 2026-07-21
Scope: bounded decisions for LeadGen Agent Runtime workforce factory (Wave-B).

## 1. Shared runtime kernel vs 31 microservices

| Field | Content |
|---|---|
| Problem | Avoid 31 chatbots / 31 containers while making agents real |
| Source | Existing ADR-128 (`agent_runtime.py`), Google SRE durable execution notes, Celery lease patterns already in-repo |
| Finding | One policy-enforced runtime + per-agent capability adapters is enough |
| Applicability | LeadGen already has Postgres/Redis/Celery/Owner OS |
| Decision | Extend `PILOT_AGENTS` + `agent_runtime_workforce.py`; no Temporal/Kafka |
| Rejected | Per-agent Docker services; second dispatcher; second admin UI |
| Consequence | Rollout stays code-allowlist gated; RED voice never env-flipped |

## 2. Human-in-the-loop approvals

| Field | Content |
|---|---|
| Problem | AMBER customer mutations must not silent-execute |
| Source | Existing `content_approval` + OpenClaw AMBER park → Owner OS |
| Finding | Approval-before-mutate is already proven for Zara |
| Decision | Keep AMBER hold agents capability-ready but out of PILOT until owner expands |
| Rejected | Auto-approve via OpenClaw confirm flag in Stage A |
| Consequence | OpenClaw mutations stay Owner OS authority |

## 3. Swara transfer without voice mutation

| Field | Content |
|---|---|
| Problem | Expose Swara to OpenClaw without touching voice stack |
| Source | User mandate + `docs/context/AGENT_OWNERSHIP.md` FROZEN |
| Finding | RED lane + `frozen_transfer_status` + OpenClaw `agent.status` transfer package |
| Decision | Zero edits under `app/voice_agent/` / telephony for Swara |
| Rejected | Re-implement Swara as runtime LLM agent; register dial capability |
| Consequence | Calling remains HARD OFF; Copilot observes only |

## 4. Idempotency / leases / DLQ

| Field | Content |
|---|---|
| Problem | Duplicate Owner OS runs must not double-mutate |
| Source | Existing `agent_runtime` + billing idempotency store |
| Finding | Already implemented — reuse |
| Decision | No new lease system |
| Rejected | New Redis key namespace redesign |
| Consequence | Wave-B inherits same gates |

## 5. Staged activation

| Field | Content |
|---|---|
| Problem | 31 simultaneous live = blast radius |
| Source | Production canary practice ADR-128 |
| Decision | Wave-A (3) + Wave-B GREEN/read-only; AMBER customer-touch hold |
| Rejected | `PILOT_AGENTS = all STAFF` |
| Consequence | Honest matrix states: canary_ready / hold / frozen |
