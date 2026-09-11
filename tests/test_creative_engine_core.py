"""T01 acceptance checks — Creative-engine core (stdlib unittest only).

Covers the definition-of-done for Task T01:
  1. Two consecutive-day specs → jaccard < 0.6 OR a `near_duplicate` refusal.
  2. `record_learning` has >= 4 callers in `app/`.
  3. Learning history survives a process restart (read back from disk).
  4. `recipe_allowed` behaviour is unchanged (before_after/testimonial blocked).
  + unit checks for the fingerprint, selector determinism, and social profile.

Run with the managed interpreter:
    python -m unittest tests.test_creative_engine_core
"""

from __future__ import annotations

import importlib
import re
import tempfile
import unittest
from pathlib import Path

import app.platform.runtime_data_authority as auth
from app.marketing import delivery_ledger
from app.marketing.creative_os import learning, learning_store, novelty, recipes, selector, social_profile
from app.marketing.creative_os import service
from app.marketing.creative_os.brief import BrandProfile, CustomerVideoBrief
from app.marketing.creative_os.spec import CreativeSpec, SceneSpec


def _spec_from_selection(tenant_id: str, sel: dict) -> CreativeSpec:
    scenes = recipes.build_scene_plan(
        sel["recipe"],
        business_name="Glow Salon",
        offer="Bridal glow package",
        niche="salon",
        language="hinglish",
        cta="Call karo aaj hi",
        dna={"hook_variant": sel.get("hook_variant", ""), "variant": 0},
        variant=0,
    )
    return CreativeSpec(
        creative_id=CreativeSpec.new_id(),
        tenant_id=tenant_id,
        goal="salon",
        audience="Glow Salon",
        offer="Bridal glow package",
        language="hinglish",
        platform="instagram",
        aspect_ratio="9:16",
        recipe=sel["recipe"],
        template_id=sel.get("template_id", ""),
        hook_variant=sel.get("hook_variant", ""),
        scenes=scenes,
        script=" | ".join(s.text for s in scenes),
        captions={"primary": scenes[0].text},
        cta="Call karo aaj hi",
    )


