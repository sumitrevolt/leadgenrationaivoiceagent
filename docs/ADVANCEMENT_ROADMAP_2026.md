# LeadGen AI — Advancement Roadmap (2026)

> Web-researched (June 2026), codebase-aware. Free-stack only · TRAI/DND/AI-disclosure/10–7 compliance gates INTACT · additive + flag-gated pattern.
> Sources at bottom. Pricing/products unchanged (Marketing + Voice, no bundle USP).

## Priority snapshot

| # | Item | Area | Impact | Effort | Status |
|---|------|------|--------|--------|--------|
| 0 | RFC 8058 one-click unsubscribe on cold outreach | Lead-gen | High (inbox placement) | S | ✅ shipped |
| 1 | Contextual Retrieval + reranker (content/marketing RAG) | RAG | High (−49%→−67% retrieval miss) | M | ✅ shipped |
| 2 | Smart Turn v3 upgrade (turn detection) | Voice | Med-High (fewer cut-offs) | S | ✅ shipped (bake+flag) |
| 3 | Kokoro TTS as EdgeTTS fallback | Voice | Med (latency + resilience) | M | ✅ shipped (bake+flag) |
| 4 | Hybrid search (semantic + BM25) in Qdrant | RAG | Med | M | ✅ shipped |
| 5 | LangGraph supervisor default for high-stakes flows | Agents | Med (reliability, audit) | M | ✅ shipped |
| 6 | Expand eval/guardrail coverage (DeepEval + cross-path) | Agents | Med (regression safety) | S-M | ✅ shipped |
| 7 | Hindi STT upgrade eval (Sarvam Saaras V3 / IndicWhisper) | Voice | Med (Hindi WER) | M | ✅ eval harness |
| 8 | Cerebras for bulk content-gen (keep Groq for voice) | Voice/LLM | Low-Med (throughput) | S | ✅ shipped |
| 9 | TRAI 2025: verbal/DTMF consent-confirm step | Compliance | High (legal) | M | 📋 spec ready + flag — build JIT @ DLT-unlock ⚠️ |

S = <½ day · M = 1–3 days. "⚠️" = touches telephony (coordinate; currently owned by the parallel cleanup).

---

## 0. RFC 8058 one-click unsubscribe — ✅ SHIPPED
**Why:** Gmail/Yahoo 2026 bulk-sender rules expect promotional mail to carry `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click`; spam-complaint rate must stay < 0.3% (target < 0.1%). Our cold outreach sent **no** `List-Unsubscribe` header → avoidable deliverability drag.
**What shipped:** `app/platform/email_unsub.py` (HMAC token + headers + suppression), `email_sender.send_email(extra_headers=…)`, public one-click endpoint `POST/GET /api/lifecycle/outreach-unsub/{token}`, and suppression-skip + headers wired into `auto_outreach.run_email_outreach` + `run_email_followups`. Test: `tests/test_email_unsub.py`.

## 1. Anthropic Contextual Retrieval + reranker (content/marketing RAG)
**Why:** Prepending a short context blurb to each chunk before embedding cuts retrieval failures ~35%; + contextual BM25 → 49%; + reranking → 67%. This is the single biggest knowledge-grounding lever.
**How (free, safe):** At ingest, prepend a 1-line LLM-generated context (free chain) to each chunk before embedding. Add a cross-encoder reranker `BAAI/bge-reranker-v2-m3` (Apache-2.0, ~600M, multilingual) over top-100→top-10. **NOT on the live voice turn** (CPU rerank ~350ms = too slow mid-call); apply to blog/content/RAG-answer endpoints only.
**Integration:** `app/ml/vector_store.py` (ingest context-prefix) + new `app/ml/reranker.py` gated `USE_RERANKER=1` (image-bake, off-loop `asyncio.to_thread` + deadline + disable-switch per the ML rule). Builds on existing `agentic_rag.py`/`USE_AGENTIC_RAG`.

## 2. Smart Turn v3 turn-detection upgrade
**Why:** `turn_detector.py` targets Smart Turn v2-era. Pipecat **Smart Turn v3/v3.2** improves accuracy on noisy environments + short responses, 14 languages, ~12ms inference, 360MB. Fewer premature cut-offs / dead-air = more natural calls.
**How:** Swap the model checkpoint behind the existing `USE_SMART_TURN=1` flag; image-bake the weights; keep RMS fallback when dep/flag absent. **Tune on the FREE web-call path first** (phone = final verify).
**Integration:** `app/voice_agent/turn_detector.py` (SmartTurnDetector model id) — already wired into `vobiz_stream` (16k) + `phone_stream` (8k). No new wiring.

