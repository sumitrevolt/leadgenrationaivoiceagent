# OPS-026 — the OPS-024 bug class found in rate-limit tier resolution (deliberately NOT changed)

**Date:** 2026-09-07 (cycle 13, 07:45 IST) · **Severity:** P3 latent (not active) · **Status:** REPORTED + PINNED, behaviour unchanged
**Authority:** local inspection + local tests only. No deploy, no SSH, no remote state change.

---

## 1. Why this document exists

OPS-024 (cycle 12) was a **substring match over an ordered constant**: `_classify` did
`for c in _CATS: if c in lab`, and because `"not_interested"` contains `"interested"`,
every rejection became a hot lead. It was found by accident.

Cycle 13 swept `app/` for the same shape — *"the first entry of a constant that appears
inside the input wins"* — to find out whether it was a one-off or a pattern.

**Result: one more instance, in `app/api/ratelimit.py`.** Two further matches are
low-stakes and listed in §5.

## 2. The instance

`app/api/ratelimit.py::_client_tier` (line 117) decides the request budget for the entire
`/ai` router — `app/api/ai.py:19` mounts `tier_rate_limit("ai", 30, 60)` at router level,
so it gates every AI endpoint:

```python
_TIER_MULT = {"free":1.0, "trial":1.0, "starter":2.0, "growth":4.0,
              "advanced":8.0, "voice":8.0, "admin":20.0}

for key in _TIER_MULT:      # substring test, dict insertion order
    if key in t:
        return key
return "free"
```

## 3. Assessment: latent, NOT an active defect

| Check | Finding |
|---|---|
| Can a caller set the value? | **No.** The client-supplied `X-Client-Tier` header was removed 2026-07-01 (self-report spoofing); the tier now comes from server-derived `request.state.tenant`. No remote exploit path. |
| Does any real plan string collide? | **No.** The vocabulary is `free / trial / starter / growth / advanced / voice / admin` (`customer_auth._VALID_PLANS`, `customer_onboard._MKT_PLANS`, `billing/usage.PLAN_MINUTES`). None contains another, so **substring == exact today**. |
| Is any tier key a substring of another? | **No** — pinned by test. |
| Fail-safe direction | Correct. Unknown / missing / broken tenant ⇒ `"free"` (smallest budget). |

**The latent risk:** the moment a plan string is introduced that merely *contains* a
high-budget key — `"super_admin"`, `"admin_lite"`, `"voice_admin"` — it silently inherits
the 20x budget, and `"voice_starter"`-style strings are decided by dict insertion order.
That is a cost/abuse-control surprise, not a data or compliance breach.

## 4. Council decision: DO NOT fix it unattended

Recorded as decision **D14**. The tempting one-line fix (match exactly) is a **net
negative**:

| Change | Effect |
|---|---|
| Exact match only | A plan like `"voice_4999"` drops from 8x to 1x → paying voice customers get **8x more 429s**. Revenue-visible harm. |
| Longest match wins | Makes it *worse*: `"free_admin"` would match `"admin"` (5 chars) over `"free"` (4) → 20x. |
| Lowest multiplier wins | Behaviour-identical to today for every realistic string, so it is a no-op refactor. |

There is no change that removes the latent risk without risking a real throttling
regression. **Rate limiting is an availability and AI-cost control, not a compliance
gate, and its default is already safe.** This needs the owner's plan-vocabulary decision,
not an unattended edit.

**What was shipped instead** — `tests/test_ops026_rate_tier_resolution.py` (19 tests),
which converts the latent risk into a loud failure at the moment it becomes real:

1. every real plan string still resolves to itself;
2. **no tier key is a substring of another** (the OPS-024 class invariant);
3. resolution is unchanged under **reversed** `_TIER_MULT` order;
4. the real plan vocabulary is collision-free;
5. unknown / empty / non-dict / missing tenant state still ⇒ `"free"`;
6. a **tripwire** asserting the current over-grant (`"not_admin" ⇒ "admin"`) so that
   fixing OPS-026 later is a visible, deliberate event rather than a silent drift.

## 5. The rest of the sweep (low-stakes, no action taken)

| Location | Shape | Assessment |
|---|---|---|
| `app/ml/codebase_indexer.py:344` | `if pattern_clean in file_path_lower: return role` over `AGENT_KNOWLEDGE_MAP` file patterns | Indexing-only; a wrong role affects a code-search label. First-match-wins is intended here. |
| `app/niche_knowledge.py:236-239` | `for key in niche_obj: if key.replace("_"," ") in low: return niche_obj[key]` | Objection → rebuttal lookup. Dict order decides which rebuttal wins when two objection keys overlap. Copy quality, not money or compliance. Worth a look if rebuttals ever look wrong. |
| `app/voice_agent/guardrails.py:572-576` | profanity/phrase hit, with `re.search` word-boundary first and substring only as a **fallback** | Correct pattern — this is what OPS-024's fix copied. |
| `app/agents/staff.py:272`, `voice_agent/telecaller_brain.py:136,182`, `agents/harness/loop.py:89`, `marketing/daily_video.py:301`, `voice_agent/natural_dialog.py:748`, `voice_agent/stt_understanding_gate.py:79` | `if marker in text` **any-match** detectors (banned words, prompt injection, secrets, error markers) | Not classification — they return a boolean, so ordering cannot mislabel anything. Benign by construction. |

## 6. Owner actions

| # | Action | Why | Cost |
|---|---|---|---|
| 1 | Decide the canonical plan → tier mapping and make it an explicit dict lookup | Removes the whole class; needs the real plan vocabulary confirmed first | ~15 min |
| 2 | If any plan string ever gains a suffix/prefix, re-run `tests/test_ops026_rate_tier_resolution.py` | Tests 2–4 will fail (by design) | 0 |
| 3 | Optional: glance at `app/niche_knowledge.py:236` if rebuttals ever look off | Same bug class, copy-quality impact | ~10 min |

## 7. Honest limits

- The sweep was **pattern-based** (regex over `app/`), so it finds the shape, not every
  semantic instance. A hand-rolled matcher that does not use `for … in CONST` would be
  missed.
- "No collision today" is asserted against the plan vocabulary **found by grep**. If the
  VPS `.env` or DB contains a plan string not present in the code, test 4 cannot see it.
- Local-only and undeployed, as always.
