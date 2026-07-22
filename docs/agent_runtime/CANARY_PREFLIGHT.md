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

## Distributed cancellation (preflight note)

Cross-process cancel requires the Redis-backed store (`DISTRIBUTED_CANCELLATION.md`).
Until that SHA is **deployed and production-proven**, treat:

```yaml
cancellation_cross_process: not_supported
```

Do not enable a third agent until owner-authorized cancel deploy + Pranav-only proof.

## Nikhil (done) / next agent (blocked)

Nikhil production canary proven on prior SHA; flags restored OFF.
Third agent canary is **blocked** until distributed cancellation is production-proven.
