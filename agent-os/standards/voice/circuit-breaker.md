# Provider Circuit Breaker

Per-provider cooldown map — a rate-limited provider is skipped, not retried per call.

```python
_LLM_COOLDOWN_UNTIL: dict[str, float] = {}
_LLM_COOLDOWN_S = 60.0          # first trip
_LLM_COOLDOWN_MAX_S = 1800.0    # cap (30 min)
```

- 429/rate/quota errors: exponential cooldown `60s * 2**(streak-1)`, capped at 30 min.
- Permanent errors (404/decommissioned model, 403): straight to MAX cooldown — a dead endpoint must not eat the chain every minute.
- Multi-key rotation (Gemini 9-key pool, OpenRouter 4 accounts): each key gets its OWN breaker.
- Model-head vs provider: a tripped model can share the provider breaker (nvidia pattern) so a dead head skips its whole tail.
- Never let breaker state raise — breaker functions are read/write on dicts, wrapped defensively.
