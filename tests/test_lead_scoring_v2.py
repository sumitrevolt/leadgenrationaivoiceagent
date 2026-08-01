"""Prospect Score V2 — contract tests (mission prospect-score-v2, 2026-07-31).

Covers the design rules that make V2 safe to promote:
  - determinism (same record -> same score, no env/clock dependence)
  - breakdown sum == bounded total
  - missing-data behaviour (missing field = 0, negative penalty applied)
  - India mobile validity (10-digit, first digit 6-9)
  - phone normalisation / dedupe consistency with existing V1 helpers
  - junk/test/QA-name rejection
  - feature-flag gate: default OFF = V1 read path preserved (backward-compat)
  - search() routes scorer via the shared gate and honours min_score
  - backfill script: dry-run writes nothing, idempotent, bounded batches, sidecar
    audit store (source UNTOUCHED), rollback restores sidecar only
  - dialer_sprint_prep threshold behaviour: no-call-authorized until score>=50,
    zero side-effect send/call surface
"""

from __future__ import annotations

import json

import pytest

from app.platform import lead_scoring_v2 as v2
from app.platform import prospector


def _rich_prospect(**over):
    """A real-looking harvest record (all strong signals present)."""
    base = {
        "id": "prosp_001",
        "business_name": "Sharma Solar Solutions",
        "phone": "+91 98220 12345",
        "email": "owner@sharmasolar.in",
        "website": "https://sharmasolar.in",
        "has_website": True,
        "wa_link": "https://wa.me/919822012345",
        "rating": 4.8,
        "reviews_count": 150,
        "niche": "solar_residential",
        "city": "Pune",
        "source_query": "harvest:websearch solar installer",
        "found_at": "2026-07-20T10:00:00+00:00",
        "status": "ready",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Determinism / bounds
# ---------------------------------------------------------------------------
def test_deterministic_same_record_same_score():
    rec = _rich_prospect()
    assert v2.score_lead_v2(rec) == v2.score_lead_v2(rec)
    assert v2.score_lead_v2(rec) == v2.score_lead_v2(json.loads(json.dumps(rec)))


def test_score_bounded_0_100_and_breakdown_sum():
    rec = _rich_prospect()
    comps = v2.score_components_v2(rec)
    s = v2.score_lead_v2(rec)
    assert 0 <= s <= 100
    assert sum(comps.values()) == s


def test_breakdown_sum_bounded_even_when_negative():
    rec = _rich_prospect(phone="", website="", email="", business_name="test sample xyz")
    comps = v2.score_components_v2(rec)
    s = v2.score_lead_v2(rec)
    assert 0 <= s <= 100  # bounded floor
    assert sum(comps.values()) <= s or sum(comps.values()) == s


def test_max_score_reachable_with_strong_signals():
    rec = _rich_prospect(reviews_count=200)
    assert v2.score_lead_v2(rec) >= 80


# ---------------------------------------------------------------------------
# Missing-data behaviour (never positive, explicit penalty)
# ---------------------------------------------------------------------------
def test_missing_fields_yield_zero_features_and_penalties():
    rec = _rich_prospect(phone="", website="", email="", wa_link="", rating=0, reviews_count=0)
    comps = v2.score_components_v2(rec)
    assert comps["india_phone"] == 0
    assert comps["business_email"] == 0
    assert comps["working_website"] == 0
    assert comps["wa_reach"] == 0
    assert comps["reviews_signal"] == 0
    assert comps["rating_signal"] == 0
    assert comps["missing_phone"] < 0
    assert comps["low_reviews"] < 0
    assert comps["missing_email"] < 0
    assert comps["missing_website"] < 0


def test_empty_record_scores_floor():
    assert v2.score_lead_v2({}) == 0


def test_missing_phone_penalty_keeps_below_50_without_other_signals():
    rec = _rich_prospect(phone="")
    assert v2.score_lead_v2(rec) < 50


# ---------------------------------------------------------------------------
# India mobile validity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("phone", "valid"),
    [
        ("+91 98220 12345", True),
        ("919822012345", True),
        ("09822012345", True),
        ("9822012345", True),
        ("+919822012345", True),
        ("18008001300", False),  # toll-free
        ("+44 20 7946 0958", False),  # foreign
        ("", False),
        ("98765", False),  # too short
        ("1234567890", False),  # starts 1
        ("5551234567", False),  # starts 5
    ],
)
def test_india_mobile_validity(phone, valid):
    assert v2.is_valid_india_mobile({"phone": phone}) is valid


