"""Compliance-safe, zero-manual email reply automation contracts."""

from __future__ import annotations

import email.utils
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.platform import reply_agent


def _write_rows(path, rows):
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def _enabled():
    return True


async def _claimed(_key, _cap):
    return 1


@pytest.mark.asyncio
async def test_auto_reply_is_inert_until_runtime_gate_is_enabled(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    _write_rows(path, [{"from": "owner@biz.in", "intent": "interested", "draft": "Hello"}])
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))

    async def disabled():
        return False

    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", disabled)
    calls = []

    async def sender(*args):
        calls.append(args)
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender)

    assert out["enabled"] is False
    assert out["sent"] == 0
    assert calls == []


@pytest.mark.asyncio
async def test_auto_reply_fails_closed_for_injection_suppression_and_unknown_sender(
    tmp_path, monkeypatch
):
    path = tmp_path / "reply_drafts.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "inject@biz.in",
                "intent": "question",
                "draft": "x",
                "at": now,
                "injection_flag": ["ignore"],
            },
            {"from": "optout@biz.in", "intent": "interested", "draft": "x", "at": now},
            {"from": "unknown@biz.in", "intent": "interested", "draft": "x", "at": now},
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {
            "inject@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"},
            "optout@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"},
        },
    )
    monkeypatch.setattr(
        "app.platform.email_unsub.is_suppressed",
        lambda email: email == "optout@biz.in",
    )
    calls = []

    async def sender(*args):
        calls.append(args)
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert out["sent"] == 0
    assert out["blocked_injection"] == 1
    assert out["blocked_suppressed"] == 1
    assert out["skipped_unknown"] == 1
    assert calls == []


@pytest.mark.asyncio
async def test_stale_known_reply_gets_honest_reengagement_and_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "owner@biz.in",
                "subject": "Pricing?",
                "intent": "question",
                "draft": "abhi demo karte hain",
                "at": old,
            }
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-06-20T00:00:00Z"}},
    )
    calls = []

    async def sender(to, subject, body, headers):
        calls.append((to, subject, body, headers))
        return True

    first = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    second = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert first["sent"] == 1 and first["stale_reengagement"] == 1
    assert second["sent"] == 0
    assert len(calls) == 1
    assert "delay" in calls[0][2].lower() or "time par" in calls[0][2].lower()
    assert "abhi demo karte hain" not in calls[0][2]
    row = _read_rows(path)[0]
    assert row["auto_send_status"] == "sent"
    assert row["hq_status"] == "done"
    assert row["auto_sent_at"]


@pytest.mark.asyncio
async def test_ambiguous_provider_failure_is_never_auto_retried(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "owner@biz.in",
                "subject": "Demo?",
                "intent": "interested",
                "draft": "Sure",
                "at": now,
                "source_at": now,
                "scan_status": "clean",
                "message_id": "<demo-question@biz.in>",
            }
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    outcomes = [False, True]

    async def sender(*_args):
        return outcomes.pop(0)

    first = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    second = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert first["failed"] == 1
    assert second["sent"] == 0
    assert outcomes == [True]
    row = _read_rows(path)[0]
    assert row["auto_send_attempts"] == 1
    assert row["auto_send_status"] == "ambiguous"


@pytest.mark.asyncio
async def test_fresh_reply_preserves_draft_and_thread_headers(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "owner@biz.in",
                "subject": "Re: audit",
                "intent": "interested",
                "draft": "Namaste, bilkul.",
                "at": now,
                "source_at": now,
                "scan_status": "clean",
                "message_id": "<inbound-1@biz.in>",
                "references": "<outbound-1@leadsgenai.in>",
            }
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    calls = []

    async def sender(to, subject, body, headers):
        calls.append((to, subject, body, headers))
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert out["sent"] == 1
    assert calls[0][2] == "Namaste, bilkul."
    assert calls[0][3]["In-Reply-To"] == "<inbound-1@biz.in>"
    assert "<outbound-1@leadsgenai.in>" in calls[0][3]["References"]
    assert "<inbound-1@biz.in>" in calls[0][3]["References"]