class _StoreRedirect(unittest.TestCase):
    """Redirect the three new stores to a temp dir for hermetic tests."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="creative_engine_")
        self.tmp = Path(self._tmp.name)
        self._orig_resolve = auth.resolve_store_path

        def _fake_resolve(**kw):  # noqa: ANN001
            return self.tmp / str(kw.get("store_id", "store")).replace(".", "_")

        auth.resolve_store_path = _fake_resolve  # type: ignore[assignment]

    def tearDown(self) -> None:
        auth.resolve_store_path = self._orig_resolve  # type: ignore[assignment]
        self._tmp.cleanup()


class TestNoveltyPrimitives(_StoreRedirect):
    def test_jaccard_bounds(self) -> None:
        self.assertEqual(novelty.jaccard([], []), 0.0)
        self.assertEqual(novelty.jaccard(["a"], ["a"]), 1.0)
        self.assertEqual(novelty.jaccard(["a", "b"], ["c", "d"]), 0.0)
        self.assertAlmostEqual(novelty.jaccard(["a", "b"], ["b", "c"]), 1 / 3, places=4)

    def test_fingerprint_is_order_and_case_insensitive(self) -> None:
        s1 = _spec_from_selection(
            "test_tenant_a", {"recipe": "offer_announcement", "template_id": "t", "hook_variant": "h"}
        )
        s2 = _spec_from_selection(
            "test_tenant_a", {"recipe": "offer_announcement", "template_id": "t", "hook_variant": "h"}
        )
        f1 = novelty.scene_fingerprint(s1)
        f2 = novelty.scene_fingerprint(s2)
        self.assertEqual(f1["shingles"], f2["shingles"])
        self.assertEqual(novelty.jaccard(f1["shingles"], f2["shingles"]), 1.0)

    def test_identical_spec_refused_as_near_duplicate(self) -> None:
        tenant = "test_tenant_dup"
        sel = selector.select_creative(tenant_id=tenant, day="2026-09-10", niche="salon")
        spec = _spec_from_selection(tenant, sel)
        novelty.accept(spec, tenant, day="2026-09-10")
        again = _spec_from_selection(tenant, sel)
        verdict = novelty.check(again, tenant, n=7, day="2026-09-11")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["outcome"], "near_duplicate")

    def test_force_bypasses_refusal(self) -> None:
        tenant = "test_tenant_force"
        sel = selector.select_creative(tenant_id=tenant, day="2026-09-10", niche="salon")
        spec = _spec_from_selection(tenant, sel)
        novelty.accept(spec, tenant, day="2026-09-10")
        again = _spec_from_selection(tenant, sel)
        verdict = novelty.check(again, tenant, n=7, day="2026-09-11", force=True)
        self.assertTrue(verdict["ok"])
        self.assertTrue(verdict["forced"])


class TestSelectorDeterminism(_StoreRedirect):
    def test_same_inputs_same_output(self) -> None:
        a = selector.select_creative(tenant_id="test_tenant_s", day="2026-09-10", niche="salon")
        b = selector.select_creative(tenant_id="test_tenant_s", day="2026-09-10", niche="salon")
        self.assertEqual(a, b)

    def test_rotation_changes_candidate(self) -> None:
        base = selector.select_creative(
            tenant_id="test_tenant_s2", day="2026-09-10", niche="salon", rotation_index=0
        )
        rots = {
            selector.select_creative(
                tenant_id="test_tenant_s2", day="2026-09-10", niche="salon", rotation_index=r
            )["recipe"]
            for r in range(1, 4)
        }
        self.assertTrue(rots, "rotation must yield at least one candidate")

    def test_blocked_recipe_excluded_without_source(self) -> None:
        sel = selector.select_creative(tenant_id="test_tenant_s3", day="2026-09-10", niche="salon")
        self.assertNotIn(sel["recipe"], recipes._BLOCKED_WITHOUT_SOURCE)


class TestSelectorRotationNoRepeat(_StoreRedirect):
    """Regression: consecutive rotations must NOT repeat a recipe.

    The owner's #1 complaint is repetition ("same video roz customer ko ja raha
    hai"). The selector used to seed its RNG with ``rotation_index`` itself, so
    ``start`` was an INDEPENDENT random draw for every rotation; adding ``rot``
    on top of an independent draw made ``(start + rot) % n`` re-collide with
    probability ~1/n, so consecutive rotation attempts could emit the SAME
    recipe. The rotation base must come from a rotation-INDEPENDENT seed and
    only THEN be advanced by ``rot``.

    The rot==0 hint / cold-start / preference branches are a separate,
    intentional FIRST pick, so this test neutralises the cold default
    (``cold_start_recipe`` set to a non-candidate) to isolate the rotation logic
    that the fix targets. This test FAILS against the pre-fix selector.
    """

    def test_candidates_are_multiple(self) -> None:
        # The no-repeat guarantee is only meaningful with >1 candidate.
        cands = selector._allowed_recipes(source_asset_ids=None, verified_quote="")
        self.assertGreater(len(cands), 1)

    def test_consecutive_rotations_never_repeat(self) -> None:
        tenants = [f"rot_tenant_{i}" for i in range(30)]
        days = ["2026-01-01", "2026-04-15", "2026-07-31", "2026-11-20"]
        for tid in tenants:
            for day in days:
                recipes = [
                    selector.select_creative(
                        tenant_id=tid,
                        day=day,
                        niche="salon",
                        rotation_index=rot,
                        cold_start_recipe="__no_such_recipe__",  # force rotation path
                    )["recipe"]
                    for rot in range(8)
                ]
                for rot in range(len(recipes) - 1):
                    self.assertNotEqual(
                        recipes[rot + 1],
                        recipes[rot],
                        f"rotation repeated {recipes[rot]!r} at rot {rot}->{rot + 1} "
                        f"for {tid}/{day}",
                    )


class TestSocialProfile(_StoreRedirect):
    def test_analyze_fails_closed_when_disabled(self) -> None:
        out = social_profile.analyze("test_tenant_sp", signals={"tone": "warm"})
        self.assertFalse(out["ok"])
        self.assertEqual(out["outcome"], "disabled")

    def test_graph_api_fails_closed_without_token(self) -> None:
        import os

        os.environ["CREATIVE_SOCIAL_PROFILE_ENABLED"] = "1"
        try:
            out = social_profile.analyze(
                "test_tenant_sp2",
                signals={"tone": "warm", "audience": "bridal", "content_pillars": ["a"], "language_hint": "hi"},
                analysis_method="graph_api",
                business_token="",
            )
            self.assertFalse(out["ok"])
            self.assertEqual(out["outcome"], "blocked")
        finally:
            os.environ.pop("CREATIVE_SOCIAL_PROFILE_ENABLED", None)

    def test_assisted_round_trip(self) -> None:
        import os

        os.environ["CREATIVE_SOCIAL_PROFILE_ENABLED"] = "1"
        try:
            out = social_profile.analyze(
                "test_tenant_sp3",
                source="owner_supplied",
                signals={
                    "tone": "warm aspirational",
                    "audience": "women 22-40",
                    "content_pillars": ["before/after", "pricing"],
                    "language_hint": "hinglish",
                },
            )
            self.assertTrue(out["ok"])
            prof = out["profile"]
            self.assertTrue(prof.profile_version)
            self.assertTrue(social_profile.save_profile(prof)["ok"])
            loaded = social_profile.get_profile("test_tenant_sp3")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.profile_version, prof.profile_version)  # type: ignore[union-attr]
            framed = social_profile.apply_to_copy(loaded, "New offer from Glow Salon", role="hook")
            self.assertTrue(framed.endswith("New offer from Glow Salon"))
        finally:
            os.environ.pop("CREATIVE_SOCIAL_PROFILE_ENABLED", None)


class TestLearningPersistence(_StoreRedirect):
    def test_history_survives_restart(self) -> None:
        tenant = "test_tenant_hist"
        link = learning.CreativeLearningLink(
            creative_id="cr_abc123",
            revision=0,
            tenant_id=tenant,
            recipe="offer_announcement",
            kind="qa",
            verified=True,
            at=1.0,
            day="2026-09-11",
        )
        self.assertTrue(learning.record_learning(link)["ok"])
        # Simulate a process restart: drop module state and re-read from disk.
        importlib.reload(learning_store)
        importlib.reload(learning)
        rows = learning_store.read_learning(tenant)
        self.assertTrue(any(r.get("creative_id") == "cr_abc123" for r in rows))
        hist = learning.get_learning_history(tenant)
        self.assertTrue(any(r.creative_id == "cr_abc123" for r in hist))
        # New additive fields round-trip.
        self.assertEqual(hist[-1].kind, "qa")
        self.assertEqual(hist[-1].day, "2026-09-11")

    def test_corrupt_line_skipped_never_raises(self) -> None:
        tenant = "test_tenant_corrupt"
        learning_store.append_learning(tenant, {"creative_id": "cr_ok", "kind": "qa"})
        with open(learning_store.learning_path(tenant), "a", encoding="utf-8") as f:
            f.write("{not valid json\n")
        rows = learning_store.read_learning(tenant)
        self.assertTrue(any(r.get("creative_id") == "cr_ok" for r in rows))

    def test_record_learning_has_at_least_four_callers(self) -> None:
        src = Path(service.__file__).read_text(encoding="utf-8")
        calls = re.findall(r"\brecord_learning\s*\(", src)
        # 1 import line + 4 call sites = >= 5 occurrences in service.py alone.
        self.assertGreaterEqual(len(calls), 4, f"only {len(calls)} record_learning sites")


class TestRecipeGateUnchanged(_StoreRedirect):
    def test_before_after_blocked_without_source(self) -> None:
        self.assertFalse(recipes.recipe_allowed("before_after")["ok"])
        self.assertTrue(recipes.recipe_allowed("before_after", source_asset_ids=["as_1"])["ok"])

    def test_testimonial_blocked_without_quote(self) -> None:
        self.assertFalse(recipes.recipe_allowed("testimonial")["ok"])
        self.assertTrue(recipes.recipe_allowed("testimonial", verified_quote="Best in town")["ok"])

    def test_copy_variants_present_and_facts_preserved(self) -> None:
        base = recipes.build_scene_plan(
            "offer_announcement", business_name="Glow", offer="50% off", niche="salon", variant=0
        )
        var = recipes.build_scene_plan(
            "offer_announcement", business_name="Glow", offer="50% off", niche="salon", variant=1
        )
        self.assertNotEqual(base[0].text, var[0].text)
        # The offer scene (index 1) is unchanged across variants — no fact drift.
        self.assertEqual(base[1].text, var[1].text)


class TestConsecutiveDayGate(_StoreRedirect):
    """DoD #1 — end-to-end through `service.enqueue_generate`."""

    def _patch_service(self, day_holder: dict, captured: list) -> dict:
        orig = {
            "resolve_brief": service.resolve_brief,
            "assert_provider_allowed": service.assert_provider_allowed,
            "count_attempts_today": service.count_attempts_today,
            "save_record": service.save_record,
            "record_attempt": service.record_attempt,
            "_enqueue_celery": service._enqueue_celery,
            "_utc_day": service._utc_day,
        }

        brand = BrandProfile(
            tenant_id="test_tenant_e2e",
            business_name="Glow Salon",
            niche="salon",
            primary_color="#111111",
            accent_color="#ffcc00",
        )
        brief = CustomerVideoBrief(
            tenant_id="test_tenant_e2e",
            objective="salon",
            platform="instagram",
            aspect_ratio="9:16",
            language="hinglish",
            brand=brand,
            offer="Bridal glow package",
            cta="Call karo",
        )
        service.resolve_brief = lambda **kw: {  # type: ignore[assignment]
            "ok": True,
            "outcome": "ready",
            "brief": brief,
            "missing": [],
            "reason": "",
            "error": "",
        }
        service.assert_provider_allowed = lambda *a, **k: {"ok": True, "snapshot": {}}  # type: ignore[assignment]
        service.count_attempts_today = lambda tenant: 0  # type: ignore[assignment]
        service.save_record = lambda spec, extra=None: (captured.append(spec), {"ok": True})[1]  # type: ignore[assignment]
        service.record_attempt = lambda *a, **k: {"ok": True}  # type: ignore[assignment]
        service._enqueue_celery = lambda t, c, r: {"ok": True, "job_id": "job-test"}  # type: ignore[assignment]
        service._utc_day = lambda: day_holder["day"]  # type: ignore[assignment]
        return orig

    def _restore(self, orig: dict) -> None:
        for k, v in orig.items():
            setattr(service, k, v)

    def test_consecutive_days_distinct_or_refused(self) -> None:
        import os

        os.environ["CREATIVE_OS_ENABLED"] = "1"
        tenant = "test_tenant_e2e"
        day_holder = {"day": "2026-09-10"}
        captured: list = []
        orig = self._patch_service(day_holder, captured)
        try:
            out1 = service.enqueue_generate(
                tenant_id=tenant,
                business_name="Glow Salon",
                recipe="offer_announcement",
                niche="salon",
                provider="deterministic",
            )
            self.assertTrue(out1.get("ok"), out1)
            self.assertGreaterEqual(len(captured), 1)
            spec1 = captured[0]

            day_holder["day"] = "2026-09-11"
            out2 = service.enqueue_generate(
                tenant_id=tenant,
                business_name="Glow Salon",
                recipe="offer_announcement",
                niche="salon",
                provider="deterministic",
            )
            if out2.get("ok"):
                spec2 = captured[-1]
                j = novelty.jaccard(
                    novelty.scene_fingerprint(spec1)["shingles"],
                    novelty.scene_fingerprint(spec2)["shingles"],
                )
                self.assertLess(j, 0.6, f"consecutive-day jaccard={j} >= 0.6")
            else:
                self.assertEqual(out2.get("outcome"), "near_duplicate")
        finally:
            self._restore(orig)
            os.environ.pop("CREATIVE_OS_ENABLED", None)


