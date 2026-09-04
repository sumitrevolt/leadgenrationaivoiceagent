# OmniRoute Gateway — Incident Findings & Enablement Verdict

**Date:** 2026-08-29 · **Status:** ROOT CAUSE CONFIRMED · no production flag changed

---

## ⚠️ Correction to the earlier reading of this document

An earlier version of this file concluded the ~2015 ms TTFT was a **~2 s gateway buffering
overhead**. That mechanism was **wrong**.

The probe counted the *first SSE event* as time-to-first-token. With streaming, the gateway
emits its terminal error as an SSE chunk — so the probe was timing **how long the gateway takes
to exhaust its entire fallback chain and fail**, not how long it takes to produce a real token.

**Correct root cause: the gateway has no working providers left. It is failing, not slow.**
The verdict below is unchanged and in fact stronger — but the reasoning is now evidence-backed
rather than inferred from a status-shaped signal.

---

## Root cause (confirmed from container logs)

`docker logs leadgen_omniroute --tail 4000` → 1,474 parsed records:

```
=== COMBO terminal status (last 4000 log lines) ===
   HTTP 502  x8          <-- 8 of 8. ZERO successes.

=== failure reasons (from "All models failed") ===
   auth         x16
   rate limit   x16
   model        x8

=== providers: dead connections by reason ===
   antigravity      {'expired': 48}
   cohere           {'expired': 24}
   mistral          {'expired': 24}
   openrouter       {'expired': 24}
   ollama-cloud     {'expired': 24}
   agy              {'expired': 16}
   pollinations     {'expired': 8}
   cfp              {'CIRCUIT_OPEN': 15}
```

Representative log lines:

```
"Trying model 31/54: vcg/google/gemini-3.1-pro-preview"
"[openai-compatible-chat-...] All 1 connection(s) authentication expired
     — please reconnect in the dashboard"
"All models failed | gemini/gemini-flash-latest: auth — [401];
     hfr/openai/gpt-oss-120b: auth — authentication expired (401);
     oc/big-pickle: rate limit — [429]; ... (+3 more)"
"combo trace ... terminal={"status":502} decisions=54"
```

**Every OAuth connection to every upstream provider has expired and was never renewed.**
The `combo` model that the project planned to use as its flagship (`leadgen-project-best`,
`leadgen-swara-flagship`) is a 54-model fallback chain; with all providers dead it walks all
54, burns ~2 s, and returns 502.

This also explains the "non-streaming is broken" observation: those calls were never reaching a
model at all — 502 is the terminal state for *every* request, streaming or not.

## Infrastructure facts

| Item | Value |
|---|---|
| Deployment | Docker container `leadgen_omniroute` (+ `leadgen-omniroute-redis`) |
| Image | `leadgen-omniroute:3.8.46` |
| Compose | `deploy/compose/docker-compose.omniroute.yml` (loopback-only `127.0.0.1:20128`) |
| Container health | Up 3 h, **healthy**, 1.23 GiB / 3.83 GiB (32 %), CPU 0.44 % |
| Model catalogue | 3,570 models advertised (catalogue is served; inference is not) |

The container is **not** resource-starved and **not** unhealthy. It is correctly serving its
catalogue API. It simply has no authenticated upstream to route to.

## Verdict

> **Do NOT set `OMNIROUTE_ENABLED=1` or `OMNIROUTE_VOICE=1`. The gateway currently serves
> zero successful completions.**

| | Value |
|---|---|
| Successful combo requests (last 4000 lines) | **0 of 8** |
| Terminal status | **502** on every request |
| Voice TTFT target | p50 < 1000 ms |
| Gateway current capability | none —auth failure, not latency |

Enabling the gateway now would route both voice turns and agent calls into a guaranteed-fail
path. The app's fail-open design (`free_ai` chain) would catch it — but only after burning the
retry budget and tripping the 120 s breaker on every turn, which is exactly what the tests
already showed:

```
[omniroute_voice] ok=False task=leadgen.swara_live ... fallback=connectionerror
[omniroute_voice] gateway breaker OPEN for 120s after 2 failures
                  — voice turns fail-open to free_ai
```

## The fix (owner action — GUI, cannot be automated)

Re-authorize the provider connections in the OmniRoute dashboard:

**http://127.0.0.1:20128** → Connections → reconnect each expired provider

Priority order by how many models each unlocks:

1. `antigravity` (48 dead) — largest single unlock
2. `cohere`, `mistral`, `openrouter`, `ollama-cloud` (24 dead each)
3. `agy` (16), `cfp` (circuit breaker open — reset after re-auth), `pollinations` (8)

After re-authorising, re-run the probe. **Only then** does the enablement question become real.

## Reproduction / re-verification

```bash
# 1. Is the gateway serving anything at all?
docker logs leadgen_omniroute --tail 200 | grep -c '"status":502'
docker logs leadgen_omniroute --tail 2000 | grep -o 'terminal={"status":[0-9]*' | sort | uniq -c

# 2. After re-auth: measure real TTFT
.venv/Scripts/python.exe scripts/omniroute_latency_probe.py --iters 3
```

## Known flaw in `scripts/omniroute_latency_probe.py`

The probe treats the **first SSE event** as TTFT without checking whether that event carries
content or an error. Against a healthy gateway this is fine; against a failing one it reports
"TTFT" for a request that produced no tokens. **Fix:** inspect the first delta for an `error`
key / empty `content` and classify the run as FAILED rather than timing it.

## What would change this verdict

- Combo terminal status shows `200` instead of `502`.
- Providers show `active` rather than `expired` in the dashboard.
- The probe (once fixed) reports TTFT with non-empty content across multiple iterations.