@pytest.mark.asyncio
async def test_only_newest_reply_per_sender_is_sent(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "owner@biz.in",
                "subject": "Old",
                "intent": "question",
                "draft": "old draft",
                "at": old,
                "source_at": old,
                "scan_status": "clean",
                "message_id": "<old@biz.in>",
            },
            {
                "from": "owner@biz.in",
                "subject": "New",
                "intent": "question",
                "draft": "new draft",
                "at": new,
                "source_at": new,
                "scan_status": "clean",
                "message_id": "<new@biz.in>",
            },
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    calls = []

    async def sender(to, subject, body, headers):
        calls.append((to, subject, body, headers))
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert out["sent"] == 1
    assert calls[0][1] == "Re: New"
    assert calls[0][2] == "new draft"


@pytest.mark.asyncio
async def test_hourly_reply_triage_always_runs_auto_reply_backlog(monkeypatch):
    monkeypatch.setenv("REPLY_AGENT", "1")
    monkeypatch.setattr(reply_agent, "_creds", lambda: ("imap.example", "u", "p"))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    calls = []

    class EmptyInbox:
        def login(self, *_args):
            return None

        def select(self, *_args):
            return None

        def search(self, *_args):
            return "OK", [b""]

        def close(self):
            return None

        def logout(self):
            return None

    monkeypatch.setattr(reply_agent.imaplib, "IMAP4_SSL", lambda *_a, **_k: EmptyInbox())

    async def backlog(**kwargs):
        calls.append(kwargs)
        return {"enabled": True, "sent": 2}

    monkeypatch.setattr(reply_agent, "run_auto_reply_backlog", backlog)
    out = await reply_agent.run_reply_triage()

    assert calls == [{}]
    assert out["auto_sent"] == 2


@pytest.mark.asyncio
async def test_backlog_still_runs_when_imap_is_down(monkeypatch):
    monkeypatch.setenv("REPLY_AGENT", "1")
    monkeypatch.setattr(reply_agent, "_creds", lambda: ("imap.example", "u", "p"))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)

    def broken_imap(*_args, **_kwargs):
        raise OSError("imap unavailable")

    monkeypatch.setattr(reply_agent.imaplib, "IMAP4_SSL", broken_imap)
    calls = []

    async def backlog(**kwargs):
        calls.append(kwargs)
        return {"enabled": True, "sent": 1}

    monkeypatch.setattr(reply_agent, "run_auto_reply_backlog", backlog)
    out = await reply_agent.run_reply_triage()

    assert calls == [{}]
    assert out["auto_sent"] == 1
    assert "imap unavailable" in out["error"]


@pytest.mark.asyncio
async def test_hard_off_overrides_env_and_runtime_enable(monkeypatch):
    monkeypatch.setenv("REPLY_AUTO_SEND", "1")
    monkeypatch.setenv("REPLY_AUTO_SEND_HARD_OFF", "1")
    assert await reply_agent._reply_auto_send_enabled() is False


@pytest.mark.asyncio
async def test_in_memory_redis_fallback_cannot_claim_delivery(monkeypatch):
    from app.cache import InMemoryCache

    fallback = InMemoryCache()

    async def get_fallback():
        return fallback

    monkeypatch.setattr("app.cache.get_redis_client", get_fallback)
    assert await reply_agent._claim_reply_auto_send("abc", 5) == 0


@pytest.mark.asyncio
async def test_real_redis_claim_reserves_message_and_daily_cap_atomically(monkeypatch):
    calls = []

    class RealRedisStub:
        async def ping(self):
            return True

        async def eval(self, *args):
            calls.append(args)
            return -1

    async def get_real():
        return RealRedisStub()

    monkeypatch.setattr("app.cache.get_redis_client", get_real)
    result = await reply_agent._claim_reply_auto_send("abc", 5)

    assert result == -1
    assert calls and calls[0][1] == 2
    assert calls[0][2] == "reply:auto-send:abc"
    assert calls[0][4] == 5


