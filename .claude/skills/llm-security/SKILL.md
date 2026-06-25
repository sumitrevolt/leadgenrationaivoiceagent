---
name: llm-security
description: LLM/agent attack-surface defense for LeadGen — indirect prompt injection (RAG/inbox/tool-output), jailbreaks, Information Flow Control, free red-team tooling (garak/Prompt-Guard/PyRIT). Use when touching any path where the model reads UNTRUSTED content (RAG ingest, web_extract/prospector, reply_agent inbox, voice agent, public /audit /demo /b widget, MCP-as-product) or user says "prompt injection", "jailbreak", "LLM security", "agent safe hai?". Complements traditional security-review (auth/SSRF/secrets).
---
# LLM Security — agent attack surface

Traditional `security-review` = auth/IDOR/SSRF/webhooks/secrets. **Yeh skill = LLM-specific** (OWASP **LLM01** = prompt injection, #1 app-layer threat). Source: ai-engineering-from-scratch ph18/15-16 (see [[ai-engineering-course-reference]]).

## Hamara attack surface (untrusted content model padhta hai)
| Surface | Vector | File |
|---|---|---|
| Qdrant RAG ingest | **RAG injection** — attacker doc retrieve hoke prompt me aata | `kb_*`, agentic_rag |
| Prospector web_extract / SearXNG | **tool-output injection** — scraped page me instruction | `web_extract.py`, lead_harvester |
| reply_agent IMAP | **inbox injection** — inbound email body me "forward/send X" | `reply_agent.py` |
| Voice agent + public /audit /demo /b widget AI-chat + MCP-product | **direct + indirect** | telecaller_brain, web_call, mcp |

## Dominant 2026 threat: Indirect Prompt Injection (IPI)
Attacker user ko touch kiye bina prompt-fragment control karta (web page / email / review / KB doc). Agent normal operation me use uthata + execute karta = **zero-click**. **User-input filter MISS karta** (payload user input me nahi, retrieved content me hai). Payload semantically-benign ho sakta ("please print Yes") → keyword filter bekaar.

## Defense: Information Flow Control (IFC) — 2026 paradigm
OS-security se: har content-source ko **trust label** do.
1. **Trusted** = user/customer ka direct query. **Untrusted** = retrieved KB, scraped web, inbound email, tool output, 3rd-party API.
2. **Untrusted content KABHI control-flow drive na kare** — yaani untrusted text se aaya "instruction" koi tool-call / send / DB-write / state-change trigger na kare bina trusted ratification (human ya deterministic gate).
3. Code + data ek hi context-window me hain → goal = **containment, prevention nahi**.
- **Hamare liye concrete**: reply_agent ka `REPLY_AUTO_SEND=0` + `_is_bulk_sender` guard = IFC ka ek instance (untrusted email → draft only, human ratifies send). Yahi pattern RAG/voice/MCP pe apply karo: untrusted-sourced answer se koi side-effect tool (call/send/post/pay) auto-fire NAHI — woh hamesha gated engine (process_engine breakpoint) se.

## "The Attacker Moves Second" (Nasr et al. 2025)
Adaptive attacks ne 12 published defenses (jo ~0% ASR claim karte the) ko **>90% ASR** tak toda. **Lesson:** static-attack benchmark = robustness ka proof NAHI. Defense ko adaptive/red-team eval ke saath hi ship karo.

## Free red-team stack (free-stack fit ✓)
| Tool | Kaam | Kab |
|---|---|---|
| **garak** (NVIDIA, open) | vuln scanner — injection/leak/jailbreak/toxicity probes | nightly regression CI |
| **Prompt-Guard-86M** + **Llama Guard** (Meta, open weights) | input/output classifier (86M tiny → ollama/local self-host possible) | model ke dono taraf (in+out moderation) |
| **PyRIT** (Microsoft, open) | multi-turn campaign (Crescendo/TAP) | pre-release deep test |
Default config: Llama-Guard dono side · garak nightly · PyRIT pre-release.

## Checklist (naya LLM-reading path add karne pe)
- [ ] Content-source ko trust-label kiya? untrusted = RAG/scrape/email/tool/3rd-party.
- [ ] Untrusted content se koi **side-effect tool auto-fire** to nahi? (send/call/post/pay/DB-write) → gated/draft-only karo.
- [ ] PII/secret exfil guard (untrusted output me system-prompt/keys/other-tenant data leak na ho — multi-tenant!).
- [ ] AI-disclosure + moderation (voice/public) intact.
- [ ] Regression: garak probe ya at least ek IPI test-case (`tests/`).

## Pairs with
`security-review` (traditional) · `voice-agent-kb` · `integration-engineering` (naya untrusted source) · `prompt-engineering`.
