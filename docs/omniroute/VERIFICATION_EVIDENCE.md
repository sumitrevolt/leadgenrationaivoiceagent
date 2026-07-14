# OmniRoute verification evidence - 2026-07-13

## Baseline

- Git SHA: `7ae14de922747313d133ff9f557137fa4df13361` on `main`.
- Gateway: OmniRoute `3.8.46`, Node `v22.23.1`, tmux `leadgen-omni`.
- Listeners: 20128 API/dashboard and 20129 loopback WS.
- Process tree before work: launcher plus one OmniRoute server process.
- Backup: `/root/.omniroute_backups/a2z-20260713T170103Z` confirmed readable.

## Provider evidence

- Fresh dashboard rendered successfully with no console warnings/errors.
- Groq was connected with 17/17 active models; its `Retest` action completed with no
  console error.
- Gemini was connected with 54/54 active models; its `Retest` action completed with no
  console error.
- Mistral was connected with 60/60 active models; its `Retest` action completed with no
  console error.
- A user-scoped local data-plane key was present without being read or displayed.
  Authenticated `/v1/models` returned 489 models.
- Sanitized `stream:false` completion through `groq/llama-3.3-70b-versatile` returned
  `omni-ok` in 1,684 ms (2,041 prompt / 4 completion tokens).
- OpenCode Free's dashboard playground returned `omni-ok`, but direct
  `oc/big-pickle` OpenAI-compatible calls returned reasoning-only, empty `content`.
  It is not accepted as an API fallback. DuckDuckGo returned `ERR_RATE_LIMIT`.

## LeadGen regression evidence

```text
pytest tests/test_omniroute_client.py tests/test_safe_ai_payload.py
       tests/test_free_ai_pii_gate.py -q  -> 42 passed
python scripts/prod_check.py              -> ALL CHECKS PASSED (1102 routes, 0 gaps)
python scripts/check_secrets.py           -> clean (79 changed files scanned)
```

## Honest verdict

PARTIALLY COMPLETE. The local runtime, backup, dashboard, authenticated data plane,
Groq sanitized completion, optional adapter, privacy guards, and regression gates are
verified. Unfinished gates are bounded fallback/failure simulations, route benchmarks,
and any production integration. LeadGen routing remains intentionally disabled.

## 2026-07-14 recovery and adapter evidence

- Backup: `/root/.omniroute_backups/20260714_035015/omniroute_config.tar.gz` exists
  outside Git; only environment variable names were printed.
- A WSL restart left no tmux session or 20128 listener. The existing idempotent
  launcher restored `leadgen-omni` with one OmniRoute process, API 20128, WS 20129,
  and version 3.8.46. Later logs showed an actual LiveWS reconnect storm (52 events in
  200 lines, with concurrent clients cycling); this remains unresolved because the
  required Chrome bridge could not start for fresh-tab diagnosis.
- The server serves `POST /v1/responses`; `POST /v1/chat/completions` is HTTP 404.
  Sanitized Groq and Mistral Responses calls passed. The Gemini 2.5 Flash model was
  rejected upstream as retired and was not routed.
- `app.platform.omniroute_client.generate()` now uses the Responses API, an explicit
  INTERNAL_SANITIZED-only task registry, masking, secret validation, one bounded
  retryable fallback, and structured metadata without raw prompt logging. It remains
  disabled unless both `OMNIROUTE_ENABLED=1` and a local API key are supplied.
- Adapter live smoke returned `leadgen-adapter-ok` through Groq. A customer-summary
  request was privacy-rejected before network dispatch.
- Chrome fresh-tab verification could not start because the local browser bridge failed
  with `Cannot redefine property: process`; this is an automation-runtime blocker, not
  a gateway/WebSocket failure. No fallback browser surface was used.

## 2026-07-14 closure evidence

- The healthguard now counts timestamped LiveWS connections only inside a bounded
  five-minute window. Fresh guard evidence: 0 reconnects and 0 active WS clients.
- The local Chrome-control bundle now preserves the runtime-owned process shim. Fresh
  Chrome UAT loaded `/dashboard` and `/dashboard/providers` on OmniRoute 3.8.46; the
  first provider-page console check had zero errors. A post-restart reload completed,
  though its captured console buffer contained two entries not inspected after tab finalization.
- `OMNIROUTE_MEMORY_MB=2048` is the verified configuration key. Tmux launch and
  recovery commands now export it; a controlled Doctor probe reports 2048 MB. No `.env`
  value or credential was changed.
- Sanitized benchmark: 100/100 successful requests across all four approved internal
  routes; p50 1020.3 ms, p95 3197.0 ms, max 3316.9 ms, zero fallbacks. Groq completed
  75 requests and Mistral completed 25. No customer data, secrets, or production traffic was used.

### Correction — active Chrome-owned reconnect storm

The initial zero-client guard sample preceded browser UAT and is not a final stability
claim. The final five-minute sample showed 130 reconnects and 9 active WS clients.
Windows TCP attribution identifies the client owner as the user's Chrome process, while
the server side is the WSL relay; no duplicate OmniRoute process exists. Closing the
user's Chrome tabs/profile is a destructive user-session action and was not performed.
The gateway and benchmark are healthy, but WebSocket stability remains blocked until
those OmniRoute dashboard clients are closed or the user authorizes closing Chrome.

### 2026-07-14 authorized Chrome recovery

The user authorized Chrome closure/restart. Terminating the Chrome session drained all
OmniRoute LiveWS clients; Chrome was then restarted to a blank window. A fresh 20-second
healthguard window measured 0 reconnects and 0 active WS clients, while the gateway
remained a single v3.8.46 process. The longer five-minute counter retains earlier
historical connections until its window ages out; it is not an active-storm signal.
