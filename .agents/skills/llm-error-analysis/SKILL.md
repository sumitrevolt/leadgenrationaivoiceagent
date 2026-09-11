---
name: llm-error-analysis
description: LLM/voice-agent quality girne pe systematic error analysis — traces padho (open-coding) → failure taxonomy banao → frequency se fix prioritize karo, project stores (llm_calls.jsonl, call_qualifications, agent_events) ke upar. Use when user says "agent galat bol raha", "quality kharab", "LLM output weird", "evals", "judge calibrate", ya prompt/model/provider switch ke baad.
---

# LLM Error Analysis (traces → taxonomy → fix priority)

**Rule: failure categories PEHLE se brainstorm mat karo — traces padho, categories EMERGE hone do.** Pre-defined list = confirmation bias. Generic scores ("hallucination score") = useless; app-specific failure modes chahiye.

## Project trace stores (yahan se sample karo)
| Store | Kya hai | Kab dekho |
|---|---|---|
| `data/llm_calls.jsonl` + `GET /api/growth/infra/llm` | per-provider calls/ok-rate/latency/last-error (llm_metrics) | provider-level failures, fallback-rate spike |
| `data/call_qualifications.jsonl` | post-call qualifier output (interest/summary/next_action) | voice-call quality, galat qualification |
| `agent_events` table + `/app/team` | har staff-job ka run log | scheduler/agent task failures |
| `scripts/agent_tester.py` | FREE voice scorecard (double/empty/repeat/long/slow) | voice change ke BAAD hamesha |
| `data/coordination_runs.jsonl` + `data/agent_memory.jsonl` | coordinator runs + Arjun critic scores + reflections | multi-agent plan quality |

## Process (open-coding → taxonomy → priority)
1. **Sample ~30-100 traces** — random + outliers (longest/slowest/most-fallback) + complaint-driven. Voice ke liye web-call transcripts (FREE tuning path, phone paisa khaata hai).
2. **Har trace: Pass/Fail + 1-line note** — *observation* likho, explanation nahi ("budget constraint ignore hua" ✓, "model samjha nahi hoga" ✗). **FIRST failure note karo** — errors cascade karte hain, root fix se downstream symptoms gayab.
3. **Group into 5-10 categories** (30-50 traces ke baad shuru) — same root cause = group ("Hinglish me English-only reply" + "Hindi me reply" → *Language drift*), alag root cause = split (fact fabricate vs intent fabricate). Naam specific + actionable.
4. **Label all + failure rates** — sabse frequent category = pehla fix. Simple counts kaafi hain (jsonl → python one-liner).
5. **Har category: "kya bas FIX kar sakte?"** — zyada failures ko evaluator nahi, seedha fix chahiye: prompt me instruction missing → add karo; tool/KB missing → wire karo; parse bug → code fix. Evaluator SIRF un failures ke liye jo fix ke baad bhi persist karein aur jin pe iterate karoge.
6. **Re-run after every big change** — prompt rewrite, provider switch (Cerebras↔Groq), niche-script change, model upgrade. One-time activity nahi.

## Arjun MAR-critic calibration (coordinator judge)
Arjun (`coordinator.py` critic) = LLM-as-judge — usko bhi calibrate karo:
- **Binary-ish + specific**: vague 0-1 score akela nahi — `{score, weak, fixes}` me `weak` concrete ho ("sirf 12 leads, goal 15 tha" jaisa — yehi uska best catch tha). Criterion EK failure mode per judge.
- **Pass/Fail definitions + 2-3 few-shot examples** prompt me do (ek clear pass, ek clear fail, ek borderline) — error-analysis ki categories se hi nikalo.
- **Calibrate against khud ke labels**: 10-20 runs ko khud grade karo, Arjun se compare — disagreement >20% = judge prompt fix, quality_bar nahi.
- Parse-fail = 0.6 neutral (no infinite loop) — ye fail-safe rakho; aur jo cheez CODE se check ho sakti hai (count, JSON shape, required keys) wo judge se mat poochho, deterministic gate lagao (process_engine pattern).

Voice changes ke baad scorecard mandatory: `python scripts/agent_tester.py`. Fix nikla = failing test + `tdd-contract-first`.

## Enterprise gate (error analysis → fix → proof)

- **Operating loop:** Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Discover = traces sample (open-coding, categories EMERGE hone do); Contract = top-frequency category + fix + jo test cover karega.
- **Change-risk tier:** taxonomy/analysis = **Trivial** (read-only). Lekin fix jo prompt/model/provider switch karta = **High-risk** (har LLM path affect) → re-run analysis + scorecard.
- **Fail-safe + reliability gates:**
  - **Fallback-aware** — fallback-rate spike ko quality-fail mat samjho jab tak provider chain itself healthy hai; provider-switch fix ke baad confirm karo agla provider quality bhi acceptable hai (cross-check `llm-quota-ops` `/api/growth/infra/llm`).
  - **Deterministic-gate first** — jo CODE se check ho sakta (count, JSON shape, required keys) = deterministic gate (process_engine pattern), LLM-judge se mat poochho. Parse-fail = 0.6 neutral (no infinite loop) fail-safe rakho.
  - **Free-stack** — judge/eval ke liye bhi koi paid LLM nahi; eval/test-bursts production-hours me mat chalao agar quota tight (voice paisa khaata).
- **Observability:** trace stores = `data/llm_calls.jsonl` (+`/api/growth/infra/llm`), `data/call_qualifications.jsonl`, `agent_events`+`/app/team`, `data/coordination_runs.jsonl`. Fix ke baad inhi me delta dikhna chahiye.
- **Evidence to close:** failure-rate table (before) + fix ke baad **re-run** (rates ghate) + voice-touch = `python scripts\agent_tester.py` scorecard + failing→passing test. One-time analysis "done" NAHI — har bड़े change pe re-run.

Adapted from hamelsmu/evals-skills `error-analysis` + `write-judge-prompt` (original hamelsmu/prompts URL 404 — repo moved) (via VoltAgent/awesome-agent-skills).
