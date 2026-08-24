"""Tests for capacity trio: cred_pool (multi-key rotation) + risk_approve (auto-approve policy).
Pure-python, no network. LLM cache (#2) already existed in free_ai — not re-tested here.
"""

from app.agents import cred_pool, risk_approve


def test_cred_pool_enabled_env(monkeypatch):
    monkeypatch.delenv("CRED_POOLS", raising=False)
    assert cred_pool.enabled() is False
    monkeypatch.setenv("CRED_POOLS", "1")
    assert cred_pool.enabled() is True


def test_rotate_single_key_returns_base(monkeypatch):
    for n in (2, 3, 4, 5):
        monkeypatch.delenv(f"GROQ_API_KEY_{n}", raising=False)
    assert cred_pool.rotate("GROQ_API_KEY", "base123") == "base123"


def test_rotate_round_robins_across_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY_2", "k2")
    monkeypatch.setenv("GROQ_API_KEY_3", "k3")
    for n in (4, 5):
        monkeypatch.delenv(f"GROQ_API_KEY_{n}", raising=False)
    seen = {cred_pool.rotate("GROQ_API_KEY", "k1") for _ in range(6)}
    # round-robin should surface all three keys over several calls
    assert {"k1", "k2", "k3"} <= seen


def test_rotate_skips_cooled_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY_2", "m2")
    for n in (3, 4, 5):
        monkeypatch.delenv(f"MISTRAL_API_KEY_{n}", raising=False)
    cred_pool.mark_fail("MISTRAL_API_KEY", "m1", cooldown_s=60)
    # m1 cooled → next picks should avoid it while cooled
    picks = {cred_pool.rotate("MISTRAL_API_KEY", "m1") for _ in range(4)}
    assert "m2" in picks


def test_key_counts_never_exposes_values(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g1")
    monkeypatch.setenv("GEMINI_API_KEY_2", "g2")
    counts = cred_pool.key_counts(["GEMINI_API_KEY"])
    assert counts["GEMINI_API_KEY"] == 2


def test_rotate_never_raises_on_garbage():
    assert cred_pool.rotate("X", None) in (None, "")  # type: ignore[arg-type]


def test_risk_enabled_env(monkeypatch):
    monkeypatch.delenv("RISK_AUTO_APPROVE", raising=False)
    assert risk_approve.enabled() is False
    monkeypatch.setenv("RISK_AUTO_APPROVE", "1")
    assert risk_approve.enabled() is True


def test_risk_low_action_auto_approves(monkeypatch):
    monkeypatch.setenv("RISK_AUTO_APPROVE_MAX_COST", "5")
    # a cheap, benign action → low score → auto-approve
    assert (
        risk_approve.should_auto_approve("reflection", cost_estimate=0.5, reason="self review")
        is True
    )


def test_risk_high_cost_blocks(monkeypatch):
    monkeypatch.setenv("RISK_AUTO_APPROVE_MAX_COST", "5")
    assert risk_approve.should_auto_approve("reflection", cost_estimate=50, reason="x") is False


def test_risk_sideeffect_word_blocks(monkeypatch):
    monkeypatch.setenv("RISK_AUTO_APPROVE_MAX_COST", "100")
    # reason mentions an outward send → score bumped → not auto-approved
    assert (
        risk_approve.should_auto_approve(
            "social_drafts", cost_estimate=1, reason="send whatsapp blast"
        )
        is False
    )


def test_risk_score_bounds():
    s = risk_approve.score("code_scan", 3, "publish and send")
    assert 0.0 <= s <= 1.0
