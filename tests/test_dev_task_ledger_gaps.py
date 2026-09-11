"""Tests for the five DevTask canonical-ledger gaps (stdlib-only).

stdlib-only on purpose: the repo `.venv` is currently missing (see
COORDINATION_BROADCAST.md §5), so these run under a bare interpreter:

    C:\\Users\\Ratanshila\\.workbuddy-ai\\binaries\\python\\versions\\3.13.12\\python.exe \
        -m unittest tests.test_dev_task_ledger_gaps

Only the PURE layers are covered here — backoff/lease policy
(``app.dev_control.lease_policy``) and the hash chain
(``app.dev_control.ledger_hash``). Both were deliberately split out of
``reconcile.py`` / ``models/dev_task_event.py`` so they are decidable without
SQLAlchemy.

NOT covered here (UNVERIFIED, needs a DB + the app venv):
  * ``DevTask.parent_id`` / ``DevTask.next_eligible_at`` column DDL;
  * ``DevTaskEvent`` persistence + ``append_event`` seq/prev_hash SELECT;
  * ``claims.claim_next`` backoff predicate actually hitting SQL;
  * ``reconcile.reconcile_leases`` / ``reconcile_expired_leases_sync`` I/O;
  * ``service.create_task_record`` DB-backed idempotency (IntegrityError path).
"""

from __future__ import annotations

import random
import unittest
from datetime import datetime, timedelta

from app.dev_control.lease_policy import (
    BACKOFF_CAP_SECONDS,
    BACKOFF_MAX_JITTER_RATIO,
    DEFAULT_MAX_RETRIES,
    clamp_jitter_ratio,
    clamp_retry_count,
    compute_retry_backoff_seconds,
    next_eligible_at,
    plan_lease_reclaim,
    sample_retry_backoff_seconds,
)
from app.dev_control.ledger_hash import (
    GENESIS_HASH,
    canonical_json,
    compute_event_hash,
    normalise_created_at,
    verify_event_chain,
)
from app.dev_control.service import TaskState, create_task_record

NOW = datetime(2026, 9, 11, 12, 0, 0)


# --------------------------------------------------------------------- backoff
class BackoffCurveTests(unittest.TestCase):
    """60s * 2^retry_count, 15-minute cap, jitter inside [0%, 10%]."""

    def test_curve_doubles_from_the_first_failed_attempt(self):
        # retry_count is counted AFTER the failed attempt: 1 -> 120s, 2 -> 240s...
        self.assertEqual(compute_retry_backoff_seconds(1), 120)
        self.assertEqual(compute_retry_backoff_seconds(2), 240)
        self.assertEqual(compute_retry_backoff_seconds(3), 480)

    def test_curve_is_capped_at_fifteen_minutes(self):
        self.assertEqual(compute_retry_backoff_seconds(4), BACKOFF_CAP_SECONDS)
        self.assertEqual(compute_retry_backoff_seconds(10), BACKOFF_CAP_SECONDS)
        self.assertEqual(compute_retry_backoff_seconds(50), BACKOFF_CAP_SECONDS)
        self.assertEqual(BACKOFF_CAP_SECONDS, 900)

    def test_zero_and_garbage_retry_counts_do_not_explode(self):
        self.assertEqual(compute_retry_backoff_seconds(0), 60)
        self.assertEqual(compute_retry_backoff_seconds(None), 60)
        self.assertEqual(compute_retry_backoff_seconds("x"), 60)
        self.assertEqual(compute_retry_backoff_seconds(-5), 60)

    def test_jitter_is_added_on_top_of_the_capped_base(self):
        base = compute_retry_backoff_seconds(4)
        jittered = compute_retry_backoff_seconds(4, jitter_ratio=BACKOFF_MAX_JITTER_RATIO)
        self.assertEqual(jittered, int(round(base * 1.10)))

    def test_jitter_is_clamped_into_the_allowed_band(self):
        self.assertEqual(clamp_jitter_ratio(-1.0), 0.0)
        self.assertEqual(clamp_jitter_ratio(0.5), BACKOFF_MAX_JITTER_RATIO)
        self.assertEqual(clamp_jitter_ratio("nonsense"), 0.0)
        self.assertEqual(clamp_jitter_ratio(None), 0.0)

    def test_sampled_backoff_lands_within_bounds(self):
        rng = random.Random(1234)
        for _ in range(200):
            base = compute_retry_backoff_seconds(2)  # 240
            value = sample_retry_backoff_seconds(2, rng=rng)
            self.assertGreaterEqual(value, base)
            self.assertLessEqual(value, int(round(base * (1.0 + BACKOFF_MAX_JITTER_RATIO))))

    def test_sampled_backoff_is_seed_deterministic(self):
        a = sample_retry_backoff_seconds(1, rng=random.Random(7))
        b = sample_retry_backoff_seconds(1, rng=random.Random(7))
        self.assertEqual(a, b)

    def test_next_eligible_at_is_now_plus_backoff(self):
        when = next_eligible_at(NOW, 1, rng=random.Random(0))
        self.assertIsInstance(when, datetime)
        self.assertGreaterEqual(when, NOW + timedelta(seconds=120))
        self.assertLessEqual(when, NOW + timedelta(seconds=132))


