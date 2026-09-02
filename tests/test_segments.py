"""Pure tests for dynamic segments (app/platform/segments.py).

No network / no DB. _match_record across all ops + all/any mode, CRUD
round-trip on a temp store (monkeypatched path), evaluate grouping on an
in-memory pool (monkeypatched loader).
"""

from __future__ import annotations

import pytest

from app.platform import segments


# --------------------------- _match_record ops --------------------------- #
REC = {
    "id": "p1",
    "business_name": "Sharma Solar",
    "niche": "solar_residential",
    "city": "Pune",
    "status": "ready",
    "source": "scrape",
    "email": "owner@sharmasolar.in",
    "score": 72,
}
REC_NO_EMAIL = {**REC, "id": "p2", "email": "", "score": 30, "city": "Delhi"}


def test_eq_string():
    assert segments._match_record(
        REC, [{"field": "niche", "op": "eq", "value": "solar_residential"}], "all"
    )
    assert not segments._match_record(
        REC, [{"field": "niche", "op": "eq", "value": "real_estate"}], "all"
    )


def test_ne_string():
    assert segments._match_record(REC, [{"field": "city", "op": "ne", "value": "Mumbai"}], "all")
    assert not segments._match_record(REC, [{"field": "city", "op": "ne", "value": "Pune"}], "all")


def test_contains():
    assert segments._match_record(
        REC, [{"field": "business_name", "op": "contains", "value": "solar"}], "all"
    )
    assert not segments._match_record(
        REC, [{"field": "business_name", "op": "contains", "value": "dental"}], "all"
    )


def test_numeric_gt_gte_lt_lte():
    assert segments._match_record(REC, [{"field": "lead_score", "op": "gt", "value": 70}], "all")
    assert segments._match_record(REC, [{"field": "lead_score", "op": "gte", "value": 72}], "all")
    assert not segments._match_record(
        REC, [{"field": "lead_score", "op": "gt", "value": 72}], "all"
    )
    assert segments._match_record(REC, [{"field": "lead_score", "op": "lt", "value": 80}], "all")
    assert segments._match_record(REC, [{"field": "lead_score", "op": "lte", "value": 72}], "all")
    # string-typed value should still coerce
    assert segments._match_record(REC, [{"field": "lead_score", "op": "gte", "value": "70"}], "all")


def test_in_list_and_csv():
    assert segments._match_record(
        REC, [{"field": "city", "op": "in", "value": ["Pune", "Mumbai"]}], "all"
    )
    assert segments._match_record(
        REC, [{"field": "city", "op": "in", "value": "Pune, Mumbai"}], "all"
    )
    assert not segments._match_record(
        REC, [{"field": "city", "op": "in", "value": ["Delhi", "Mumbai"]}], "all"
    )


def test_exists_has_email_bool():
    # has_email derived from email field
    assert segments._match_record(REC, [{"field": "has_email", "op": "eq", "value": True}], "all")
    assert not segments._match_record(
        REC_NO_EMAIL, [{"field": "has_email", "op": "eq", "value": True}], "all"
    )
    # exists op on a present string field
    assert segments._match_record(REC, [{"field": "email", "op": "exists", "value": True}], "all")
    assert segments._match_record(
        REC_NO_EMAIL, [{"field": "email", "op": "exists", "value": False}], "all"
    )


def test_all_vs_any_mode():
    conds = [
        {"field": "niche", "op": "eq", "value": "solar_residential"},
        {"field": "lead_score", "op": "gt", "value": 90},  # fails
    ]
    assert not segments._match_record(REC, conds, "all")
    assert segments._match_record(REC, conds, "any")  # first cond passes


def test_empty_conditions_matches_all():
    assert segments._match_record(REC, [], "all")
    assert segments._match_record(REC, [], "any")


def test_bad_op_never_raises():
    # garbage op -> False, no exception
    assert (
        segments._match_record(REC, [{"field": "niche", "op": "weird", "value": "x"}], "all")
        is False
    )


