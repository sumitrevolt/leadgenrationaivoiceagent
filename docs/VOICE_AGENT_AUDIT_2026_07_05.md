# Voice Agent Deep Audit — 2026-07-05

**Trigger:** user — "AI voice agent abhi bhi noob... complete fix hona".
**Method:** 7-dimension parallel code audit (brain-routing · RAG/KB · conversation-quality · latency-streaming · eval-harness · guardrails-compliance · memory-context), each agent reading the real voice-stack code. Live evidence from VPS `docker exec llm_probe`. **56 defects** found. (Adversarial-verify phase hit a token limit mid-run — high-severity defects were self-verified by reading the cited code before fixing.)

## ✅ FIXED this pass (commit `bc8654a`, deployed) — 10 defects

| # | Area | File | What was wrong → fix |
|---|---|---|---|
| 1 | **Compliance** | `llm_brain.py:58` | Rule 9 told the model "don't say you're an AI unless directly asked" (TRAI AI-disclosure violation) → rewritten to disclose honestly, never deny |
| 2 | **Compliance** | `intent_detector.py:153` | Devanagari opt-out ("बंद करो", "मत करो कॉल") never matched romanized patterns → DND/opt-out MISSED. Now `to_roman()`-normalize before match |
| 3 | KB grounding | `llm_brain.py:392` | `find_objection_responses(limit=2)` → TypeError every call (sig is `top_k`), swallowed → objection-RAG context never reached prompt. Fixed kwarg + result-key mapping (`user_message`/`agent_response`) |
| 4 | KB grounding | `telecaller_brain.py:2649` | Flat `KB_MIN_SCORE=0.35` gate discarded all keyword/TF-IDF-fallback hits (their scale ~0.04) → generic ungrounded answers. Now backend-aware (0.35 qdrant-only, else 0.05) |
| 5 | KB grounding | `telecaller_brain.py:2583` | 2 facts joined then chopped to 220 chars mid-word → vague/cut pricing answers. Now per-fact word-boundary trim, combined cap 450 |
| 6 | Conversation | `telecaller_brain.py:1491` | Discovery fast-path intercepted ≤7-word replies (real info) with canned ack + scripted question → robotic. Lowered to ≤3 (bare acks only); info-carrying turns go to LLM |
| 7 | Conversation | `telecaller_brain.py:348` | Post-close fired on ANY affirmation even mid-question ("haan par pehle price batao" → wrapped) → rude/deaf. Now skips wrap on question/price signal unless a number is present |
| 8 | Security | `telecaller_brain.py:138` | `_sanitize_utterance` blanked injection markers as bare substrings → garbled legit words ("exact assessment"→"ex[...]sessment"). Word-boundary now |
| 9 | Security | `guardrails.py:565` | `_first_match` substring match → false injection blocks on innocent turns. Word-boundary lookarounds (colon-safe) |
| 10 | Routing/cost | `free_ai.py:604` | Non-gemini-primary chain tail hardcoded paid `gemini-2.5-flash`, ignored env override → paid-model burn on free keys. Now uses overridable `gemini_model` |

Guard: `tests/test_voice_quality_fixes_2026_07_05.py` (10 tests, all green).

---

## ⏳ BACKLOG — remaining ~40 defects, prioritized (NOT yet done)

### P1 — Production-impacting (do next)

- **Prod KB is a MOCK** (`vector_store.py`): ChromaDB + sentence-transformers not in the Docker image → "using mock store"; also `vector_store.py:132` `'list' object has no attribute 'tolist'` embed bug. The *voice FACTS* path uses `knowledge_base.py` (Qdrant, which runs) — fix #4 helps that — but the **objection-RAG + ML-learning conversation store is mock in prod**. Decide: install deps in `Dockerfile.lock` OR repoint `vector_store` to the running Qdrant. *(medium-large — image change)*
- **`USE_LLM_STREAM_TTS` defaults OFF** (`llm_stream_tts.py:41`): fresh deploys run the non-stream phone path → bot waits for full LLM reply before speaking (huge time-to-first-audio). Set `USE_LLM_STREAM_TTS=1` in prod `.env` (fast, low-risk) or flip the code default after a phone smoke-test. *(small)*
- **Eval can't see the real brain** (`eval_suite.py:564`): eval only runs the rule-based fallback (`brain=None`), never the LLM brain prod uses → the exact "noob" path has zero automated coverage. Add an `EVAL_BRAIN=llm` factory. *(medium)*
- **No automated regression gate** (`agent_tester.py` never run by CI/deploy): brain/prompt changes ship unmeasured. Add a post-deploy or nightly `agent_tester.py` run wired to `eval_gate`. *(medium)*
- **Pre-existing red test** `tests/test_voice_tools.py::test_reply_with_tools_routes_tool_call` — fails on clean `main` (a "buy/close signal → confirm setup" pre-LLM path intercepts before the tool-call). NOT caused by this pass; needs its own root-cause. *(small-medium)*

