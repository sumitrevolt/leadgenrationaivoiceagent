# AGENT_OWNERSHIP — non-voice agents

Canonical count: **31** (`app/platform/team.py` STAFF + `agent_registry`).
Do not assign two owners to the same state transition.

## Swara (voice)
```text
Status: FROZEN
Scope: OUT OF CURRENT UPGRADE
Modification permission: NONE
```
Related: all voice personas that only exist to support calling remain read-only this wave. `platform_dial` HARD OFF.

---

## Control plane (not a 32nd STAFF agent)
- **Agent ID:** agent_os / Owner OS / Boss coordinator (`manager`)
- **Mission:** policy, kill board, dispatch gates
- **Owned workflow:** runtime evaluate_policy + kills
- **Trigger:** admin / scheduled (Phase-C pending for full converge)
- **Kill switch:** `owner_all_agents`, `owner_schedulers`, unset `AGENT_RUNTIME`
- **Current status:** PRODUCTION-PROVEN canary for runtime flag; scheduler converge PARTIAL

## Pilots (AGENT_RUNTIME)
| Agent ID | Mission | Workflow | Trigger | Autonomy | Kill | Status |
|---|---|---|---|---|---|---|
| kavya | Ops health | read-only automation_health rollup | on-demand runtime | L0 | owner + schedulers | PRODUCTION-PROVEN canary succeeded |
| isha | Draft/propose | draft brief (LLM optional `AGENT_RUNTIME_LLM`) | on-demand | L1 | owner | CODE-PRESENT, not canary-proven |
| zara | Approval-gated publish handoff | social_engine enqueue after approval | on-demand | AMBER | owner + publishing | CODE-PRESENT, needs approved content |

## Delivery / revenue (non-voice)
| Agent ID | Mission | Owned workflow | Trigger | Outputs | Kill | Status |
|---|---|---|---|---|---|---|
| nikhil | Revenue ops / delivery assurance scan | missed/at-risk paid customers (read-only) | on-demand admin + embedded log_event | assurance report | owner_all / payment_mutation | CODE-PRESENT; admin wire WS-1 |
| (product_one_health job) | Health/approval/SLA sweep | recovery side-effects | hourly :20 | reminders / recovery | schedulers | PRODUCTION-PROVEN job exists |

## Content / growth (summary — full contracts in agent_registry)
GREEN draft/report personas (content, blog, SEO, prospect, SRE, security, etc.) own their JOB_META cadences.
AMBER customer-touch (email outreach, social drain) stay capped + HITL where required.
RED cold-call path = Swara/platform_dial = FROZEN.

## Overlap rules
- **Assurance detection** = nikhil / `delivery_assurance` (read-only)
- **Assurance recovery sends** = existing `AUTO_DELIVER_VALUE` / `deliver_client_value` only — do not duplicate in assurance
- **Publish** = Zara + social_engine after approval — not Isha
- **Blog alias drift** (`ALIAS_TO_MEMBER['blog']=ravi` vs JOB_META isha) = KNOWN_DRIFT in registry — do not “fix” casually without workstream

## Tests
- Registry: `tests/test_agent_registry.py`
- Runtime: `tests/test_agent_runtime.py`
- Delivery assurance: `tests/test_delivery_assurance.py`
