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

## Nikhil future plan (not executed here)

1. Deploy flag-isolation PR with all runtime flags OFF.
2. Force every canary-ready peer flag OFF (census list).
3. Set `DELIVERY_ASSURANCE_AGENT=1` only.
4. Re-run preflight → eligible `{nikhil}`.
5. Then arm `AGENT_RUNTIME=1`.
6. Prove → rollback all OFF.
