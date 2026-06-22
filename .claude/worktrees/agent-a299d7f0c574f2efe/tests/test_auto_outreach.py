"""
Tests: automated email outreach (app/platform/auto_outreach.py).
=================================================================

No real SMTP / network:
  - prospector._PROSPECTS_FILE tmp_path pe redirect (real data/ na chhue)
  - email_sender.send_email ko async stub se monkeypatch
  - settings.auto_email_outreach / smtp_user monkeypatch
  - throttle sleep ko no-op kar dete hain (test fast rahe)
  - email_verify.verify (MX/DNS lookup) ko deterministic stub se monkeypatch
    (autouse) — test domains fake hain, real DNS kabhi nahi hota
"""

import json
import os
from datetime import datetime, timedelta

import pytest

from app.config import settings as app_settings
from app.platform import auto_outreach, prospector


@pytest.fixture(autouse=True)
def _hermetic_email_verify(monkeypatch):
    """MX-deliverability gate ko hermetic banao — koi real DNS lookup nahi.

    `auto_outreach._valid_email` ab `email_verify.verify` (email-validator + MX)
    call karta hai; test emails ke domains fake hain to real DNS = 0 sends.
    Stub same return-shape deta hai ("absent" reason NAHI, taaki _valid_email
    verifier ka verdict hi use kare) — syntax-level ok/not-ok deterministic.
    """
    from app.lead_scraper import email_verify

    def _fake_verify(addr, check_mx=True):
        a = (addr or "").strip()
        ok = "@" in a and "." in a.split("@")[-1] and len(a) >= 6
        return {"ok": ok, "email": a, "reason": "valid (stub)" if ok else "bad syntax (stub)"}

    monkeypatch.setattr(email_verify, "verify", _fake_verify)


@pytest.fixture
def tmp_prospects(monkeypatch, tmp_path):
    """prospects.jsonl ko tmp_path pe le jao."""
    pfile = os.path.join(str(tmp_path), "prospects.jsonl")
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", pfile)
    return pfile


@pytest.fixture
def no_sleep(monkeypatch):
    """Throttle sleep ko instant kar do."""

    async def _instant(*_a, **_k):
        return None

    monkeypatch.setattr(auto_outreach.asyncio, "sleep", _instant)


