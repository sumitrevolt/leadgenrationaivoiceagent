# CUA (Computer-Use Agent) — PM Analysis

**Owner:** Alice (Product Manager) · **For:** Team Lead → Architect
**Date:** 2026-09-16 · **Status:** Final for routing
**Method note:** Written from professional domain grounding; no live web research was performed for this pass. All benchmark figures that are vendor-reported or from memory are explicitly labeled *(approx / verify)*. The Architect should treat marked numbers as directional, not contract values.

---

## 1. Executive Summary

Computer-use agents (CUA) — LLM-driven systems that control a desktop GUI by looking at screenshots and issuing clicks/keystrokes — moved from research demo to production capability in 2025. Two frontier labs now ship first-party offerings (Anthropic "computer use" tool on Claude; OpenAI CUA-1 model powering the ChatGPT agent / Operator). Meanwhile a thick open-source layer (Browser Use, Skyvern, UI-TARS, CogAgent, OSWorld/WindowsAgentArena benchmarks, sandbox harnesses) now covers most of the plumbing, which means **building a capable CUA stack is an integration + evaluation problem, not a model problem**.

Key conclusions:

- **Don't chase state-of-the-art autonomy.** The differentiating product value is *reliable, safe, auditable automation of desktop workflows that lack APIs* — with human-approval gates and full replay.
- **API-first, GUI-fallback.** Use MCP/REST/browser-DOM access wherever an app exposes it; reserve pixel-level computer use for the long tail (legacy desktop apps, ERP screens, no-API SaaS UI).
- **Evaluation is the moat.** A regression suite of replayable GUI tasks (built on WindowsAgentArena/OSWorld-style methodology, adapted to our target apps) matters more than any single benchmark score.
- **Security and ToS risk are the top non-technical blockers**: prompt-injection via screen content, credential handling, and automating third-party app UIs against their terms of service.
- **Recommended composition:** planner agent loop + vision-grounded model (or our existing LLM stack) + Windows sandbox VM + UIA/CDP input layer + allowlist/confirmation guardrails + trace-and-replay observability. See §5.

---

## 2. Claude vs ChatGPT: Computer-Use Gap Analysis

### 2.1 What each lab ships (as of this writing)

| Dimension | Anthropic "Computer Use" (Claude) | OpenAI CUA (CUA-1 model, ChatGPT agent / ex-Operator) |
|---|---|---|
| Interface shape | A **tool** (`computer`) inside the model API: screenshot in → `click / double_click / type / key / scroll / mouse_move / wait / screenshot / done` out. Developer owns the execution environment (VM). | **Purpose-trained model** (CUA-1 preview) exposed inside ChatGPT agent and via API (AgentKit-style). OpenAI owns more of the loop + environment in consumer product. |
| Execution env | You provide one (their reference demo: Docker/VM + xdotool/pyautogui + screenshot capture). macOS-focused reference; port to Windows yourself. | Consumer: OpenAI-hosted cloud VM. API/AgentKit: hosted environment you configure. |
| Vision input | Screenshot-based (base64 PNG/JP into the model). | Screenshot + some UI-structure context (web-app mode uses structured element data, not just pixels). |
| Agent loop control | Model emits tool calls; **your** harness decides step budget, retries, approval gates. | OpenAI harness manages the loop; consumer product has built-in confirmation prompts for sensitive actions. |
| Ecosystem fit | Works with any Anthropic-model backend; pairs well with MCP tool layer. | Locked to OpenAI models; pairs with AgentKit + hosted env. |

### 2.2 Benchmark standing (directional)

| Benchmark | What it measures | Claude (4.x family) | OpenAI (CUA-1) | Note |
|---|---|---|---|---|
| OSWorld (full, 369 tasks, Windows/macOS/Linux desktop) | End-to-end real desktop tasks | ~30–60% *(approx / verify)* | ~38% (OpenAI-reported) | Human baseline ≈ 72% on OSWorld-Verified *(approx / verify)* |
| OSWorld-Verified | Curated verifiable subset | ~61% (Anthropic-reported) *(approx / verify)* | ~61% (OpenAI-reported) *(approx / verify)* | **Vendor-curated subsets inflate both scores; treat as marketing-grade** |
| GAIA (assistant-style, web-centric) | Web + file tasks | ~62% *(approx / verify)* | ~47% *(approx / verify)* | Claude generally leads on web-assistant tasks |
| Terminal-Bench | CLI/terminal tasks | low-30s% *(approx / verify)* | ~22% (OpenAI-reported) | Both weak; terminal work still API/script-friendly |
| SWE-bench Verified | Coding | ~70%+ (Anthropic-reported) | ~59% (OpenAI-reported) *(approx / verify)* | Not a CUA benchmark; included because vendor marketing blurs the two |

