---
name: tdd-contract-first
description: Red-green-refactor + "contract tests PEHLE" discipline — naya feature/bugfix likhne se pehle failing test, aur business-critical numbers (price/plan/route/flag) ke contract asserts up-front. Use when user says "naya feature", "test likho", "TDD", "bugfix karo", ya jab billing/pricing/public API touch ho raha ho.
---

# TDD + Contract-First (test pehle, code baad me)

**Iron rule: failing test dekhe bina production code nahi.** Test jo turant pass ho jaye = kuch prove nahi karta. Bug fix? Pehle repro-test jo FAIL kare, fir fix.

## Red → Green → Refactor (project flow)

1. **RED** — `tests/test_<feature>.py` me EK minimal test (ek behavior, clear naam, pure-python — no network/DB, parallel-batch rule). Chalao: `python -m pytest tests/test_x.py -x -q` → **fail hote dekho**, aur sahi reason se fail ho (feature missing, typo nahi).
2. **GREEN** — minimal code jo pass kare. Over-engineering nahi (YAGNI) — options/knobs tab jodo jab test maange.
3. **REFACTOR** — green rehte hue cleanup. Behavior add nahi.
4. **Full gate** — TARGETED suites chalao (`python -m pytest tests\test_<feature>.py tests\test_billing_truth_2026.py -q`) — full run_tests.bat offline HANG hota hai (2026-07-05) (console truncate hota hai — log = truth). Fir `python scripts/prod_check.py`.

## CONTRACT tests pehle (billing-truth lesson 🚨)
/pricing checkout legacy Cloud-Run plans se ₹15k+18% GST charge karta tha jabki page advertised price dikhata — legacy plans ne `packages.py` ko shadow kar diya, 'advanced' checkout 404 + unregistered hote hue illegal GST. `tests/test_billing_truth_2026.py` ab ye LOCK karta hai. **Naya feature jisme paisa/plan/public promise hai → pehla test = contract assert:**
- Price/plan (REAL keys, `app/marketing/packages.py`): `assert float(PRICING_PLANS[pkg["key"]].monthly_price) == float(pkg["price_inr_month"])` har pkg pe; advanced = ₹5,999 + `calls_per_month == 500`; starter monthly ₹1,999 / yearly ₹19,990; packages keys `== ["starter","growth","advanced"]` (growth = `public:False` legacy-hidden). SOURCE of truth vs har surface (API, page, checkout).
- GST contract: `GST_GSTIN` unset → total == advertised, tax == 0; set → ×1.18, tax_rate 18 (`test_calculate_price_unregistered_flat`/`_registered_gst`).
- Voice pricing alag source: `app/marketing/voice_packages.py` (flat band A/B/C ₹4,999/9,999/19,999).
- Public API shape: response keys/status codes assert karo (`/api/public/*` backward-compat).
- Flag-OFF = zero change: `monkeypatch.delenv("FLAG")` → assert old behavior bilkul same (gated-feature pattern).
- Fail-open/fail-closed DELIBERATE assert: compliance DND = fail-CLOSED (block), rate-limit/billing = fail-OPEN; webhook signature = fail-CLOSED (prod 503 if secret unset) — test me yehi contract likho, weaken kabhi nahi.

## free_ai mock pattern (LLM tests hermetic rakho)
```python
async def fake_chat(*a, **k):
    return '{"score": 0.8}'  # ya jo shape callee expect kare
monkeypatch.setattr(module_under_test.free_ai, "chat", fake_chat)
```
- `free_ai.chat` ka REAL signature respect karo (system, messages-list → growth_optimizer bug isi drift se tha).
- Parse-fail path bhi test karo (LLM garbage de to fallback chale, raise nahi).
- Network-touch tests me **timeout marker zaroor** — bina timeout full pytest hang ho chuka hai (~27th test).
- MX/DNS-dependent (email_verify) = autouse stub (test_auto_outreach pattern copy karo).

## Common rationalizations (sab reject)
| Excuse | Reality |
|---|---|
| "Simple hai, test nahi chahiye" | Simple code bhi tutta hai; test 30 sec ka hai |
| "Test baad me likh dunga" | Tests-after = "kya karta hai"; tests-first = "kya karna CHAHIYE" |
| "Manually test kar liya" | No record, no re-run — har deploy pe dobara manual? |
| "Pricing page bas UI hai" | ₹15k-checkout-vs-advertised bug bolta hai: UI bhi contract hai |

Bug mila debugging me? → failing test PEHLE (sibling skill `systematic-debugging` Phase 4). Ship flow = `leadgen-ops`.

Adapted from obra/superpowers `test-driven-development` (via VoltAgent/awesome-agent-skills).
