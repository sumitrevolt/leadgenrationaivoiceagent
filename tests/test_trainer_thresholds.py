"""W2.3 — trainer (meera) suggestion thresholds are env-tunable (were hardcoded).

`run_trainer` emitted suggestions off hardcoded cutoffs (repeats>2, junk_ratio>0.3,
avg_reply_len>28), so a deployment whose call profile differs (e.g. a noisier STT niche)
couldn't retune what counts as "a problem" without a code change. Fix:
`_trainer_thresholds()` reads TRAINER_REPEAT_MAX / TRAINER_JUNK_RATIO /
TRAINER_REPLY_WORDS (env), falling back to the original defaults.
"""

from __future__ import annotations

import app.agents.staff as staff


def test_defaults_when_unset(monkeypatch):
    for e in ("TRAINER_REPEAT_MAX", "TRAINER_JUNK_RATIO", "TRAINER_REPLY_WORDS"):
        monkeypatch.delenv(e, raising=False)
    assert staff._trainer_thresholds() == (2, 0.3, 28)


def test_env_override(monkeypatch):
    monkeypatch.setenv("TRAINER_REPEAT_MAX", "5")
    monkeypatch.setenv("TRAINER_JUNK_RATIO", "0.5")
    monkeypatch.setenv("TRAINER_REPLY_WORDS", "40")
    assert staff._trainer_thresholds() == (5, 0.5, 40)


def test_garbage_env_falls_back(monkeypatch):
    monkeypatch.setenv("TRAINER_REPEAT_MAX", "not-a-number")
    monkeypatch.delenv("TRAINER_JUNK_RATIO", raising=False)
    monkeypatch.delenv("TRAINER_REPLY_WORDS", raising=False)
    assert staff._trainer_thresholds() == (2, 0.3, 28)
