"""Sweep counter truth: dedupe-suppressed items ko `sent` NAHI ginna chahiye.

Kyun ye file hai (2026-07-14 postmortem):
`notify_approval` jab idempotency pe short-circuit karta hai to wo
`_audit(existing, note="duplicate_suppressed")` lautata hai — jisme `status` field
us PURANI ROW ka persisted status hota hai, yaani `"sent"`. Sweep ka counter
seedha `counts[r["status"]] += 1` karta tha, isliye ek dedupe-suppressed item
`sent=1` + `attempted=1` report karta tha jabki **koi email nahi gaya**.

Live impact: production me lagataar sweeps `sent: 1` dikhate rahe jabki DB row ka
`attempted_at` hila tak nahi tha (= zero real sends). Isse "customer ko reminder
gaya?" ka JHOOTHA HAAN milta hai — audit/health dono jhooth bolte hain, aur ek
operator galti se ye samajh sakta hai ki customer ko baar-baar spam ja raha hai.

Contract: real send hi `sent` hai; dedupe alag counter (`deduplicated`) me jaye
aur `attempted` bhi na bade (kyunki koi attempt hua hi nahi).
"""

from __future__ import annotations

import pytest

from app.platform import approval_notifier as an


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    import app.marketing.delivery_ledger as dl

    monkeypatch.setattr(dl, "log_event", lambda *a, **k: True)
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setenv("APPROVAL_EMAIL_CLIENT_ALLOWLIST", "cli-0")
    an._LOCAL_LOCK["held"] = False


class Sender:
    def __init__(self):
        self.calls: list[str] = []

    async def __call__(self, to_email, subject, html, text):
        self.calls.append(to_email)
        return (True, "pm", "")


_ALLOW = lambda c, e: (True, "")  # noqa: E731
_RESOLVE = lambda c: f"{c}@x.com"  # noqa: E731
_ONE = [{"id": "a0", "client_id": "cli-0", "status": "pending", "content": {"t": 0}}]


async def test_second_sweep_dedupes_and_does_not_report_a_send(async_db_session, monkeypatch):
    """Do baar sweep: pehla asli bheje, doosra dedupe kare aur `sent` na bole."""
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": list(_ONE))

    s1 = Sender()
    first = await an.notify_pending_approvals(
        session=async_db_session, send_fn=s1, resolve_recipient=_RESOLVE, email_allowed=_ALLOW
    )
    assert first["sent"] == 1, "pehla sweep asli send hai"
    assert len(s1.calls) == 1

    # Doosra sweep — same approval, same version => idempotency short-circuit.
    s2 = Sender()
    second = await an.notify_pending_approvals(
        session=async_db_session, send_fn=s2, resolve_recipient=_RESOLVE, email_allowed=_ALLOW
    )

    # Sabse zaroori: provider ko dobara chhua hi nahi.
    assert len(s2.calls) == 0, "dedupe hone par koi email nahi jana chahiye"

    # Counter sach bole — yehi wo bug tha jisne live triage ko bharma diya.
    assert second["sent"] == 0, (
        f"dedupe-suppressed item `sent` me nahi ginna chahiye (mila: {second})"
    )
    assert second["deduplicated"] == 1, f"dedupe alag counter me aana chahiye (mila: {second})"
    assert second["attempted"] == 0, "koi attempt hua hi nahi to attempted 0 rahe"
    assert second["seen"] == 1, "seen phir bhi item ko count kare"


async def test_real_send_still_counts_as_sent(async_db_session, monkeypatch):
    """Regression guard: fix ne asli send ki ginti nahi todi."""
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": list(_ONE))
    s = Sender()
    out = await an.notify_pending_approvals(
        session=async_db_session, send_fn=s, resolve_recipient=_RESOLVE, email_allowed=_ALLOW
    )
    assert out["sent"] == 1 and out["attempted"] == 1 and out["deduplicated"] == 0
    assert len(s.calls) == 1
