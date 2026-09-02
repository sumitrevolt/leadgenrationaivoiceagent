"""Hot Queue quick-actions (GTM council 2026-07-03): tap-to-act ntfy buttons.

Root cause found live: 344 hot replies accumulated, 0 ever cleared, despite
the push notification already firing every time — cost-of-action, not
visibility. Fix = put Reply/Done buttons IN the notification. These tests
cover the new stateless HMAC token (no login needed for the Done tap) and
that the action buttons actually get attached to outbound ntfy pushes.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# make_hq_done_token / verify_hq_done_token — stateless HMAC round-trip
# --------------------------------------------------------------------------- #
def test_hq_done_token_round_trip():
    from app.platform import reply_agent as ra

    tok = ra.make_hq_done_token("abc123")
    assert ra.verify_hq_done_token(tok) == "abc123"


def test_hq_done_token_rejects_tampering():
    from app.platform import reply_agent as ra

    tok = ra.make_hq_done_token("abc123")
    tampered = tok[:-2] + ("aa" if tok[-2:] != "aa" else "bb")
    assert ra.verify_hq_done_token(tampered) is None


def test_hq_done_token_rejects_garbage():
    from app.platform import reply_agent as ra

    assert ra.verify_hq_done_token("") is None
    assert ra.verify_hq_done_token("not-a-real-token") is None
    assert ra.verify_hq_done_token(None) is None  # type: ignore[arg-type]


def test_hq_done_token_scoped_to_its_own_hq_id():
    from app.platform import reply_agent as ra

    tok_a = ra.make_hq_done_token("lead-a")
    # a token minted for lead-a must never verify as lead-b
    assert ra.verify_hq_done_token(tok_a) != "lead-b"


# --------------------------------------------------------------------------- #
# PUBLIC quick-done endpoint — no admin token required (ntfy can't log in)
# --------------------------------------------------------------------------- #
def test_quick_done_endpoint_marks_handled(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text(
        '{"from": "a@x.com", "subject": "hi", "intent": "interested", '
        '"draft": "d", "at": "2026-07-01T10:00:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {"a@x.com": {"emailed_at": "2026-06-28T10:00:00Z"}},
    )

    hq_id = ra.hot_queue()[0]["hq_id"]
    token = ra.make_hq_done_token(hq_id)

    r = client.post(f"/api/growth/reply/hot-queue/quick-done/{token}")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "hq_id": hq_id}

    # queue is now empty — the tap actually cleared it
    assert ra.hot_queue() == []


def test_quick_done_endpoint_rejects_invalid_token():
    r = client.post("/api/growth/reply/hot-queue/quick-done/garbage-token")
    assert r.status_code == 400


def test_quick_done_endpoint_no_admin_auth_required():
    """The whole point: ntfy's http action can't do interactive login — a
    bogus-but-well-formed token must 400 (invalid), never 401/403 (auth)."""
    r = client.post("/api/growth/reply/hot-queue/quick-done/still-garbage")
    assert r.status_code not in (401, 403)


# --------------------------------------------------------------------------- #
# whatsapp_reply — action buttons attached to the ntfy push (parity fix:
# WA hot replies previously never pushed at all)
# --------------------------------------------------------------------------- #
def test_whatsapp_reply_attaches_reply_and_done_actions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.integrations import ntfy
    from app.platform import reply_agent

    # NOTE (2026-07-07): _classify/_draft ab history/history_msgs kwarg lete hain
    # (wa_conversation chat-continuity) — fakes signature-sync warna TypeError→"other".
    async def fake_classify(subject, body, history=""):
        return "interested"

    async def fake_draft(biz, subject, body, intent, history_msgs=None):
        return "Namaste! Free demo set karein?"

    calls = []

    async def fake_push(title, message, priority="default", tags=None, actions=None):
        calls.append({"title": title, "actions": actions})
        return True

    monkeypatch.setattr(reply_agent, "_classify", fake_classify)
    monkeypatch.setattr(reply_agent, "_draft", fake_draft)
    monkeypatch.setattr(ntfy, "push", fake_push)

    rec = asyncio.run(reply_agent.whatsapp_reply("919876543210", "price batao"))
    assert rec["channel"] == "whatsapp"

    assert len(calls) == 1
    actions = calls[0]["actions"]
    labels = [a["label"] for a in actions]
    assert "✔ Done" in labels
    assert "💬 Reply" in labels
    reply_action = next(a for a in actions if a["label"] == "💬 Reply")
    assert reply_action["action"] == "view"
    assert reply_action["url"].startswith("https://wa.me/919876543210?text=")
    done_action = next(a for a in actions if a["label"] == "✔ Done")
    assert done_action["action"] == "http"
    assert done_action["method"] == "POST"
    assert "/api/growth/reply/hot-queue/quick-done/" in done_action["url"]


def test_whatsapp_reply_does_not_make_reply_action_for_meta_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.integrations import ntfy
    from app.platform import reply_agent

    async def fake_classify(subject, body, history=""):
        return "interested"

    async def fake_draft(biz, subject, body, intent, history_msgs=None):
        return "Namaste! Free demo set karein?"

    calls = []

    async def fake_push(title, message, priority="default", tags=None, actions=None):
        calls.append({"title": title, "actions": actions})
        return True

    monkeypatch.setattr(reply_agent, "_classify", fake_classify)
    monkeypatch.setattr(reply_agent, "_draft", fake_draft)
    monkeypatch.setattr(ntfy, "push", fake_push)

    rec = asyncio.run(reply_agent.whatsapp_reply("103723644784777", "price batao"))
    assert rec["channel"] == "whatsapp"

    actions = calls[0]["actions"]
    assert any(a["action"] == "http" for a in actions)
    assert not any(a["action"] == "view" and "wa.me/" in a.get("url", "") for a in actions)


def test_whatsapp_reply_no_push_for_non_hot_intent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.integrations import ntfy
    from app.platform import reply_agent

    async def fake_classify(subject, body, history=""):
        return "not_interested"

    def _boom(*_a, **_kw):  # pragma: no cover - asserts non-call
        raise AssertionError("ntfy.push must not fire for a non-hot intent")

    monkeypatch.setattr(reply_agent, "_classify", fake_classify)
    monkeypatch.setattr(ntfy, "push", _boom)

    rec = asyncio.run(reply_agent.whatsapp_reply("919876543210", "bas thanks"))
    assert rec["intent"] == "not_interested"


# --------------------------------------------------------------------------- #
# ntfy.push — JSON-publish path when actions are provided
# --------------------------------------------------------------------------- #
def test_ntfy_push_uses_json_api_when_actions_given(monkeypatch):
    from app.integrations import ntfy

    monkeypatch.setenv("NTFY_URL", "http://ntfy.local")
    monkeypatch.setenv("NTFY_TOPIC", "leadgen")

    captured = {}

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None, content=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            captured["content"] = content
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    ok = asyncio.run(
        ntfy.push(
            "Title",
            "Body",
            priority="high",
            tags=["fire"],
            actions=[{"action": "view", "label": "Reply", "url": "https://example.com"}],
        )
    )
    assert ok is True
    assert captured["url"] == "http://ntfy.local/"
    assert captured["json"]["topic"] == "leadgen"
    assert captured["json"]["priority"] == 4  # "high" -> 4
    assert captured["json"]["actions"][0]["label"] == "Reply"
    assert captured["headers"]["Content-Type"] == "application/json"


def test_ntfy_push_plain_path_unchanged_without_actions(monkeypatch):
    """Existing callers (no actions arg) must keep hitting the old header-based
    /{topic} endpoint — zero behaviour change for the other ~10 ntfy.push call
    sites in the codebase."""
    from app.integrations import ntfy

    monkeypatch.setenv("NTFY_URL", "http://ntfy.local")
    monkeypatch.setenv("NTFY_TOPIC", "leadgen")

    captured = {}

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None, content=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    ok = asyncio.run(ntfy.push("Title", "Body", priority="high", tags=["fire"]))
    assert ok is True
    assert captured["url"] == "http://ntfy.local/leadgen"
    assert captured["content"] == "Body"
    assert captured["headers"]["Priority"] == "high"