@pytest.mark.asyncio
async def test_fresh_reply_without_explicit_clean_scan_is_blocked(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "owner@biz.in",
                "subject": "Demo?",
                "intent": "interested",
                "draft": "Sure",
                "at": now,
                "source_at": now,
            }
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    calls = []

    async def sender(*args):
        calls.append(args)
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert out["blocked_unverified"] == 1
    assert out["sent"] == 0 and calls == []
    assert _read_rows(path)[0]["auto_send_status"] == "blocked"


@pytest.mark.asyncio
async def test_source_message_date_controls_expiry_not_processing_time(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    source = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "owner@biz.in",
                "subject": "Old",
                "intent": "question",
                "draft": "fresh-looking",
                "at": now,
                "source_at": source,
                "scan_status": "clean",
            }
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-06-01T00:00:00Z"}},
    )

    out = await reply_agent.run_auto_reply_backlog(claim_fn=_claimed)

    assert out["expired"] == 1 and out["sent"] == 0
    assert _read_rows(path)[0]["auto_send_status"] == "expired"


@pytest.mark.asyncio
async def test_batch_budget_counts_failed_provider_attempts(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    now = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    rows = [
        {"from": f"owner{i}@biz.in", "subject": "Q", "intent": "question", "draft": "x", "at": now}
        for i in range(5)
    ]
    _write_rows(path, rows)
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {f"owner{i}@biz.in": {"emailed_at": "2026-06-01T00:00:00Z"} for i in range(5)},
    )
    calls = []

    async def sender(*args):
        calls.append(args)
        return False

    out = await reply_agent.run_auto_reply_backlog(limit=2, send_fn=sender, claim_fn=_claimed)

    assert len(calls) == 2
    assert out["failed"] == 2


def test_thread_headers_are_bounded_and_rfc_shaped():
    class Msg:
        values = {
            "Message-ID": "bad\r\nX: y <good@biz.in> " + ("z" * 500),
            "References": " ".join(f"<id{i}@biz.in>" for i in range(20)),
        }

        def get(self, key):
            return self.values.get(key, "")

    message_id, references = reply_agent._safe_thread_headers(Msg())

    assert message_id == "<good@biz.in>"
    assert references.count("<") == 5
    assert len(references) <= 1000


@pytest.mark.asyncio
async def test_same_inbound_message_id_cannot_send_twice_across_runs(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    now = datetime.now(timezone.utc)
    base = {
        "from": "owner@biz.in",
        "subject": "Audit",
        "intent": "question",
        "draft": "Reply",
        "source_at": now.isoformat(),
        "scan_status": "clean",
        "message_id": "<stable-inbound@biz.in>",
    }
    _write_rows(path, [{**base, "at": now.isoformat()}])
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    claims = set()

    async def claim(key, _cap):
        if key in claims:
            return 0
        claims.add(key)
        return 1

    calls = []

    async def sender(*args):
        calls.append(args)
        return True

    first = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=claim)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**base, "at": (now + timedelta(minutes=1)).isoformat()}) + "\n")
    second = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=claim)

    assert first["sent"] == 1
    assert second["sent"] == 0 and second["claimed_elsewhere"] == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_pre_send_lock_failure_releases_claim_and_recovers_once(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    _write_rows(
        path,
        [
            {
                "from": "owner@biz.in",
                "subject": "Audit",
                "intent": "question",
                "draft": "Reply",
                "at": now,
                "source_at": now,
                "scan_status": "clean",
                "message_id": "<stable@biz.in>",
            }
        ],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    original_update = reply_agent._update_draft_fields
    update_calls = 0

    def flaky_update(*args, **kwargs):
        nonlocal update_calls
        update_calls += 1
        if update_calls == 1:
            return False
        return original_update(*args, **kwargs)

    monkeypatch.setattr(reply_agent, "_update_draft_fields", flaky_update)
    claims = set()

    async def claim(key, _cap):
        if key in claims:
            return 0
        claims.add(key)
        return 1

    async def release(key):
        claims.discard(key)
        return True

    calls = []

    async def sender(*args):
        calls.append(args)
        return True

    first = await reply_agent.run_auto_reply_backlog(
        send_fn=sender, claim_fn=claim, release_unattempted_fn=release
    )
    second = await reply_agent.run_auto_reply_backlog(
        send_fn=sender, claim_fn=claim, release_unattempted_fn=release
    )

    assert first["failed"] == 1 and first["skipped"] == "state_lock"
    assert second["sent"] == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_hard_off_is_rechecked_before_each_claim(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    _write_rows(
        path,
        [{"from": "owner@biz.in", "subject": "Q", "intent": "question", "draft": "x", "at": old}],
    )
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    states = [True, False]

    async def enabled_then_off():
        return states.pop(0)

    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", enabled_then_off)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-06-01T00:00:00Z"}},
    )
    calls = []

    async def sender(*args):
        calls.append(args)
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert out["skipped"] == "hard_off_or_disabled"
    assert calls == []


