"""T03 acceptance checks — video automation health probes (stdlib unittest only).

The load-bearing assertion is the **fake-green fix**: a probe that only observed
a HEARTBEAT (the job "ran") must report `warn`, never `ok`. `ok` requires a real,
fresh ARTIFACT. This is the class of bug that hid a 15-day video outage behind
green heartbeats (2026-08-09 postmortem).

Run with the managed interpreter:
    python -m unittest tests.test_video_health
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app.platform.runtime_data_authority as auth
from app.marketing import delivery_ledger, video_health
from app.marketing.creative_os import novelty


class _StoreRedirect(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t03_health_")
        self.tmp = Path(self._tmp.name)
        self._orig = auth.resolve_store_path

        def _fake(**kw):  # noqa: ANN001
            return self.tmp / str(kw.get("store_id", "store")).replace(".", "_")

        auth.resolve_store_path = _fake  # type: ignore[assignment]
        self._env: dict[str, str | None] = {}

    def tearDown(self) -> None:
        auth.resolve_store_path = self._orig  # type: ignore[assignment]
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _set(self, k: str, v: str) -> None:
        self._env.setdefault(k, os.environ.get(k))
        os.environ[k] = v


def _beats(job: str) -> dict:
    return {job: {"job": job, "ok": True, "at": "2026-09-11T09:45:00+00:00", "s": 12.0}}


class TestRanVersusProduced(_StoreRedirect):
    def test_ran_but_not_produced_is_warn(self) -> None:
        """THE fake-green fix: heartbeat present, artifact absent ⇒ warn, not ok."""
        self._set("DAILY_VIDEO_ENABLED", "1")
        with mock.patch(
            "app.platform.automation_health._load_beats", return_value=_beats("daily_video")
        ), mock.patch(
            "app.marketing.daily_video.status",
            return_value={"clients": [{"client_id": "t", "generated_today": False}]},
        ):
            p = video_health.probe_daily_video()
        self.assertTrue(p["ran"], p)
        self.assertFalse(p["produced"], p)
        self.assertEqual(p["status"], "warn", p)
        self.assertFalse(p["verified"], "a heartbeat is NOT evidence of output")
        self.assertIn("produced no artifact", p["reason"])

    def test_produced_and_fresh_is_ok(self) -> None:
        self._set("DAILY_VIDEO_ENABLED", "1")
        with mock.patch(
            "app.platform.automation_health._load_beats", return_value=_beats("daily_video")
        ), mock.patch(
            "app.marketing.daily_video.status",
            return_value={"clients": [{"client_id": "t", "generated_today": True}]},
        ):
            p = video_health.probe_daily_video()
        self.assertTrue(p["produced"])
        self.assertEqual(p["status"], "ok", p)
        self.assertTrue(p["verified"])

    def test_no_heartbeat_no_artifact_is_down(self) -> None:
        self._set("DAILY_VIDEO_ENABLED", "1")
        with mock.patch("app.platform.automation_health._load_beats", return_value={}), mock.patch(
            "app.marketing.daily_video.status",
            return_value={"clients": [{"client_id": "t", "generated_today": False}]},
        ):
            p = video_health.probe_daily_video()
        self.assertFalse(p["ran"])
        self.assertEqual(p["status"], "down", p)

    def test_flag_off_is_gated_inert(self) -> None:
        self._set("DAILY_VIDEO_ENABLED", "0")
        with mock.patch("app.platform.automation_health._load_beats", return_value={}), mock.patch(
            "app.marketing.daily_video.status",
            return_value={"clients": []},
        ):
            p = video_health.probe_daily_video()
        self.assertEqual(p["status"], "gated_inert", p)
        self.assertFalse(p["enabled"])

    def test_truth_gate_force_labels_unverified(self) -> None:
        self._set("DAILY_VIDEO_ENABLED", "1")
        with mock.patch("app.platform.automation_health._load_beats", return_value=_beats("daily_video")), mock.patch(
            "app.marketing.daily_video.status",
            return_value={"clients": [{"client_id": "t", "generated_today": False}]},
        ):
            p = video_health.probe_daily_video()
        # The owner_feed event goes through the truth gate → verified stays False.
        self.assertIn("owner_feed", p)
        self.assertIs(p["owner_feed"].get("verified"), False)


class TestOtherProbes(_StoreRedirect):
    def test_novelty_probe_produced_when_lineage_exists(self) -> None:
        novelty.append_lineage(
            novelty.CreativeLineage(
                tenant_id="t03_h", creative_id="cr_x", revision=0, day="2026-09-11",
                recipe="offer_announcement", template_id="t", hook_variant="h",
                spec_hash="s", scene_text_hash="h", shingles=["a", "b", "c"],
            )
        )
        p = video_health.probe_novelty_gate()
        self.assertTrue(p["produced"], p)
        self.assertEqual(p["status"], "ok", p)
        self.assertGreaterEqual(p["tenant_lineages"], 1)

    def test_delivery_probe_produced_when_receipt_exists(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "1")
        delivery_ledger.log_event(
            "t03_h2", "video_delivered", detail="cr:rev0:customer", meta={"message_id": "9"}
        )
        p = video_health.probe_tg_delivery()
        self.assertTrue(p["produced"], p)
        self.assertEqual(p["status"], "ok", p)
        self.assertEqual(p["last_artifact_id"], "9")

    def test_local_render_probe_reports_plane_availability_honestly(self) -> None:
        p = video_health.probe_local_render()
        # T02 shipped the render plane. The probe must report availability
        # HONESTLY (True now that app/render_plane.jobstore exists, False where it
        # cannot be imported), and must never crash either way.
        expected = True
        try:
            from app.render_plane import jobstore  # noqa: F401
        except Exception:
            expected = False
        self.assertIsInstance(p["plane_available"], bool)
        self.assertEqual(p["plane_available"], expected)
        self.assertIn(p["status"], ("gated_inert", "warn", "down", "unknown", "ok"))


class TestLocalRenderSyncSeam(_StoreRedirect):
    """The ran-vs-produced fake-green fix, pinned at the sync seam.

    Before T02's ``recent_done`` the probe called the ASYNC ``list_jobs``
    synchronously, received a coroutine, degraded into ``plane_error``, and so
    could NEVER report ``produced`` — it could only say "the plane exists", never
    "the plane finished something". These three cases are the ones T02 measured
    against a real temp store.
    """

    def _probe(self, recent_done_return: object) -> dict:
        with mock.patch(
            "app.platform.automation_health._load_beats", return_value={}
        ), mock.patch(
            "app.render_plane.jobstore.recent_done", return_value=recent_done_return
        ):
            return video_health.probe_local_render()

    def test_populated_store_reports_produced_true(self) -> None:
        """A finished job WITH a real file on disk ⇒ produced True (the whole point)."""
        self._set("CREATIVE_RENDER_PLANE_ENABLED", "1")
        j2 = self.tmp / "j2.mp4"
        j1 = self.tmp / "j1.mp4"
        j2.write_bytes(b"newest")
        j1.write_bytes(b"older")
        r = self._probe(
            {
                "ok": True,
                "items": [
                    {"job_id": "j2", "artifact_sha256": "b" * 64, "artifact_path": str(j2)},
                    {"job_id": "j1", "artifact_sha256": "a" * 64, "artifact_path": str(j1)},
                ],
                "count": 2,
                "done": 2,
            }
        )
        self.assertTrue(r["produced"], r)
        self.assertIs(r["plane_available"], True)
        self.assertEqual(r["completed_jobs"], 2)
        self.assertEqual(r["last_artifact_id"], "j2")  # newest finished first
        self.assertEqual(r["last_artifact_hash"], "b" * 64)
        self.assertEqual(r["status"], "ok", r)  # produced + fresh ⇒ ok
        self.assertTrue(r["verified"])
        self.assertNotIn("plane_error", r)

    def test_done_row_without_a_file_on_disk_is_not_produced(self) -> None:
        """A done ROW whose artifact file is absent must NOT grade green (fake-green)."""
        self._set("CREATIVE_RENDER_PLANE_ENABLED", "1")
        ghost = self.tmp / "ghost.mp4"  # never created
        r = self._probe(
            {
                "ok": True,
                "items": [{"job_id": "j2", "artifact_sha256": "b" * 64, "artifact_path": str(ghost)}],
                "count": 1,
                "done": 1,
            }
        )
        self.assertFalse(r["produced"], r)
        self.assertNotEqual(r["status"], "ok", r)
        self.assertFalse(r["verified"], r)
        self.assertTrue(r.get("artifact_missing"), r)
        self.assertIn("artifact_missing", r["reason"])

    def test_empty_store_is_a_legit_zero_not_an_error(self) -> None:
        """ok:True with no jobs is honest empty — must NOT surface plane_error."""
        self._set("CREATIVE_RENDER_PLANE_ENABLED", "1")
        r = self._probe({"ok": True, "items": [], "count": 0, "done": 0})
        self.assertFalse(r["produced"], r)
        self.assertIs(r["plane_available"], True)
        self.assertEqual(r["completed_jobs"], 0)
        self.assertNotIn("plane_error", r)
        self.assertEqual(r["status"], "down", r)  # no heartbeat + no artifact

    def test_unreadable_store_is_honest_plane_error_never_green(self) -> None:
        """ok:False ⇒ produced False + plane_error present (never a fake 0-as-green)."""
        self._set("CREATIVE_RENDER_PLANE_ENABLED", "1")
        r = self._probe({"ok": False, "error": "recent_done_failed:RuntimeError"})
        self.assertFalse(r["produced"], r)  # NEVER faked green
        self.assertIs(r["plane_available"], True)
        self.assertIn("plane_error", r)
        self.assertIn("recent_done_failed", r["plane_error"])
        self.assertEqual(r["status"], "down", r)


class TestHealth(_StoreRedirect):
    def test_health_ok_requires_no_degraded(self) -> None:
        with mock.patch(
            "app.marketing.video_health.probe_automation",
            side_effect=lambda name: {
                "automation": name, "enabled": True, "ran": True, "produced": True,
                "stale": False, "artifact_age_s": 1.0, "verified": True,
                "status": "ok", "reason": "ok", "owner_feed": {},
            },
        ):
            h = video_health.health()
        self.assertTrue(h["ok"])
        self.assertEqual(h["degraded"], [])
        self.assertEqual(len(h["automations"]), 4)

    def test_health_degraded_on_warn(self) -> None:
        with mock.patch(
            "app.marketing.video_health.probe_automation",
            side_effect=lambda name: {
                "automation": name, "enabled": True, "ran": True, "produced": False,
                "stale": False, "artifact_age_s": None, "verified": False,
                "status": "warn", "reason": "ran but produced nothing", "owner_feed": {},
            },
        ):
            h = video_health.health()
        self.assertFalse(h["ok"])
        self.assertEqual(len(h["degraded"]), 4)


class TestNeverRaises(_StoreRedirect):
    _GARBAGE = [None, "", "   ", 12345, {"a": 1}, ["x"], "a/b", "x" * 5000]

    def test_never_raises(self) -> None:
        failures: list[str] = []
        with mock.patch(
            "app.platform.automation_health._load_beats", return_value={}
        ), mock.patch("app.marketing.daily_video.status", return_value={"clients": []}):
            for g in self._GARBAGE:
                for label, fn in {
                    "probe_automation": lambda g=g: video_health.probe_automation(g),
                    "local_render_status": lambda g=g: video_health.local_render_status(),
                    "health": lambda g=g: video_health.health(),
                    "probe_daily_video": lambda g=g: video_health.probe_daily_video(),
                    "probe_novelty_gate": lambda g=g: video_health.probe_novelty_gate(),
                    "probe_tg_delivery": lambda g=g: video_health.probe_tg_delivery(),
                    "probe_local_render": lambda g=g: video_health.probe_local_render(),
                }.items():
                    try:
                        fn()
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"{label}({g!r:.20}) -> {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_unknown_automation(self) -> None:
        p = video_health.probe_automation("does_not_exist")
        self.assertEqual(p["status"], "unknown")
        self.assertFalse(p["verified"])


if __name__ == "__main__":
    unittest.main()
