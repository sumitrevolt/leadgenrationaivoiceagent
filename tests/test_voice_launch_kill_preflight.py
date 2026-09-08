"""Deployment preflight classification for VOICE_LAUNCH_KILL.

Preflight and runtime are deliberately DIFFERENT layers:

  runtime  FALSE_TOKEN -> ENV_DISENGAGED  (the operator said "do not kill")
  preflight FALSE_TOKEN -> BLOCKER        (that same setting makes the
                                           file-based emergency toggle inert,
                                           so it must not ship silently)

The raw token must never reach a log, an error, a report or a test diagnostic —
only its class.
"""

from __future__ import annotations

import pytest

from scripts import prod_check

TRUE_TOKENS = ("1", "true", "yes", "on", " TRUE ", "On", "true_token", " TRUE_TOKEN ")
FALSE_TOKENS = ("0", "false", "no", "off", " FALSE ", "Off")
INVALID_TOKENS = ("maybe", "kill", "2", "-", "yes please", "tru")


def _classify(value):
    fn = getattr(prod_check, "classify_voice_launch_kill_env", None)
    assert fn is not None, "classify_voice_launch_kill_env() is not implemented"
    return fn(value)


@pytest.mark.parametrize("value", [None, "", "   ", "\t"])
def test_unset_or_blank_is_unset(value):
    assert _classify(value) == "UNSET"


@pytest.mark.parametrize("value", TRUE_TOKENS)
def test_true_tokens(value):
    assert _classify(value) == "TRUE_TOKEN"


@pytest.mark.parametrize("value", FALSE_TOKENS)
def test_false_tokens(value):
    assert _classify(value) == "FALSE_TOKEN"


@pytest.mark.parametrize("value", INVALID_TOKENS)
def test_invalid_tokens(value):
    assert _classify(value) == "INVALID_TOKEN"


def test_classifier_is_pure_and_total():
    """No I/O, no mutation, and only the four allowed outputs."""
    allowed = {"UNSET", "TRUE_TOKEN", "FALSE_TOKEN", "INVALID_TOKEN"}
    before = list(prod_check.PROBLEMS)
    for v in (None, "", "on", "off", "weird"):
        assert _classify(v) in allowed
    assert prod_check.PROBLEMS == before, "classifier mutated PROBLEMS"


# ---------------------------------------------------------------- gate policy


def _run_check(monkeypatch, value):
    fn = getattr(prod_check, "check_voice_launch_kill_env", None)
    assert fn is not None, "check_voice_launch_kill_env() is not implemented"
    if value is None:
        monkeypatch.delenv("VOICE_LAUNCH_KILL", raising=False)
    else:
        monkeypatch.setenv("VOICE_LAUNCH_KILL", value)
    monkeypatch.setattr(prod_check, "PROBLEMS", [], raising=False)
    result = fn()
    return result, list(prod_check.PROBLEMS)


def test_true_token_is_the_only_passing_state(monkeypatch):
    result, problems = _run_check(monkeypatch, "true")
    assert result["classification"] == "TRUE_TOKEN"
    assert result["status"] == "PASS"
    assert result["reason"] == "EXPLICITLY_ENGAGED"
    assert problems == []


@pytest.mark.parametrize(
    ("value", "classification", "reason"),
    [
        (None, "UNSET", "ENV_NOT_CONFIGURED"),
        ("false", "FALSE_TOKEN", "ENV_EXPLICITLY_DISENGAGED"),
        ("maybe", "INVALID_TOKEN", "ENV_INVALID"),
    ],
)
def test_every_other_state_blocks(monkeypatch, value, classification, reason):
    result, problems = _run_check(monkeypatch, value)
    assert result["classification"] == classification
    assert result["status"] == "BLOCKER"
    assert result["reason"] == reason
    assert len(problems) == 1, problems


def test_false_token_blocks_because_env_overrides_the_file(monkeypatch):
    """Semantic assertion — the literal token is never echoed."""
    result, problems = _run_check(monkeypatch, "off")
    assert result["status"] == "BLOCKER"
    assert result["reason"] == "ENV_EXPLICITLY_DISENGAGED"
    assert "off" not in problems[0].lower().split()


@pytest.mark.parametrize("value", ["s3cr3t-token-value", "off", "maybe"])
def test_no_raw_token_or_path_leaks(monkeypatch, value):
    result, problems = _run_check(monkeypatch, value)
    blob = repr(result) + " ".join(problems)
    assert value not in blob, "raw token leaked"
    assert "voice_launch_kill.json" not in blob, "kill-file path leaked"
    assert "VOICE_LAUNCH_KILL=" not in blob


def test_check_component_identity_is_stable(monkeypatch):
    result, _ = _run_check(monkeypatch, "true")
    assert result["check"] == "voice_launch_kill_env"


def test_preflight_does_not_touch_the_kill_file(monkeypatch, tmp_path):
    """ENV layer only: no read, no write, no directory creation."""
    target = tmp_path / "nested" / "voice_launch_kill.json"
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", str(target))
    _run_check(monkeypatch, None)
    assert not target.exists()
    assert not target.parent.exists()