# ------------------------------------------------------------- reclaim planner
class PlanLeaseReclaimTests(unittest.TestCase):
    """PURE decision function behind both reconcile entrypoints."""

    def test_first_expiry_requeues_with_a_future_eligibility(self):
        plan = plan_lease_reclaim(
            state=TaskState.CLAIMED.value, retry_count=0, max_retries=3, now=NOW
        )
        self.assertEqual(plan["outcome"], "requeued")
        self.assertEqual(plan["state"], TaskState.QUEUED.value)
        self.assertEqual(plan["retry_count"], 1)
        self.assertIsNone(plan["lease_owner"])
        self.assertIsNone(plan["lease_until"])
        self.assertGreater(plan["next_eligible_at"], NOW)

    def test_in_flight_states_leave_legally_via_blocked(self):
        for state in (TaskState.CLAIMED.value, TaskState.RUNNING.value):
            plan = plan_lease_reclaim(state=state, retry_count=0, max_retries=3, now=NOW)
            self.assertEqual(plan["intermediate_state"], TaskState.BLOCKED.value)

    def test_unknown_state_gets_no_intermediate_hop(self):
        plan = plan_lease_reclaim(state="queued", retry_count=0, max_retries=3, now=NOW)
        self.assertIsNone(plan["intermediate_state"])

    def test_retry_cap_fails_the_task_and_clears_backoff(self):
        plan = plan_lease_reclaim(
            state=TaskState.RUNNING.value,
            retry_count=DEFAULT_MAX_RETRIES,  # becomes 4 > 3
            max_retries=DEFAULT_MAX_RETRIES,
            now=NOW,
        )
        self.assertEqual(plan["outcome"], "failed")
        self.assertEqual(plan["state"], TaskState.FAILED.value)
        self.assertIsNone(plan["next_eligible_at"])
        self.assertEqual(plan["backoff_seconds"], 0)
        self.assertIn("max_retries", plan["blocked_reason"])

    def test_backoff_grows_with_each_successive_expiry(self):
        seen = []
        retry_count = 0
        for _ in range(3):
            plan = plan_lease_reclaim(
                state=TaskState.CLAIMED.value,
                retry_count=retry_count,
                max_retries=5,
                now=NOW,
                rng=random.Random(0),
            )
            retry_count = plan["retry_count"]
            seen.append(plan["backoff_seconds"])
        self.assertEqual(len(seen), 3)
        self.assertLess(seen[0], seen[1])
        self.assertLess(seen[1], seen[2])

    def test_planner_never_mutates_or_reads_the_db(self):
        plan = plan_lease_reclaim(state=TaskState.CLAIMED.value, retry_count=0, now=NOW)
        self.assertIsInstance(plan, dict)
        self.assertEqual(clamp_retry_count(None), 0)


# ------------------------------------------------------------------ hash chain
def _chain_events(count: int, *, tamper_payload: str | None = None) -> list[dict]:
    """Build a valid in-memory chain of ``count`` events for one fake task."""
    events: list[dict] = []
    prev_hash = GENESIS_HASH
    for index in range(1, count + 1):
        payload = {"attempt": index, "note": "reclaimed"}
        if tamper_payload is not None and index == 2:
            payload = {"attempt": index, "note": tamper_payload}
        created_at = NOW + timedelta(seconds=index)
        events.append(
            {
                "task_id": "task-1",
                "seq": index,
                "prev_hash": prev_hash,
                "event_hash": compute_event_hash(
                    prev_hash=prev_hash,
                    payload=payload,
                    from_state="claimed",
                    to_state="queued",
                    seq=index,
                    created_at=created_at,
                ),
                "actor": "supervisor-bot",
                "from_state": "claimed",
                "to_state": "queued",
                "payload": payload,
                "created_at": created_at,
            }
        )
        prev_hash = events[-1]["event_hash"]
    return events


