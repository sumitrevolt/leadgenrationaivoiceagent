"""Unified Inbox frontend contracts for human-in-the-loop reply actions."""

from pathlib import Path

HTML = Path("frontend/inbox.html")


def test_hot_queue_email_action_prefills_subject_and_draft():
    html = HTML.read_text(encoding="utf-8")
    start = html.index("function renderHotQueue()")
    end = html.index("async function rec(", start)
    snippet = html[start:end]

    assert "function emailDraftLink(" in html
    assert "encodeURIComponent(reSubj)" in html
    assert "encodeURIComponent(body)" in html
    assert "emailDraftLink(r.from,r.subject,r.draft)" in snippet
    assert "Email draft" in snippet
    assert "href=\"mailto:'+esc(r.from)+'\"" not in snippet


def test_stale_hot_queue_draft_requires_explicit_timing_review():
    html = HTML.read_text(encoding="utf-8")
    start = html.index("function renderHotQueue()")
    end = html.index("async function rec(", start)
    snippet = html[start:end]

    assert "function staleDraftWarning(" in html
    assert "ageDays<7" in html
    assert "aaj/kal/abhi" in html
    assert "staleDraftWarning(r.age_days,r.draft)" in snippet
    assert 'class="stale-note"' in snippet


def test_inbox_sprint_banner_and_honest_empty_states():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="hqSprint"' in html
    assert "15-minute Hot Queue sprint" in html
    assert "min-height:44px" in html
    assert "inboxOk" in html
    assert "_hqOk" in html
    assert "scraping/scoring chal rahi hai ✅" not in html
    assert "HTTP 200 page ka matlab cards nahi" in html
    assert "tabLabel(key,label)" in html
    assert "HQ_SCOPE==='admin'" in html
    assert "COUNTS.hotq=(hqSummary && Number(hqSummary.total_open||0)>0)" in html
    assert 'aria-live="polite"' in html
    assert "prefers-reduced-motion" in html
