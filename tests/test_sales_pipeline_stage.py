"""Sales pipeline stage-ordering guard tests — data-integrity (forward-only).

Covers the additive guard in app/marketing/sales_pipeline.py that prevents a
re-classified reply (or any re-upsert) from silently pulling an advanced deal
(won/negotiating) BACKWARD to an earlier stage like `interested`.

Hermetic: store paths redirected to tmp_path; no network/DB/Redis. The prod
code is never-raise by design, so these assert the contract, not exceptions.

Run: .venv\\Scripts\\python.exe -m pytest tests/test_sales_pipeline_stage.py -q
"""

from __future__ import annotations


def _stage_of(sp, deal_id: str) -> str | None:
    for r in sp._read(sp._DEALS):
        if r.get("id") == deal_id:
            return r.get("stage")
    return None


def test_stage_no_backward_overwrite(monkeypatch, tmp_path):
    """won deal must NOT be silently downgraded to interested; allow_reverse forces it."""
    from app.marketing import sales_pipeline as sp

    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    monkeypatch.setattr(sp, "_ACTIONS", str(tmp_path / "deal_actions.jsonl"))

    deal = sp.upsert_deal({"business_name": "Mehta Clinic", "phone": "9000000001"})
    deal_id = deal["id"]

    # Advance all the way to the furthest stage.
    assert sp.set_stage(deal_id, "won") is True
    assert _stage_of(sp, deal_id) == "won"

    # A re-classified "interested" reply tries to pull it back → BLOCKED.
    # Deal is found (returns True) but the stage is preserved (no silent overwrite).
    assert sp.set_stage(deal_id, "interested") is True
    assert _stage_of(sp, deal_id) == "won"  # still won — not downgraded

    # The same guard protects the re-upsert path (the actual reply_agent flow).
    sp.upsert_deal({"business_name": "Mehta Clinic", "phone": "9000000001"}, stage="interested")
    assert _stage_of(sp, deal_id) == "won"  # re-upsert can't downgrade either

    # Explicit escape hatch: allow_reverse=True DOES move it back.
    assert sp.set_stage(deal_id, "interested", allow_reverse=True) is True
    assert _stage_of(sp, deal_id) == "interested"


def test_stage_forward_and_lateral_still_move(monkeypatch, tmp_path):
    """Forward moves and entry-level lateral (interested→contacted) stay allowed;
    invalid stage and unknown deal still return False (existing contract)."""
    from app.marketing import sales_pipeline as sp

    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    monkeypatch.setattr(sp, "_ACTIONS", str(tmp_path / "deal_actions.jsonl"))

    deal = sp.upsert_deal({"business_name": "Roy Spa", "phone": "9000000002"}, stage="interested")
    deal_id = deal["id"]

    # Entry-level lateral (this is the move the e2e playbook test relies on).
    assert sp.set_stage(deal_id, "contacted") is True
    assert _stage_of(sp, deal_id) == "contacted"

    # Forward progression works.
    for nxt in ("demo_sent", "proposal_sent", "negotiating", "won"):
        assert sp.set_stage(deal_id, nxt) is True
        assert _stage_of(sp, deal_id) == nxt

    # `lost` is a terminal sink — always allowed even from won (churn/close).
    assert sp.set_stage(deal_id, "lost") is True
    assert _stage_of(sp, deal_id) == "lost"

    # Invalid stage rejected; unknown deal not found — both False (unchanged contract).
    assert sp.set_stage(deal_id, "not-a-stage") is False
    assert sp.set_stage("no-such-deal", "won") is False
