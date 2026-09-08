"""Wiring-level regression guard for TRAI AI-disclosure (security-auditor finding
#1, 2026-07-07): `ensure_ai_disclosure()` itself is solid and unit-tested
(tests/test_ai_disclosure.py), but unlike DND/calling-window/DLT — which are
unified inside `ComplianceGate.check()` — AI-disclosure is enforced ad hoc at
each opener-construction call site, with no single code-enforced chokepoint.

Folding this into `ComplianceGate.check()` would be architecturally wrong (that
gate runs on phone-number/call-type metadata BEFORE the opener text is
finalized in several flows) — the actual, lower-risk gap is that nothing
guarantees a call site keeps calling the helper across future edits. This test
locks in the 4 real call sites so a future refactor that silently drops the
wrap (exactly the failure mode that shipped today's ADR-043 P0 elsewhere in
this same audit) fails loudly here instead of shipping quietly.
"""

from __future__ import annotations

import inspect


def test_telephony_vobiz_custom_message_discloses():
    from app.api import telephony_vobiz

    src = inspect.getsource(telephony_vobiz)
    idx = src.index('message = (request.message or "").strip()')
    assert "ensure_ai_disclosure" in src[idx : idx + 400]


def test_web_call_demo_opener_discloses():
    from app.api import web_call

    src = inspect.getsource(web_call)
    idx = src.index("opening = _script_opening(niche")
    assert "ensure_ai_disclosure" in src[idx : idx + 700]


def test_vobiz_stream_opening_line_discloses():
    from app.telephony import vobiz_stream

    src = inspect.getsource(vobiz_stream)
    idx = src.index("def _opening_line(self)")
    snippet = src[idx : idx + 800]
    assert "ensure_ai_disclosure" in snippet
    # this must be the function every real call site funnels through, per its
    # own docstring — regression guard if that claim is ever contradicted.
    assert "All call-sites" in snippet


def test_platform_pitch_intro_discloses():
    from app.voice_agent import platform_pitch

    src = inspect.getsource(platform_pitch)
    idx = src.index('intro = (s.get("opening")')
    assert "ensure_ai_disclosure" in src[idx : idx + 300]


def test_qa_checks_backstop_still_exists():
    """The mid-call post-hoc detector (defense-in-depth if a pre-emptive wrap
    above is ever bypassed) must keep existing — asserts on the real transcript
    shape, not a mock, so a signature drift here fails this test not silently
    disarm the backstop."""
    from app.voice_agent.qa_checks import check_missing_ai_disclosure

    undisclosed = [{"role": "assistant", "content": "Namaste, Acme se bol raha hoon."}]
    assert check_missing_ai_disclosure(undisclosed) is not None

    disclosed = [{"role": "assistant", "content": "Main ek AI assistant hoon, Acme se."}]
    assert check_missing_ai_disclosure(disclosed) is None
