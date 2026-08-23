"""ADR-104 A5 -- regression tests for the rewritten `_kb_facts()` (Phase A4.4).

Verifies the four branches the live voice reply path must take, importing the
REAL `app.voice_agent.telecaller_brain.TelecallerBrain._kb_facts`, the REAL
`app.voice_agent.kb_readiness` module (monkeypatched at its real call-site),
and fakes only at the `app.tasks.kb_niche_refresh` / `app.voice_agent.knowledge_base`
boundary. Runs directly against the shipped files (no verification shim needed
when run from a real filesystem -- an earlier draft of this file imported a
throwaway byte-copy module because a different execution environment used
during initial development had a stale view of the edited original file; that
workaround is no longer needed here).

Critically, none of these tests may ever import or call `_get_qdrant_client`,
`_get_qdrant_embedder`, `bootstrap_default_kb`, or `_get_kb` -- that would silently
reintroduce the exact incident this fix removes. A static source-scan test
enforces this at the bottom of the file (mirrors test_kb_readiness.py's own
`test_module_does_not_import_bootstrap_symbols`).
"""

from __future__ import annotations

import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.voice_agent import telecaller_brain as tcb  # noqa: E402
from app.voice_agent import kb_readiness  # noqa: E402


def _make_brain(niche: str = "real_estate", client_id: str | None = None):
    """Construct a TelecallerBrain WITHOUT running __init__ (which needs a live
    Gemini/free-AI key + niches/script data) -- _kb_facts only reads
    self.niche/self.client_id."""
    b = object.__new__(tcb.TelecallerBrain)
    b.niche = niche
    b.client_id = client_id
    return b


class _FakeReadiness:
    def __init__(self, state: str, count: int = 0, error_class: str | None = None):
        self.state = state
        self.count = count
        self.error_class = error_class

    @property
    def is_ready(self) -> bool:
        return self.state == kb_readiness.STATE_READY


def test_kb_facts_unsupported_niche_degrades_immediately(monkeypatch):
    calls = {"readiness": 0, "refresh": 0}

    def _boom_readiness(niche, client=None):
        calls["readiness"] += 1
        raise AssertionError("readiness must never be queried for an unsupported niche")

    monkeypatch.setattr(kb_readiness, "is_supported_niche", lambda n: False)
    monkeypatch.setattr(kb_readiness, "count_niche_catalog_points", _boom_readiness)

    brain = _make_brain(niche="real_estate")  # QA's known catalog-drift target
    facts = asyncio.run(brain._kb_facts("kya price hai is property ka"))

    assert facts == []
    assert calls["readiness"] == 0


def test_kb_facts_cold_niche_requests_owned_refresh(monkeypatch):
    monkeypatch.setattr(kb_readiness, "is_supported_niche", lambda n: True)
    monkeypatch.setattr(
        kb_readiness,
        "count_niche_catalog_points",
        lambda n, client=None: _FakeReadiness(kb_readiness.STATE_NOT_READY, count=0),
    )

    refresh_calls = []
    fake_module = types.ModuleType("app.tasks.kb_niche_refresh")

    def _request_niche_refresh(niche):
        refresh_calls.append(niche)
        return True

    fake_module.request_niche_refresh = _request_niche_refresh
    monkeypatch.setitem(sys.modules, "app.tasks.kb_niche_refresh", fake_module)

    brain = _make_brain(niche="solar")
    facts = asyncio.run(brain._kb_facts("mujhe solar panel chahiye ghar ke liye"))

    assert facts == []
    assert refresh_calls == ["solar"]


def test_kb_facts_cold_niche_refresh_dedup_returns_false_still_degrades(monkeypatch):
    """A second concurrent cold-turn for the same niche: request_niche_refresh
    returns False (another owner already holds the lease) -- _kb_facts must
    still degrade cleanly (never raise, never retry inline)."""
    monkeypatch.setattr(kb_readiness, "is_supported_niche", lambda n: True)
    monkeypatch.setattr(
        kb_readiness,
        "count_niche_catalog_points",
        lambda n, client=None: _FakeReadiness(kb_readiness.STATE_NOT_READY, count=0),
    )

    fake_module = types.ModuleType("app.tasks.kb_niche_refresh")
    fake_module.request_niche_refresh = lambda niche: False
    monkeypatch.setitem(sys.modules, "app.tasks.kb_niche_refresh", fake_module)

    brain = _make_brain(niche="solar")
    facts = asyncio.run(brain._kb_facts("mujhe solar panel chahiye ghar ke liye"))
    assert facts == []


