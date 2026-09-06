# OPS-013 — Is the LeadGen WhatsApp AI agent "general-purpose"? (scope verdict)

**Date:** 2026-09-07 (cycle 7, 05:15 IST) · **Status:** verdict = **TASK-SCOPED (compliant by construction)** with **one drift vector** — one env var away
**Authority:** local inspection + web research only. No deploy, no SSH, no behaviour change beyond an added warning.

---

## 1. Why this matters

Meta changed the WhatsApp Business API terms to bar **general-purpose AI chatbots** (TechCrunch, 2025-10-18); India-focused 2026 guidance reports it effective **2026-01-15**, and stresses that task-scoped bots (support, bookings, orders) remain allowed ("Not all chatbots are banned", respond.io).

LeadGen sells an **AI WhatsApp agent**. If it behaves as an open-ended assistant, the number risks a platform ban — which would take down the very rail OPS-010/ENG-004 are trying to fix.

## 2. Verdict

> **TASK-SCOPED.** The agent is a fixed-vocabulary classifier plus a bounded sales-reply drafter. It does not hold open-ended conversations **by default**.
> **However**, `WHATSAPP_AI_AUTOREPLY=1` silently widens its scope to open-ended replies — the only drift vector found.

## 3. Evidence

| # | Check | Finding | Evidence |
|---|---|---|---|
| 1 | Is the reply open-ended or label-bounded? | **Bounded.** Intent must be exactly one of 7 fixed labels: `interested`, `question`, `objection`, `not_interested`, `unsubscribe`, `ooo`, `other` | `app/platform/reply_agent.py:689-712` — *"SIRF ek label reply karo, kuch aur nahi."* |
| 2 | Can the classifier ramble? | **No.** `max_tokens=8`, `temperature=0.0` — it emits a label, not prose | `app/platform/reply_agent.py:725-729` |
| 3 | Is the draft role-constrained? | **Yes.** *"Tu LeadGen AI ka helpful sales rep hai… Free Google audit + demo offer kar; pushy mat ban… Sirf reply text de."* `max_tokens=160` | `app/platform/reply_agent.py:866-873` |
| 4 | Which intents get a draft? | `interested`, `question`, `objection` — **plus `other` only when auto-reply is ON** | `app/platform/reply_agent.py:1645` `_draft_intents = ("interested","question","objection") + (("other",) if _auto else ())` |
| 5 | Does it cold-message people? | **No.** It only reacts to **inbound** 1:1 messages; bulk cold send is a separate, still-gated path (`WHATSAPP_AUTO_SEND`) | `app/platform/reply_agent.py:1596-1600`, `app/integrations/whatsapp.py::send_permitted` |
| 6 | Is auto-reply on by default? | **No — OFF.** `WHATSAPP_AI_AUTOREPLY` unset ⇒ `_auto = False` | `app/platform/reply_agent.py:1639-1644` |
| 7 | Is the flag documented / set anywhere? | **Nowhere.** Only 3 references in the whole repo, all inside `reply_agent.py`. Absent from `.env.example`, `config/`, `deploy/`, `docker-compose.vps.yml` | `grep -rn WHATSAPP_AI_AUTOREPLY` |
| 8 | Noise guards | Status/broadcast senders + blocklist + spam-content dropped before classification | `app/platform/reply_agent.py:1608-1616` |

**Interpretation:** checks 1–3 and 5–6 are exactly what Meta permits (a narrowly scoped business assistant reacting to customer-initiated threads). Check 4 is the exposure: with the flag ON, an open-ended inbound message is answered by an LLM with **conversation history** — that is the shape the policy targets.

## 4. What was changed (additive only, zero behaviour change)

1. `app/platform/reply_agent.py` — new `autoreply_policy_warning(enabled)`: when the flag is on, every inbound handling logs a loud, quotable warning naming the policy and the risk. Returns the message (empty when off) so it is testable with no network/file side effects.
2. `.env.example` — the flag is now documented as **default OFF** with the policy context, so nobody arms it "to see what happens".
3. `tests/test_ops013_autoreply_policy_warning.py` — 4 tests pinning the warning.

## 5. Owner actions (in priority order)

| # | Action | Why | Cost |
|---|---|---|---|
| **A1** | **Verify the VPS does not have it set:** `grep WHATSAPP_AI_AUTOREPLY /opt/leadgen/.env` — expect no match / `=0` | The flag is undocumented, so it would never show up in a config review. This is the single highest-value 10-second check in this document | 10 s |
| **A2** | Keep it OFF until the agent's scope is written down and reviewed | Cheapest possible risk removal | 0 |
| **A3** | Decide on the narrowing (OPS-016): when auto-reply is ON, still **exclude `other`** from `_draft_intents` | Removes the general-purpose exposure entirely while keeping `interested/question/objection` auto-replies | ~1 line, needs owner sign-off (changes behaviour) |

## 6. Honest limits

- The verdict is based on **code inspection**, not on a review of real transcripts. A task-scoped prompt can still produce an off-scope reply; the guardrail is the 160-token cap and the fixed intent set, not a hard guarantee.
- Sources for the policy are secondary (TechCrunch, 2Factor 2026 India guide, respond.io), not the Meta policy document itself. Before A3 or any decision to run auto-reply in production, read Meta's current Business Messaging Policy directly.
- Everything here is **local-only and undeployed**.
