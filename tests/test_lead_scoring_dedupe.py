"""top_hot_leads() phone-dedupe + scan-cap regression (2026-07-04 dialer-sprint
audit). Same underlying business can be stored under two raw phone formats by
different ingestion paths (see tests/test_lead_dedup_2026_07_01.py for the
ingestion-side fix) — the "who to call next" ranking must not surface both.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.platform import lead_scoring


class _FakeLead:
    def __init__(self, **kw):
        self._d = kw

    def to_dict(self):
        return dict(self._d)


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


class _FakeAsyncSession:
    def __init__(self, items):
        self._items = items

    async def execute(self, *a, **k):
        return _FakeResult(self._items)


def _patch_leads(monkeypatch, items):
    @asynccontextmanager
    async def _fake_get_async_session():
        yield _FakeAsyncSession(items)

    monkeypatch.setattr("app.models.base.get_async_session", _fake_get_async_session)


def test_phone_key_normalizes_format_variants():
    assert lead_scoring._phone_key({"phone": "+919967993679"}) == "9967993679"
    assert lead_scoring._phone_key({"phone": "919967993679"}) == "9967993679"
    assert lead_scoring._phone_key({"phone": "09967993679"}) == "9967993679"
    assert lead_scoring._phone_key({"phone": ""}) == ""
    assert lead_scoring._phone_key({}) == ""


@pytest.mark.asyncio
async def test_top_hot_leads_dedupes_cross_format_duplicates(monkeypatch):
    """The exact live scenario: same business, two Lead rows, phone stored
    with vs without '+91' — must appear ONCE in the ranked output."""
    monkeypatch.setenv("LEAD_HOT_THRESHOLD", "0")  # everything counts as "hot" for this test
    items = [
        _FakeLead(
            company_name="Passport Office Solapur",
            phone="+916019377936",
            status="new",
            source="import",
            category="immigration",
            niche="immigration",
        ),
        _FakeLead(
            company_name="Passport Office Solapur",
            phone="916019377936",
            status="new",
            source="google_maps",
            category=None,
            niche=None,
        ),
        _FakeLead(
            company_name="Genuinely Different Biz",
            phone="+919111111111",
            status="new",
            source="google_maps",
        ),
    ]
    _patch_leads(monkeypatch, items)

    out = await lead_scoring.top_hot_leads(limit=25)

    assert out["ok"] is True
    assert out["count"] == 3  # raw rows scanned
    assert out["unique_count"] == 2  # after phone-dedupe
    phones = [lead_scoring._phone_key(x) for x in out["leads"]]
    assert phones.count("6019377936") == 1, "duplicate must be collapsed to one entry"
    assert "9111111111" in phones


@pytest.mark.asyncio
async def test_top_hot_leads_keeps_higher_scoring_duplicate(monkeypatch):
    """When duplicates differ in completeness (one has category/niche set,
    contributing +6 niche-fit points), the dedupe must keep the HIGHER-scored
    row, not an arbitrary one — the richer record is the better one to call with.

    Note: source alone isn't a safe differentiator here — _SOURCE_PTS gives
    google_maps(10) vs import(4), which happens to exactly offset the +6
    niche_fit bonus from category/niche being set. So this fixture adds
    phone_verified (+8) to the richer duplicate to force an unambiguous gap,
    same as a real verified/unverified pair would differ in practice."""
    monkeypatch.setenv("LEAD_HOT_THRESHOLD", "0")
    richer = _FakeLead(
        company_name="Test Co",
        phone="+919967993679",
        status="new",
        source="import",
        category="hair_transplant",
        niche="hair_transplant",
        phone_verified=True,
    )
    thinner = _FakeLead(
        company_name="Test Co",
        phone="919967993679",
        status="new",
        source="google_maps",
        category=None,
        niche=None,
        phone_verified=False,
    )
    _patch_leads(monkeypatch, [thinner, richer])  # order shouldn't matter — rank() sorts first

    out = await lead_scoring.top_hot_leads(limit=25)

    assert out["unique_count"] == 1
    assert out["leads"][0]["source"] == "import", "must keep the richer/higher-scoring duplicate"
