# PB-PROVIDER-FAILOVER — Provider Failover Playbook (P0)

- **Purpose**: Keep the free AI stack alive when a provider degrades — automatically, cheaply.
- **Trigger**: provider 429 / quota exhaust / 5xx / latency spike.
- **Scope**: detection -> confirm -> failover -> recover -> record.
- **Prereqs**: circuit-breaker chain live (free_ai.py), llm_metrics, provider status source.

## Strategy
1. DETECT: llm_metrics ok-rate drop; circuit-breaker cooldowns; voice scorecard regression; Sentry burst.
2. CONFIRM it's the provider, not the app (check breaker state; check error series END timestamp — ADR-097).
3. FAILOVER is AUTOMATIC per-call: Mistral -> Groq -> Cerebras -> Gemini -> NVIDIA -> SambaNova -> OpenRouter; voice: Gemini 9-key rotation -> free chain; STT Groq -> Gemini -> local.
4. RECOVER: key rotation/add keys (owner), or wait cooldown; never fight the breaker.
5. RECORD: incident entry + prevention rule.

## Decision tree
```
Provider degraded
├─ 429/quota -> breaker cooldown auto (60s..30min) — usually NO action
├─ primary flapping -> chain routes around; watch ok-rate recover
├─ voice Gemini pool exhausted -> add keys via admin (AMBER)
└─ all providers down (rare) -> owner + RB-VOICE-007
```

## Allowed actions
- Rotate keys (scripted), watch metrics, add Gemini keys via admin API, escalate.

## Prohibited actions
- Adding PAID providers (free-stack mandate); disabling the breaker; claiming fix without error-series end timestamp.

## Escalation
- Multi-provider outage or voice deaf/silent -> owner immediately (RB-VOICE-007/009).

## KPIs
- Provider ok-rate; breaker recovery time; voice scorecard; cost per outcome.

## Guardrails
- Free providers ONLY; circuit-breaker never disabled; keys in env/data (never committed).

## Linked runbooks
RB-VOICE-007 (provider outage), RB-AGENT-005 (quota exhausted).

## Evidence requirements
- Metrics window (before/during/after), breaker state, decision log.

## Owner approval conditions
- Introducing ANY paid provider; manual intervention in a live call system.
