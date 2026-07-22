# Canary preflight (single-agent isolation)

## API

```python
from app.platform.agent_canary_preflight import canary_isolation_preflight

out = canary_isolation_preflight("nikhil", assume_runtime_on=True)
# out["allowed"] must be True before arming AGENT_RUNTIME for that canary
```

## Contract

```yaml
mode: single_agent_canary
expected_agent: nikhil
allowed: true|false
eligible_agents: [...]
unexpected_agents: [...]
reason_code: canary_agent_isolation_failed | expected_agent_not_eligible | ""
```

Read-only. Never flips env flags.

## Rule

`AGENT_RUNTIME=1` is only safe for a single-agent canary when preflight proves:

```text
set(eligible_agents) == {expected_agent}
```

and `ungated_dispatchable_count == 0`.

## Distributed durability gates (before third agent)

| Gate | Status |
|---|---|
| cancellation_cross_process | production_proven (`d4b248f5`) |
| idempotency_cross_process | **not** production-proven until fail-closed Redis idempotency PR is deployed + Pranav proof |

Do not enable a third agent until idempotency is production-proven.

See `DISTRIBUTED_IDEMPOTENCY.md` · `DISTRIBUTED_CANCELLATION_PRODUCTION_PROOF.md`.
