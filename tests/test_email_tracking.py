"""Pure-python tests for app.marketing.email_tracking (no network / no DB).

Covers: token round-trip, instrument() pixel+link wrap when enabled,
instrument() unchanged when disabled, record_open/record_click + stats,
invalid token verify -> None, click decodes original URL, non-http scheme reject.
"""

from __future__ import annotations

import importlib

import pytest

import app.marketing.email_tracking as et


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Point the event store at a temp file so tests don't touch real data/."""
    monkeypatch.setattr(et, "_STORE", tmp_path / "email_events.jsonl", raising=True)
    yield


def _enable(monkeypatch):
    monkeypatch.setattr(et, "enabled", lambda: True, raising=True)


# --------------------------------------------------------------------------- #
# Token round-trip
# --------------------------------------------------------------------------- #
def test_open_token_round_trip():
    tok = et.make_open_token("123", "cold_email")
    assert tok
    data = et.verify_open_token(tok)
    assert data is not None
    assert data["recipient_id"] == "123"
    assert data["campaign"] == "cold_email"
    assert data["type"] == "o"


def test_click_token_round_trip_decodes_url():
    url = "https://example.com/path?a=1&b=2|x"
    tok = et.make_click_token("42", "cold_email", url)
    data = et.verify_click_token(tok)
    assert data is not None
    assert data["url"] == url
    assert data["recipient_id"] == "42"


def test_invalid_token_returns_none():
    assert et.verify_open_token("not-a-real-token") is None
    assert et.verify_click_token("garbage.....") is None


def test_tampered_token_rejected():
    tok = et.make_open_token("1", "c")
    assert et.verify_open_token(tok + "x") is None


def test_token_type_not_confused():
    """An open token must not verify as a click token and vice-versa."""
    otok = et.make_open_token("1", "c")
    assert et.verify_click_token(otok) is None
    ctok = et.make_click_token("1", "c", "https://x.com")
    assert et.verify_open_token(ctok) is None


def test_non_http_scheme_rejected():
    bad = et.make_click_token("1", "c", "javascript:alert(1)")
    assert et.verify_click_token(bad) is None
    bad2 = et.make_click_token("1", "c", "ftp://host/file")
    assert et.verify_click_token(bad2) is None


# --------------------------------------------------------------------------- #
# instrument()
# --------------------------------------------------------------------------- #
def test_instrument_disabled_returns_unchanged(monkeypatch):
    monkeypatch.setattr(et, "enabled", lambda: False, raising=True)
    html = '<html><body><a href="https://x.com">hi</a></body></html>'
    assert et.instrument(html, "1", "cold_email") == html


def test_instrument_empty_returns_unchanged(monkeypatch):
    _enable(monkeypatch)
    assert et.instrument("", "1", "cold_email") == ""


def test_instrument_injects_pixel_and_wraps_link(monkeypatch):
    _enable(monkeypatch)
    html = '<html><body><a href="https://example.com/landing">Click</a></body></html>'
    out = et.instrument(html, "55", "cold_email")
    # pixel injected before </body>
    assert "/t/o/" in out
    assert ".gif" in out
    assert 'width="1"' in out
    assert out.index("/t/o/") < out.index("</body>")
    # link rewritten through /t/c/
    assert "/t/c/" in out
    assert 'href="https://example.com/landing"' not in out


def test_instrument_skips_mailto_and_unsub(monkeypatch):
    _enable(monkeypatch)
    html = (
        "<body>"
        '<a href="mailto:x@y.com">mail</a>'
        '<a href="https://leadsgenai.in/api/lifecycle/outreach-unsub/abc">unsub</a>'
        "</body>"
    )
    out = et.instrument(html, "9", "cold_email")
    assert "mailto:x@y.com" in out  # untouched
    assert "outreach-unsub/abc" in out  # untouched
    # no link should have been wrapped
    assert "/t/c/" not in out


def test_instrument_no_body_tag_appends_pixel(monkeypatch):
    _enable(monkeypatch)
    html = "<p>hello</p>"
    out = et.instrument(html, "1", "c")
    assert out.startswith("<p>hello</p>")
    assert "/t/o/" in out


def test_instrument_idempotent_skips_already_tracked(monkeypatch):
    _enable(monkeypatch)
    html = '<body><a href="https://leadsgenai.in/t/c/sometoken">x</a></body>'
    out = et.instrument(html, "1", "c")
    # already-tracked link left alone (only one /t/c/ occurrence, the original)
    assert out.count("/t/c/") == 1


# --------------------------------------------------------------------------- #
# record + stats
# --------------------------------------------------------------------------- #
def test_record_open_and_click_and_stats():
    ot = et.make_open_token("u1", "camp1")
    assert et.record_open(ot) is True
    assert et.record_open(ot) is True  # second open counts (dedupe not required)

    ct = et.make_click_token("u1", "camp1", "https://t.co/x")
    url = et.record_click(ct)
    assert url == "https://t.co/x"

    # different recipient, same campaign
    et.record_open(et.make_open_token("u2", "camp1"))

    s = et.stats()
    assert s["opens"] == 3
    assert s["clicks"] == 1
    assert s["unique_opens"] == 2
    assert s["unique_clicks"] == 1
    assert "camp1" in s["by_campaign"]
    assert s["by_campaign"]["camp1"]["unique_opens"] == 2


def test_stats_campaign_filter():
    et.record_open(et.make_open_token("a", "alpha"))
    et.record_open(et.make_open_token("b", "beta"))
    s = et.stats(campaign="alpha")
    assert s["opens"] == 1
    assert s["unique_opens"] == 1


def test_record_open_bad_token_returns_false():
    assert et.record_open("bad") is False


def test_record_click_bad_token_returns_none():
    assert et.record_click("bad") is None


def test_stats_empty_store_safe():
    s = et.stats()
    assert s == {
        "opens": 0,
        "clicks": 0,
        "unique_opens": 0,
        "unique_clicks": 0,
        "by_campaign": {},
    }


def test_module_imports_clean():
    importlib.reload(et)
