"""T02 acceptance: dev_workers execution proof + DB-backed idempotency + DLQ + kill switch.

Proves the PRD §1c "#1 trust gap": after a REAL task completes, `dev_workers > 0`.
All tests use an isolated temp DB (no touching of the real orchestrator ledger).
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.platform.automation_orchestrator import (
    AutomationOrchestrator,
    StructuredEvidence,
    TaskStatus,
)
from app.platform.dev_workers import DevWorkerStore, worker_id_for


class _IsolatedOrchestrator:
    """Context: an orchestrator + dev-worker store on a throwaway DB."""

    def __init__(self, testcase: unittest.TestCase):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "orchestrator_ledger.db")
        self.orchestrator = AutomationOrchestrator(
            store=self._make_store(),
            lease_file=os.path.join(self._tmp.name, "leases.json"),
            dev_worker_store=DevWorkerStore(db_path=self.db_path),
        )

    def _make_store(self):
        from app.platform.automation_orchestrator import DurableTaskStore

        return DurableTaskStore(db_path=self.db_path, ledger_file=os.path.join(self._tmp.name, "l.json"))

    def close(self):
        self._tmp.cleanup()


def _evidence(agent: str) -> StructuredEvidence:
    return StructuredEvidence(
        type="file_artifact",
        uri_or_path=f"data/artifacts/{agent}.json",
        producer=agent,
        checksum_or_result={"ok": True},
    )


class DevWorkersExecutionProofTests(unittest.TestCase):
    def setUp(self):
        self.env = _IsolatedOrchestrator(self)
        self.orch = self.env.orchestrator

    def tearDown(self):
        self.env.close()

    # ---- acceptance #1: a completed task yields dev_workers > 0 ----
    def test_completed_task_yields_dev_workers_gt_zero(self):
        completed = self.orch.execute_end_to_end(
            owner_bot="sales",
            assigned_agent="rohan",
            task_description="qualify_lead",
            input_payload={"lead": "L-1"},
        )
        self.assertEqual(completed.status, TaskStatus.DONE)
        self.assertGreater(self.orch.dev_workers_count(), 0)
        row = self.orch.dev_workers.get(completed.task_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "done")
        self.assertTrue(row["evidence"], "done worker row must carry evidence")

    def test_claim_writes_row_before_completion(self):
        task, _new = self.orch.submit_task(owner_bot="pilot", assigned_agent="dev", input_payload={"x": 1})
        self.orch.dispatch_task(task.task_id)
        row = self.orch.dev_workers.get(task.task_id)
        self.assertIsNotNone(row)
        self.assertIn(row["state"], ("claimed", "running"))

    # ---- acceptance #2: idempotency survives a process restart (DB truth) ----
    def test_idempotency_survives_restart(self):
        key = "sales:rohan:stablehash"
        t1, new1 = self.orch.submit_task(
            owner_bot="sales", assigned_agent="rohan", input_payload={"a": 1}, idempotency_key=key
        )
        self.assertTrue(new1)
        # Simulate a process restart: brand-new orchestrator on the SAME DB file.
        restarted = AutomationOrchestrator(
            store=self.env._make_store(),
            lease_file=os.path.join(self.env._tmp.name, "leases2.json"),
            dev_worker_store=DevWorkerStore(db_path=self.env.db_path),
        )
        t2, new2 = restarted.submit_task(
            owner_bot="sales", assigned_agent="rohan", input_payload={"a": 1}, idempotency_key=key
        )
        self.assertFalse(new2, "duplicate submit after restart must NOT re-execute")
        self.assertEqual(t1.task_id, t2.task_id)

    # ---- acceptance #3: kill switch respected ----
    def test_kill_switch_blocks_dispatch_and_writes_no_worker(self):
        task, _new = self.orch.submit_task(owner_bot="pilot", assigned_agent="dev", input_payload={"k": 1})
        os.environ["AUTOMATION_STOP_NEW_CLAIMS"] = "1"
        try:
            ok = self.orch.dispatch_task(task.task_id)
            self.assertFalse(ok)
            blocked = self.orch.store.get(task.task_id)
            self.assertEqual(blocked.status, TaskStatus.BLOCKED)
            self.assertIsNone(self.orch.dev_workers.get(task.task_id))
        finally:
            os.environ.pop("AUTOMATION_STOP_NEW_CLAIMS", None)

    # ---- acceptance #4: DLQ path (retry exhausted ⇒ FAILED + dlq_count) ----
    def test_dlq_path_after_max_retries(self):
        task, _new = self.orch.submit_task(owner_bot="pilot", assigned_agent="dev", input_payload={"d": 1})
        self.orch.dispatch_task(task.task_id)
        final = None
        for _ in range(task.max_retries):
            cur = self.orch.store.get(task.task_id)
            if cur.status == TaskStatus.READY:
                self.orch.dispatch_task(task.task_id)
            final = self.orch.verify_and_complete(
                task_id=task.task_id, execution_evidence=None, is_success=False, error_msg="boom"
            )
        self.assertEqual(final.status, TaskStatus.FAILED)
        self.assertGreaterEqual(self.orch.metrics["dlq_count"], 1)
        row = self.orch.dev_workers.get(task.task_id)
        self.assertEqual(row["state"], "failed")


class DevWorkerStoreUnitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DevWorkerStore(db_path=os.path.join(self._tmp.name, "dw.db"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_double_claim_is_idempotent(self):
        self.assertTrue(self.store.claim("task_aaaa", lease_token="fence1"))
        self.assertFalse(self.store.claim("task_aaaa", lease_token="fence2"), "same task cannot double-claim")
        self.assertEqual(self.store.count(), 1)

    def test_done_without_evidence_is_not_verified(self):
        self.store.claim("task_bbbb")
        self.store.finish("task_bbbb", success=True, evidence="")
        row = self.store.get("task_bbbb")
        self.assertEqual(row["state"], "done")
        self.assertEqual(self.store.verified_count(), 0, "done without evidence must NOT count as verified")

    def test_done_with_evidence_is_verified(self):
        self.store.claim("task_cccc")
        self.store.finish("task_cccc", success=True, evidence="data/artifacts/x.json")
        self.assertEqual(self.store.verified_count(), 1)

    def test_worker_id_format(self):
        self.assertEqual(worker_id_for("task_1234"), "dw_task_1234")

    def test_never_raises_on_empty_task(self):
        self.assertFalse(self.store.claim(""))
        self.assertFalse(self.store.heartbeat(""))
        self.assertFalse(self.store.finish(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