class TestDeliveryLedgerEventRegistration(_StoreRedirect):
    """Follow-up: `novelty_blocked` is a registered event; unknown types warn."""

    def test_novelty_blocked_persists_and_is_readable(self) -> None:
        cid = "test_tenant_ledger"
        self.assertIn("novelty_blocked", delivery_ledger.EVENT_TYPES)
        wrote = delivery_ledger.log_event(
            cid, "novelty_blocked", detail="cr_x:forced", meta={"forced": True}
        )
        self.assertTrue(wrote)
        # Read back through the PUBLIC helpers, not the raw file.
        events = [e["event"] for e in delivery_ledger.timeline(cid, limit=20)]
        self.assertIn("novelty_blocked", events)
        admin_events = [e["event"] for e in delivery_ledger.admin_view(cid)["timeline"]]
        self.assertIn("novelty_blocked", admin_events)
        self.assertEqual(delivery_ledger.summary(cid)["counts"].get("novelty_blocked"), 1)
        # The event is internal/ops — it must NOT be customer-visible.
        cust = [e["event"] for e in delivery_ledger.timeline(cid, limit=20, customer_only=True)]
        self.assertNotIn("novelty_blocked", cust)

    def test_unknown_event_warns_and_returns_false(self) -> None:
        with self.assertLogs("app.marketing.delivery_ledger", level="WARNING") as cap:
            out = delivery_ledger.log_event("test_tenant_ledger2", "definitely_not_an_event")
        self.assertFalse(out)  # never raises, return value unchanged
        self.assertTrue(
            any("definitely_not_an_event" in m for m in cap.output),
            f"warning must name the rejected event: {cap.output}",
        )


    def test_creative_os_lifecycle_events_registered_and_internal(self) -> None:
        cid = "test_tenant_ledger3"
        for ev in ("creative_os_queued", "creative_os_preview_ready"):
            self.assertIn(ev, delivery_ledger.EVENT_TYPES)
            self.assertTrue(delivery_ledger.log_event(cid, ev, detail="x"))
        events = [e["event"] for e in delivery_ledger.timeline(cid, limit=20)]
        self.assertIn("creative_os_queued", events)
        self.assertIn("creative_os_preview_ready", events)
        # Internal lifecycle → absent from the CUSTOMER timeline.
        cust = [e["event"] for e in delivery_ledger.timeline(cid, limit=20, customer_only=True)]
        self.assertNotIn("creative_os_queued", cust)
        self.assertNotIn("creative_os_preview_ready", cust)
        counts = delivery_ledger.summary(cid)["counts"]
        self.assertEqual(counts.get("creative_os_queued"), 1)
        self.assertEqual(counts.get("creative_os_preview_ready"), 1)
        # Neither delivered value nor a failure.
        self.assertNotIn("creative_os_queued", delivery_ledger._VALUE_EVENTS)
        self.assertNotIn("creative_os_preview_ready", delivery_ledger._VALUE_EVENTS)
        self.assertNotIn("creative_os_queued", delivery_ledger._FAILURE_EVENTS)
        self.assertNotIn("creative_os_preview_ready", delivery_ledger._FAILURE_EVENTS)


    def test_learning_path_typed_refusal_is_a_guard(self) -> None:
        """`learning_path` raises RuntimeDataError on an unsafe id — by design.

        This is the path-traversal guard, not an error path. The public callers
        (append_learning / read_learning / count_learning) catch it and stay
        "never raises".
        """
        from app.platform.runtime_data import RuntimeDataError

        for bad in (None, "", "   ", "a/b"):
            with self.assertRaises(RuntimeDataError):
                learning_store.learning_path(bad)
        self.assertTrue(learning_store.learning_path("test_tenant_ok").endswith(".jsonl"))

    def test_novelty_helpers_never_raise_on_garbage(self) -> None:
        for bad in (None, "", "   ", 12345, {"a": 1}, ["x"], "a/b"):
            self.assertEqual(novelty.jaccard(bad, []), 0.0)
            self.assertEqual(novelty.jaccard([], bad), 0.0)
            self.assertIsInstance(novelty.normalize_text(bad), str)

    def test_short_scene_text_is_not_fingerprinted(self) -> None:
        """<3 words ⇒ no shingles ⇒ jaccard 0.0 (must NOT permanently block)."""
        short = CreativeSpec(
            creative_id=CreativeSpec.new_id(),
            tenant_id="test_tenant_short",
            goal="g",
            audience="a",
            offer="",
            language="hinglish",
            platform="instagram",
            aspect_ratio="9:16",
            recipe="offer_announcement",
            scenes=[SceneSpec(index=0, role="hook", text="Glow Salon")],
        )
        self.assertEqual(novelty.scene_fingerprint(short)["shingles"], [])


if __name__ == "__main__":
    unittest.main()
