---
name: leadgen-voice-compliance
description: P2 voice-calling readiness + compliance gate audit — Vobiz/FreeSWITCH, STT/LLM/TTS, DND, consent, opt-out, AI-disclosure, calling-window, call-logs, recordings, aur external blockers (DLT, DID, recharge). Use jab voice ko powerful par gated rakhna ho. P2 audit P1 launch se SEPARATE.
---

# LeadGen Voice Compliance (P2 gate)

> Enterprise audit skill. Voice powerful par GATED — outbound AI calling tab tak na chale jab tak compliance + provider deps explicitly satisfy na hon. P2 audit ko P1 launch-blocker mat banao. Pehle `context-first`.
> **NOTE**: compliance GATE code (TRAI/DND/AI-disclosure/9am–7pm window) kabhi disable mat karo — yeh sirf audit skill hai, gate-removal nahi.

## Mission
P2 ko code-ready rakho par compliance/provider dependency ke bina dial na hone do.

## Repo truth
- **Provider**: Vobiz (`TELEPHONY_PROVIDER=vobiz`, `vobiz_handler.py` + `vobiz_stream.py` WS L16/16k). **Exotel DELETED** (2026-06-18). Twilio = international fallback only (India-domestic foreign-trunk ILLEGAL).
- **Compliance gates (INTACT)**: 140-series + DLT + DND-scrub + calling-window (TRAI 9am–9pm; code default promo **9am–7pm** conservative) + AI-disclosure-at-start ("ek AI assistant"). **DND FAIL-CLOSED** (lookup-fail = promotional BLOCK `dnd_lookup_failed`).
- **Consent**: `consent_ledger.py` — opt-out INSTANT cross-channel suppression + 90-din recording retention. `CallRequest.call_type` promotional default (transactional looser).
- **Brain**: `telecaller_brain.py` (KB-grounded, ≤2 sentences/1 question) + `niche_scripts.py`. Voice LLM = free_ai chain (Mistral primary, Gemini late fallback); `VOICE_GEMINI_PRIMARY=1` = optional opt-in override, default OFF (2026-07-05).
- **External blockers** (user paperwork — token mat jalao): DLT (Udyam re-apply pending), Vobiz DID + recharge, missed-call callback webhook.

## Workflow
1. Voice routes/tasks/providers/env-vars/call-queues/suppression/recordings inventory.
2. Har capability classify: `code-ready` / `config-missing` / `external-blocked` / `unsafe-non-compliant`.
3. DND + calling-window + consent + AI-disclosure + opt-out + suppression — dial se PEHLE enforce verify.
4. Blocked call queued ho bhi to dial NA ho — test.
5. P2 audit P1 readiness se separate rakho.

## Enterprise checks
- Compliance preflight ke bina koi call place na ho.
- Calls sirf allowed time-window me.
- AI identity disclosure present.
- Opt-out stored + globally respected.
- Recording analysis sensitive data unnecessarily expose na kare.
- Provider failure → actionable status, endless-retry nahi.

## Output
P2 readiness /100 · compliance-gate matrix · external-blocker list · tests proving unsafe calls cannot happen.

## Related repo skills (duplicate mat banao)
`voice-agent-kb` (KB grounding) · `telephony-engineering` (provider/stream) · `voice-roles` (Swara/etc) · `web-call-triage` (free tuning) · `leadgen-security-rbac` (consent/PII) · `leadgen-test-guardian` (compliance-preflight tests).
