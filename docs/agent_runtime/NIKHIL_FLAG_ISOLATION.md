# Nikhil isolated runtime flag

## Why

Production canary for Nikhil stopped with:

```text
BLOCKED — NIKHIL DOES NOT HAVE AN ISOLATED FEATURE FLAG
```

`primary_flag` was empty, so `AGENT_RUNTIME=1` would make Nikhil eligible together with every other pilot whose peer flags were already `1` in prod (e.g. `OPS_WATCHDOG`, `FINOPS_AGENT`, `SOCIAL_ENGINE`).

## Flag

| | |
|---|---|
| Name | `DELIVERY_ASSURANCE_AGENT` |
| Default | OFF (`0` / unset) |
| Registry | `agent_registry` → nikhil `primary_flag` |
| Adapter | `nikhil_scan_delivery_assurance` → `_flag_skip("DELIVERY_ASSURANCE_AGENT")` |
| Automation registry | `app/api/automation_flags.py` |

Independent of any non-agent delivery product flags. Does not disable customer delivery sends.

## Lane decision (2026-07-22)

| Before | After | Why |
|---|---|---|
| AMBER + draft | **GREEN + live** | Engine `scan_missed_deliverables` is PURE READ (no send/publish/remediate). Capability `side_effect=none`, `contact_cap=0`. |

## Safe canary pattern (future auth only)

```text
# force peer pilot flags OFF (census-driven), then:
AGENT_RUNTIME=1
DELIVERY_ASSURANCE_AGENT=1
```

Preflight must return:

```yaml
eligible_agents: [nikhil]
unexpected_agents: []
```

See `CANARY_PREFLIGHT.md` and `AGENT_FLAG_CENSUS.md`.
