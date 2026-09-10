"""Tests for app/utils/owner_feed.py (T-02 owner feed store).

stdlib-only on purpose: the repo `.venv` is currently missing (see
COORDINATION_BROADCAST.md §5), so these must run under a bare interpreter via
`python -m unittest tests.test_owner_feed`.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from app.utils.owner_feed import (
    DEFAULT_TRUSTED_SOURCES,
    FORCE_UNVERIFIED_SOURCES,
    REQUIRED_FIELDS,
    append_event,
    build_event,
    emit,
    read_events,
)


def _feed(tmp: str) -> str:
    return os.path.join(tmp, "owner_feed_events.jsonl")


class BuildEventSchemaTests(unittest.TestCase):
    def test_build_event_has_all_required_fields(self):
        ev = build_event(source="workbuddy", actor="nova", text="claimed C-01")
        for field in REQUIRED_FIELDS:
            self.assertIn(field, ev)

    def test_defaults_are_info_heartbeat_unverified(self):
        ev = build_event(source="workbuddy", actor="nova", text="x")
        self.assertEqual(ev["severity"], "info")
        self.assertEqual(ev["kind"], "heartbeat")
        self.assertFalse(ev["verified"])
        self.assertTrue(ev["ts"].endswith("Z"))

    def test_source_is_lowercased_and_trimmed(self):
        ev = build_event(source="  WorkBuddy ", actor="nova", text="x")
        self.assertEqual(ev["source"], "workbuddy")


class TruthGateTests(unittest.TestCase):
    """The fail-closed rule that keeps false confidence out of the owner feed."""

    def test_workforce_can_never_be_verified(self):
        self.assertIn("workforce", FORCE_UNVERIFIED_SOURCES)
        ev = build_event(source="workforce", actor="probe", text="592 actions", verified=True)
        self.assertFalse(ev["verified"], "workforce must stay unverified until T-05 lands")

    def test_trusted_source_can_be_verified(self):
        self.assertIn("hermes", DEFAULT_TRUSTED_SOURCES)
        ev = build_event(source="hermes", actor="hermes-gui", text="9119 up", verified=True)
        self.assertTrue(ev["verified"])

    def test_unknown_source_is_downgraded(self):
        ev = build_event(source="totally-unknown", actor="x", text="y", verified=True)
        self.assertFalse(ev["verified"])

    def test_verified_false_is_always_honoured(self):
        ev = build_event(source="hermes", actor="x", text="y", verified=False)
        self.assertFalse(ev["verified"])


class AppendTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.feed = _feed(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _valid(self, **kw):
        base = dict(
            ts="2026-09-10T07:35:00Z",
            source="workbuddy",
            actor="nova",
            severity="info",
            kind="ack",
            text="C-01 claimed",
            evidence="docs/context/WORKER_ROSTER.md",
            verified=False,
        )
        base.update(kw)
        return base

    def test_roundtrip(self):
        self.assertTrue(append_event(self._valid(), self.feed))
        events, corrupt = read_events(self.feed)
        self.assertEqual(corrupt, 0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["text"], "C-01 claimed")

    def test_line_is_compact_json_with_all_keys(self):
        append_event(self._valid(), self.feed)
        with open(self.feed, encoding="utf-8") as fh:
            line = fh.readline().strip()
        self.assertEqual(len(line.splitlines()), 1)
        obj = json.loads(line)
        self.assertEqual(set(REQUIRED_FIELDS) - set(obj), set())

    def test_invalid_severity_rejected(self):
        self.assertFalse(append_event(self._valid(severity="URGENT"), self.feed))
        self.assertEqual(read_events(self.feed)[0], [])

    def test_invalid_kind_rejected(self):
        self.assertFalse(append_event(self._valid(kind="vibes"), self.feed))

    def test_missing_field_rejected(self):
        ev = self._valid()
        del ev["evidence"]
        self.assertFalse(append_event(ev, self.feed))

    def test_non_bool_verified_rejected(self):
        self.assertFalse(append_event(self._valid(verified="yes"), self.feed))

    def test_empty_text_rejected(self):
        self.assertFalse(append_event(self._valid(text="   "), self.feed))

    def test_oversized_text_rejected(self):
        self.assertFalse(append_event(self._valid(text="x" * 1001), self.feed))

    def test_dedupe_suppresses_repeat(self):
        self.assertTrue(append_event(self._valid(dedupe_key="9119-down"), self.feed))
        self.assertFalse(append_event(self._valid(dedupe_key="9119-down"), self.feed))
        self.assertEqual(len(read_events(self.feed)[0]), 1)

    def test_distinct_dedupe_keys_both_written(self):
        append_event(self._valid(dedupe_key="a"), self.feed)
        append_event(self._valid(dedupe_key="b"), self.feed)
        self.assertEqual(len(read_events(self.feed)[0]), 2)

    def test_corrupt_line_counted_not_returned(self):
        os.makedirs(os.path.dirname(self.feed), exist_ok=True)
        with open(self.feed, "w", encoding="utf-8") as fh:
            fh.write("not json at all\n")
            fh.write(json.dumps(self._valid()) + "\n")
        events, corrupt = read_events(self.feed)
        self.assertEqual(corrupt, 1)
        self.assertEqual(len(events), 1)

    def test_limit_keeps_most_recent(self):
        for i in range(5):
            append_event(self._valid(text=f"event-{i}"), self.feed)
        events, _ = read_events(self.feed, limit=2)
        self.assertEqual([e["text"] for e in events], ["event-3", "event-4"])

    def test_missing_file_returns_empty(self):
        self.assertEqual(read_events(os.path.join(self._tmp.name, "nope.jsonl")), ([], 0))

    def test_never_raises_on_unwritable_path(self):
        # A directory cannot be opened for append — must return False, not raise.
        self.assertFalse(append_event(self._valid(), self._tmp.name))

    def test_never_raises_on_garbage_event(self):
        self.assertFalse(append_event({"unexpected": object()}, self.feed))


class EmitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.feed = _feed(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_emit_writes_valid_event(self):
        self.assertTrue(
            emit(
                source="hermes",
                actor="hermes-gui",
                text="9119 listening",
                severity="P1",
                kind="incident",
                evidence="netstat pid 29444",
                verified=True,
                path=self.feed,
            )
        )
        events, corrupt = read_events(self.feed)
        self.assertEqual(corrupt, 0)
        self.assertTrue(events[0]["verified"])
        self.assertEqual(events[0]["severity"], "P1")

    def test_emit_never_raises_on_bad_input(self):
        self.assertFalse(emit(source="", actor="", text="", path=self.feed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