def test_source_received_at_rejects_future_date_and_prefers_older_truth():
    now = datetime.now(timezone.utc)

    class Msg:
        def __init__(self, date):
            self.date = date

        def get(self, _key):
            return self.date

    future = email.utils.format_datetime(now + timedelta(days=2))
    assert reply_agent._source_received_at(Msg(future)) == ""

    sender_date = email.utils.format_datetime(now - timedelta(days=2))
    internal = (now - timedelta(days=1)).strftime("%d-%b-%Y %H:%M:%S %z")
    fetch = [(f'1 (INTERNALDATE "{internal}" RFC822 {{1}}'.encode(), b"x")]
    got = datetime.fromisoformat(reply_agent._source_received_at(Msg(sender_date), fetch))
    assert got.date() == (now - timedelta(days=2)).date()


def test_save_draft_fails_closed_when_strict_lock_is_unavailable(tmp_path, monkeypatch):
    from contextlib import contextmanager

    path = tmp_path / "reply_drafts.jsonl"
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))

    @contextmanager
    def unlocked(*_args, **_kwargs):
        yield False

    monkeypatch.setattr("app.utils.file_lock.file_lock", unlocked)
    assert reply_agent._save_draft({"from": "owner@biz.in"}) is False

    assert not path.exists()


@pytest.mark.asyncio
async def test_imap_message_stays_unseen_until_draft_persists(tmp_path, monkeypatch):
    from email.message import EmailMessage

    path = tmp_path / "reply_drafts.jsonl"
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setenv("REPLY_AGENT", "1")
    monkeypatch.setattr(reply_agent, "_creds", lambda: ("imap.example", "u", "p"))

    async def disabled():
        return False

    async def classify(*_args, **_kwargs):
        return "other"

    async def no_record(*_args, **_kwargs):
        return None

    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", disabled)
    monkeypatch.setattr(reply_agent, "_classify", classify)
    monkeypatch.setattr(reply_agent, "_prospect_map", lambda: {"owner@biz.in": {}})
    monkeypatch.setattr(reply_agent, "_notify", lambda *_a, **_k: None)
    monkeypatch.setattr("app.platform.interaction_log.record", no_record)
    monkeypatch.setattr("app.platform.objection_extractor.extract_from_reply", no_record)
    monkeypatch.setattr("app.platform.llm_guard.scan", lambda *_a, **_k: {"suspicious": False})

    msg = EmailMessage()
    msg["From"] = "owner@biz.in"
    msg["Subject"] = "Hello"
    msg["Date"] = email.utils.format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = "<imap-persist@biz.in>"
    msg.set_content("hello")

    class Mailbox:
        seen = False
        fetch_specs = []

        def login(self, *_args):
            return None

        def select(self, *_args):
            return None

        def search(self, *_args):
            return "OK", [b"" if self.seen else b"1"]

        def fetch(self, _id, spec):
            self.fetch_specs.append(spec)
            internal = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S %z")
            return "OK", [(f'1 (INTERNALDATE "{internal}" BODY[] {{1}}'.encode(), msg.as_bytes())]

        def store(self, *_args):
            self.seen = True
            return "OK", []

        def close(self):
            return None

        def logout(self):
            return None

    mailbox = Mailbox()
    monkeypatch.setattr(reply_agent.imaplib, "IMAP4_SSL", lambda *_a, **_k: mailbox)
    original_save = reply_agent._save_draft
    saves = 0

    def flaky_save(row):
        nonlocal saves
        saves += 1
        return False if saves == 1 else original_save(row)

    monkeypatch.setattr(reply_agent, "_save_draft", flaky_save)

    first = await reply_agent.run_reply_triage()
    assert first["skipped"] == 1
    assert mailbox.seen is False

    second = await reply_agent.run_reply_triage()
    assert second["processed"] == 1
    assert mailbox.seen is True
    assert mailbox.fetch_specs == ["(BODY.PEEK[] INTERNALDATE)"] * 2
    assert len(_read_rows(path)) == 1