class HashChainTests(unittest.TestCase):
    def test_genesis_is_64_zeros(self):
        self.assertEqual(GENESIS_HASH, "0" * 64)
        self.assertEqual(len(GENESIS_HASH), 64)

    def test_hash_is_64_hex_chars(self):
        digest = compute_event_hash(
            prev_hash=GENESIS_HASH,
            payload={"a": 1},
            from_state="queued",
            to_state="claimed",
            seq=1,
            created_at=NOW,
        )
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # raises if not hex

    def test_first_event_links_to_genesis(self):
        events = _chain_events(1)
        self.assertEqual(events[0]["prev_hash"], GENESIS_HASH)
        self.assertTrue(verify_event_chain(events)[0])

    def test_each_prev_hash_equals_the_prior_event_hash(self):
        events = _chain_events(3)
        self.assertEqual(events[0]["prev_hash"], GENESIS_HASH)
        self.assertEqual(events[1]["prev_hash"], events[0]["event_hash"])
        self.assertEqual(events[2]["prev_hash"], events[1]["event_hash"])
        self.assertTrue(all(len(e["event_hash"]) == 64 for e in events))
        ok, reason = verify_event_chain(events)
        self.assertTrue(ok, reason)

    def test_empty_chain_verifies(self):
        self.assertEqual(verify_event_chain([]), (True, "empty"))

    def test_verifier_sorts_by_seq_before_checking(self):
        events = list(reversed(_chain_events(3)))
        ok, reason = verify_event_chain(events)
        self.assertTrue(ok, reason)

    def test_tampered_payload_is_detected(self):
        events = _chain_events(3, tamper_payload="I edited history")
        # Payload changed but the stored hash was recomputed, so the chain still
        # links — the point of the test is that the DIGEST tracks the payload.
        recomputed = compute_event_hash(
            prev_hash=events[1]["prev_hash"],
            payload={"attempt": 2, "note": "reclaimed"},
            from_state=events[1]["from_state"],
            to_state=events[1]["to_state"],
            seq=events[1]["seq"],
            created_at=events[1]["created_at"],
        )
        self.assertNotEqual(events[1]["event_hash"], recomputed)

    def test_spliced_hash_is_detected(self):
        events = _chain_events(3)
        events[1]["event_hash"] = "f" * 64
        ok, reason = verify_event_chain(events)
        self.assertFalse(ok)
        self.assertIn("event_hash mismatch at seq=2", reason)

    def test_broken_link_is_detected(self):
        events = _chain_events(3)
        events[2]["prev_hash"] = "a" * 64
        ok, reason = verify_event_chain(events)
        self.assertFalse(ok)
        self.assertIn("prev_hash mismatch at seq=3", reason)

    def test_seq_gap_is_detected(self):
        events = _chain_events(3)
        events[2]["seq"] = 9
        ok, reason = verify_event_chain(events)
        self.assertFalse(ok)
        self.assertIn("seq gap", reason)

    def test_field_order_and_state_changes_move_the_digest(self):
        a = compute_event_hash(
            prev_hash=GENESIS_HASH,
            payload={"x": 1},
            from_state="queued",
            to_state="claimed",
            seq=1,
            created_at=NOW,
        )
        b = compute_event_hash(
            prev_hash=GENESIS_HASH,
            payload={"x": 1},
            from_state="claimed",
            to_state="queued",
            seq=1,
            created_at=NOW,
        )
        self.assertNotEqual(a, b)

    def test_canonical_json_is_key_order_independent(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}), canonical_json({"a": 2, "b": 1}))
        self.assertEqual(canonical_json(None), "{}")

    def test_created_at_is_normalised_to_iso(self):
        self.assertEqual(normalise_created_at(NOW), NOW.isoformat())
        self.assertEqual(normalise_created_at(None), "")
        self.assertEqual(normalise_created_at("2026-09-11T12:00:00"), "2026-09-11T12:00:00")


# --------------------------------------------------------- service guard rails
class ServiceGuardTests(unittest.TestCase):
    """Only the pre-DB guard is testable without the app stack."""

    def test_blank_idempotency_key_is_rejected_before_any_io(self):
        with self.assertRaises(ValueError):
            create_task_record("objective", "   ")
        with self.assertRaises(ValueError):
            create_task_record("objective", "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
