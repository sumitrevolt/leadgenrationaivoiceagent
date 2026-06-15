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
| **Cost/day** | $20-50 | $10-40 (varies) | $5-20 | Human labor |
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