**Takeaway for us:** the gap between the two frontier offerings is *architectural, not purely accuracy* — Anthropic gives you a tool and makes you build the harness (more control, more work, Windows-porting burden); OpenAI gives you a more integrated product but with model/platform lock-in. For a company that already runs a multi-model LLM gateway (OmniRoute-style), the **Anthropic-style tool contract is the more portable abstraction** — we can run the same harness against Claude, GPT, or local open-weights VLMs.

---

## 3. Open-Source Landscape Map

| Project | Type | License | Platform / Tech | What it gives us | Watch-out |
|---|---|---|---|---|---|
| **Browser Use** (browser-use) | Agent (browser) | MIT *(verify)* | Python, Playwright/CDP | Best-in-class open browser agent; element-aware, not pixel-only | Core is open; enterprise features proprietary |
| **Skyvern** | Agent (browser, LLM+vision) | AGPL-ish *(verify)* | Python + vision LLM | Strong no-code-style web automation | AGPL may constrain embedding in a commercial product — legal review |
| **UI-TARS / UI-TARS-1.5** (ByteDance) | Open-weights VLM + agent | Apache-2.0 *(verify)* | GUI grounding model, Windows agent demos | Self-hostable GUI pointing/grounding; reduces cloud cost | Chinese org; fine-tuning data quality varies |
| **CogAgent / CogVLM4** (THUDM) | Open-weights VLM | Apache-2.0 *(verify)* | GUI-specialized vision | Strong GUI understanding at open-weight quality | Token-heavy (tiled screenshots) → latency/cost |
| **Qwen2.5-VL / GUI fine-tunes** | Open-weights VLM | Apache-2.0 *(verify)* | Multi-resolution, good pointing | Flexible grounding model; big community | Verify current version's license tag |
| **Sakana DROID** | Open-weights VLM | Apache-2.0 *(verify)* | General GUI/OCR/vision model | Strong OCR+grounding; research-grade agent demo | Experimental |
| **Open Interpreter** | Agent (code-exec) | MIT | Python | Runs LLM code that drives the OS; fast to demo | Low reliability; no sandbox by default |
| **Anthropic computer-use-demo** | Reference harness | Apache-2.0 *(verify)* | Docker + xdotool + screenshot | The canonical loop: screenshot → tool call → execute → loop | Linux/X11 reference; Windows port is on us |
| **OS-World** (xlang.ai) | Benchmark + data | CC-BY-NC *(verify)* | Windows/macOS/Linux desktop tasks | Task schema to model our own regression suite on | **NC license — cannot ship their data in a commercial product; use as methodology only** |
| **WindowsAgentArena** | Benchmark | MIT *(verify)* | Windows desktop tasks, replay infra | Windows-specific task suite + determinism methodology | Young project; task count still small |
| **WebArena / WebVoyager / Mind2Web** | Benchmarks (web) | mostly MIT/CC-BY | Web environments | Web-task regression patterns | Web-only; not desktop |
| **Cradle** (Foundation Agents) | Agent (computer use) | Apache-2.0 *(verify)* | General-purpose CUA harness | Alternative loop design to compare against | Low adoption |
| **MCP (Model Context Protocol) servers** | Integration layer | Various | Standard tool protocol | **Preferred primary action layer** — apps that expose MCP/REST are never touched by pixels | Quality of server coverage per app varies |

**Read of the landscape:** models and agents are a *commodity tier* (buy/self-host); the scarce assets are (a) **deterministic replay & regression infra**, (b) **Windows input abstraction** (UIA-based, not just xdotool), and (c) **guardrail/audit layers**. Those three are where our engineering effort should go.

---

## 4. Technical Gap Analysis

Gaps between "demo computer use" and "production CUA we can sell/operate," ranked by severity:

