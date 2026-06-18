---
name: advancement-roadmap
description: LeadGen AI 2026 advancement backlog — web-researched, codebase-aware, free-stack. Use when user bole "advanced bano", "next feature", "competitor se aage", "roadmap", "deep research", ya moat planning.
---

# Advancement Roadmap (2026)

> Free-stack only · TRAI/DND/AI-disclosure/10–7 gates INTACT · additive + flag-gated · DO products (Marketing ≠ Voice, no bundle USP).
> Competitor P0 truth: `docs/Competitor_Top20_Feature_Gap_2026.md` — grep pehle, rebuild mat karo (~80% built).

## Priority snapshot

| # | Item | Area | Impact | Effort | Status |
|---|------|------|--------|--------|--------|
| 0 | RFC 8058 one-click unsubscribe (cold outreach) | Lead-gen | High (inbox) | S | ✅ shipped |
| 1 | Contextual Retrieval + reranker (content/marketing RAG) | RAG | High (−49%→−67% miss) | M | ✅ shipped (lexical rerank; crossencoder opt-in) |
| 2 | Smart Turn v3 upgrade | Voice | Med-High (fewer cut-offs) | S | ✅ code+bake ready (`USE_SMART_TURN=1`) |
| 3 | Kokoro TTS as EdgeTTS fallback | Voice | Med (resilience) | M | proposed |
| 4 | Hybrid search (semantic + BM25) in Qdrant | RAG | Med | M | proposed |
| 5 | LangGraph supervisor default (high-stakes flows) | Agents | Med | M | proposed |
| 6 | Expand eval/guardrail (DeepEval + cross-path) | Agents | Med | S-M | proposed |
| 7 | Hindi STT upgrade eval (Saaras V3 / IndicWhisper) | Voice | Med | M | eval only |
| 8 | Cerebras for bulk content-gen (Groq stays voice) | LLM | Low-Med | S | proposed |
| 9 | TRAI 2025 verbal/DTMF consent-confirm ⚠️ | Compliance | High (legal) | M | proposed |

S = <½ day · M = 1–3 days · ⚠️ = telephony flow — coordinate before edit.

## 0. RFC 8058 — ✅ SHIPPED

`email_unsub.py` (HMAC + headers + suppression) · `email_sender` extra_headers · `POST/GET /api/lifecycle/outreach-unsub/{token}` · wired `auto_outreach` + followups. Test: `tests/test_email_unsub.py`.

## 1–9 Integration pointers (proposed)

| # | How | Touch |
|---|-----|-------|
| 1 | Ingest: 1-line LLM context prefix per chunk; rerank top-100→10 via `BAAI/bge-reranker-v2-m3` off-loop + deadline. **NOT live voice turn.** | `vector_store.py`, new `reranker.py`, `USE_RERANKER=1` |
| 2 | Swap Smart Turn checkpoint behind `USE_SMART_TURN=1`; image-bake; tune on FREE web-call first. | `turn_detector.py` (already in vobiz_stream + phone_stream) |
| 3 | Kokoro 82M CPU fallback when EdgeTTS fails; `USE_KOKORO_TTS=1`. | TTS chain + `agent_tester.py` scorecard |
| 4 | Qdrant sparse + dense, RRF fuse. | `vector_store.py`, `USE_HYBRID_SEARCH=1` (pairs #1) |
| 5 | LangGraph for sales/process breakpoints; cheap coordinator for fan-out. | `staff_supervisor.py`, `process_engine.py`, `USE_LANGGRAPH_SUPERVISOR=1` |
| 6 | DeepEval faithfulness/relevancy on voice-brain + RAG; CI + `final_integration_check`. | `evals/`, `eval_gate`, `cross_path_audit.py` pattern |
| 7 | Benchmark Sarvam/IndicWhisper on `data/call_transcripts/`; no default swap yet. | `free_ai.py` STT chain |
| 8 | Task routing: bulk→Cerebras-first, realtime→Groq-first; existing circuit-breaker. | `free_ai.py` |
| 9 | After AI-disclosure opener: verbal/DTMF confirm before continue (promotional only); log `consent_ledger`. | `telecaller_brain` + telephony — flag-gated, web-call verify first |

## Product gaps (separate from table — still wireable)

| P | Item | Touch |
|---|------|-------|
| P0 | Human call transfer | `call_transfer.py`, `CALL_TRANSFER=1` + Vobiz DID |
| P0 | Public `/geo-check` page | API ready (`geo_visibility.py`); need `frontend/website` route |
| P0 | `call.report.ready` customer webhook | `post_call_hooks.py` after qualify |
| P1 | Post-call analytics DB (not jsonl-only) | migration + worker |
| EXT | Meta auto-post, GBP API, DLT cold-call | user paperwork |

## Cross-path discipline (har item pe)

1. `grep` touch-points + duplicate `@router` check
2. Additive + never-raise + flag default OFF
3. `cross_path_audit.py` + targeted test + `prod_check`
4. `leadgen-ops` deploy loop

## Sources (web, Jun 2026)

TTS benchmarks · Pipecat Smart Turn v3 · Anthropic Contextual Retrieval · bge-reranker-v2-m3 · LangGraph 2026 · Gmail/Yahoo RFC8058 · free-LLM APIs · Sarvam/IndicWhisper · TRAI TCCCPR Feb-2025 amendment.
