"""T03 acceptance checks — video delivery + capture flow (stdlib unittest only).

Covers:
  * delivery is fail-closed (flag off / no token ⇒ honest no-op, never a raise);
  * a per-customer binding is tenant-scoped and the raw chat id is NEVER exposed
    by the masked view;
  * a delivered video produces a ledger receipt with the Telegram message id;
  * a failed target is queued for retry and eventually marked exhausted;
  * the capture flow REFUSES without explicit consent and unlocks
    `before_after` / `testimonial` only through the unchanged `recipe_allowed`;
  * every public entry returns a dict and never raises.

Run with the managed interpreter:
    python -m unittest tests.test_video_delivery
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app.platform.runtime_data_authority as auth
from app.marketing import delivery_ledger, video_delivery
from app.marketing.creative_os import recipes


class _StoreRedirect(unittest.TestCase):
    """Redirect every store resolved through runtime_data_authority to a temp dir."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t03_delivery_")
        self.tmp = Path(self._tmp.name)
        self._orig_resolve = auth.resolve_store_path

        def _fake_resolve(**kw):  # noqa: ANN001
            return self.tmp / str(kw.get("store_id", "store")).replace(".", "_")

        auth.resolve_store_path = _fake_resolve  # type: ignore[assignment]
        self._env: dict[str, str | None] = {}

    def tearDown(self) -> None:
        auth.resolve_store_path = self._orig_resolve  # type: ignore[assignment]
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _set(self, key: str, val: str) -> None:
        self._env.setdefault(key, os.environ.get(key))
        os.environ[key] = val


def _make_mp4(tmp: Path) -> str:
    p = tmp / "out.mp4"
    p.write_bytes(b"\x00" * 32)
    return str(p)


class TestFailClosed(_StoreRedirect):
    def test_disabled_is_honest_noop(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "0")
        out = video_delivery.deliver_video("t03_a", "cr_1")
        self.assertFalse(out["ok"])
        self.assertEqual(out["outcome"], "disabled")

    def test_enabled_without_token_is_honest_noop(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "1")
        self._set("TELEGRAM_BOT_TOKEN", "")
        out = video_delivery.deliver_video("t03_a", "cr_1")
        self.assertFalse(out["ok"])
        self.assertEqual(out["outcome"], "no_token")

    def test_missing_ids_is_invalid_request(self) -> None:
        out = video_delivery.deliver_video("", "")
        self.assertFalse(out["ok"])
        self.assertEqual(out["outcome"], "invalid_request")


class TestBindings(_StoreRedirect):
    def test_bind_and_mask(self) -> None:
        out = video_delivery.bind_customer("t03_bind", "123456789", label="owner")
        self.assertTrue(out["ok"])
        self.assertNotIn("123456789", out["chat_masked"])
        view = video_delivery.binding_view("t03_bind")
        self.assertTrue(view["bound"])
        self.assertNotIn("123456789", view["chat_masked"])
        # Raw id is available to the owning module (delivery needs it)…
        raw = video_delivery.get_binding("t03_bind")
        self.assertTrue(raw["ok"])
        self.assertEqual(raw["binding"]["chat_id"], "123456789")

    def test_cross_tenant_binding_is_not_found(self) -> None:
        video_delivery.bind_customer("t03_iso_a", "111")
        self.assertFalse(video_delivery.get_binding("t03_iso_b")["ok"])
        self.assertFalse(video_delivery.binding_view("t03_iso_b")["bound"])

    def test_unbind(self) -> None:
        video_delivery.bind_customer("t03_un", "222")
        self.assertTrue(video_delivery.unbind_customer("t03_un")["removed"])
        self.assertFalse(video_delivery.binding_view("t03_un")["bound"])

    def test_mask_helper(self) -> None:
        self.assertEqual(video_delivery.mask_chat_id(""), "")
        self.assertEqual(video_delivery.mask_chat_id("12"), "**")
        self.assertTrue(video_delivery.mask_chat_id("123456789").endswith("89"))


