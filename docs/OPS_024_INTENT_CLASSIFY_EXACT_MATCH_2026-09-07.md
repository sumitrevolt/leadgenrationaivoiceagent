# OPS-024 — `_classify` matched intent by SUBSTRING: every "not interested" was read as "interested"

**Date:** 2026-09-07 (cycle 12, 01:20 IST) · **Severity:** P1 · **Status:** FIXED locally, NOT deployed
**Found while:** executing OPS-016 (narrowing the WhatsApp AI's scope). The fix for OPS-016
initially failed its own test, which is how this surfaced.
**Authority:** local inspection + local fix only. No deploy, no SSH, no remote state change.

---

## 1. The defect

`app/platform/reply_agent.py::_classify` (line ~728) resolved the LLM's label like this:

```python
lab = (reply or "").strip().lower()
for c in _CATS:            # ["interested","question","objection","not_interested",...]
    if c in lab:           # <-- SUBSTRING test, in _CATS ORDER
        return c
```

`"not_interested"` **contains** `"interested"`, and `"interested"` is checked first.
Therefore `not_interested` was **unreachable** — the classifier could never return it.

Verified directly:

```
not_interested   -> interested      <-- BUG
unsubscribe      -> unsubscribe
interested       -> interested
other            -> other
objection        -> objection
```

## 2. Why it matters

`_classify` is shared by the **email** and **WhatsApp** inbound paths, so the blast radius
is both channels:

| Consequence | Detail |
|---|---|
| **Rejections became hot leads** | `"not_interested"` → `"interested"` → `reply_drafts.jsonl` + Hot-Queue entry + `calling_priority: "high"`. Sales time spent chasing people who said no. |
| **Rejections got a sales pitch auto-sent** | With `WHATSAPP_AI_AUTOREPLY=1`, the draft is sent automatically. Messaging someone a pitch right after they declined is the fastest route to a block/report — the exact ban risk OPS-013 exists to prevent. |
| **A compliance guard was dead code** | The auto-send guard `intent not in ("unsubscribe","not_interested","ooo")` could never fire for `not_interested`, because `intent` was never `not_interested`. The code *looked* safe and was not. |
| **CRM state wrong** | Line 465 maps `"not_interested" -> "dead"`. That status was never applied on this path. |

No other `_CATS` entry is affected: it is the only member that contains an earlier member
as a substring.

## 3. The fix (cycle 12)

```python
raw = (reply or "").strip().lower()
# OPS-024: EXACT match first, word-boundary match only as a fallback.
# `probe` collapses every separator to one space so "not_interested", "not interested"
# and "Not-Interested" are one verdict, while "not_interested" still fails the
# `\binterested\b` search (underscore is a word char inside the token).
probe = re.sub(r"[^a-z0-9]+", " ", raw).strip()
compact = probe.replace(" ", "_")
if compact in _CATS:
    return compact
for c in _CATS:
    if re.search(rf"\b{re.escape(c.replace('_', ' '))}\b", probe):
        return c
```

Design notes:
- **Exact match wins**, so `_CATS` ordering can never decide a verdict again (pinned by
  `test_cat_ordering_can_never_decide_a_verdict`, which reverses `_CATS` and re-checks).
- The word-boundary fallback preserves the old tolerance for chatty LLM output
  ("I am interested", "label: question", "unsubscribe please").
- `re` was already imported; no new dependency.
- Still returns `"other"` for anything unrecognised (unchanged fail-safe).

## 4. Verification evidence

- `tests/test_ops024_classify_exact_label.py` — 21 tests, all green:
  - `test_not_interested_is_not_misread_as_interested` (the regression; failed pre-fix)
  - `not interested` / `Not-Interested` / `not_interested.` all → `not_interested`
  - every `_CATS` member round-trips, under both original and **reversed** `_CATS`
  - prose labels still resolve; junk still → `other`
- Full combo: **257 collected, 256 passed, 1 pre-existing failure**
  (`tests/test_compliance.py::test_dnd_fail_open_honoured_outside_production`, proven
  identical at HEAD in an earlier cycle).
- `ruff check` clean · `scripts/check_secrets.py` OK · `scripts/prod_check.py`
  **ALL PASSED, 1396 routes UNCHANGED** (no new public surface).

## 5. Honest limits

- **Not deployed.** Prod is `b4a457f2`; local HEAD `a531833b`. Until deployed, prod still
  misclassifies `not_interested` as `interested`.
- The fix relies on the LLM emitting a recognisable label. With `max_tokens=8`,
  `temperature=0.0` and the label list in the prompt that is a reasonable assumption, but
  a truly unparseable reply still falls through to `"other"` (fail-safe, unchanged).
- **OPS-022 bit twice this cycle** — a concurrent worker reverted the fix after each of my
  first two edits; only a `grep -c` immediately before the test run caught it. Any future
  edit to this file should be re-verified the same way.
- This does **not** weaken any §5 / TRAI / DND gate; it removes a false *positive* and
  makes an opt-out signal actually respected.

## 6. Owner actions

| # | Action | Why | Cost |
|---|---|---|---|
| 1 | Deploy cycles 2–12 (via `scripts/deploy_vps.sh`) | Until then, rejections keep being treated as hot leads in prod | owner-gated |
| 2 | Re-examine historical Hot-Queue entries for false `interested` on `not_interested` replies | Past sales time may have been spent on people who declined | ~15 min |
| 3 | Resolve **OPS-022** (concurrent agents editing `app/`): per-file lock or file-ownership map | This cycle lost two edits to silent reverts | decision only |
