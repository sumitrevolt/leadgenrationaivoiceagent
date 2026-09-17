"""T03 acceptance: owner_notify fail-open + dedupe + evidence-required + truth gate.

Also proves: workforce events are UNVERIFIED, digest works, and there is ZERO
`getUpdates` in the new egress modules.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from pathlib import Path

import app.utils.owner_notify as owner_notify
from app.platform import owner_feed_bridge, owner_feed_digest
from app.utils.owner_feed import FORCE_UNVERIFIED_SOURCES, build_event, emit, read_events

REPO = Path(__file__).resolve().parents[1]


def _feed(tmp: str) -> str:
    return os.path.join(tmp, "owner_feed_events.jsonl")


class SendOwnerTests(unittest.TestCase):
    def setUp(self):
        owner_notify.reset_caches()
        self._tmp = tempfile.TemporaryDirectory()
        self.feed = _feed(self._tmp.name)
        os.environ["OWNER_FEED_PATH"] = self.feed

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("OWNER_FEED_PATH", None)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        owner_notify.reset_caches()

    # ---- acceptance: fail-open (Telegram down must not break the app) ----
    def test_fail_open_without_token(self):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        # dry_run avoids real network; delivery path must simply return without raising.
        self.assertFalse(
            owner_notify.send_owner("hello", severity="P1", evidence="data/x.json", dedupe_key="k1")
        )

    def test_never_raises_on_garbage(self):
        self.assertFalse(owner_notify.send_owner("", severity="P0"))
        self.assertFalse(owner_notify.send_owner(None))  # type: ignore[arg-type]

    # ---- evidence required ⇒ UNVERIFIED tag ----
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
        # The suppressed duplicate must NOT add a second alert line.
        self.assertEqual(after, before)

    # ---- dry run returns True and does not hit the network ----
    def test_dry_run_true(self):
        self.assertTrue(owner_notify.send_owner("x", severity="P0", evidence="e", dedupe_key="dr1", dry_run=True))


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
        written = owner_feed_bridge.bridge_bot_fleet()
        self.assertEqual(written, 1)
        events, _ = read_events(self.feed)
        bf = [e for e in events if e.get("source") == "bot_fleet"]
        self.assertEqual(len(bf), 1)


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