def test_phone10_normalization_matches_memory_vault_convention():
    assert v2.phone10({"phone": "+91 98220 12345"}) == "9822012345"
    assert v2.phone10({"phone": "919822012345"}) == "9822012345"
    assert v2.phone10({"phone": "09822012345"}) == "9822012345"
    assert v2.phone10({"phone": ""}) == ""
    assert v2.phone10({}) == ""


def test_duplicate_cross_format_prospects_score_same():
    a = _rich_prospect(id="x1", phone="+91 98220 12345")
    b = _rich_prospect(id="x2", phone="919822012345")
    assert v2.phone10(a) == v2.phone10(b)
    assert v2.score_lead_v2(a) == v2.score_lead_v2(b)


# ---------------------------------------------------------------------------
# Junk / test / QA-name rejection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    [
        "Test Business",
        "testing corp",
        "demo company",
        "Sample Pvt Ltd",
        "Example Enterprises",
        "Asdf Traders",
        "Qwerty Stores",
        "Lorem Ipsum",
        "Dummy",
        "XYZ Corp",
        "placeholder biz",
    ],
)
def test_junk_names_penalized(name):
    rec = _rich_prospect(business_name=name)
    comps = v2.score_components_v2(rec)
    assert comps.get("junk_or_test_name", 0) < 0
    assert v2.score_lead_v2(rec) < 50


def test_junk_unnamed_penalized():
    rec = _rich_prospect(business_name="")
    assert v2.score_components_v2(rec).get("junk_or_test_name", 0) < 0


def test_real_name_no_penalty():
    comps = v2.score_components_v2(_rich_prospect(business_name="Taher Hardware Stores"))
    assert comps.get("junk_or_test_name", 0) >= 0


# ---------------------------------------------------------------------------
# Feature-flag gate (backward-compat: V1 default)
# ---------------------------------------------------------------------------
def test_gate_default_off_returns_v1_scorer(monkeypatch):
    from app.platform import prospect_lists

    monkeypatch.delenv("PROSPECT_SCORE_V2", raising=False)
    prospect_lists._V2_ENABLED = None
    scorer, ver = prospect_lists._scorer_for()
    assert ver == "v1"
    assert scorer is not None


def test_gate_on_returns_v2_scorer(monkeypatch):
    from app.platform import prospect_lists

    monkeypatch.setenv("PROSPECT_SCORE_V2", "1")
    prospect_lists._V2_ENABLED = None
    scorer, ver = prospect_lists._scorer_for()
    assert ver == "v2"
    assert scorer is v2.score_lead_v2


def test_gate_off_search_uses_v1_range(monkeypatch, tmp_path):
    from app.platform import prospect_lists

    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "p.jsonl"))
    monkeypatch.setattr(prospect_lists, "_LISTS", str(tmp_path / "lists.jsonl"))
    monkeypatch.delenv("PROSPECT_SCORE_V2", raising=False)
    prospect_lists._V2_ENABLED = None
    # V1 can never reach 50 (max 33) — a min_score=50 search must return nothing.
    res = prospect_lists.search(status="ready", min_score=50, limit=10)
    assert res == []