class TestDeliveryHappyPath(_StoreRedirect):
    def _enable(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "1")
        self._set("TELEGRAM_BOT_TOKEN", "test-token")
        self._set("TELEGRAM_OPS_GROUP_ID", "-100999")

    def test_delivers_and_records_receipt(self) -> None:
        self._enable()
        video_delivery.bind_customer("t03_ok", "555")
        mp4 = _make_mp4(self.tmp)

        from app.social_engine.base import PublishResult

        async def _fake_publish(self, req, account):  # noqa: ANN001
            return PublishResult(ok=True, platform="telegram", post_id="777")

        with mock.patch(
            "app.marketing.creative_os.service.resolve_output_path",
            return_value={"ok": True, "path": mp4, "sha256": "abc", "revision": 0},
        ), mock.patch(
            "app.social_engine.providers.TelegramProvider.publish", new=_fake_publish
        ):
            out = video_delivery.deliver_video("t03_ok", "cr_ok", caption="hello")

        self.assertTrue(out["ok"], out)
        self.assertEqual(out["outcome"], "delivered")
        self.assertEqual(out["targets"]["customer"]["message_id"], "777")
        self.assertTrue(out["targets"]["ops"]["ok"])
        # A receipt exists in the ledger, carrying the message id.
        events = [e for e in delivery_ledger.timeline("t03_ok", limit=20) if e["event"] == "video_delivered"]
        self.assertTrue(events, "no delivery receipt recorded")
        self.assertEqual(events[0]["meta"]["message_id"], "777")
        # Raw chat id must NOT appear in the ledger meta.
        self.assertNotIn("555", str(events[0]["meta"]))

    def test_customer_not_bound_queues_retry_for_customer_only(self) -> None:
        self._enable()
        mp4 = _make_mp4(self.tmp)
        from app.social_engine.base import PublishResult

        async def _fake_publish(self, req, account):  # noqa: ANN001
            return PublishResult(ok=True, platform="telegram", post_id="1")

        with mock.patch(
            "app.marketing.creative_os.service.resolve_output_path",
            return_value={"ok": True, "path": mp4, "sha256": "abc", "revision": 0},
        ), mock.patch(
            "app.social_engine.providers.TelegramProvider.publish", new=_fake_publish
        ):
            out = video_delivery.deliver_video("t03_nobind", "cr_x")
        # ops succeeded → overall ok True, but the customer target is queued.
        self.assertFalse(out["targets"]["customer"]["ok"])
        self.assertEqual(out["targets"]["customer"]["error"], "customer_not_bound")
        q = video_delivery.retry_queue("t03_nobind")
        self.assertEqual(q["pending"], 1)
        self.assertEqual(q["items"][0]["target"], "customer")

    def test_artifact_unavailable(self) -> None:
        self._enable()
        with mock.patch(
            "app.marketing.creative_os.service.resolve_output_path",
            return_value={"ok": False, "error": "output_asset_missing"},
        ):
            out = video_delivery.deliver_video("t03_noart", "cr_y")
        self.assertFalse(out["ok"])
        self.assertEqual(out["outcome"], "artifact_unavailable")

    def test_rerun_does_not_double_send(self) -> None:
        """A receipted target is skipped on re-run (Telegram has no idempotency)."""
        self._enable()
        video_delivery.bind_customer("t03_idem", "555")
        mp4 = _make_mp4(self.tmp)
        calls = {"n": 0}
        from app.social_engine.base import PublishResult

        async def _fake_publish(self, req, account):  # noqa: ANN001
            calls["n"] += 1
            return PublishResult(ok=True, platform="telegram", post_id="42")

        with mock.patch(
            "app.marketing.creative_os.service.resolve_output_path",
            return_value={"ok": True, "path": mp4, "sha256": "abc", "revision": 0},
        ), mock.patch("app.social_engine.providers.TelegramProvider.publish", new=_fake_publish):
            first = video_delivery.deliver_video("t03_idem", "cr_idem")
            calls_after_first = calls["n"]
            second = video_delivery.deliver_video("t03_idem", "cr_idem")

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(calls["n"], calls_after_first, "re-run re-sent to Telegram")
        self.assertTrue(second["targets"]["customer"].get("idempotent"))
        self.assertTrue(second["targets"]["ops"].get("idempotent"))

    def test_ops_only_receipt_is_not_customer_visible(self) -> None:
        """An ops-group receipt must NOT claim the CUSTOMER received a video.

        `video_delivered` is customer_visible and reads "aapko bhej diya gaya".
        When only the ops group received the file (customer unbound), the
        customer timeline must stay silent — otherwise the shop owner is told
        their video arrived when it never reached their thread.
        """
        self._enable()  # customer is deliberately NOT bound
        mp4 = _make_mp4(self.tmp)
        from app.social_engine.base import PublishResult

        async def _fake_publish(self, req, account):  # noqa: ANN001
            return PublishResult(ok=True, platform="telegram", post_id="888")

        with mock.patch(
            "app.marketing.creative_os.service.resolve_output_path",
            return_value={"ok": True, "path": mp4, "sha256": "abc", "revision": 0},
        ), mock.patch("app.social_engine.providers.TelegramProvider.publish", new=_fake_publish):
            out = video_delivery.deliver_video("t03_opsvis", "cr_ops")

        self.assertTrue(out["targets"]["ops"]["ok"])
        self.assertFalse(out["targets"]["customer"]["ok"])
        customer_events = [
            e["event"]
            for e in delivery_ledger.timeline("t03_opsvis", limit=20, customer_only=True)
        ]
        self.assertNotIn(
            "video_delivered",
            customer_events,
            "an ops-only send leaked into the customer timeline",
        )
        all_events = [e["event"] for e in delivery_ledger.timeline("t03_opsvis", limit=20)]
        self.assertIn("video_delivered_ops", all_events)


