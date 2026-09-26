from __future__ import annotations

from scripts import agent_task_packet as packet


def test_task_packet_injects_canonical_coordination_and_typesafe_rules(monkeypatch) -> None:
    monkeypatch.setattr(
        packet.pc,
        "load_store",
        lambda _path: {"nodes": [], "edges": [], "meta": {"head_sha": "abc12345"}},
    )
    monkeypatch.setattr(packet.q, "query", lambda *_args, **_kwargs: [])

    text = packet.build_packet(
        objective="repair one bounded production blocker",
        files=["app/platform/example.py"],
        query="production blocker",
        test="tests/test_example.py",
    )

    assert "existing canonical ledger/orchestrator only" in text
    assert "claim/lease/fencing-token" in text
    assert "canonical TypeSafe integration" in text
    assert "plan/route, intermediate QA or revision, and final/outcome validation" in text
    assert "not repeated identical-input calls" in text
    assert "Never fabricate a TypeSafe call" in text
    assert "assign or state the next concrete bounded task" in text
    assert "never print, commit, or paste API keys" in text