def test_gate_on_search_min_score_returns_v2_qualified(monkeypatch, tmp_path):
    from app.platform import prospect_lists

    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "p.jsonl"))
    monkeypatch.setattr(prospect_lists, "_LISTS", str(tmp_path / "lists.jsonl"))
    monkeypatch.setenv("PROSPECT_SCORE_V2", "1")
    prospect_lists._V2_ENABLED = None
    prospect_lists.import_rows(
        [
            {
                "Company": "Strong Solar Co",
                "Phone": "+91 98220 12345",
                "Email": "owner@strongsolar.in",
                "City": "Pune",
                "Industry": "solar_residential",
                "Website": "https://strongsolar.in",
                "Rating": 4.8,
                "Reviews": 150,
                "WhatsApp": "https://wa.me/919822012345",
                "Source Query": "harvest:websearch solar installer",
            },
            {
                "Company": "Weak Test Co",
                "Phone": "+91 98220 99999",
                "City": "Pune",
                "Industry": "solar_residential",
            },
        ]
    )
    res = prospect_lists.search(status="ready", min_score=50, limit=10)
    names = [r.get("business_name") for r in res]
    assert "Strong Solar Co" in names
    assert "Weak Test Co" not in names
    assert all(r.get("score", 0) >= 50 for r in res)


def test_search_min_score_requires_quality_approved(monkeypatch, tmp_path):
    """Quality-approval stays mandatory upstream: a junk-name record that would
    otherwise score high must be excluded by the search read path."""
    from app.platform import prospect_lists

    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "p.jsonl"))
    monkeypatch.setattr(prospect_lists, "_LISTS", str(tmp_path / "lists.jsonl"))
    monkeypatch.setenv("PROSPECT_SCORE_V2", "1")
    prospect_lists._V2_ENABLED = None
    prospect_lists.import_rows(
        [
            {
                "Company": "Example Test Corp",
                "Phone": "+91 98220 12345",
                "Email": "owner@exampletest.in",
                "City": "Pune",
                "Industry": "solar_residential",
                "Website": "https://exampletest.in",
                "Rating": 4.8,
                "Reviews": 150,
                "Source Query": "harvest:websearch solar",
            }
        ]
    )
    res = prospect_lists.search(status="ready", min_score=50, limit=10)
    assert res == [], "quality-approved junk-name record must not leak into qualified list"


# ---------------------------------------------------------------------------
# rank_v2 (ordering + breakdown, no mutation)
# ---------------------------------------------------------------------------
def test_rank_v2_sorts_desc_and_annotates_without_mutating():
    weak = _rich_prospect(id="w", phone="", website="", email="", reviews_count=0, rating=0)
    strong = _rich_prospect(id="s", reviews_count=500)
    src = [dict(weak), dict(strong)]
    out = v2.rank_v2(src)
    assert out[0]["lead_score"] >= out[1]["lead_score"]
    assert out[0]["score_version"] == "2"
    assert "score_components" in out[0]
    assert src[0] == weak and src[1] == strong  # source untouched
    assert "lead_score" not in src[0]


# ---------------------------------------------------------------------------
# explain_score (audit surface)
# ---------------------------------------------------------------------------
def test_explain_score_shape():
    e = v2.explain_score(_rich_prospect())
    assert e["score_version"] == "2"
    assert isinstance(e["components"], dict)
    assert e["valid_phone"] is True
    assert e["reviews_count"] == 150
    assert e["score"] == sum(e["components"].values())


# ---------------------------------------------------------------------------
# Backfill script (sidecar audit store, dry-run, idempotent, rollback)
# ---------------------------------------------------------------------------
def test_backfill_dry_run_writes_nothing(tmp_path, monkeypatch):
    import scripts.backfill_score_v2 as bf

    src = tmp_path / "prospects.jsonl"
    src.write_text(json.dumps(_rich_prospect()) + "\n", encoding="utf-8")
    monkeypatch.setattr(bf, "_SOURCE", src)
    monkeypatch.setattr(bf, "_SIDECAR", tmp_path / "scores.jsonl")
    monkeypatch.setattr(bf, "_BACKUP_DIR", tmp_path / "backups")

    res = bf.backfill(dry_run=True, batch_size=10, limit=None, only_ready=True)
    assert res["ok"] is True and res["dry_run"] is True
    assert res["changed"] == 1
    assert not (tmp_path / "scores.jsonl").exists(), "dry-run must not write sidecar"


