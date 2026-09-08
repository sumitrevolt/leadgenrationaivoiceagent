"""Staged A/B rollout gate for cold-email subject variants (2026-07-04, LLM-council
recommendation): OUTREACH_AB=1 used to apply the A/B variant to 100% of sends
immediately. Council verdict on the outreach_quality (0-reply) incident: canary a
new content change on a small slice first, watch bounce_rate_7d/reply-rate, then
widen — rather than flipping everything at once. OUTREACH_AB_PCT enforces that.
"""

from app.marketing import outreach_variants as ov


def test_default_pct_is_full_rollout(monkeypatch):
    monkeypatch.delenv("OUTREACH_AB_PCT", raising=False)
    assert ov._ab_rollout_pct() == 100
    subj, text, html = ov.apply_ab(
        {"email": "someone@biz.com", "business_name": "Biz"}, "orig subj", "t", "h"
    )
    assert subj != "orig subj"  # default = old behavior, A/B applies to everyone


def test_zero_pct_disables_ab(monkeypatch):
    monkeypatch.setenv("OUTREACH_AB_PCT", "0")
    out = ov.apply_ab({"email": "someone@biz.com", "business_name": "Biz"}, "orig subj", "t", "h")
    assert out == ("orig subj", "t", "h")


def test_partial_rollout_is_a_slice_not_all_or_nothing(monkeypatch):
    monkeypatch.setenv("OUTREACH_AB_PCT", "5")
    changed = 0
    n = 1000
    for i in range(n):
        subj, _, _ = ov.apply_ab(
            {"email": f"user{i}@example.com", "business_name": "X"}, "orig subj", "t", "h"
        )
        if subj != "orig subj":
            changed += 1
    rate = changed / n
    assert 0.0 < rate < 0.15  # roughly 5%, not 0% and not 100%


def test_rollout_bucket_is_deterministic_per_recipient(monkeypatch):
    monkeypatch.setenv("OUTREACH_AB_PCT", "50")
    a = ov.apply_ab({"email": "stable@x.com", "business_name": "Y"}, "orig", "t", "h")
    b = ov.apply_ab({"email": "stable@x.com", "business_name": "Y"}, "orig", "t", "h")
    assert a == b


def test_ab_rollout_pct_never_raises(monkeypatch):
    monkeypatch.setenv("OUTREACH_AB_PCT", "not-a-number")
    assert ov._ab_rollout_pct() == 100  # fail-open to old behavior
    monkeypatch.setenv("OUTREACH_AB_PCT", "500")
    assert ov._ab_rollout_pct() == 100  # clamped
    monkeypatch.setenv("OUTREACH_AB_PCT", "-20")
    assert ov._ab_rollout_pct() == 0  # clamped
