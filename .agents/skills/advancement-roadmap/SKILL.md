---
name: advancement-roadmap
description: LeadGen AI 2026 advancement backlog — web-researched, codebase-aware, free-stack. Use when user bole "advanced bano", "next feature", "competitor se aage", "roadmap", "deep research", ya moat planning.
---

# Advancement Roadmap (2026)

> Free-stack only · TRAI/DND/AI-disclosure/9–7 gates INTACT · additive + flag-gated · DO products (Marketing ≠ Voice, no bundle USP).
> Competitor P0 truth: `docs/Competitor_Top20_Feature_Gap_2026.md` — grep pehle, rebuild mat karo (~80% built).

## Priority snapshot

| # | Item | Area | Impact | Effort | Status |
|---|------|------|--------|--------|--------|
| 0 | RFC 8058 one-click unsubscribe (cold outreach) | Lead-gen | High (inbox) | S | ✅ shipped |
| 1 | Contextual Retrieval + reranker (content/marketing RAG) | RAG | High (−49%→−67% miss) | M | ✅ shipped (lexical rerank; crossencoder opt-in) |
| 2 | Smart Turn v3 upgrade | Voice | Med-High (fewer cut-offs) | S | ✅ code+bake ready (`USE_SMART_TURN=1`) |
| 3 | Kokoro TTS as EdgeTTS fallback | Voice | Med (resilience) | M | ✅ shipped (`kokoro_tts.py`, `USE_KOKORO_TTS=1`, image-baked) |
| 4 | Hybrid search (semantic + BM25) in Qdrant | RAG | Med | M | ✅ shipped |
| 5 | LangGraph supervisor default (high-stakes flows) | Agents | Med | M | ✅ shipped |
| 6 | Expand eval/guardrail (DeepEval + cross-path) | Agents | Med | S-M | ✅ shipped |
| 7 | Hindi STT upgrade eval (Saaras V3 / IndicWhisper) | Voice | Med | M | ✅ eval harness |
| 8 | Cerebras for bulk content-gen (Groq stays voice) | LLM | Low-Med | S | ✅ shipped |
| 9 | TRAI 2025 verbal/DTMF consent-confirm ⚠️ | Compliance | High (legal) | M | 📋 spec ready (`docs/TRAI_CONSENT_CONFIRM_SPEC.md`) + flag registered — build JIT @ DLT-unlock |

S = <½ day · M = 1–3 days · ⚠️ = telephony flow — coordinate before edit.

## 0. RFC 8058 — ✅ SHIPPED

`email_unsub.py` (HMAC + headers + suppression) · `email_sender` extra_headers · `POST/GET /api/lifecycle/outreach-unsub/{token}` · wired `auto_outreach` + followups. Test: `tests/test_email_unsub.py`.

## 1–9 Integration pointers (proposed)

| # | How | Touch |
|---|-----|-------|
| 1 | Ingest: 1-line LLM context prefix per chunk; rerank top-100→10 via `BAAI/bge-reranker-v2-m3` off-loop + deadline. **NOT live voice turn.** | `vector_store.py`, new `reranker.py`, `USE_RERANKER=1` |
| 2 | Swap Smart Turn checkpoint behind `USE_SMART_TURN=1`; image-bake; tune on FREE web-call first. | `turn_detector.py` (already in vobiz_stream + phone_stream) |
| 3 | ✅ SHIPPED — Kokoro 82M CPU fallback when EdgeTTS fails; `USE_KOKORO_TTS=1`. Wired `tts.py`, baked `Dockerfile.lock`, test `test_kokoro_tts.py`. | TTS chain + `agent_tester.py` scorecard |
| 4 | Qdrant sparse + dense, RRF fuse. | `knowledge_base.py`, `USE_HYBRID_SEARCH=1` |
| 5 | LangGraph high-stakes on sales deep-dive. | `staff_supervisor.py`, `USE_LANGGRAPH_HIGH_STAKES=1` |
| 6 | DeepEval faithfulness/relevancy on voice-brain + RAG; CI + `final_integration_check`. | `evals/`, `eval_gate`, `eval_guardrail.py` |
| 7 | STT eval harness (`scripts/stt_eval.py`); no default swap yet. | `stt_eval.py` |
| 8 | `chat(profile=)` bulk→Cerebras-first; auto when max_tokens≥180. | `free_ai.py` |
| 9 | After AI-disclosure opener: verbal/DTMF confirm before continue (promotional only); log `consent_ledger`. | `telecaller_brain` + telephony — flag-gated, web-call verify first |

## Product gaps (separate from table — still wireable)

| P | Item | Touch |
|---|------|-------|
| P0 | Human call transfer | `call_transfer.py`, `CALL_TRANSFER=1` + Vobiz DID |
| P0 | ✅ SHIPPED — Public `/geo-check` page | `frontend/website/geo-check.html` + wired `main.py` + `localseo.py` |
| P0 | ✅ SHIPPED — `call.report.ready` customer webhook | `post_call_hooks.emit_call_report` → both telephony paths; event in `customer_webhooks.SUPPORTED_EVENTS` |
| P1 | Post-call analytics DB (not jsonl-only) | migration + worker |
| EXT | Meta auto-post, GBP API, DLT cold-call | user paperwork |

## Cross-path discipline (har item pe)

1. `grep` touch-points + duplicate `@router` check
2. Additive + never-raise + flag default OFF
3. `cross_path_audit.py` + targeted test + `prod_check`
4. `leadgen-ops` deploy loop

## Sources (web, Jun 2026)

TTS benchmarks · Pipecat Smart Turn v3 · Anthropic Contextual Retrieval · bge-reranker-v2-m3 · LangGraph 2026 · Gmail/Yahoo RFC8058 · free-LLM APIs · Sarvam/IndicWhisper · TRAI TCCCPR Feb-2025 amendment.
