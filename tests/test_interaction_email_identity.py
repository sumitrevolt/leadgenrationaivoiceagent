"""Email identity resolution for interactions — the funnel-linkage gate.

The bug this pins (found on production 2026-07-25):

    interactions rows = 2611
    rows with lead_id = 0          <-- every single one orphaned
    outcome='interested'  = 295    <-- warm prospects, invisible to the pipeline
    leads.status          = 'new' x 10559
    lead_status_history   = 0 rows

Cause: ``interaction_log.record()`` resolved identity from PHONE only, but
outreach is overwhelmingly EMAIL and an email interaction carries no phone. So
every reply — including "interested" ones — landed unlinked, and no lead could
ever advance.

These tests lock the resolution rules and the backfill's honesty. They avoid a
live DB: the resolution logic is exercised through the pure planning function,
and the writer is checked structurally.
"""

from __future__ import annotations

from scripts import backfill_interaction_identity as bf


# --------------------------- backfill planning ----------------------------
def _rec(iid, email, outcome="sent"):
    return {"id": iid, "email": email, "outcome": outcome}


def test_links_interaction_to_lead_by_email():
    p = bf.plan(
        [_rec("i1", "Owner@Shop.com")],
        lead_by_email={"owner@shop.com": "lead-1"},
        contact_by_email={},
        orphan_ids={"i1"},
    )
    assert p["updates"] == [("i1", "lead-1", None)]
    assert p["stats"]["linkable"] == 1


def test_email_match_is_case_and_space_insensitive():
    p = bf.plan(
        [_rec("i1", "  OWNER@shop.com  ")],
        lead_by_email={"owner@shop.com": "lead-1"},
        contact_by_email={},
        orphan_ids={"i1"},
    )
    assert p["updates"][0][1] == "lead-1"


def test_falls_back_to_contact_when_no_lead():
    p = bf.plan(
        [_rec("i1", "x@y.com")],
        lead_by_email={},
        contact_by_email={"x@y.com": "contact-9"},
        orphan_ids={"i1"},
    )
    assert p["updates"] == [("i1", None, "contact-9")]


def test_never_invents_an_id_for_unmatched_email():
    p = bf.plan(
        [_rec("i1", "stranger@nowhere.com")],
        lead_by_email={"owner@shop.com": "lead-1"},
        contact_by_email={},
        orphan_ids={"i1"},
    )
    assert p["updates"] == []
    assert p["stats"]["unmatched"] == 1
    assert p["unmatched_domains"][0][0] == "nowhere.com"


def test_skips_rows_that_are_already_linked():
    """Only NULL lead_id rows are candidates — never overwrite."""
    p = bf.plan(
        [_rec("i1", "owner@shop.com")],
        lead_by_email={"owner@shop.com": "lead-1"},
        contact_by_email={},
        orphan_ids=set(),  # i1 is not an orphan
    )
    assert p["updates"] == []
    assert p["stats"]["already_linked_or_absent"] == 1


def test_records_without_email_are_counted_not_guessed():
    p = bf.plan(
        [_rec("i1", "")],
        lead_by_email={"owner@shop.com": "lead-1"},
        contact_by_email={},
        orphan_ids={"i1"},
    )
    assert p["updates"] == []
    assert p["stats"]["no_email"] == 1


def test_interested_replies_are_counted_separately():
    """The whole point: surface the warm ones."""
    p = bf.plan(
        [_rec("i1", "a@b.com", outcome="interested"), _rec("i2", "c@d.com", outcome="sent")],
        lead_by_email={"a@b.com": "L1", "c@d.com": "L2"},
        contact_by_email={},
        orphan_ids={"i1", "i2"},
    )
    assert p["stats"]["linkable"] == 2
    assert p["stats"]["linkable_interested"] == 1


def test_plan_is_deterministic_and_sorted():
    recs = [_rec("i3", "c@x.com"), _rec("i1", "a@x.com"), _rec("i2", "b@x.com")]
    leads = {"a@x.com": "L1", "b@x.com": "L2", "c@x.com": "L3"}
    a = bf.plan(recs, leads, {}, {"i1", "i2", "i3"})
    b = bf.plan(recs, leads, {}, {"i1", "i2", "i3"})
    assert a["updates"] == b["updates"]
    assert [u[0] for u in a["updates"]] == ["i1", "i2", "i3"]


def test_plan_writes_nothing():
    """plan() must stay pure — the dry run has to be trustworthy."""
    import inspect

    src = inspect.getsource(bf.plan)
    for banned in ("execute(", "commit(", "update ", "insert "):
        assert banned not in src.lower(), banned


def test_apply_is_opt_in():
    src = (bf.ROOT / "scripts" / "backfill_interaction_identity.py").read_text(encoding="utf-8")
    assert 'apply = "--apply" in argv' in src
    # the write path must be guarded by the flag
    assert "if not apply:" in src


def test_backfill_reads_the_real_settings_key():
    """app.config exposes `database_url` lowercase.

    The first production dry run died on `getattr(settings, "DATABASE_URL")`
    returning empty. Fail-closed caught it (exit 2, nothing written), but the
    key name is pinned here so it cannot regress.
    """
    src = (bf.ROOT / "scripts" / "backfill_interaction_identity.py").read_text(encoding="utf-8")
    assert 'getattr(settings, "database_url", "")' in src
    assert "+asyncpg" in src  # async driver must be stripped for the sync engine


def test_backfill_uses_coalesce_so_it_never_overwrites():
    src = (bf.ROOT / "scripts" / "backfill_interaction_identity.py").read_text(encoding="utf-8")
    assert "coalesce(lead_id, :lid)" in src
    assert "coalesce(contact_id, :cid)" in src


def test_backfill_does_not_touch_lead_status():
    """Linking is fact; declaring a lead 'interested' is an opinion — out of scope."""
    src = (bf.ROOT / "scripts" / "backfill_interaction_identity.py").read_text(encoding="utf-8")
    low = src.lower()
    assert "update leads" not in low
    assert (
        "lead_status_history" not in low.split("SCOPE")[-1].split('"""')[0].lower()
        or "does NOT write" in src
    )


# --------------------------- forward fix ----------------------------------
def test_record_resolves_identity_by_email():
    """The writer must try email, not just phone."""
    src = (bf.ROOT / "app" / "platform" / "interaction_log.py").read_text(encoding="utf-8")
    assert "func.lower(Contact.email) == em" in src
    assert "func.lower(Lead.email) == em" in src


def test_record_prefers_explicit_lead_id_over_lookup():
    src = (bf.ROOT / "app" / "platform" / "interaction_log.py").read_text(encoding="utf-8")
    assert 'resolved_lead_id = (lead_id or "").strip() or None' in src
    assert "if not resolved_lead_id:" in src


def test_record_inherits_lead_from_matched_contact():
    src = (bf.ROOT / "app" / "platform" / "interaction_log.py").read_text(encoding="utf-8")
    assert 'getattr(row, "lead_id", None)' in src


def test_record_identity_stays_best_effort():
    """Identity resolution must never break the outreach path."""
    src = (bf.ROOT / "app" / "platform" / "interaction_log.py").read_text(encoding="utf-8")
    body = src.split("async def record(", 1)[1]
    assert "except Exception as e:" in body
    assert "[interaction_log] db skip" in body
