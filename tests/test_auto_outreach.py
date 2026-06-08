"""
Tests: automated email outreach (app/platform/auto_outreach.py).
=================================================================

No real SMTP / network:
  - prospector._PROSPECTS_FILE tmp_path pe redirect (real data/ na chhue)
  - email_sender.send_email ko async stub se monkeypatch
  - settings.auto_email_outreach / smtp_user monkeypatch
  - throttle sleep ko no-op kar dete hain (test fast rahe)
"""
import json
import os

import pytest

from app.config import settings as app_settings
from app.platform import auto_outreach, prospector


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
    async def test_smtp_unset_skips(self, monkeypatch):
        monkeypatch.setattr(app_settings, "auto_email_outreach", True, raising=False)
        monkeypatch.setattr(app_settings, "smtp_user", "", raising=False)
        out = await auto_outreach.run_email_outreach()
        assert out == {"skipped": "smtp_unset"}


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
        _seed(tmp_prospects, {
            "id": "p1", "business_name": "Sharma Solar", "city": "Pune",
            "email": "info@sharmasolar.in", "status": "ready",
            "rating": 4.3, "reviews_count": 120,
        })
        _seed(tmp_prospects, {
            "id": "p2", "business_name": "No Email Biz", "city": "Pune",
            "email": "", "status": "ready",
        })

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
        assert out2["sent"] == 0          # already emailed
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
            _seed(tmp_prospects, {
                "id": f"c{i}", "business_name": f"Biz {i}", "city": "Pune",
                "email": f"biz{i}@example.org".replace("example.org", "site.in"),
                "status": "ready",
            })

        out = await auto_outreach.run_email_outreach()
        assert out["cap"] == 2
        assert out["sent"] == 2  # capped


# --------------------------------------------------------------------------- #
# outreach_stats
# --------------------------------------------------------------------------- #
class TestStats:
    def test_counts(self, tmp_prospects):
        _seed(tmp_prospects, {"id": "a", "business_name": "A", "email": "a@x.in",
                              "status": "ready"})
        _seed(tmp_prospects, {"id": "b", "business_name": "B", "email": "",
                              "status": "ready"})
        _seed(tmp_prospects, {"id": "c", "business_name": "C", "email": "c@x.in",
                              "status": "ready", "emailed_at": "2026-06-08T00:00:00Z"})
        stats = auto_outreach.outreach_stats()
        assert stats["total"] == 3
        assert stats["with_email"] == 2   # a + c
        assert stats["emailed"] == 1      # c
        assert stats["pending"] == 1      # a (has email, ready, not emailed)