class TestRetryQueue(_StoreRedirect):
    def test_retry_scheduled_and_exhausted(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "1")
        self._set("TELEGRAM_BOT_TOKEN", "tok")
        self._set("VIDEO_DELIVERY_MAX_RETRIES", "1")
        mp4 = _make_mp4(self.tmp)
        from app.social_engine.base import PublishResult

        async def _fail(self, req, account):  # noqa: ANN001
            return PublishResult(ok=False, platform="telegram", error="boom")

        with mock.patch(
            "app.marketing.creative_os.service.resolve_output_path",
            return_value={"ok": True, "path": mp4, "sha256": "a", "revision": 0},
        ), mock.patch("app.social_engine.providers.TelegramProvider.publish", new=_fail):
            video_delivery.deliver_video("t03_retry", "cr_r")  # attempt 1 → schedule
            video_delivery.deliver_video("t03_retry", "cr_r")  # attempt 2 → exhausted

        events = [e["event"] for e in delivery_ledger.timeline("t03_retry", limit=50)]
        self.assertIn("video_delivery_retry_scheduled", events)
        self.assertIn("video_delivery_exhausted", events)

    def test_process_retries_disabled_is_noop(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "0")
        out = video_delivery.process_retries()
        self.assertFalse(out["ok"])
        self.assertEqual(out["attempted"], 0)


class TestCaptureFlow(_StoreRedirect):
    def test_asset_refused_without_consent(self) -> None:
        out = video_delivery.capture_asset("t03_cap", ref="x.jpg", sha256="a" * 40)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "consent_required")

    def test_asset_with_consent_registers_and_unlocks_gate(self) -> None:
        with mock.patch(
            "app.marketing.creative_os.assets.register_asset",
            return_value={"ok": True, "asset": {"asset_id": "asset_abc"}},
        ):
            out = video_delivery.capture_asset(
                "t03_cap2", ref="x.jpg", sha256="a" * 40, consent_status="granted", kind="before_after"
            )
        self.assertTrue(out["ok"])
        self.assertEqual(out["source_asset_id"], "asset_abc")
        ready = video_delivery.capture_ready("t03_cap2")
        self.assertTrue(ready["ready_for_before_after"])
        self.assertIn("verified_testimonial", ready["needs"])
        # The gate is UNCHANGED — it now passes because a real source exists.
        self.assertFalse(recipes.recipe_allowed("before_after")["ok"])
        self.assertTrue(recipes.recipe_allowed("before_after", source_asset_ids=ready["source_asset_ids"])["ok"])

    def test_quote_refused_without_consent(self) -> None:
        out = video_delivery.capture_quote("t03_q", quote="Best salon")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "consent_required")

    def test_quote_with_consent_unlocks_testimonial(self) -> None:
        out = video_delivery.capture_quote(
            "t03_q2", quote="Best salon in Mumbai", attribution="Priya", consent_status="granted"
        )
        self.assertTrue(out["ok"])
        ready = video_delivery.capture_ready("t03_q2")
        self.assertTrue(ready["ready_for_testimonial"])
        self.assertFalse(recipes.recipe_allowed("testimonial")["ok"])
        self.assertTrue(recipes.recipe_allowed("testimonial", verified_quote=ready["verified_quote"])["ok"])

    def test_capture_ready_needs_honest(self) -> None:
        ready = video_delivery.capture_ready("t03_empty")
        self.assertEqual(ready["source_asset_ids"], [])
        self.assertEqual(ready["verified_quote"], "")
        self.assertEqual(
            set(ready["needs"]), {"before_after_photos", "verified_testimonial"}
        )


