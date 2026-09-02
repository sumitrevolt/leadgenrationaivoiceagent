# Agent flag census (31 STAFF)

Source of truth at runtime: `app.platform.agent_canary_preflight.agent_flag_census()`.

## Invariant

Every **dispatchable** agent (`PILOT_AGENTS`) must have a non-empty `primary_flag`.
`validate_registry()` fails otherwise. `evaluate_policy` fail-closes with `agent_flag_missing`.

## How to print

```python
from app.platform.agent_canary_preflight import agent_flag_census
print(agent_flag_census(assume_runtime_on=True))
```

Each row includes `label` like `Nikhil (Revenue Ops)` — name + title in brackets.

## Dispatchable pilots (canary_ready) — must be gated

| Agent | Primary flag |
|---|---|
| Kavya (Ops Watchdog) | `OPS_WATCHDOG` |
| Isha (Marketing Executive) | `AFTERNOON_CONTENT` |
| Zara (Social Publisher) | `SOCIAL_ENGINE` |
| Hermes (Infra Handler) | `INFRA_HANDLER` |
| Pranav (SRE / Reliability) | `SRE_AGENT` |
| Vidya (FinOps / Cost) | `FINOPS_AGENT` |
| Arnav (Security / Compliance) | `SECURITY_AGENT` |
| Kabir (DB Reliability Engineer) | `DBRE_AGENT` |
| Diya (Data-Integrity Engineer) | `DATA_INTEGRITY_AGENT` |
| Aryan (Deps / Supply-chain) | `DEPS_AGENT` |
| Arya (MCP Engineer) | `MCP_ENGINEER` |
| Nikhil (Revenue Ops) | `DELIVERY_ASSURANCE_AGENT` |

## Intentionally disabled

| Agent | Notes |
|---|---|
| Swara (Voice AI) | RED / hard_off — not in pilots |
| Ananya (Booking Voice) | RED / hard_off — not in pilots |

## Rollout hold

Remaining STAFF (Boss=`manager` once) stay capability-registered but out of `PILOT_AGENTS`. Empty flags on hold personas are inventory-only (not runtime-dispatchable).

## Production note (2026-07-22 probe)

Several peer pilot flags were already `=1` in prod `.env` while `AGENT_RUNTIME=0`.
Arming runtime without forcing peers OFF is a multi-agent canary violation — use preflight.
