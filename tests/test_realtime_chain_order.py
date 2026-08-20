"""test_realtime_chain_order.py — audit §10 fix: realtime chain latency-first order.

Red-first: old order was mistral→groq→cerebras; this test would FAIL on the old
code (mistral first = higher p50 first-token latency for short voice turns).
Fixed: groq→cerebras→mistral for realtime (audit §10 [LOW] 2026-07-06).
Bulk unchanged: cerebras→groq→mistral (throughput-first).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_ollama_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_PRIMARY", raising=False)
    monkeypatch.delenv("NVIDIA_PRIMARY", raising=False)
    monkeypatch.delenv("VOICE_GEMINI_PRIMARY", raising=False)
    monkeypatch.delenv("GEMINI_PRIMARY", raising=False)


def test_realtime_chain_groq_first():
    """Groq must be the FIRST core provider for realtime (lowest p50 latency)."""
    from app.voice_agent import free_ai

    chain = free_ai._build_llm_chain("realtime")
    providers = [p for p, _ in chain]

    # Only core providers (groq/cerebras/mistral) — skip tail/gemini/nvidia/etc
    core_providers = [p for p in providers if p in ("groq", "cerebras", "mistral")]
    # First occurrence ordering
    first_groq = providers.index("groq")
    first_cerebras = providers.index("cerebras")
    first_mistral = providers.index("mistral")

    assert (
        first_groq < first_cerebras
    ), f"realtime: groq ({first_groq}) should be before cerebras ({first_cerebras})"
    assert (
        first_cerebras < first_mistral
    ), f"realtime: cerebras ({first_cerebras}) should be before mistral ({first_mistral})"
    assert (
        core_providers[0] == "groq"
    ), f"realtime: first core provider should be groq, got {core_providers[0]}"


def test_bulk_chain_cerebras_first():
    """Bulk profile is throughput-first: cerebras must still lead (unchanged)."""
    from app.voice_agent import free_ai

    chain = free_ai._build_llm_chain("bulk")
    providers = [p for p, _ in chain]

    first_cerebras = providers.index("cerebras")
    first_groq = providers.index("groq")
    first_mistral = providers.index("mistral")

    assert (
        first_cerebras < first_groq
    ), f"bulk: cerebras ({first_cerebras}) should be before groq ({first_groq})"
    assert (
        first_groq < first_mistral
    ), f"bulk: groq ({first_groq}) should be before mistral ({first_mistral})"


def test_trainer_timeout_within_celery_limit():
    """Trainer wait_for timeout must be < Celery task_soft_time_limit (540s)."""
    import ast
    import pathlib

    scheduler_path = pathlib.Path("app/platform/team_scheduler.py")
    src = scheduler_path.read_text(encoding="utf-8")

    # Find wait_for timeout for run_nightly_training
    tree = ast.parse(src)
    timeouts = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "wait_for"
        ):
            # Check if it mentions run_nightly_training
            src_segment = ast.get_source_segment(src, node) or ""
            if "run_nightly_training" in src_segment:
                # Extract timeout keyword
                for kw in node.keywords:
                    if kw.arg == "timeout":
                        if isinstance(kw.value, ast.Constant):
                            timeouts.append(kw.value.value)
    assert timeouts, "Could not find wait_for(run_nightly_training, timeout=...) in scheduler"
    for t in timeouts:
        assert t <= 360, (
            f"trainer wait_for timeout {t}s leaves no room for transcript analysis "
            "before Celery's 540s soft_time_limit"
        )


def test_trainer_ingest_kb_budget_within_celery_limit():
    """KB ingest wait_for timeout must exist and leave room for ML training (360s)
    inside Celery's 600s hard / 540s soft limit (was unbounded sync → daily
    TimeLimitExceeded(600) DLQ deaths)."""
    import ast
    import pathlib

    scheduler_path = pathlib.Path("app/platform/team_scheduler.py")
    src = scheduler_path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    timeouts = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "wait_for"
        ):
            src_segment = ast.get_source_segment(src, node) or ""
            if "ingest_to_kb" in src_segment:
                for kw in node.keywords:
                    if kw.arg == "timeout":
                        if isinstance(kw.value, ast.Constant):
                            timeouts.append(kw.value.value)
    assert timeouts, (
        "Could not find wait_for(ingest_to_kb, timeout=...) in scheduler — "
        "bounded ingest is required to keep the trainer job under Celery's hard limit"
    )
    for t in timeouts:
        assert 0 < t <= 200, (
            f"ingest_to_kb wait_for timeout {t}s must be ≤200s so trainer "
            "transcript analysis + ML 360s window stay under the 600s hard limit"
        )


def test_both_profiles_have_all_three_core_providers():
    """Sanity: both profiles must include groq, cerebras, mistral in core."""
    from app.voice_agent import free_ai

    for profile in ("realtime", "bulk"):
        chain = free_ai._build_llm_chain(profile)
        providers = {p for p, _ in chain}
        for expected in ("groq", "cerebras", "mistral"):
            assert expected in providers, f"{profile} chain missing '{expected}': {providers}"