@pytest.mark.asyncio
async def test_llm_draft_failure_uses_safe_fallback_then_sends_exactly_once(tmp_path, monkeypatch):
    from email.message import EmailMessage

    path = tmp_path / "reply_drafts.jsonl"
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setenv("REPLY_AGENT", "1")
    monkeypatch.setattr(reply_agent, "_creds", lambda: ("imap.example", "u", "p"))

    async def disabled():
        return False

    async def interested(*_args, **_kwargs):
        return "interested"

    async def failed_draft(*_args, **_kwargs):
        return ""

    async def no_record(*_args, **_kwargs):
        return None

    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", disabled)
    monkeypatch.setattr(reply_agent, "_classify", interested)
    monkeypatch.setattr(reply_agent, "_draft", failed_draft)
    prospect = {
        "business_name": "Example Business",
        "emailed_at": "2026-07-01T00:00:00Z",
    }
    monkeypatch.setattr(reply_agent, "_prospect_map", lambda: {"owner@biz.in": prospect})
    monkeypatch.setattr(reply_agent, "_full_prospect_map", lambda: {"owner@biz.in": prospect})
    monkeypatch.setattr(reply_agent, "_notify", lambda *_a, **_k: None)
    monkeypatch.setattr("app.platform.interaction_log.record", no_record)
    monkeypatch.setattr("app.platform.objection_extractor.extract_from_reply", no_record)
    monkeypatch.setattr("app.platform.llm_guard.scan", lambda *_a, **_k: {"suspicious": False})
    monkeypatch.setattr("app.platform.email_unsub.is_suppressed", lambda *_a, **_k: False)

    msg = EmailMessage()
    msg["From"] = "owner@biz.in"
    msg["Subject"] = "Demo please"
    msg["Date"] = email.utils.format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = "<llm-failure@biz.in>"
    msg.set_content("I am interested")

    class Mailbox:
        seen = False

        def login(self, *_args):
            return None

        def select(self, *_args):
            return None

        def search(self, *_args):
            return "OK", [b"" if self.seen else b"1"]

        def fetch(self, _id, _spec):
            internal = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S %z")
            return "OK", [(f'1 (INTERNALDATE "{internal}" BODY[] {{1}}'.encode(), msg.as_bytes())]

        def store(self, *_args):
            self.seen = True
            return "OK", []

        def close(self):
            return None

        def logout(self):
            return None

    monkeypatch.setattr(reply_agent.imaplib, "IMAP4_SSL", lambda *_a, **_k: Mailbox())
    first = await reply_agent.run_reply_triage()
    row = _read_rows(path)[0]
    assert first["processed"] == 1
    assert row["draft_source"] == "deterministic_fallback"
    assert "receive" in row["draft"].lower()

    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    calls = []

    async def sender(*args):
        calls.append(args)
        return True

    second = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    third = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    assert second["sent"] == 1
    assert third["sent"] == 0
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# WI-CP2-AUTO-REPLY: auto_sent_at ⇒ interaction_log OUT row (observability)
# ---------------------------------------------------------------------------


def _fresh_verified_draft(**extra):
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "from": "owner@biz.in",
        "subject": "Demo?",
        "intent": "interested",
        "draft": "Haanji, demo book karte hain",
        "at": now,
        "source_at": now,
        "scan_status": "clean",
        "message_id": "<demo-observe@biz.in>",
    }
    row.update(extra)
    return row


