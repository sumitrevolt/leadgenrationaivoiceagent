---
name: orchestrate-goal
description: "Mere paas ek goal hai — kaunsa automation loop?" — self-improve (daily hands-off) vs coordinator (NOW multi-agent) vs process-engine (deterministic + human gates) vs manual/chat me se sahi chuno. Use when deciding HOW to run a goal/task, ya jab confuse ho ki self-improve vs coordinator vs process-engine kaunsa fit hai.
---

# Orchestrate Goal: Which Loop?

Decision tree: "I have a goal. Which automation loop should I use?"

## Problem This Solves

You have a goal or task, but LeadGenAI has **4 ways** to execute it:

1. **Self-Improve Loop** (daily hands-off learning)
2. **Coordinator** (now-execute multi-agent goal)
3. **Process-Engine** (deterministic workflow with human gates)
4. **Chatbot/Manual** (human does it, AI assists)

You need to pick the right one or you'll be frustrated:
- Wrong loop = wasted cost or missed deadline
- Right loop = fast, cheap, trustworthy result

This skill teaches you to **match your goal to the right loop**.

---

## Quick Decision Tree

```
START: I have a goal

├─ Is it a DAILY task (repeats every day/week)?
│  └─ YES → SELF-IMPROVE LOOP
│     (prospector.scrape daily, cadence.run_due, email.send, etc.)
│
├─ Is it a NOW goal (needs doing in next 30 min)?
│  └─ YES → COORDINATOR
│     (research + strategy + draft, 1-3 min)
│
├─ Is it a WORKFLOW (multiple steps + human approval gates)?
│  └─ YES → PROCESS-ENGINE
│     (lead_campaign: harvest → score → HUMAN-APPROVE → cadence enroll)
│
└─ Does it need a HUMAN in the loop?
   └─ YES → CHATBOT or Manual work
      (sales call, customer chat, custom request)
```

---

## Comparison Table

| Aspect | Self-Improve | Coordinator | Process-Engine | Manual/Chat |
|--------|---|---|---|---|
| **Best for** | Daily tasks | Now-goals + strategy | Workflows + gates | Custom/interactive |
| **Speed** | Slow (180s) | Fast (1-3 min) | Medium (approval waits) | Real-time |
| **Cost** | High LLM-call volume (free-stack, sirf quota) | Med (5-6+ calls/run) | Low (gates, kam calls) | Human labor |
| **Automation** | Full | Partial | Full (with gates) | Human |
| **Repeatability** | Daily | On-demand | Repeatable workflow | Case-by-case |
| **Learning** | Yes (bandit) | Yes (memory) | No | No |
| **Audit trail** | Yes | Yes | Yes (event-sourced) | Manual |
| **Approval gates** | Cost cap only | Optional | Required (breakpoints) | Human decides |
| **Example** | Scrape daily | Research + draft | Lead campaign | Sales call |

---

## Rule of Thumb

**Pick loops by this priority**:

1. **Compliance-critical + repeating?** → Process-Engine (audit trail)
2. **Need NOW (< 5 min)?** → Coordinator
3. **Daily/recurring + measurable outcome?** → Self-Improve Loop
4. **Real-time conversation?** → Chatbot/Manual

---

## Enterprise gate (picking + running the loop)

Run the operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Picking a loop = **Standard tier**; but the loop you pick inherits its OWN tier — **compliance-critical or paisa-touching steps MUST route to Process-Engine** (event-sourced + enforced human breakpoints), not coordinator (LLM-opinion ≠ gate). Ambiguous "which loop / go-no-go" → council `POST /api/agents/council`, ask mat karo.

- **Draft-safe default:** coordinator goals run `execute=false` first; self-improve actions stay flag-gated default OFF + `SELFIMPROVE_COST_CAP`; no loop auto-sends/auto-posts/auto-dials (those need gated engines + DLT/DND/warmup compliance).
- **Match the gate to the loop:** Self-Improve → idempotency + DLQ `dlq:failed_tasks` + `automation_health` parity. Coordinator → bounded + draft-verify. Process-Engine → required breakpoints + audit trail (`/api/growth/process/*`). Chatbot/Manual → human owns compliance.
- **Observability:** all 4 loops audit-trail (self-improve heartbeat · coordination_runs.jsonl · process journal/events · manual notes) — visible via `/app/automation` + `/api/growth/infra/flags`.
- **Rollback (NAMED):** wrong-loop pick = re-route the goal (no code change); self-improve action flag OFF; process run resume/abort at breakpoint. No deploy in this skill.
- **Evidence (done):** the goal landed in the loop matching its tier (compliance→process, NOW→coordinator, daily→self-improve, human→manual) AND that loop's own done-criteria met. Mis-routing (e.g. cold-send via coordinator) = wrong even if it "ran".

---

## References

The per-loop deep-dives, worked scenarios, and cost/FAQ detail live in `references/` to keep this decision guide lean:

- See `references/loop-patterns.md` for the full per-loop breakdown of all 4 patterns (self-improve / coordinator / process-engine / chatbot-manual): best-for, pros, cons, cost, triggers, when-not-to-use.
- See `references/decision-scenarios.md` for 5 concrete worked scenarios mapping a goal to the right loop, with setup commands.
- See `references/cost-and-faq.md` for the daily cost summary across all loops and the FAQ.

## Related Skills

- **coordinator-orchestration**: Deep dive into coordinator modes (sequential, parallel, hierarchical, advanced)
- **self-improve-control**: Monitor and audit the self-improve loop
- **automation-control-center**: See all 4 loops in one dashboard
- **agent-loop-design**: Design custom loops