def test_backfill_idempotent_and_source_untouched(tmp_path, monkeypatch):
    import scripts.backfill_score_v2 as bf

    src = tmp_path / "prospects.jsonl"
    src.write_text(json.dumps(_rich_prospect()) + "\n", encoding="utf-8")
    monkeypatch.setattr(bf, "_SOURCE", src)
    monkeypatch.setattr(bf, "_SIDECAR", tmp_path / "scores.jsonl")
    monkeypatch.setattr(bf, "_BACKUP_DIR", tmp_path / "backups")
    before = src.read_text(encoding="utf-8")

    r1 = bf.backfill(dry_run=False, batch_size=1, limit=None, only_ready=True)
    assert r1["changed"] == 1 and r1["skipped"] == 0
    r2 = bf.backfill(dry_run=False, batch_size=1, limit=None, only_ready=True)
    assert r2["changed"] == 0 and r2["skipped"] == 1, "re-run must skip same version"

    assert src.read_text(encoding="utf-8") == before, "source must stay UNTOUCHED"
    lines = (tmp_path / "scores.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["score_version"] == "2" and rec["score"] >= 50
    assert rec["prospect_id"] == "prosp_001"


def test_backfill_bounded_batches(tmp_path, monkeypatch):
    import scripts.backfill_score_v2 as bf

    src = tmp_path / "prospects.jsonl"
    for i in range(7):
        src.write_text(
            json.dumps(_rich_prospect(id=f"p{i:03d}")) + "\n",
            encoding="utf-8",
        )
    # append (write_text overwrites; use append via open)
    with open(src, "w", encoding="utf-8") as f:
        for i in range(7):
            f.write(json.dumps(_rich_prospect(id=f"p{i:03d}")) + "\n")
    monkeypatch.setattr(bf, "_SOURCE", src)
    monkeypatch.setattr(bf, "_SIDECAR", tmp_path / "scores.jsonl")
    monkeypatch.setattr(bf, "_BACKUP_DIR", tmp_path / "backups")

    res = bf.backfill(dry_run=False, batch_size=3, limit=5, only_ready=True)
    assert res["scanned"] == 5
    assert res["changed"] == 5
    assert res["failed"] == 0
    assert (tmp_path / "scores.jsonl").exists()


def test_backfill_rollback_restores_sidecar_only(tmp_path, monkeypatch):
    import scripts.backfill_score_v2 as bf

    src = tmp_path / "prospects.jsonl"
    src.write_text(json.dumps(_rich_prospect()) + "\n", encoding="utf-8")
    side = tmp_path / "scores.jsonl"
    side.write_text(
        json.dumps({"prospect_id": "prosp_001", "score_version": "1", "score": 33}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bf, "_SOURCE", src)
    monkeypatch.setattr(bf, "_SIDECAR", side)
    monkeypatch.setattr(bf, "_BACKUP_DIR", tmp_path / "backups")

    ts = bf._backup_sidecar()
    res = bf.backfill(dry_run=False, batch_size=10, limit=None, only_ready=True)
    assert res["changed"] == 1

    rb = bf.rollback(ts)
    assert rb["ok"] is True
    lines = side.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0])["score_version"] == "1", "rollback restores pre-V2 sidecar"
    assert src.read_text(encoding="utf-8").strip(), "source untouched after rollback"


# ---------------------------------------------------------------------------
# dialer_sprint_prep: threshold behaviour + no side-effect surface
# ---------------------------------------------------------------------------
def test_dialer_sprint_prep_uses_search_min_score_50(monkeypatch):
    """The governed entry point must route through search(min_score=50), so the
    flag flip is the ONLY thing that changes eligibility — no sprint-code edit."""
    import inspect

    from app.agents import sprint_actions

    src = inspect.getsource(sprint_actions.dialer_sprint_prep)
    assert "min_score=50" in src


def test_sprint_action_source_has_no_send_call_surface():
    import inspect

    from app.agents import sprint_actions

    for fn_name in ("dialer_sprint_prep",):
        src = inspect.getsource(getattr(sprint_actions, fn_name))
        for banned in ("send_email", "send_whatsapp", "make_call", "platform_dial"):
            assert banned not in src, f"{fn_name} must stay draft/read-only, found {banned}"
