# Voice "Smart-Fix Bundle" — Design Spec (2026-06-29)

## Problem
The Hinglish AI telecaller (`app/voice_agent/telecaller_brain.py`) sounds **noob / loops /
confused** in live web-call tests. A 3-agent root-cause investigation (datasets · learning-infra ·
noob-root-cause) concluded:

- **Primary cause = STT, not the model or data volume.** Groq `whisper-large-v3` is called with
  `language="hi"` (`app/voice_agent/free_ai.py`), which transliterates code-switched Hinglish into
  Devanagari and mangles English domain words + numbers ("trial"→"ritail", "1999"→"van thousand
  nine hundred"). The downstream NLU is keyword/romanized gates — one garbled token and the
  deterministic "answer-the-customer" path misses → the turn falls to the LLM, which ALSO got the
  garbled text → non-sequitur ("noob"), and the layered fallbacks then script-march ("loop").
- **"Train on data" is not the right first lever:** real-call data is thin (~63 transcript turns,
  34 recordings, 37 sessions). A self-host fine-tune is a real plan but **GPU + Vobiz-recharge
  blocked** and needs far more data. The model (Gemini-2.5-flash-lite primary / 8B fallback) is
  capable enough.
- **A learn-from-calls loop already runs but dead-ends:** `web_call_learn → voice_self_improve →
  data/voice_proposals.jsonl` (with a working promotion gate), but `promote` writes nothing back to
  the live agent. The `app/ml/*` sklearn stack is signature-broken and fed nothing (quarantine).

## Approach (user-approved): no-GPU, flag-gated, incremental bundle
Ship in sequence; each piece flag-gated (default ON), fail-open, verified before the next.

### Component 1 — STT Hinglish-correction layer  ← THIS SPRINT (highest leverage)
- **1a. Strengthen per-niche STT bias** — pass a richer initial-prompt/keyterms string (domain vocab:
  trial, plan, price, rupees, posts, ads, Google, Instagram, WhatsApp, setup, booking + per-niche
  terms) to Groq whisper so it hears domain words correctly **at the source**.
- **1b. New module `app/voice_agent/hinglish_stt_fix.py`** → `correct_stt(text, niche="") -> str`:
  (a) number-words→digits, (b) curated mis-hear map ("ritail"→"trial", …) that is **data-extensible**
  (Component 3 can append learned pairs), (c) Devanagari/roman normalisation reuse. Applied to the
  STT output that feeds **both** the NLU gates and the LLM.
- **Flag** `STT_CORRECT=1` (default ON), fail-open (any error → original text).
- **Tests:** offline unit (garbled→corrected, no false-rewrites on clean text) + live WS-probe +
  `agent_tester` scorecard (no regression).

### Component 2 — Anti-loop acknowledge-bridge
In `telecaller_brain.reply()` script-fallback: when the LLM is rejected, prefer a short
acknowledge-the-last-user-turn bridge (reuse `_mirror_ack`) before the next scripted question, and
gate discovery-advance on whether the prior turn was understood — instead of blindly emitting the
next unasked discovery question (the "marching checklist" loop). Flag `ANTI_LOOP=1`, fail-open.

### Component 3 — Close the learning-loop ("data se seekhna", realistically)
`promote_voice_proposal` (admin-approved real-call correction) appends the candidate to a curated,
voice-only, niche-tagged `data/voice_learned.jsonl` (bounded top-N/niche) that `telecaller_brain`
injects as few-shot / KB grounding. Keeps the existing promotion-gate + admin click as the guardrail
(never blind-write). Flag `VOICE_LEARNED_INJECT=1`. Also feeds the Component-1b mis-hear map.

### Component 4 — Deepen 39 niche scripts (richest present asset)
Deepen objection-rebuttals + value-lines for the most-used niches (`niche_scripts_data.py`). Pure
data-authoring, incremental, no code-risk.

### Cleanup
Quarantine the dead `app/ml/*` sklearn stack (signature-broken, never fed) — flag-off / mark legacy.

## Cross-cutting
- **Rollback:** every component flag-gated default-ON with a `=0` kill-switch; surgical `docker cp` +
  `:latest` re-commit per the live deploy method (see memory `voice-role-injection-guard`).
- **Verify:** offline unit + live WS-probe (`scratchpad/ws_probe.py`) + `agent_tester` scorecard +
  re-transcribe a saved recording.
- **Non-goal (deferred):** the self-host Indic STT/LLM fine-tune (GPU + Vobiz blocked) — tracked in
  `docs/VOICE_SELFHOST_FINETUNE_PIPELINE.md`.
