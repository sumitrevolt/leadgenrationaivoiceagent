"""Tests for app/platform/omniroute_combo_health.py (Owner Command Center Q5).

stdlib ``unittest`` on purpose — the module is stdlib-only so these run under a
bare interpreter while the repo ``.venv`` is missing:
    python -m unittest tests.test_omniroute_combo_health

The point of these tests is the truth gate: this adapter must NEVER invent a
green tile. Missing state file, stale state file, unprobed combo and typo'd
combo id must all degrade to ``unknown`` / not-instrumented.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone

from app.platform.omniroute_combo_health import (
    CANONICAL_COMBOS,
    DEFAULT_STRIKES,
    EXPECTED_COMBO_COUNT,
    STATUS_DEGRADED,
    STATUS_DOWN,
    STATUS_OK,
    STATUS_UNKNOWN,
    canonical_ids,
    classify_combo,
    load_state,
    resolve_combo,
    snapshot,
    state_mtime,
)

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


def _write_state(tmp: str, payload: dict, age_seconds: float = 0.0) -> str:
    path = os.path.join(tmp, "omniroute_combo_state.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(path, (old, old))
    return path


def _ok() -> dict:
    return {"fails": 0, "alerted": False, "last_ok": NOW.isoformat(), "last_error": ""}


def _failing(n: int, error: str = "timeout") -> dict:
    return {"fails": n, "alerted": n >= DEFAULT_STRIKES, "last_ok": "", "last_error": error}


class ComboIdentityTests(unittest.TestCase):
    def test_exactly_fourteen_canonical_combos(self):
        self.assertEqual(len(CANONICAL_COMBOS), EXPECTED_COMBO_COUNT)
        self.assertEqual(len(canonical_ids()), EXPECTED_COMBO_COUNT)
        self.assertEqual(len(set(canonical_ids())), EXPECTED_COMBO_COUNT)

    def test_canonical_ids_are_numbered_1_to_14(self):
        self.assertEqual(
            canonical_ids(), [f"leadsgen combo {i}" for i in range(1, 15)]
        )

    def test_resolve_canonical_id(self):
        self.assertEqual(resolve_combo("leadsgen combo 7"), "leadsgen combo 7")

    def test_resolve_friendly_alias_from_combo_distribution_yaml(self):
        """The two namespaces must reconcile — this is the drift this module fixes."""
        self.assertEqual(resolve_combo("leadgen-free-first"), "leadsgen combo 1")
        self.assertEqual(resolve_combo("hermes-engineer"), "leadsgen combo 1")
        self.assertEqual(resolve_combo("hermes-voice"), "leadsgen combo 6")
        self.assertEqual(resolve_combo("hermes-qa"), "leadsgen combo 4")
        self.assertEqual(resolve_combo("leadgen-project-best"), "leadsgen combo 12")

    def test_resolve_is_case_and_space_tolerant(self):
        self.assertEqual(resolve_combo("  HERMES-SALES "), "leadsgen combo 5")

    def test_unknown_combo_does_not_silently_attach(self):
        self.assertIsNone(resolve_combo("totally-made-up"))
        self.assertIsNone(resolve_combo(""))
        self.assertIsNone(resolve_combo(None))


class ClassifyTests(unittest.TestCase):
    def test_zero_fails_is_ok(self):
        self.assertEqual(classify_combo(_ok()), STATUS_OK)

    def test_one_or_two_fails_is_degraded(self):
        self.assertEqual(classify_combo(_failing(1)), STATUS_DEGRADED)
        self.assertEqual(classify_combo(_failing(2)), STATUS_DEGRADED)

    def test_at_strikes_is_down(self):
        self.assertEqual(classify_combo(_failing(3)), STATUS_DOWN)
        self.assertEqual(classify_combo(_failing(99)), STATUS_DOWN)

    def test_strikes_threshold_is_configurable(self):
        self.assertEqual(classify_combo(_failing(2), strikes=2), STATUS_DOWN)
        self.assertEqual(classify_combo(_failing(2), strikes=5), STATUS_DEGRADED)

    def test_missing_or_malformed_record_is_unknown_not_ok(self):
        self.assertEqual(classify_combo(None), STATUS_UNKNOWN)
        self.assertEqual(classify_combo({}), STATUS_UNKNOWN)
        self.assertEqual(classify_combo("nonsense"), STATUS_UNKNOWN)
        self.assertEqual(classify_combo({"fails": "many"}), STATUS_UNKNOWN)


class SnapshotTruthGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_state_file_is_not_instrumented(self):
        snap = snapshot(os.path.join(self.tmp, "does_not_exist.json"), now_dt=NOW)
        self.assertFalse(snap["instrumented"])
        self.assertEqual(snap["total"], EXPECTED_COMBO_COUNT)
        self.assertEqual(snap["unknown"], EXPECTED_COMBO_COUNT)
        self.assertEqual(snap["ok"], 0)

    def test_stale_state_file_is_reported_stale_and_demoted(self):
        """A 2-hour-old 'all ok' must NOT be shown as a green tile."""
        path = _write_state(
            self.tmp, {c: _ok() for c in canonical_ids()}, age_seconds=7200
        )
        snap = snapshot(path, now=time.time(), now_dt=NOW)
        self.assertTrue(snap["stale"])
        self.assertFalse(snap["instrumented"])
        self.assertEqual(snap["ok"], 0)
        self.assertEqual(snap["unknown"], EXPECTED_COMBO_COUNT)

    def test_fresh_all_ok_snapshot(self):
        path = _write_state(self.tmp, {c: _ok() for c in canonical_ids()})
        snap = snapshot(path, now=time.time(), now_dt=NOW)
        self.assertTrue(snap["instrumented"])
        self.assertFalse(snap["stale"])
        self.assertEqual(snap["ok"], EXPECTED_COMBO_COUNT)
        self.assertEqual(snap["down"], 0)

    def test_mixed_status_counts(self):
        payload = {c: _ok() for c in canonical_ids()}
        payload["leadsgen combo 3"] = _failing(1)
        payload["leadsgen combo 9"] = _failing(DEFAULT_STRIKES)
        path = _write_state(self.tmp, payload)
        snap = snapshot(path, now=time.time(), now_dt=NOW)
        self.assertEqual(snap["ok"], EXPECTED_COMBO_COUNT - 2)
        self.assertEqual(snap["degraded"], 1)
        self.assertEqual(snap["down"], 1)
        down = [c for c in snap["combos"] if c["status"] == STATUS_DOWN]
        self.assertEqual(down[0]["combo"], "leadsgen combo 9")
        self.assertEqual(down[0]["last_error"], "timeout")

    def test_unprobed_combo_is_unknown_even_when_others_are_ok(self):
        payload = {c: _ok() for c in canonical_ids()}
        payload.pop("leadsgen combo 14")
        path = _write_state(self.tmp, payload)
        snap = snapshot(path, now=time.time(), now_dt=NOW)
        row = [c for c in snap["combos"] if c["combo"] == "leadsgen combo 14"][0]
        self.assertEqual(row["status"], STATUS_UNKNOWN)
        self.assertTrue(snap["instrumented"])  # partially instrumented is still real

    def test_alias_keyed_record_is_recognised(self):
        """Watchdog recorded under a friendly id — still maps to the canonical row."""
        path = _write_state(self.tmp, {"hermes-voice": _failing(3)})
        snap = snapshot(path, now=time.time(), now_dt=NOW)
        row = [c for c in snap["combos"] if c["combo"] == "leadsgen combo 6"][0]
        self.assertEqual(row["status"], STATUS_DOWN)

    def test_payload_has_no_secret_keys(self):
        path = _write_state(self.tmp, {c: _ok() for c in canonical_ids()})
        snap = snapshot(path, now=time.time(), now_dt=NOW)
        banned = ("token", "secret", "password", "api_key", "apikey", "credential", "email")
        for row in snap["combos"]:
            for key in row:
                self.assertNotIn(key.lower(), banned)
        self.assertNotIn("key", snap)

    def test_corrupt_state_file_degrades_gracefully(self):
        path = os.path.join(self.tmp, "corrupt.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json at all")
        self.assertEqual(load_state(path), {})
        snap = snapshot(path, now_dt=NOW)
        self.assertFalse(snap["instrumented"])

    def test_state_mtime_returns_none_for_missing_file(self):
        self.assertIsNone(state_mtime(os.path.join(self.tmp, "nope.json")))


if __name__ == "__main__":
    unittest.main()