class TestDeliverPending(_StoreRedirect):
    """The beat-driven sweep must find ONLY approved-but-undelivered work."""

    def _enable(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "1")
        self._set("TELEGRAM_BOT_TOKEN", "test-token")
        self._set("TELEGRAM_OPS_GROUP_ID", "-100999")

    def test_disabled_is_honest_noop(self) -> None:
        self._set("VIDEO_TELEGRAM_DELIVERY_ENABLED", "0")
        out = video_delivery.deliver_pending()
        self.assertFalse(out["ok"])
        self.assertEqual(out["scanned"], 0)

    def test_sweep_delivers_approved_undelivered(self) -> None:
        self._enable()
        video_delivery.bind_customer("t03_sweep", "555")
        mp4 = _make_mp4(self.tmp)
        from app.social_engine.base import PublishResult

        async def _fake_publish(self, req, account):  # noqa: ANN001
            return PublishResult(ok=True, platform="telegram", post_id="900")

        def _fake_project(tenant_id, creative_id):  # noqa: ANN001
            return {
                "ok": True,
                "tenant_id": tenant_id,
                "creative_id": creative_id,
                "stages": [
                    {"stage": "approval", "status": "passed", "evidence": {"revision": 2}},
                    {"stage": "delivery", "status": "not_reached", "evidence": {}},
                ],
                "failed_stage": "delivery",
            }

        with mock.patch(
            "app.marketing.creative_os.store.list_records",
            return_value={"ok": True, "items": [{"creative_id": "cr_s1"}]},
        ), mock.patch(
            "app.marketing.creative_os.lifecycle.project", new=_fake_project
        ), mock.patch(
            "app.marketing.creative_os.service.resolve_output_path",
            return_value={"ok": True, "path": mp4, "sha256": "abc", "revision": 2},
        ), mock.patch(
            "app.social_engine.providers.TelegramProvider.publish", new=_fake_publish
        ):
            out = video_delivery.deliver_pending()

        self.assertTrue(out["ok"], out)
        self.assertEqual(out["scanned"], 1)
        self.assertEqual(out["delivered"], 1)
        events = [e for e in delivery_ledger.timeline("t03_sweep", limit=20) if e["event"] == "video_delivered"]
        self.assertTrue(events, "sweep did not record a receipt")

    def test_sweep_skips_already_delivered(self) -> None:
        self._enable()
        video_delivery.bind_customer("t03_sweep2", "555")

        def _fake_project(tenant_id, creative_id):  # noqa: ANN001
            return {
                "ok": True,
                "stages": [
                    {"stage": "approval", "status": "passed", "evidence": {"revision": 0}},
                    {"stage": "delivery", "status": "passed", "evidence": {}},
                ],
            }

        with mock.patch(
            "app.marketing.creative_os.store.list_records",
            return_value={"ok": True, "items": [{"creative_id": "cr_done"}]},
        ), mock.patch("app.marketing.creative_os.lifecycle.project", new=_fake_project):
            out = video_delivery.deliver_pending()
        self.assertEqual(out["scanned"], 0)
        self.assertEqual(out["delivered"], 0)

    def test_sweep_skips_unapproved(self) -> None:
        self._enable()
        video_delivery.bind_customer("t03_sweep3", "555")

        def _fake_project(tenant_id, creative_id):  # noqa: ANN001
            return {
                "ok": True,
                "stages": [
                    {"stage": "approval", "status": "pending", "evidence": {"revision": 0}},
                    {"stage": "delivery", "status": "not_reached", "evidence": {}},
                ],
            }

        with mock.patch(
            "app.marketing.creative_os.store.list_records",
            return_value={"ok": True, "items": [{"creative_id": "cr_p"}]},
        ), mock.patch("app.marketing.creative_os.lifecycle.project", new=_fake_project):
            out = video_delivery.deliver_pending()
        self.assertEqual(out["scanned"], 0)
        self.assertEqual(out["delivered"], 0)

    def test_sweep_skips_unbound_tenant(self) -> None:
        self._enable()
        # A creative exists but the tenant has NO customer binding → not swept.
        with mock.patch(
            "app.marketing.creative_os.store.list_records",
            return_value={"ok": True, "items": [{"creative_id": "cr_nb"}]},
        ):
            out = video_delivery.deliver_pending()
        self.assertEqual(out["scanned"], 0)


