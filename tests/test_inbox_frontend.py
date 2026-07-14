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
