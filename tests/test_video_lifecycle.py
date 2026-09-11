"""T03 acceptance checks — 9-stage lifecycle projection (stdlib unittest only).

Covers:
  * the projection always returns all 9 stages in order;
  * a MISSING stage is `not_reached` / `failed` and is NEVER `passed` (the
    honesty rule the dashboard depends on);
  * the `failed_stage` names the single root cause;
  * the projection is tenant-scoped (a cross-tenant read is `not_found`);
  * every public entry returns a dict and never raises.

Run with the managed interpreter:
    python -m unittest tests.test_video_lifecycle
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.marketing.creative_os import lifecycle
from app.marketing.creative_os.recipes import build_scene_plan
from app.marketing.creative_os.spec import CreativeSpec
from app.marketing.creative_os.store import save_record


class _LedgerRedirect(unittest.TestCase):
    """Redirect the creative store (CREATIVE_LEDGER_ROOT) to a temp dir."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t03_lifecycle_")
        self.tmp = Path(self._tmp.name)
        self._old = os.environ.get("CREATIVE_LEDGER_ROOT")
        os.environ["CREATIVE_LEDGER_ROOT"] = str(self.tmp)

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("CREATIVE_LEDGER_ROOT", None)
        else:
            os.environ["CREATIVE_LEDGER_ROOT"] = self._old
        self._tmp.cleanup()

    def _spec(self, tenant: str, **over) -> CreativeSpec:  # noqa: ANN003
        scenes = build_scene_plan(
            "offer_announcement",
            business_name="Glow Salon",
            offer="Bridal glow",
            niche="salon",
            language="hinglish",
            cta="Call karo",
        )
        base = dict(
            creative_id=CreativeSpec.new_id(),
            tenant_id=tenant,
            goal="salon",
            audience="Glow Salon",
            offer="Bridal glow",
            language="hinglish",
            platform="instagram",
            aspect_ratio="9:16",
            recipe="offer_announcement",
            template_id="beauty_luxury_offer_v1",
            hook_variant="statement",
            scenes=scenes,
            script=" | ".join(s.text for s in scenes),
            captions={"primary": scenes[0].text},
            cta="Call karo",
        )
        base.update(over)
        return CreativeSpec(**base)


class TestStageContract(_LedgerRedirect):
    def test_stages_ordered(self) -> None:
        self.assertEqual(
            lifecycle.stages(),
            [
                "spec",
                "assets",
                "render",
                "qa",
                "enterprise_grade",
                "approval",
                "publish",
                "delivery",
                "evidence",
            ],
        )

    def test_projection_always_returns_all_nine(self) -> None:
        spec = self._spec("t03_lc_a")
        save_record(spec)
        proj = lifecycle.project("t03_lc_a", spec.creative_id)
        self.assertTrue(proj["ok"], proj)
        self.assertEqual([r["stage"] for r in proj["stages"]], list(lifecycle.STAGES))

    def test_missing_stage_is_never_passed(self) -> None:
        """A brand-new queued spec: only `spec` may pass; everything else must
        be not_reached — the exact honesty rule (no green for un-run stages)."""
        spec = self._spec("t03_lc_b")
        save_record(spec)
        proj = lifecycle.project("t03_lc_b", spec.creative_id)
        by = {r["stage"]: r for r in proj["stages"]}
        self.assertEqual(by["spec"]["status"], lifecycle.PASSED)
        for stage in ("assets", "render", "qa", "enterprise_grade", "approval", "publish", "delivery", "evidence"):
            self.assertNotEqual(by[stage]["status"], lifecycle.PASSED, f"{stage} wrongly passed")
        self.assertEqual(proj["failed_stage"], "assets")
        self.assertFalse(proj["complete"])

    def test_failed_stage_names_root_cause(self) -> None:
        spec = self._spec("t03_lc_c", status="qa_failed", failure_reason="black_frame")
        spec.qa_results = {"ok": False, "blockers": ["black_frame"]}
        save_record(spec)
        proj = lifecycle.project("t03_lc_c", spec.creative_id)
        by = {r["stage"]: r for r in proj["stages"]}
        self.assertEqual(by["qa"]["status"], lifecycle.FAILED)
        self.assertIn("black_frame", by["qa"]["reason"])
        self.assertEqual(proj["failed_stage"], "assets")  # assets precedes qa in order

    def test_approval_pending_is_pending_not_failed(self) -> None:
        spec = self._spec("t03_lc_d")
        spec.output_hash = "deadbeef" * 4
        spec.output_asset_id = "asset_x"
        spec.qa_results = {"ok": True, "enterprise": {"customer_approvable": True, "classification": "PREMIUM"}}
        spec.status = "approval_pending"
        save_record(spec)
        proj = lifecycle.project("t03_lc_d", spec.creative_id)
        by = {r["stage"]: r for r in proj["stages"]}
        self.assertEqual(by["qa"]["status"], lifecycle.PASSED)
        self.assertEqual(by["enterprise_grade"]["status"], lifecycle.PASSED)
        self.assertEqual(by["approval"]["status"], lifecycle.PENDING)

    def test_cross_tenant_is_not_found(self) -> None:
        spec = self._spec("t03_lc_iso_a")
        save_record(spec)
        proj = lifecycle.project("t03_lc_iso_b", spec.creative_id)
        self.assertFalse(proj["ok"])
        self.assertIn(proj["status"], ("not_found", "tenant_mismatch"))

    def test_evidence_incomplete_reported_honestly(self) -> None:
        spec = self._spec("t03_lc_e")
        spec.output_hash = "a" * 64
        save_record(spec)
        proj = lifecycle.project("t03_lc_e", spec.creative_id)
        by = {r["stage"]: r for r in proj["stages"]}
        self.assertEqual(by["evidence"]["status"], lifecycle.NOT_REACHED)
        self.assertIn("incomplete", by["evidence"]["reason"])


