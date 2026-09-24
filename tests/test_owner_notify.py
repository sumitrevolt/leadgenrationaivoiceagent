"""T03 acceptance: owner_notify fail-open + dedupe + evidence-required + truth gate.

Also proves: workforce events are UNVERIFIED, digest works, and there is ZERO
`getUpdates` in the new egress modules.
Tests cover:
  - Fail-open when no token
  - UNVERIFIED tag when no evidence
  - Dedupe suppression
  - Dry-run path
  - 401 retry via ACTUAL candidate order (Notify first, JARVIS second) with
    valid-format tokens and a scripted httpx fake (no _send_via_bot_api mock)
  - DM fallback payload carries the recipient chat_id (Bot API sendMessage
    requires chat_id in the request body)
  - Async-caller context: truthful success AND failure results (no
    optimistic True, no loop deadlock)
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.utils.owner_notify as owner_notify
from app.platform import owner_feed_bridge, owner_feed_digest
from app.utils import telegram_egress
from app.utils.owner_feed import FORCE_UNVERIFIED_SOURCES, build_event, emit, read_events

REPO = Path(__file__).resolve().parents[1]


def _make_fake_httpx(script):
    """Build a fake httpx.AsyncClient class.

    `script` is a list of (status_code, json_body) consumed in call order
    (last entry repeats if exhausted). Records every (url, json_body) so
    tests can assert the ACTUAL outgoing payload and recipient.
    """
    calls: list = []

    class _Resp:
        def __init__(self, status_code: int, body: dict):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

        @property
        def text(self):
            return json.dumps(self._body)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, json=None, **kwargs):
            calls.append((url, json))
            idx = min(len(calls) - 1, len(script) - 1)
            status_code, body = script[idx]
            return _Resp(status_code, body)

    return _FakeClient, calls


def _feed(tmp: str) -> str:
    return os.path.join(tmp, "owner_feed_events.jsonl")


class SendOwnerTests(unittest.TestCase):
    def setUp(self):
        owner_notify.reset_caches()
        # Hermetic: strip any real bot tokens / chat ids from the dev env so
        # no test can fire a real Telegram request.
        for _k in (
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_NOTIFY_BOT_TOKEN",
            "TELEGRAM_JARVIS_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
        ):
            os.environ.pop(_k, None)
        # Reset the per-process 401 blacklist so candidate-order tests are
        # deterministic.
        telegram_egress._dead_tokens.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.feed = _feed(self._tmp.name)
        os.environ["OWNER_FEED_PATH"] = self.feed

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("OWNER_FEED_PATH", None)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        os.environ.pop("TELEGRAM_NOTIFY_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_JARVIS_BOT_TOKEN", None)
        telegram_egress._dead_tokens.clear()
        owner_notify.reset_caches()

    # ---- acceptance: fail-open (Telegram down must not break the app) ----
    def test_fail_open_without_token(self):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        self.assertFalse(
            owner_notify.send_owner("hello", severity="P1", evidence="data/x.json", dedupe_key="k1")
        )

    def test_never_raises_on_garbage(self):
        self.assertFalse(owner_notify.send_owner("", severity="P0"))
        self.assertFalse(owner_notify.send_owner(None))  # type: ignore[arg-type]

    # ---- evidence required => UNVERIFIED tag ----
    def test_missing_evidence_tags_unverified_in_feed(self):
        owner_notify.send_owner("payment received", severity="P1", evidence=None, dedupe_key="noev")
        events, _ = read_events(self.feed)
        mirrored = [e for e in events if e.get("source") == "owner_notify"]
        self.assertEqual(len(mirrored), 1)
        self.assertIn("UNVERIFIED", mirrored[0]["text"])
        self.assertFalse(mirrored[0]["verified"])

    def test_with_evidence_has_evidence_line(self):
        owner_notify.send_owner("paid ₹1999", severity="P1", evidence="data/invoices.jsonl#INV-1", dedupe_key="ev1")
        events, _ = read_events(self.feed)
        mirrored = [e for e in events if e.get("source") == "owner_notify"]
        self.assertEqual(len(mirrored), 1)
        self.assertNotIn("UNVERIFIED", mirrored[0]["text"])
        self.assertIn("data/invoices.jsonl#INV-1", mirrored[0]["text"])

    # ---- dedupe per hour ----
    def test_dedupe_suppresses_repeat_within_hour(self):
        owner_notify.send_owner("alert A", severity="P1", evidence="e", dedupe_key="dup1")
        before = len([e for e in read_events(self.feed)[0] if e.get("source") == "owner_notify"])
        owner_notify.send_owner("alert A again", severity="P1", evidence="e", dedupe_key="dup1")
        after = len([e for e in read_events(self.feed)[0] if e.get("source") == "owner_notify"])
        self.assertEqual(after, before)

    # ---- dry run returns True and does not hit the network ----
    def test_dry_run_true(self):
        self.assertTrue(owner_notify.send_owner("x", severity="P0", evidence="e", dedupe_key="dr1", dry_run=True))

    # ---- 401 retry via ACTUAL candidate order (no _send_via_bot_api mock) ----
    def test_401_retry_follows_actual_candidate_order(self):
        """Notify token 401s, JARVIS token succeeds — proved through the REAL
        _send_via_bot_api token loop + 401-blacklist, using valid-format
        tokens and a scripted httpx fake. Asserts candidate order, the retry
        sequence, and the receipt message_id (evidence, not a label)."""
        notify_token = "111111111:AAFakeNotifyTokenForTest0"
        jarvis_token = "222222222:AAFakeJarvisTokenForTest1"
        os.environ["TELEGRAM_NOTIFY_BOT_TOKEN"] = notify_token
        os.environ["TELEGRAM_JARVIS_BOT_TOKEN"] = jarvis_token
        os.environ["TELEGRAM_CHAT_ID"] = "999888"

        # 1. ACTUAL candidate order from the real _token_candidates().
        self.assertEqual(telegram_egress._token_candidates(), [notify_token, jarvis_token])

        script = [
            (401, {"ok": False, "error_code": 401, "description": "Unauthorized"}),
            (200, {"ok": True, "result": {"message_id": 4242, "chat_id": "999888"}}),
        ]
        fake_client, calls = _make_fake_httpx(script)
        with patch("httpx.AsyncClient", fake_client):
            with patch.object(telegram_egress, "resolve_chat_id", return_value="999888"):
                result = owner_notify.send_owner(
                    "test", severity="P0", evidence="owner_feed#t-401", dedupe_key="re1"
                )

        # 2. Delivery succeeded and the receipt carries a message_id (evidence).
        self.assertTrue(result, "401 on first token must trigger retry, not failure")
        self.assertEqual(len(calls), 2, "exactly one 401 attempt + one successful retry")
        url_1, _ = calls[0]
        url_2, payload_2 = calls[1]
        # 3. ACTUAL order: Notify bot first, JARVIS bot second.
        self.assertIn(f"/bot{notify_token}/sendMessage", url_1)
        self.assertIn(f"/bot{jarvis_token}/sendMessage", url_2)
        # 4. The 401 token was blacklisted for this process (real retry evidence).
        self.assertIn(notify_token, telegram_egress._dead_tokens)
        # 5. Outgoing payload carried the intended recipient chat_id.
        self.assertEqual(payload_2["chat_id"], "999888")
        self.assertIn("P0", payload_2["text"])

    # ---- DM fallback: outgoing payload + intended recipient ----
    def test_dm_fallback_payload_carries_recipient_chat_id(self):
        """When group resolution fails, the DM fallback must send a
        sendMessage payload that carries the actual recipient chat_id
        (Telegram Bot API requires chat_id in the request body)."""
        dm_token = "333333333:AAFakeDmTokenForTest2"
        os.environ["TELEGRAM_BOT_TOKEN"] = dm_token
        os.environ["TELEGRAM_CHAT_ID"] = "777000"

        script = [
            (200, {"ok": True, "result": {"message_id": 5151, "chat_id": "777000"}}),
        ]
        fake_client, calls = _make_fake_httpx(script)
        with patch("httpx.AsyncClient", fake_client):
            with patch.object(telegram_egress, "resolve_chat_id", return_value=None):
                result = owner_notify.send_owner(
                    "dm test", severity="P1", evidence="owner_feed#t-dm", dedupe_key="dm2"
                )

        self.assertTrue(result, "DM fallback must deliver when group is unresolvable")
        self.assertEqual(len(calls), 1, "unknown group → exactly one DM attempt")
        url, payload = calls[0]
        self.assertIn(f"/bot{dm_token}/sendMessage", url)
        # Recipient evidence: payload chat_id == intended TELEGRAM_CHAT_ID.
        self.assertEqual(payload["chat_id"], "777000")
        self.assertIn("P1", payload["text"])

    # ---- async-caller context: truthful success AND failure ----
    def test_send_owner_from_async_caller_is_truthful_success(self):
        """send_owner() called FROM a running event loop must still return a
        truthful True — delivery runs to completion (worker thread), it does
        not deadlock the loop nor optimistically claim success."""
        async_token = "444444444:AAFakeAsyncTokenForTest3"
        os.environ["TELEGRAM_BOT_TOKEN"] = async_token
        os.environ["TELEGRAM_CHAT_ID"] = "666555"

        script = [
            (200, {"ok": True, "result": {"message_id": 7070, "chat_id": "666555"}}),
        ]
        fake_client, calls = _make_fake_httpx(script)

        async def _async_caller():
            return owner_notify.send_owner(
                "async ok", severity="P0", evidence="owner_feed#t-async", dedupe_key="ac1"
            )

        with patch("httpx.AsyncClient", fake_client):
            with patch.object(telegram_egress, "resolve_chat_id", return_value=None):
                result = asyncio.run(_async_caller())

        self.assertTrue(result, "async-caller success must be truthful (delivered)")
        self.assertEqual(len(calls), 1)

    def test_send_owner_from_async_caller_is_truthful_failure(self):
        """Same async context, but every token 401s → send_owner() must
        return a truthful False (no optimistic success, no raise)."""
        dead_a = "555555555:AAFakeDeadTokenAForTest4"
        dead_b = "666666666:AAFakeDeadTokenBForTest5"
        os.environ["TELEGRAM_NOTIFY_BOT_TOKEN"] = dead_a
        os.environ["TELEGRAM_JARVIS_BOT_TOKEN"] = dead_b
        os.environ["TELEGRAM_CHAT_ID"] = "666555"

        script = [
            (401, {"ok": False, "error_code": 401, "description": "Unauthorized"}),
            (401, {"ok": False, "error_code": 401, "description": "Unauthorized"}),
        ]
        fake_client, calls = _make_fake_httpx(script)

        async def _async_caller():
            return owner_notify.send_owner(
                "async fail", severity="P0", evidence="owner_feed#t-asyncf", dedupe_key="ac2"
            )

        with patch("httpx.AsyncClient", fake_client):
            with patch.object(telegram_egress, "resolve_chat_id", return_value=None):
                result = asyncio.run(_async_caller())

        self.assertFalse(result, "async-caller failure must be truthful (all tokens 401)")
        self.assertEqual(len(calls), 2, "each candidate tried exactly once")


class WorkforceTruthGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.feed = _feed(self._tmp.name)
        os.environ["OWNER_FEED_PATH"] = self.feed

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("OWNER_FEED_PATH", None)

    def test_bridge_workforce_is_force_unverified(self):
        owner_feed_bridge.bridge_workforce({"active_workers": 0, "task_execution_verified": False})
        events, _ = read_events(self.feed)
        wf = [e for e in events if e.get("source") == "workforce"]
        self.assertEqual(len(wf), 1)
        self.assertFalse(wf[0]["verified"], "workforce events must never be verified")

    def test_build_event_workforce_verified_true_is_downgraded(self):
        self.assertIn("workforce", FORCE_UNVERIFIED_SOURCES)
        ev = build_event(source="workforce", actor="p", text="t", verified=True)
        self.assertFalse(ev["verified"])

    def test_bridge_bot_fleet_writes_heartbeat(self):
        class _FakeOrchestrator:
            def dev_workers_count(self):
                return 2
            def get_metrics(self):
                return {"dev_workers_verified": 2, "done_tasks": 3, "running_tasks": 1}

        written = owner_feed_bridge.bridge_bot_fleet(_FakeOrchestrator())
        self.assertEqual(written, 1)
        events, _ = read_events(self.feed)
        bf = [e for e in events if e.get("source") == "bot_fleet"]
        self.assertEqual(len(bf), 1)
        self.assertIn("dev_workers=2", bf[0]["text"])


class DigestTests(unittest.TestCase):
    def setUp(self):
        owner_notify.reset_caches()
        self._tmp = tempfile.TemporaryDirectory()
        self.feed = _feed(self._tmp.name)
        os.environ["OWNER_FEED_PATH"] = self.feed

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("OWNER_FEED_PATH", None)
        owner_notify.reset_caches()

    def test_route_splits_p0_from_digest(self):
        events = [
            {"severity": "P0", "verified": True, "text": "pay"},
            {"severity": "P1", "verified": False, "text": "deploy"},
            {"severity": "info", "verified": True, "text": "hb"},
        ]
        routed = owner_feed_digest.route_events(events)
        self.assertEqual(len(routed["immediate"]), 1)
        self.assertEqual(len(routed["digest"]), 2)
        self.assertEqual(routed["verified"], 2)
        self.assertEqual(routed["unverified"], 1)

    def test_digest_has_verified_unverified_tail(self):
        events = [
            {"severity": "P1", "verified": True, "text": "a"},
            {"severity": "info", "verified": False, "text": "b"},
        ]
        text = owner_feed_digest.format_digest(events)
        self.assertIn("verified 1 / unverified 1", text)

    def test_run_digest_dry_run_never_raises(self):
        emit(source="hermes", actor="x", text="p1 event", severity="P1", kind="heartbeat", evidence="e")
        result = owner_feed_digest.run_digest(dry_run=True)
        self.assertIn("total", result)
        self.assertGreaterEqual(result["total"], 1)


class EgressOnlyTests(unittest.TestCase):
    """Hermes is the sole getUpdates consumer — our egress files must not poll."""

    def test_no_getupdates_in_owner_egress_modules(self):
        for mod in (owner_notify, owner_feed_bridge, owner_feed_digest):
            src = inspect.getsource(mod)
            self.assertNotIn("getUpdates", src, f"{mod.__name__} must not consume getUpdates")


if __name__ == "__main__":
    unittest.main(verbosity=2)