@pytest.mark.asyncio
async def test_auto_sent_writes_outbound_interaction_with_delivery_key(tmp_path, monkeypatch):
    """Invariant: auto_sent_at set ⇒ exactly one interaction_log.record(direction=out)."""
    path = tmp_path / "reply_drafts.jsonl"
    _write_rows(path, [_fresh_verified_draft()])
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {
            "owner@biz.in": {
                "emailed_at": "2026-07-01T00:00:00Z",
                "phone": "919999999999",
                "id": "prospect-only-id",
            }
        },
    )
    records = []

    async def capture_record(**kwargs):
        records.append(kwargs)
        return {"id": "ix-1"}

    monkeypatch.setattr("app.platform.interaction_log.record", capture_record)

    async def sender(*_a):
        return True

    first = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    second = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert first["sent"] == 1
    assert second["sent"] == 0
    row = _read_rows(path)[0]
    assert row["auto_sent_at"]
    assert len(records) == 1
    rec = records[0]
    assert rec["channel"] == "email"
    assert rec["direction"] == "out"
    assert rec["email"] == "owner@biz.in"
    assert rec["lead_id"] == ""  # never stuff prospect id as lead_id
    assert rec["meta"]["source"] == "reply_agent"
    assert rec["meta"]["delivery_key"] == row["delivery_key"]
    assert rec["meta"]["prospect_id"] == "prospect-only-id"
    assert rec["meta"]["delivery_key"]


@pytest.mark.asyncio
async def test_failed_send_does_not_write_interaction(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    _write_rows(path, [_fresh_verified_draft()])
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    records = []

    async def capture_record(**kwargs):
        records.append(kwargs)
        return {}

    monkeypatch.setattr("app.platform.interaction_log.record", capture_record)

    async def sender(*_a):
        return False

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    assert out["sent"] == 0
    assert out["failed"] == 1
    assert records == []
    assert not _read_rows(path)[0].get("auto_sent_at")


@pytest.mark.asyncio
async def test_interaction_log_failure_does_not_undo_sent(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    _write_rows(path, [_fresh_verified_draft()])
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )

    async def boom(**_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.platform.interaction_log.record", boom)

    async def sender(*_a):
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    assert out["sent"] == 1
    assert out.get("error") is None
    row = _read_rows(path)[0]
    assert row["auto_send_status"] == "sent"
    assert row["auto_sent_at"]


@pytest.mark.asyncio
async def test_reply_agent_interaction_log_opt_out_skips_record(tmp_path, monkeypatch):
    path = tmp_path / "reply_drafts.jsonl"
    _write_rows(path, [_fresh_verified_draft()])
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setenv("REPLY_AGENT_INTERACTION_LOG", "0")
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )
    records = []

    async def capture_record(**kwargs):
        records.append(kwargs)
        return {}

    monkeypatch.setattr("app.platform.interaction_log.record", capture_record)

    async def sender(*_a):
        return True

    out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)
    assert out["sent"] == 1
    assert records == []
    assert _read_rows(path)[0]["auto_sent_at"]


@pytest.mark.asyncio
async def test_interaction_log_skipped_emits_warning_keeps_sent(tmp_path, monkeypatch, caplog):
    """INTERACTION_LOG off returns skipped dict — must warn, must not undo send."""
    import logging

    path = tmp_path / "reply_drafts.jsonl"
    _write_rows(path, [_fresh_verified_draft()])
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(path))
    monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _enabled)
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-07-01T00:00:00Z"}},
    )

    async def skipped(**_kwargs):
        return {"skipped": "INTERACTION_LOG off"}

    monkeypatch.setattr("app.platform.interaction_log.record", skipped)

    async def sender(*_a):
        return True

    with caplog.at_level(logging.WARNING, logger="app.platform.reply_agent"):
        out = await reply_agent.run_auto_reply_backlog(send_fn=sender, claim_fn=_claimed)

    assert out["sent"] == 1
    assert _read_rows(path)[0]["auto_sent_at"]
    assert any("interaction_log skipped" in r.message for r in caplog.records)
