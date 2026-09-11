---
name: prompt-engineering
description: Prompt-design discipline anchored to LeadGen's free-stack LLM chain — cheap-model-robust instructions, Hinglish output, voice ≤2-sentence ACP, structured output (Instructor), eval_gate reward. Use when writing/tuning ANY LLM prompt (telecaller_brain, niche_scripts, marketing content gen, council, free_ai), agent "noob/confused/off-format" lage, or user says "prompt better karo", "system prompt", "few-shot".
---
# Prompt Engineering (LeadGen free-stack)

Tum cheap/free models pe chal rahe (`free_ai.py` chain: Mistral-small → Groq-8b → Cerebras → Gemini-lite → …). Inko **explicit, structured, short** prompt chahiye — GPT-4-class implicit reasoning maan ke mat likho.

## Core rules (is project ke liye)
1. **Cheap-model-robust:** instruction explicit + numbered. "Be concise" ≠ enough → "Reply in MAX 2 sentences, exactly 1 question." Constraint repeat karo end me (recency).
2. **Output format pin karo:** free models format drift karte. Voice = `≤2 sentences / 1 question` (ACP, `telecaller_brain.py`). Structured data = **Instructor** (`USE_STRUCTURED_CONTENT=1`, `structured.py`) — JSON schema force, parse-retry built-in. Kabhi raw "give me JSON" pe trust mat karo.
3. **Hinglish discipline:** output language explicitly bolo ("Roman Hindi, no Devanagari") — warna model English ya Devanagari pe drift karta.
4. **Few-shot > instruction** cheap models pe: 2-3 in-context examples (KB/RAG se, `kb_main` niche namespace) >> lambi prose. Grounding = hallucination kam.
5. **System vs user split:** role/rules/format = system; variable input = user. Voice me persona+compliance (AI-disclosure greeting) system me lock.
6. **Compliance non-negotiable in prompt:** AI-disclosure-at-start, no medical/legal claims, TRAI window — yeh prompt me bake, model ki marzi pe mat chhodo.

## Anti-patterns (yahan dekhe gaye)
- **Fast-path canned line LLM ko hijack** kare (voice-brain-fluency-fix lesson) → agar template-reply LLM ko bypass kare, model "noob" lagta. LLM ko actually chalne do.
- Unbounded "explain everything" → cheap model rambles → voice me dead-air/long-turn. Hard cap.
- Single mega-prompt for multi-step → fail. Decompose (coordinator/process_engine) ya structured stages.
- Provider switch pe same prompt assume working — Groq vs Gemini format-sensitivity alag; chain-wide test.

## Tune → verify loop
1. Edit prompt (telecaller_brain / niche_scripts / marketing template).
2. Voice change → `scripts/agent_tester.py` scorecard (double/empty/repeat/long/slow). Web-call pe tune (free), phone = final verify.
3. Regression signal → **`eval_gate`** (median-baseline reward, self_improve wired) — score gire to revert.
4. Marketing/content → sample 3 outputs, format + Hinglish + claim-safety check.

## Pairs with
`voice-agent-kb` · `voice-humanization` · `hinglish-copywriting` · `llm-error-analysis` · `llm-quota-ops` (provider chain).