# --------------------------- CRUD round-trip --------------------------- #
@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    p = tmp_path / "segments.jsonl"
    monkeypatch.setattr(segments, "_STORE", str(p))
    return p


def test_create_list_get_delete_roundtrip(tmp_store):
    assert segments.list_segments() == []
    rec = segments.create_segment(
        "Hot Pune Solar",
        match="all",
        conditions=[
            {"field": "city", "op": "eq", "value": "Pune"},
            {"field": "lead_score", "op": "gte", "value": 60},
        ],
    )
    assert rec["id"]
    assert rec["match"] == "all"
    assert len(rec["conditions"]) == 2

    listed = segments.list_segments()
    assert len(listed) == 1
    assert listed[0]["id"] == rec["id"]

    got = segments.get_segment(rec["id"])
    assert got and got["name"] == "Hot Pune Solar"
    assert segments.get_segment("nope") is None

    assert segments.delete_segment(rec["id"]) is True
    assert segments.delete_segment(rec["id"]) is False
    assert segments.list_segments() == []


def test_create_normalizes_bad_op_and_match(tmp_store):
    rec = segments.create_segment(
        "x",
        match="garbage",
        conditions=[{"field": "niche", "op": "nope", "value": "a"}, {"field": "", "op": "eq"}],
    )
    assert rec["match"] == "all"  # garbage -> all
    assert len(rec["conditions"]) == 1  # empty-field cond dropped
    assert rec["conditions"][0]["op"] == "eq"  # bad op -> eq


# --------------------------- evaluate grouping --------------------------- #
POOL = [
    {
        "id": "a",
        "business_name": "Sharma Solar",
        "niche": "solar_residential",
        "city": "Pune",
        "status": "ready",
        "email": "a@x.in",
        "score": 80,
    },
    {
        "id": "b",
        "business_name": "Delhi Dental",
        "niche": "dental",
        "city": "Delhi",
        "status": "ready",
        "email": "",
        "score": 40,
    },
    {
        "id": "c",
        "business_name": "Pune Estates",
        "niche": "real_estate",
        "city": "Pune",
        "status": "ready",
        "email": "c@x.in",
        "score": 65,
    },
]


def test_evaluate_all_mode(monkeypatch):
    monkeypatch.setattr(segments, "_load_pool", lambda limit=500: POOL)
    seg = {
        "match": "all",
        "conditions": [
            {"field": "city", "op": "eq", "value": "Pune"},
            {"field": "lead_score", "op": "gte", "value": 70},
        ],
    }
    res = segments.evaluate(seg)
    assert res["count"] == 1
    assert res["matched_ids"] == ["a"]
    assert res["sample"][0]["business_name"] == "Sharma Solar"
    assert res["sample"][0]["lead_score"] == 80
    assert res["sample"][0]["has_email"] is True


def test_evaluate_any_mode(monkeypatch):
    monkeypatch.setattr(segments, "_load_pool", lambda limit=500: POOL)
    seg = {
        "match": "any",
        "conditions": [
            {"field": "niche", "op": "eq", "value": "dental"},
            {"field": "city", "op": "eq", "value": "Pune"},
        ],
    }
    res = segments.evaluate(seg)
    assert res["count"] == 3  # dental(b) OR pune(a,c)
    assert set(res["matched_ids"]) == {"a", "b", "c"}


def test_evaluate_has_email_filter(monkeypatch):
    monkeypatch.setattr(segments, "_load_pool", lambda limit=500: POOL)
    seg = {"match": "all", "conditions": [{"field": "has_email", "op": "eq", "value": True}]}
    res = segments.evaluate(seg)
    assert set(res["matched_ids"]) == {"a", "c"}


def test_evaluate_empty_pool_never_raises(monkeypatch):
    monkeypatch.setattr(segments, "_load_pool", lambda limit=500: [])
    res = segments.evaluate({"match": "all", "conditions": []})
    assert res == {"count": 0, "sample": [], "matched_ids": []}