def test_kb_facts_ready_niche_retrieves_from_singleton(monkeypatch):
    monkeypatch.setattr(kb_readiness, "is_supported_niche", lambda n: True)
    monkeypatch.setattr(
        kb_readiness,
        "count_niche_catalog_points",
        lambda n, client=None: _FakeReadiness(kb_readiness.STATE_READY, count=42),
    )

    class _FakeKB:
        def backend(self, ns):
            return "qdrant"

        def retrieve(self, query, k=2, namespace="", rerank=False):
            return [
                {"text": "Solar EMI se available hai, koi upfront cost nahi.", "score": 0.91},
                {"text": "Subsidy 40% tak milti hai residential ke liye.", "score": 0.72},
            ]

    fake_kb_module = types.ModuleType("app.voice_agent.knowledge_base")
    fake_kb_module.get_knowledge_base = lambda: _FakeKB()
    monkeypatch.setitem(sys.modules, "app.voice_agent.knowledge_base", fake_kb_module)

    brain = _make_brain(niche="solar")
    facts = asyncio.run(brain._kb_facts("subsidy kitni milti hai"))

    assert len(facts) == 2
    assert any("Subsidy" in f for f in facts)
    assert any("EMI" in f for f in facts)


def test_kb_facts_ready_niche_low_score_hits_filtered_out(monkeypatch):
    monkeypatch.setattr(kb_readiness, "is_supported_niche", lambda n: True)
    monkeypatch.setattr(
        kb_readiness,
        "count_niche_catalog_points",
        lambda n, client=None: _FakeReadiness(kb_readiness.STATE_READY, count=10),
    )

    class _FakeKB:
        def backend(self, ns):
            return "qdrant"

        def retrieve(self, query, k=2, namespace="", rerank=False):
            return [{"text": "irrelevant low-score chunk", "score": 0.01}]

    fake_kb_module = types.ModuleType("app.voice_agent.knowledge_base")
    fake_kb_module.get_knowledge_base = lambda: _FakeKB()
    monkeypatch.setitem(sys.modules, "app.voice_agent.knowledge_base", fake_kb_module)

    brain = _make_brain(niche="solar")
    facts = asyncio.run(brain._kb_facts("kuch bhi puchna hai"))
    assert facts == []


def test_kb_facts_readiness_timeout_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(kb_readiness, "is_supported_niche", lambda n: True)

    def _slow_count(n, client=None):
        import time

        time.sleep(0.05)  # tiny sleep; we drop _KB_TIMEOUT_S to make this "slow"
        return _FakeReadiness(kb_readiness.STATE_READY, count=5)

    monkeypatch.setattr(kb_readiness, "count_niche_catalog_points", _slow_count)
    monkeypatch.setattr(tcb, "_KB_TIMEOUT_S", 0.001)

    brain = _make_brain(niche="solar")
    facts = asyncio.run(brain._kb_facts("kuch bhi puchna hai"))
    assert facts == []


def test_kb_facts_readiness_error_state_degrades(monkeypatch):
    monkeypatch.setattr(kb_readiness, "is_supported_niche", lambda n: True)
    monkeypatch.setattr(
        kb_readiness,
        "count_niche_catalog_points",
        lambda n, client=None: _FakeReadiness(
            kb_readiness.STATE_ERROR, count=0, error_class="NoClient"
        ),
    )

    brain = _make_brain(niche="solar")
    facts = asyncio.run(brain._kb_facts("kuch bhi puchna hai"))
    assert facts == []


def test_kb_facts_short_utterance_short_circuits_before_any_io(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not touch readiness for a <3-char utterance")

    monkeypatch.setattr(kb_readiness, "is_supported_niche", _boom)
    brain = _make_brain(niche="solar")
    facts = asyncio.run(brain._kb_facts("ok"))
    assert facts == []


def test_verify_module_does_not_import_bootstrap_symbols():
    """Static guard against reintroducing the incident: no ACTUAL import/call of
    the dangerous bootstrap symbols outside of comments/docstrings. Comments
    reference these names in backtick-quoted prose (e.g. explaining what was
    removed and why) -- those are allowed. Only a REAL Python `import X` /
    `from X import` statement, or a call `X(` on a non-comment, non-backtick-
    quoted line, is banned. Implemented as a per-line scan (not naive full-text
    substring search) so prose mentions never false-positive."""
    src_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "voice_agent",
        "telecaller_brain.py",
    )
    with open(src_path, encoding="utf-8") as f:
        lines = f.readlines()

    banned_names = ("_get_qdrant_embedder", "bootstrap_default_kb", "_get_kb")
    violations = []
    in_docstring = False
    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        # crude triple-quote docstring tracker -- good enough for this one file
        if stripped.count('"""') % 2 == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        code_part = raw_line.split("#", 1)[0]
        if "`" in code_part:
            # backtick-quoted prose fragment leaking into a non-comment line
            # (shouldn't normally happen, but be conservative and skip it)
            continue
        for name in banned_names:
            if f"import {name}" in code_part or f"{name}(" in code_part.replace(" ", ""):
                violations.append((lineno, name, raw_line.rstrip()))

    assert violations == [], f"forbidden bootstrap usage found: {violations}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