### P2 — Quality / latency

- **`system=""` prompt stuffing** (`telecaller_brain.py:2746`): entire persona/rules/KB in one user message; small free models follow user-role weakly (why `_clean` has to chop transcript continuations — the code's own "noob" symptom). Split into `system=persona` + real chat turns. *(medium — core path, needs careful test)*
- **Filler synth on every turn** (`web_call.py:1469`, `fillers.py` unwired): thinking-filler live-synthesized + awaited before the LLM turn → serial network round-trip per turn. Pre-synthesize + cache. *(small-medium)*
- **STT endpoint 650ms clips Hinglish** (`vobiz_stream.py:171`): mid-sentence pauses finalize early. Raise `TURN_SILENCE_MS`~800-900 or enable text-endpoint check. *(small — env tune)*
- **vobiz LLMBrain fallback**: bypasses the whole free_ai chain (no circuit-breaker/budget), generates 300 verbose tokens, AND runs with ZERO guardrails + persists raw PII. Route through `free_ai.chat` + wrap in guards + redact transcripts. *(medium — compliance-adjacent)*
- **Streaming guards only first sentence** (`telecaller_brain.py:1882`): sentences 2+ skip PII/injection post-checks. Run cheap regex checks per sentence. *(small — compliance)*
- **History turns not sanitized** (`telecaller_brain.py:2588`): only current utterance sanitized; injection payload in an earlier turn persists in context. *(small)*
- **Transcript PII unredacted** (`vobiz_stream.py:2817`): full transcripts with raw phone/WhatsApp numbers to disk. Map user turns through `redact_for_logs`. *(small — compliance)*

### P3 — Dead / unwired modules (real value, touch call loop)

- `fillers.py` FillerPlayer — dead (no live caller)
- `agent_memory.py` session memory (`SESSION_MEMORY` flag) — 100% dead code, never called
- `CallAnalyzer` (`natural_dialog.py:906`) — write-only sink, `analyze_call` has zero callers
- Qualifier verdicts (`post_call_hooks.py:307`) — never fed back into next call's context
- `GraphRAG.aquery` (`graph_rag.py:141`) — written at onboarding, never queried during calls

### P4 — Eval harness build-out

- Hinglish STT WER harness + reference set (`voice_metrics.py:135` `score_asr` has no callers) *(large)*
- Barge-in <150ms never measured (`voice_metrics.py:27` unused constant)
- Latency metric wrong (`agent_tester.py:186` measures after 2.5s settle, not time-to-first-reply)
- Trivially-passing criteria (`eval_suite.py:238` "confused" passes if any line contains "main")
- Held-out set too small (4 golden cases, wrong niches) + binary scoring

### P5 — Config / cleanup

- `google-generativeai==0.3.2` (ancient) coexists with new `google-genai`; `_gemini_reply` mutates process-global key per call → concurrent-call key race. Port to `google-genai` client. *(medium)*
- `llm_brain` "Maya" `saas_sales_agent` persona — off from Swara/Ananya/Riya set; align or gate. *(small)*
- `to_roman` word-map gap — "नंबर हटाओ" (number hatao) still unmapped (opt-out miss). Extend `_WORD_MAP`. *(small)*
- `AMD_DETECT` defaults OFF on the paid vobiz path → bot pitches to voicemail, burns minutes. *(small — env)*

## Notes

- Every P1/P2 compliance item (PII, disclosure, guard parity) should ship as its own gated commit — voice/telephony = **High-risk tier** (money + TRAI).
- This pass fixed the highest-leverage + lowest-risk + compliance-critical defects. The heavier items (KB deps, streaming default, prompt-role split, eval build-out, dead-module wiring) each warrant their own verify+test+ship pass.