class TestProjectTenant(_LedgerRedirect):
    def test_project_tenant_lists_and_counts(self) -> None:
        for i in range(3):
            save_record(self._spec("t03_lc_t", creative_id=f"cr_t{i:04d}"))
        out = lifecycle.project_tenant("t03_lc_t", limit=10)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["items"]), 3)
        self.assertIn("assets", out["counts"])  # every fresh spec stops at assets

    def test_project_tenant_requires_tenant(self) -> None:
        out = lifecycle.project_tenant("")
        self.assertFalse(out["ok"])


class TestReconcile(_LedgerRedirect):
    def test_reconcile_reports_stuck_across_tenants(self) -> None:
        save_record(self._spec("t03_rec_a", creative_id="cr_rec_a"))
        save_record(self._spec("t03_rec_b", creative_id="cr_rec_b"))
        out = lifecycle.reconcile(limit=50)
        self.assertTrue(out["ok"], out)
        self.assertGreaterEqual(out["tenants"], 2)
        self.assertGreaterEqual(out["creatives"], 2)
        # A fresh queued spec stops at `assets` — the sweep must say so honestly.
        self.assertIn("assets", out["stuck"])
        self.assertEqual(out["complete"], 0)
        self.assertTrue(any(i["stuck_at"] == "assets" for i in out["items"]))

    def test_reconcile_never_raises(self) -> None:
        for g in (None, "", 0, -5, 3, "x" * 5000, {"a": 1}):
            try:
                out = lifecycle.reconcile(limit=g)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                self.fail(f"reconcile(limit={g!r}) raised {type(exc).__name__}: {exc}")
            self.assertIsInstance(out, dict)


class TestNeverRaises(_LedgerRedirect):
    _GARBAGE = [None, "", "   ", 12345, {"a": 1}, ["x"], "a/b", "x" * 5000]

    def test_never_raises(self) -> None:
        failures: list[str] = []
        for g in self._GARBAGE:
            for label, fn in {
                "project": lambda g=g: lifecycle.project(g, g),
                "project_tenant": lambda g=g: lifecycle.project_tenant(g),
                "reconcile": lambda g=g: lifecycle.reconcile(limit=g),
            }.items():
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{label}({g!r:.20}) -> {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
