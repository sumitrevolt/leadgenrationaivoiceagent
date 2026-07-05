---
name: pairwise-test-design
description: Combinatorial (pairwise / PICT) test-case design for LeadGen AI's huge config space — niche × band × tier × channel × call_type. Use when a feature has many independent inputs and full cartesian is too big, or user says "pairwise", "combinatorial", "test matrix", "cover all combos", "PICT", "edge-case matrix". Reduces N^k combos to ~dozen rows covering every input PAIR.
---
# Pairwise Test Design (PICT)

**Kyun:** LeadGen ka config-space combinatorial hai —
`niche(39) × band(A/B/C) × tier(starter/advanced + legacy-hidden growth[public:False]) × channel × call_type(promo/transactional) × gst(on/off)`.
Full cartesian = hazaaron cases. **Pairwise** har input-PAIR ko cover karta hai ~10-20 rows me (research: ~zyaadatar bugs 2-input interaction se).

## Kab use karo
- Naya feature jisme 3+ independent inputs (pricing tiers, niche-band routing, flag combos, channel matrix).
- Bug "sirf is combo pe aata" — pairwise se interaction pakdo.
- Test-gap audit: `test-expand` ke baad agar inputs bahut → pairwise se compress.

## Free tooling (Windows + Python)
Paid kuch nahi. Pure-Python:
```bash
pip install allpairspy   # pure python, koi binary nahi
```
```python
from allpairspy import AllPairs
params = {
    "tier":      ["starter", "growth", "advanced"],
    "band":      ["A", "B", "C"],
    "call_type": ["promotional", "transactional"],
    "gst":       [True, False],
}
rows = list(AllPairs(list(params.values())))
# ~12 rows har PAIR ko cover karte (vs 3*3*2*2 = 36 full)
```
Alt: Microsoft **PICT** binary (free) — `.txt` model file, par allpairspy zero-dep behtar hai yahan.

## Pattern: pairwise → pytest parametrize
```python
import pytest
from allpairspy import AllPairs

CASES = [
    tuple(row) for row in AllPairs([
        ["starter", "growth", "advanced"],
        ["A", "B", "C"],
        ["promotional", "transactional"],
    ])
]

@pytest.mark.parametrize("tier,band,call_type", CASES)
def test_quote_routing(tier, band, call_type):
    q = compute_quote(tier=tier, band=band, call_type=call_type)
    assert q.price_inr > 0
```

## Constraints (invalid combos drop karo)
Kuch combos illegal hote (e.g. `voice_pilot + gst`, ya promo + DND-window). `allpairspy` me filter:
```python
AllPairs(values, filter_func=lambda row: not (row[0]=="voice_pilot" and row[3] is True))
```
Compliance combos (TRAI 9am-7pm window, DND fail-closed, AI-disclosure) ko hamesha apne axis me rakho taaki pairwise unko explicitly cover kare.

## Verify
- `scripts\run_tests.bat` → `pytest_run.log` Read karo (CLAUDE.md deploy-loop).
- Row count log karo (kitne full-cartesian se bache) — silent truncation mat karo.
- High-risk pairs (billing, compliance) → pairwise ke ALAWA explicit single-case bhi add karo.

## Pairs with
`tdd-contract-first` (cases pehle) · `test-expand` · `parallel-batch-build` (matrix features).