class TestNeverRaises(_StoreRedirect):
    _GARBAGE = [None, "", "   ", 12345, {"a": 1}, ["x"], "a/b", "x" * 5000]

    def test_dict_api_never_raises(self) -> None:
        failures: list[str] = []
        for g in self._GARBAGE:
            cases = {
                "deliver_video": lambda g=g: video_delivery.deliver_video(g, g),
                "bind_customer": lambda g=g: video_delivery.bind_customer(g, g),
                "get_binding": lambda g=g: video_delivery.get_binding(g),
                "binding_view": lambda g=g: video_delivery.binding_view(g),
                "unbind_customer": lambda g=g: video_delivery.unbind_customer(g),
                "retry_queue": lambda g=g: video_delivery.retry_queue(g),
                "enqueue_retry": lambda g=g: video_delivery.enqueue_retry(g, creative_id=g, revision=0, target=g),
                "delivery_status": lambda g=g: video_delivery.delivery_status(g),
                "deliver_pending": lambda g=g: video_delivery.deliver_pending(),
                "capture_ready": lambda g=g: video_delivery.capture_ready(g),
                "capture_asset": lambda g=g: video_delivery.capture_asset(g, ref=g, sha256=g),
                "capture_quote": lambda g=g: video_delivery.capture_quote(g, quote=g),
                "mask_chat_id": lambda g=g: video_delivery.mask_chat_id(g),
            }
            for label, fn in cases.items():
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{label}({g!r:.20}) -> {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "public dict-API raised:\n" + "\n".join(failures))


class TestLedgerEvents(_StoreRedirect):
    def test_events_registered(self) -> None:
        for ev in (
            "video_delivered",
            "video_delivery_failed",
            "video_delivery_retry_scheduled",
            "video_delivery_exhausted",
            "render_plane_queued",
            "render_plane_completed",
            "render_plane_failed",
            "social_profile_analyzed",
            "social_profile_updated",
            "capture_asset_registered",
            "capture_quote_registered",
        ):
            self.assertIn(ev, delivery_ledger.EVENT_TYPES, f"{ev} not registered")

    def test_only_video_delivered_is_customer_visible(self) -> None:
        cid = "t03_ledger_vis"
        for ev in ("video_delivered", "video_delivery_failed", "render_plane_queued", "social_profile_analyzed"):
            self.assertTrue(delivery_ledger.log_event(cid, ev, detail="x"))
        cust = [e["event"] for e in delivery_ledger.timeline(cid, limit=20, customer_only=True)]
        self.assertIn("video_delivered", cust)
        for ev in ("video_delivery_failed", "render_plane_queued", "social_profile_analyzed"):
            self.assertNotIn(ev, cust)

    def test_video_delivered_counts_as_value(self) -> None:
        self.assertIn("video_delivered", delivery_ledger._VALUE_EVENTS)
        # An in-flight retry is not an incident.
        self.assertNotIn("video_delivery_failed", delivery_ledger._FAILURE_EVENTS)


if __name__ == "__main__":
    unittest.main()
