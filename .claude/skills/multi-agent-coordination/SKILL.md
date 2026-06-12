---
name: multi-agent-coordination
description: Coordinator modes (plan/handoff, Reflexion, hierarchical, fanout, debate) vs process-engine vs FDE vs sales_team — kaunsa kab use karo, naya agent/tool/team kaise add karo. Use when assigning multi-agent goals, extending the roster, or choosing the right orchestration primitive.
---

# Multi-Agent Coordination — sahi primitive chuno

> Engines: `app/agents/coordinator.py` (free-stack, always-on) · `process_engine.py` (deterministic) · `fde.py` (client deploy) · `sales_team.py` (prospect deep-dive) · `staff_supervisor.py` (langgraph, gated). UI: `/app/agents` + `/app/automation` Agents tab.

## Decision matrix (pehla sawaal: output kya hai?)
| Zaroorat | Use karo | API |
|---|---|---|
| Ek goal, ordered sub-tasks, drafts | `coordinate(goal)` — planner + sequential handoff (blackboard) | `POST /api/agents/coordinate` |
| Quality bar + retry chahiye | `coordinate_advanced` — Reflexion loop + Arjun-critic + episodic memory (max 3 iters, early-stop) | `POST /coordinate-advanced` |
| Bade goal me ALAG teams parallel | `coordinate_hierarchical` — Boss → sub-teams (growth/ops/sales) gather | `POST /coordinate-hierarchical` |
| Same prompt, sab agents ka take | `fanout` (asyncio.gather) | `POST /agents/fanout` |
| Pro/con faisla | `debate(question)` — Rohan vs Kavya → Boss verdict | `POST /agents/debate` |
| **Order + code-gates + human approval** | process engine (journal, breakpoints, resume) — LLM-opinion gates NAHI | `POST /api/growth/process/start` |
| Client ke liye stack deploy | FDE (Isha/Veer/Aarav/Neo, 11 skills registry) | `POST /api/growth/fde/deploy` |
| Ek prospect ka sales deep-dive | sales_team (Riya/Veer/Dev/Isha/Arjun parallel, BANT) | `POST /api/growth/sales/prospect-analysis` |

Rule of thumb: **ban-risky ya paisa-touching step = process engine** (enforced breakpoint); **creative/strategy = coordinator**; dono ko mila ke (coordinator idea → process execute) bhi chalta hai.

## Execute-mode safety (DEFAULT drafts)
- `execute=False` default = sab DRAFTS, zero side-effect. `execute=True` pe bhi sirf `_TOOLS` registry agents real kaam karte hain (isha→post_generator, dev→hashtags, kavya→run_ops, arjun→run_qa, meera→run_trainer).
- **rohan (email) / swara (calls) jaan-bujhke _TOOLS se BAHAR** — side-effect agents draft-only; send/call sirf gated engines (auto_outreach caps, call queue compliance) se.
- Naya tool add: `_TOOLS[agent] = fn(task, goal)` — bounded, never-raise, draft-first; roster `executable` flag auto.

## Naya agent/team add
1. `team.py` STAFF me member (+`product` field: marketing/voice/platform) — events /app/team pe dikhenge.
2. Coordinator persona: `coordinator.py` agent map me 1-line persona; heavy = mat banao, existing reuse.
3. Hierarchical team: `_TEAMS` dict me member add ya naya team (Boss `_assign_teams` LLM-pick karta hai).
4. Monitor duty dena ho to `team_pulse()` rotation me cheap no-LLM check add karo.

## Memory + tracing
- Episodic: `data/agent_memory.jsonl` (reflections, `_recall` keyword-overlap next-run inject) · runs: `coordination_runs.jsonl` · events: agent_events table → `/app/team` + Events tab.
- Skills: agents runtime pe `skill_pack.find/snippet_for` se .claude/skills + `data/skills_extra` padhte hain (SKILL_PACK=1) — naya skill image-rebuild ke baad container me dikhta hai (Dockerfile COPY).

## Anti-patterns (in galtiyon se seekha)
- LLM-opinion ko gate mat banao — deterministic code-gates (min_count etc.) hi process advance karein.
- Coordinator se direct send/post karwana — KABHI nahi, ban-risk.
- Har feature pe naya orchestrator — pehle yeh matrix, fir extend, last resort naya.
- Critic ko same persona me grade mat karwao — alag persona (Arjun) JSON grade, parse-fail = 0.6 neutral (infinite loop nahi).
- CLAUDE.md rule: heavy sub-agents kam — orchestration VPS engines me hai, Claude-session me sirf jab disjoint-files batch ho (`parallel-batch-build`).