def _seed(pfile, rec):
    with open(pfile, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# _email_subject_body
# --------------------------------------------------------------------------- #
class TestSubjectBody:
    def test_returns_personalized_non_empty(self):
        prospect = {
            "business_name": "Sharma Solar",
            "city": "Pune",
            "rating": 4.3,
            "reviews_count": 120,
            "email": "info@sharmasolar.in",
        }
        subject, text, html = auto_outreach._email_subject_body(prospect)
        assert subject.strip()
        assert "Sharma Solar" in subject
        assert text.strip() and html.strip()
        # personalization: business name + a real signal acknowledged
        assert "Sharma Solar" in text
        assert "120" in text  # reviews count mentioned
        # mandatory unsubscribe + sender footer
        assert "REMOVE" in text
        assert "LeadGen AI" in text
        assert "leadsgenai.in/audit" in text

    def test_handles_missing_fields(self):
        # No name/rating/reviews — must still build a sane email.
        subject, text, html = auto_outreach._email_subject_body({})
        assert subject.strip() and text.strip() and html.strip()
        assert "REMOVE" in text


# --------------------------------------------------------------------------- #
# run_email_outreach — guards
# --------------------------------------------------------------------------- #
class TestGuards:
    @pytest.mark.asyncio
    async def test_flag_off_skips(self, monkeypatch):
        monkeypatch.setattr(app_settings, "auto_email_outreach", False, raising=False)
        out = await auto_outreach.run_email_outreach()
        assert out == {"skipped": "AUTO_EMAIL_OUTREACH off"}

    @pytest.mark.asyncio
    async def test_email_unconfigured_skips(self, monkeypatch):
        monkeypatch.setattr(app_settings, "auto_email_outreach", True, raising=False)
        monkeypatch.setattr(app_settings, "smtp_user", "", raising=False)
        # neither SMTP nor an email API key configured
        monkeypatch.setattr(app_settings, "resend_api_key", "", raising=False)
        monkeypatch.setattr(app_settings, "brevo_api_key", "", raising=False)
        out = await auto_outreach.run_email_outreach()
        assert out == {"skipped": "email_unconfigured"}


# --------------------------------------------------------------------------- #
# run_email_outreach — happy path
# --------------------------------------------------------------------------- #
class TestRun:
    @pytest.mark.asyncio
    async def test_sends_and_marks_prospect(self, monkeypatch, tmp_prospects, no_sleep):
        # Flag on + SMTP "configured"
        monkeypatch.setattr(app_settings, "auto_email_outreach", True, raising=False)
        monkeypatch.setattr(app_settings, "smtp_user", "user@leadsgenai.in", raising=False)
        monkeypatch.setattr(app_settings, "smtp_password", "x", raising=False)

        # Capture sends; stub async send_email -> True
        sent_to = []

        async def _fake_send(self, to_emails, subject, body, html_body=None, **kw):
            sent_to.append((to_emails, subject))
            return True

        from app.integrations import email_sender

        monkeypatch.setattr(email_sender.EmailSender, "send_email", _fake_send)

        # One emailable ready prospect + one with no email (skipped).
        _seed(
            tmp_prospects,
            {
                "id": "p1",
                "business_name": "Sharma Solar",
                "city": "Pune",
                "email": "info@sharmasolar.in",
                "status": "ready",
                "rating": 4.3,
                "reviews_count": 120,
            },
        )
        _seed(
            tmp_prospects,
            {
                "id": "p2",
                "business_name": "No Email Biz",
                "city": "Pune",
                "email": "",
                "status": "ready",
            },
        )

        out = await auto_outreach.run_email_outreach()
        assert out["sent"] == 1
        assert out["skipped_no_email"] == 1
        assert len(sent_to) == 1
        assert sent_to[0][0] == ["info@sharmasolar.in"]

        # Prospect marked emailed_at — must not re-email on a second run.
        p1 = next(p for p in prospector.list_prospects(limit=10) if p["id"] == "p1")
        assert p1.get("emailed_at")

        sent_to.clear()
        out2 = await auto_outreach.run_email_outreach()
        assert out2["sent"] == 0  # already emailed
        assert sent_to == []

    @pytest.mark.asyncio
    async def test_respects_daily_cap(self, monkeypatch, tmp_prospects, no_sleep):
        monkeypatch.setattr(app_settings, "auto_email_outreach", True, raising=False)
        monkeypatch.setattr(app_settings, "smtp_user", "user@leadsgenai.in", raising=False)
        monkeypatch.setattr(app_settings, "smtp_password", "x", raising=False)
        monkeypatch.setattr(app_settings, "outreach_daily_cap", 2, raising=False)

        async def _fake_send(self, *a, **k):
            return True

        from app.integrations import email_sender

        monkeypatch.setattr(email_sender.EmailSender, "send_email", _fake_send)

        for i in range(5):
            _seed(
                tmp_prospects,
                {
                    "id": f"c{i}",
                    "business_name": f"Biz {i}",
                    "city": "Pune",
                    "email": f"biz{i}@example.org".replace("example.org", "site.in"),
                    "status": "ready",
                },
            )

        out = await auto_outreach.run_email_outreach()
        assert out["cap"] == 2
        assert out["sent"] == 2  # capped


# --------------------------------------------------------------------------- #
# outreach_stats
# --------------------------------------------------------------------------- #
class TestStats:
    def test_counts(self, tmp_prospects):
        _seed(
            tmp_prospects, {"id": "a", "business_name": "A", "email": "a@x.in", "status": "ready"}
        )
        _seed(tmp_prospects, {"id": "b", "business_name": "B", "email": "", "status": "ready"})
        _seed(
            tmp_prospects,
            {
                "id": "c",
                "business_name": "C",
                "email": "c@x.in",
                "status": "ready",
                "emailed_at": "2026-06-08T00:00:00Z",
            },
        )
        stats = auto_outreach.outreach_stats()
        assert stats["total"] == 3
        assert stats["with_email"] == 2  # a + c
        assert stats["emailed"] == 1  # c
        assert stats["pending"] == 1  # a (has email, ready, not emailed)


def _iso_days_ago(days: float) -> str:
    return (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"


# --------------------------------------------------------------------------- #
# _followup_subject_body
# --------------------------------------------------------------------------- #
class TestFollowupSubjectBody:
    def test_step1_and_step2_non_empty_and_different(self):
        prospect = {"business_name": "Sharma Solar", "city": "Pune"}
        s1, t1, h1 = auto_outreach._followup_subject_body(prospect, 1)
        s2, t2, h2 = auto_outreach._followup_subject_body(prospect, 2)
        # non-empty
        for v in (s1, t1, h1, s2, t2, h2):
            assert v and v.strip()
        # business name personalization + mandatory unsubscribe + footer
        for t in (t1, t2):
            assert "Sharma Solar" in t
            assert "REMOVE" in t
            assert "LeadGen AI" in t
        # the two touches must read differently (distinct subject + body)
        assert s1 != s2
        assert t1 != t2

    def test_handles_missing_fields(self):
        s, t, h = auto_outreach._followup_subject_body({}, 1)
        assert s.strip() and t.strip() and h.strip()
        assert "REMOVE" in t


# --------------------------------------------------------------------------- #
# run_email_followups — guards
# --------------------------------------------------------------------------- #
class TestFollowupGuards:
    @pytest.mark.asyncio
    async def test_flag_off_skips(self, monkeypatch):
        monkeypatch.setattr(app_settings, "auto_email_outreach", False, raising=False)
        out = await auto_outreach.run_email_followups()
        assert out == {"skipped": "AUTO_EMAIL_OUTREACH off"}

    @pytest.mark.asyncio
    async def test_email_unconfigured_skips(self, monkeypatch):
        monkeypatch.setattr(app_settings, "auto_email_outreach", True, raising=False)
        monkeypatch.setattr(app_settings, "smtp_user", "", raising=False)
        monkeypatch.setattr(app_settings, "resend_api_key", "", raising=False)
        monkeypatch.setattr(app_settings, "brevo_api_key", "", raising=False)
        out = await auto_outreach.run_email_followups()
        assert out == {"skipped": "email_unconfigured"}


# --------------------------------------------------------------------------- #
# run_email_followups — happy path + timing
# --------------------------------------------------------------------------- #
class TestFollowupRun:
    @pytest.mark.asyncio
    async def test_sends_followup1_and_increments(self, monkeypatch, tmp_prospects, no_sleep):
        monkeypatch.setattr(app_settings, "auto_email_outreach", True, raising=False)
        monkeypatch.setattr(app_settings, "smtp_user", "user@leadsgenai.in", raising=False)
        monkeypatch.setattr(app_settings, "smtp_password", "x", raising=False)

        sent = []

        async def _fake_send(self, to_emails, subject, body, html_body=None, **kw):
            sent.append((to_emails, subject))
            return True

        from app.integrations import email_sender

        monkeypatch.setattr(email_sender.EmailSender, "send_email", _fake_send)

        # Emailed 4 days ago, no follow-up yet → eligible for follow-up #1.
        _seed(
            tmp_prospects,
            {
                "id": "f1",
                "business_name": "Sharma Solar",
                "city": "Pune",
                "email": "info@sharmasolar.in",
                "status": "ready",
                "emailed_at": _iso_days_ago(4),
                "followup_count": 0,
            },
        )

        out = await auto_outreach.run_email_followups()
        assert out["sent"] == 1
        assert out["by_step"]["1"] == 1
        assert len(sent) == 1
        assert sent[0][0] == ["info@sharmasolar.in"]

        # followup_count incremented + emailed_at bumped (so next touch waits).
        f1 = next(p for p in prospector.list_prospects(limit=10) if p["id"] == "f1")
        assert int(f1.get("followup_count")) == 1

        # Immediate re-run: emailed_at is now "today" → gap not met → no send.
        sent.clear()
        out2 = await auto_outreach.run_email_followups()
        assert out2["sent"] == 0
        assert sent == []

    @pytest.mark.asyncio
    async def test_timing_and_status_filters(self, monkeypatch, tmp_prospects, no_sleep):
        monkeypatch.setattr(app_settings, "auto_email_outreach", True, raising=False)
        monkeypatch.setattr(app_settings, "smtp_user", "user@leadsgenai.in", raising=False)
        monkeypatch.setattr(app_settings, "smtp_password", "x", raising=False)

        async def _fake_send(self, *a, **k):
            return True

        from app.integrations import email_sender

        monkeypatch.setattr(email_sender.EmailSender, "send_email", _fake_send)

        # Too recent (2 days, count 0) — gap (3d) not met → NOT eligible.
        _seed(
            tmp_prospects,
            {
                "id": "recent",
                "business_name": "Recent",
                "email": "r@x.in",
                "status": "ready",
                "emailed_at": _iso_days_ago(2),
                "followup_count": 0,
            },
        )
        # Replied — must be skipped even though old.
        _seed(
            tmp_prospects,
            {
                "id": "replied",
                "business_name": "Replied",
                "email": "rep@x.in",
                "status": "replied",
                "emailed_at": _iso_days_ago(10),
                "followup_count": 0,
            },
        )
        # Maxed out (count 2) — no more follow-ups.
        _seed(
            tmp_prospects,
            {
                "id": "maxed",
                "business_name": "Maxed",
                "email": "m@x.in",
                "status": "ready",
                "emailed_at": _iso_days_ago(30),
                "followup_count": 2,
            },
        )
        # Eligible for follow-up #2 (count 1, emailed 8 days ago > 7d gap).
        _seed(
            tmp_prospects,
            {
                "id": "step2",
                "business_name": "Step Two",
                "email": "s2@x.in",
                "status": "ready",
                "emailed_at": _iso_days_ago(8),
                "followup_count": 1,
            },
        )
        # Never emailed (no emailed_at) — initial outreach handles it, not this.
        _seed(
            tmp_prospects,
            {
                "id": "fresh",
                "business_name": "Fresh",
                "email": "fr@x.in",
                "status": "ready",
            },
        )

        out = await auto_outreach.run_email_followups()
        assert out["sent"] == 1  # only step2
        assert out["by_step"]["2"] == 1
        assert out["by_step"]["1"] == 0
        s2 = next(p for p in prospector.list_prospects(limit=10) if p["id"] == "step2")
        assert int(s2.get("followup_count")) == 2
