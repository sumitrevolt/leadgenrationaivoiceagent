# OmniRoute architecture

## Purpose and boundary

OmniRoute is a local WSL development gateway for sanitized coding and operator work.
It is not part of LeadGen's production customer, voice, billing, CRM, compliance, or
automation path. `app/platform/omniroute_client.py` remains optional and inert until
both `OMNIROUTE_ENABLED=1` and a local `OMNIROUTE_API_KEY` are deliberately supplied.

The production LLM path remains `app/voice_agent/free_ai.py` and its direct-provider,
circuit-breaker fallback chain. An unavailable OmniRoute instance must never block
FastAPI, dashboards, Celery, scheduler, payment, or customer delivery.

## Verified local topology (2026-07-14)

```text
Windows LeadGen checkout
  -> WSL Ubuntu 24.04
     -> tmux session: leadgen-omni
        -> gateway-only OmniRoute 3.8.46 (Node 22.23.1)
           HTTP API/dashboard: 0.0.0.0:20128
           live WS:            127.0.0.1:20129
           Responses API:      POST /v1/responses
           encrypted state:    /root/.omniroute/storage.sqlite
```

The effective executable is
`/root/.nvm/versions/node/v22.23.1/bin/omniroute`. `/usr/bin/omniroute` is a stale
system installation whose `better-sqlite3` binary targets a different Node ABI; do
not use it for operations.

## Safety controls

- No import-time or boot-time OmniRoute dependency exists.
- Existing `safe_ai_payload` masks PII and blocks unsafe-provider dispatch.
- The local gateway must receive only public or internal-sanitized coding context.
- Claude/ChatGPT alone own repository/worktree access and all tools. OmniRoute gets
  one bounded packet and returns a review-only draft; it cannot apply or execute it.
- Each written proposal is SHA-256 pinned. Tests/staging fail closed until the
  review ledger contains separately HMAC-authenticated `claude` and `chatgpt`
  approvals for that exact hash; a new proposal starts with an empty review map.
- Governor secrets are scoped to one signed review surface. Governors do not receive
  an admin token; the local submitter refuses non-loopback destinations.
- Provider-facing research/implement/review shell panes and automatic OmniRoute
  worktree creation are prohibited.
- Customer identifiers, call/WhatsApp transcripts, secrets, payment data, production
  logs, and compliance decisions are prohibited from gateway routing.
- The local server does not expose `POST /v1/chat/completions`; callers must use the
  verified Responses surface.
- Every supported launcher exports `OMNIROUTE_MEMORY_MB=2048`; a controlled Doctor
  probe verified the effective 2048 MB setting on 2026-07-14.
