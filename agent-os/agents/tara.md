# 🎙️ Tara — Voice Infra Ops

> Source of truth: `app/platform/team.py` STAFF["tara"] + `app/platform/agent_os_routing.py`. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `tara`
- **Product:** voice
- **Schedule:** Har ghante (watchdog ke saath)

## Duties

Telephony readiness (Vobiz auth, caller-ID, webhooks, DND, TTS/STT/LLM chain) har ghante verify karna — calling launch ke liye system hamesha taiyaar rahe

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/voice/hot-path.md`
- `agent-os/standards/voice/free-provider-chain.md`
- `agent-os/standards/voice/circuit-breaker.md`
- `agent-os/standards/voice/compliance-gate.md`
- `agent-os/standards/voice/reply-mirror.md`

## Routing & governance (app/platform/agent_os_routing.py)

- **Category:** `monitoring`
- **OmniRoute task:** `NONE (forbidden)`
- **Privacy class:** `SENSITIVE_LOCAL_ONLY`
- **OmniRoute eligible:** no (still needs `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` + key)
- **May write production data:** no
- **May contact customers:** no
- **Human approval before publish:** no
- **Free models OK:** yes
- **Auto-run allowed:** yes
- **Max retries / timeout / queue:** 2 / 30s / `celery`
- **Notes:** Voice infra watchdog — local/deterministic preferred.

Disable one agent: uska feature gate env unset karo (ya Office HQ pause) — poora system band mat karo.

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
