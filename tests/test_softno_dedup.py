"""REPEAT-guard: consecutive graceful soft-no closes must NOT repeat verbatim.

Self-test (agent_tester polite_soft_no) found the bot saying the SAME
de-escalation line on the 2nd and 3rd soft-no. deescalation_reply now rotates
by soft-no count so consecutive closers differ. Pure-function test (no WS/LLM)."""

from app.voice_agent import intent_softno as sn

_SOFT = ["dekhte hain baad me", "abhi nahi", "nahi bhai zarurat nahi hai", "baad me sochenge"]


def _hist(n: int) -> list[dict]:
    return [{"role": "user", "content": _SOFT[i % len(_SOFT)]} for i in range(n)]


def test_softno_phrases_are_detected():
    # guard: the fix's rotation depends on soft_no_count seeing these as refusals.
    assert sn.soft_no_count(_hist(2), _SOFT[1]) >= 2


def test_consecutive_deescalation_closers_differ():
    h2, cur2 = _hist(2), _SOFT[1]  # 2nd soft-no
    h3, cur3 = _hist(3), _SOFT[2]  # 3rd soft-no
    r2 = sn.deescalation_reply("solar", "", h2, cur2)
    r3 = sn.deescalation_reply("solar", "", h3, cur3)
    assert r2 in sn.DEESCALATION_TEMPLATES and r3 in sn.DEESCALATION_TEMPLATES
    assert r2 != r3, "consecutive graceful closes repeated verbatim (REPEAT bug)"


def test_backward_compatible_without_history():
    # old 2-arg callers must still work (rotation defaults to 0, no crash).
    r = sn.deescalation_reply("solar", "")
    assert r in sn.DEESCALATION_TEMPLATES