## 3. Kokoro TTS as EdgeTTS fallback — ✅ SHIPPED
**Why:** EdgeTTS (`hi-IN-SwaraNeural`) occasionally 403s and is network-dependent. Kokoro (82M, CPU, low-latency, Apache-2.0) gives a self-hosted fallback → resilience + lower tail-latency. Caveat: weaker Hindi naturalness + no voice cloning — keep EdgeTTS primary.
**What shipped:** `app/voice_agent/kokoro_tts.py` provider behind `USE_KOKORO_TTS=1`, wired into `app/voice_agent/tts.py` (used only when the EdgeTTS primary fails — off-loop `asyncio.to_thread`, never blocks the raise). Model image-baked in `Dockerfile.lock`; verify in `scripts/vps_verify_deploy.py`. Test: `tests/test_kokoro_tts.py`. Compare on `scripts/agent_tester.py` scorecard before promoting to primary.

## 4. Hybrid search (semantic + BM25) in Qdrant
**Why:** Hybrid (dense + sparse/BM25) beats pure-semantic in production RAG and pairs with #1's contextual BM25. Qdrant supports sparse vectors natively.
**Integration:** `app/ml/vector_store.py` — add a sparse index alongside `kb_main`; fuse with RRF. Flag `USE_HYBRID_SEARCH=1`. Pairs with #1.

## 5. LangGraph supervisor as default for high-stakes flows
**Why:** In 2026 LangGraph is the production standard for stateful, auditable agent workflows (built-in checkpointing + time-travel + rollback). Framework/scaffold choice can swing agent accuracy up to ~30 points. We already have `staff_supervisor.py` behind `USE_LANGGRAPH_SUPERVISOR=1` (off).
**How:** Promote LangGraph for the high-stakes deterministic flows (sales close, process_engine breakpoints), keep the lightweight coordinator for cheap fan-out. Add checkpointing to `data/`.
**Integration:** `app/agents/staff_supervisor.py` + `process_engine.py`; flip `USE_LANGGRAPH_SUPERVISOR=1` after eval.

## 6. Expand eval/guardrail coverage
**Why:** Agent reliability is mostly an eval problem in 2026. We have `eval_gate` + `cross_path_audit.py`. Widen DeepEval metrics (faithfulness, answer-relevancy) on the voice-brain + RAG, wire into CI/`final_integration_check`.
**Integration:** `evals/` + `eval_gate` reward signal; new metrics behind the existing DeepEval CI step. Reuse the cross-path-audit "exit-nonzero guard wired into final_integration_check" pattern.

## 7. Hindi STT upgrade eval
**Why:** Current STT = Groq `whisper-large-v3` (strong, free) → Gemini → local faster-whisper (Hindi weak). 2026 options worth benchmarking: **Sarvam Saaras V3** (~19.3% WER on IndicVoices-top10), **IndicWhisper / AI4Bharat IndicASR** (self-host, Hindi telephony WER ~22–30%), NVIDIA Canary-Qwen. Keep Groq primary; add the best self-host as the offline floor.
**Integration:** `app/voice_agent/free_ai.py` STT chain — add a provider, A/B on call transcripts (`data/call_transcripts/`). Eval first, no default change.

## 8. Cerebras for bulk content-gen
**Why:** Cerebras ≈ 2,000 tok/s, ~1M tok/day free — ideal for non-latency-critical bulk (blog/content packs). Keep Groq (OpenAI-compatible, ~320 tok/s, low TTFT) for the voice turn. Cerebras is 429-prone under load (already noted) → use for batch, not realtime.
**Integration:** `app/voice_agent/free_ai.py` — task-typed routing (bulk → Cerebras-first; realtime → Groq-first). Tune within the existing circuit-breaker chain.

## 9. TRAI Feb-2025 verbal/DTMF consent-confirm ⚠️
**Why:** The Feb-2025 TCCCPR 2nd amendment expects AI promotional calls to **open with AI disclosure + obtain a verbal or DTMF confirmation before continuing**, timestamp/log consent, and honor opt-out in 24–48h. We already have AI-disclosure greeting + DND fail-closed + consent ledger + opt-out; the explicit **confirm-before-continue** step is the gap.
**How:** Add a consent-capture turn after the AI-disclosure opener on promotional calls (transactional unaffected); log to `consent_ledger`. **Touches telephony (`telecaller_brain`/flow) — coordinate with the in-flight telephony work before editing.**
**Integration:** voice flow + `consent_ledger`. Compliance-critical; keep behind a flag and verify on the free web-call path.

---

## Sources
- TTS 2026: BentoML, Inworld, MarkTechPost benchmarks
- Turn detection: Pipecat/Daily.co Smart Turn v2/v3
- RAG: Anthropic Contextual Retrieval; "RAG is not dead" advanced patterns 2026
- Rerankers: BAAI bge-reranker-v2-m3 (HF); reranker leaderboards 2026
- Agent frameworks: LangChain/CrewAI/OpenAI Agents SDK 2026 comparisons
- Email: Gmail/Yahoo 2026 sender requirements; Mailgun RFC 8058
- Free LLMs: free-LLM-API 2026 comparisons (Cerebras/Groq/Gemini)
- Hindi STT: Sarvam Saaras V3; AI4Bharat/IndicWhisper; Gladia OSS STT 2026
- Compliance: TRAI TCCCPR Feb-2025 2nd Amendment; AI-calling 2026 guides

(Full URLs in the chat message accompanying this roadmap.)