| # | Gap | What's missing | Impact if unaddressed |
|---|---|---|---|
| 1 | **Long-horizon reliability** | No error-recovery loop; small UI drift → cascading failure. State-of-art agents fail most multi-step tasks. | Useless on real workflows; trust loss fast. |
| 2 | **Grounding on dynamic UIs** | Pixel-only grounding breaks on scrolling, lazy-render, DPI scaling, pop-ups. DOM/accessibility-tree fusion is immature in open source. | Silent misclicks → wrong data entry. |
| 3 | **Windows input layer** | Most OSS references target Linux/X11 or macOS. UI Automation (UIA) + SendInput + DPI-awareness work is unglamorous and missing. | Our target apps are largely Windows desktop; #2 of our own build items. |
| 4 | **Security / sandboxing** | No default least-privilege environment; prompt-injection via on-screen text can steer the agent; credentials in screenshots. | Data exfiltration / ransomware-class incident; blocking enterprise adoption. |
| 5 | **Approval & rollback** | No standard "pause for human confirm on irreversible action" or undo layer. | Cannot meet ops teams' risk threshold. |
| 6 | **Observability & replay** | Traces ad-hoc; no deterministic task replay for regression (WindowsAgentArena proves the method, but we need our own task set). | No CI for agent behavior; regressions ship blind. |
| 7 | **Cost/latency per step** | Cloud VLM: ~1 screenshot + full context per step → $ and seconds per action; 20-step task multiplies this. | Throughput and margin limits for high-volume automation. |
| 8 | **App-to-app handoff** | Cross-application workflows (ERP → email → sheet) need window management, focus tracking, clipboard hygiene. | Fragmentation; each app is a separate fragile script. |
| 9 | **ToS/authorization** | Automating third-party UIs may breach their ToS; account-level risk. | Legal exposure; see §6. |

**The single most important architectural decision** (for the Architect): **hybrid action layer** — structured access (MCP tools / app APIs / browser CDP / UIA element selectors) first, pixel-computer-use as the *fallback* and for apps with no structure at all. This converts most steps from "VLM reasoning at $X/step" to cheap deterministic calls, and directly attacks gaps #1, #2, #7.

---

## 5. Recommended Building Blocks & Composition

### 5.1 Blocks

| Block | Purpose | Candidate (build vs buy) |
|---|---|---|
| **Planner / agent loop** | Task decomposition, step budget, retry-on-failure, goal-check | Build thin loop; model-agnostic (run via our OmniRoute-style gateway). Reference: Anthropic computer-use loop. |
| **Perception** | Screenshot + accessibility tree (UIA on Windows) + optional OCR merge | Build thin capture service; feed fused "screen state" to model (screenshot + compact UIA JSON). |
| **Grounding model** | Map intent → target element | Hybrid: DOM/CDP for browser, UIA selectors for desktop apps, VLM pointing only for the rest. Model choice open: Claude/GPT (cloud) vs UI-TARS/Qwen-VL (self-host, cheaper at volume) — **open question OQ-1**. |
| **Execution sandbox** | Isolated, disposable VM per task run; no production data on the host | Buy/ops: cloud VM (Windows) or local VM (Hyper-V/VMware) + snapshot/restore. |
| **Input layer** | Click/type/scroll/kbd | Build: Windows UI Automation + SendInput wrapper, DPI-aware; CDP for browsers. |
| **Guardrails** | Action allowlist (apps, selectors, URL patterns), irreversible-action confirmation gate, screen-content sanitization for prompt injection, per-task credentials vault | Build (this is differentiating; no off-the-shelf OSS does it well). |
| **Observability & replay** | Per-step trace: screenshot, action JSON, model output, cost; deterministic replay runner; task-level success oracle | Build on WindowsAgentArena methodology; task suite authored per target app. |
| **Evaluation suite** | Regression harness | ~50–150 replayable tasks across our top 5–10 target apps as v1. |

### 5.2 Composition (target architecture)

```mermaid
flowchart LR
  subgraph Client["Ops console / API"]
    T[Task request + app context]
    A[Human approval gate]
  end
  subgraph Core["CUA Core (our build)"]
    P[Planner / agent loop]
    G[Guardrails: allowlist,\ncreds vault, sanitize]
    L[Action router:\nMCP/API → UIA → CDP → pixel-VLM]
    O[Trace + replay logger]
  end
  subgraph Env["Sandboxed Windows VM (disposable)"]
    CAP[Screen capture + UIA tree]
    INP[SendInput / UIA / CDP drivers]
  end
  LLM[LLM/VLM gateway\nClaude | GPT | self-hosted open weights]
  T --> P
  P <--> L
  L <--> CAP
  L <--> INP
  P <--> LLM
  G -. intercept .-> L
  INP -. events .-> O
  P -. approvals .-> A
  O --> R[Regression / eval runner]
```

**Phase plan (for the Architect to size):**
- **P0 (MVP):** one target app, UIA-first + pixel fallback, sandbox VM, trace log, manual approval on all irreversible actions, 10-task replay suite.
- **P1:** 3–5 apps, guardrail allowlists, credential vault, cost/latency dashboard, 50-task regression in CI.
- **P2:** self-hosted grounding model for volume tasks, cross-app workflow chaining, per-tenant task marketplace.

---

## 6. Risks, Licensing & Open Questions

### 6.1 Risks (top 8)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Prompt injection via on-screen text steering agent to exfiltrate data | High | Critical | Screen-content sandboxing, egress controls in VM, allowlisted actions only |
| Long-horizon task failure rate too high for ops trust | High | High | Hybrid structured action layer (kill most VLM steps), step budgets, goal-oracle checks |
| UIA/Windows input work underestimated | Med-High | High | Spike early (Architect task), UIA coverage audit per target app |
| Benchmark marketing (vendor-curated "Verified" subsets) misleads scoping | High | Med | Re-benchmark on our own task suite; discount vendor numbers |
| Third-party app ToS violation via UI automation | Med | High | Legal review per app; prefer API/MCP where offered; customer-bears-risk clause |
| Agentic cost runaway (VLM $/task) | High | Med | Structured-first routing; self-host open weights at volume; per-task cost cap + kill switch |
| Credential handling in screenshots/traces | Med | Critical | Secret masking in capture pipeline, trace redaction, VM isolation, no prod data on trace store |
| Vendor lock-in on CUA-1/Claude tooling | Low-Med | Med | Model-agnostic loop via our gateway; tool contract mirrors Anthropic `computer` schema |

### 6.2 Licensing (verify before code drops)

- **OS-World dataset:** CC-BY-NC class license *(verify)* → **methodology only; never ship their tasks/data in our product.**
- **Skyvern:** AGPL-family *(verify)* → embedding in a commercial product needs legal sign-off or a commercial license; **prefer Browser Use (MIT) or build our own loop** to avoid AGPL contagion.
- **Open-weights VLMs (UI-TARS, CogAgent, Qwen-VL, DROID):** Apache-2.0 family *(verify per release)* → self-hosting is generally clean; watch for modified-LLM clauses and per-model card conditions.
- **Everything we build (loop, UIA drivers, guardrails, eval infra):** keep Apache-2.0/MIT-internal clean; no GPL components in the core path.

### 6.3 Open Questions (need owner answers)

| ID | Question | Suggested owner |
|---|---|---|
| OQ-1 | Cloud VLM vs self-hosted open-weights grounding at volume — cost break-even point? | Architect + Finance |
| OQ-2 | Target OS is Windows-first, or must macOS/Linux sandbox runtimes be P1? | Product + Ops |
| OQ-3 | Human-approval UX: inline console prompts vs async approval queue vs time-boxed autonomy windows? | Product (me) |
| OQ-4 | Which 5–10 target apps define the v1 regression suite? (needs ops input on highest-value no-API workflows) | Ops / customers |
| OQ-5 | Legal posture on ToS-violating automation of third-party apps — what's the company line? | Legal |
| OQ-6 | Do we accept per-tenant VM (strong isolation, $$$) or shared-VM pool with profiles (cheaper, weaker isolation)? | Architect |
| OQ-7 | Benchmark targets: what pass-rate on our own suite is "good enough" to sell (suggested bar: ≥80% task success, ≤2 human interventions/task)? | Product + Sales |

---

*End of 01-pm-analysis.md — route to Architect with §4 (gap ranking) and §5 (composition + phases) as the primary handoff inputs; OQ-1/OQ-6 are the two decisions that shape the architecture.*
