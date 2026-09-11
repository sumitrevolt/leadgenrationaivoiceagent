"""Adversarial QA verification of Task T01 — Creative-engine core.

Independent of `tests/test_creative_engine_core.py` (the implementer's suite).
This file tries to BREAK the implementation, not confirm it. Stdlib unittest
only (pytest is not installed in this environment).

Targets V1..V10 from the QA brief:
  V1  novelty gate (fingerprint / jaccard boundary / rotation / force / cross-tenant)
  V2  learning feed actually fires (QA / approval / rejection / engagement)
  V3  persistence survives a FRESH interpreter (not just a module reload)
  V4  compliance gate untouched (recipe_allowed byte-identical + behaviour)
  V5  tenant isolation on all three new stores
  V6  "never raises" contract on garbage input
  V7  store resolution at CALL time, not import time
  V8  fail-closed flag defaults + flag_snapshot
  V9  no new third-party dependency
  V10 `novelty_blocked` event registration + persistence

Run with the managed interpreter:
    python -m unittest tests.test_creative_engine_core_qa -v
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable

import app.platform.runtime_data_authority as auth  # noqa: E402
from app.marketing import delivery_ledger  # noqa: E402
from app.marketing.creative_os import (  # noqa: E402
    learning,
    learning_store,
    novelty,
    recipes,
    selector,
    service,
    social_profile,
)
from app.marketing.creative_os.brief import BrandProfile, CustomerVideoBrief  # noqa: E402
from app.marketing.creative_os.spec import CreativeSpec, SceneSpec  # noqa: E402

TARGET_FILES = [
    "app/marketing/creative_os/social_profile.py",
    "app/marketing/creative_os/selector.py",
    "app/marketing/creative_os/novelty.py",
    "app/marketing/creative_os/learning_store.py",
    "app/marketing/creative_os/spec.py",
    "app/marketing/creative_os/recipes.py",
    "app/marketing/creative_os/brief.py",
    "app/marketing/creative_os/learning.py",
    "app/marketing/creative_os/flags.py",
    "app/marketing/creative_os/service.py",
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _spec(
    tenant_id: str,
    *,
    recipe: str = "offer_announcement",
    template_id: str = "beauty_luxury_offer_v1",
    hook_variant: str = "statement",
    scenes: list[SceneSpec] | None = None,
) -> CreativeSpec:
    if scenes is None:
        scenes = recipes.build_scene_plan(
            recipe,
            business_name="Glow Salon",
            offer="Bridal glow package",
            niche="salon",
            language="hinglish",
            cta="Call karo aaj hi",
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
        recipe=recipe,
        template_id=template_id,
        hook_variant=hook_variant,
        scenes=scenes,
        script=" | ".join(s.text for s in scenes),
        captions={"primary": scenes[0].text if scenes else ""},
        cta="Call karo aaj hi",
    )


class _StoreRedirect(unittest.TestCase):
    """Redirect every store resolved through runtime_data_authority to a temp dir."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t01qa_")
        self.tmp = Path(self._tmp.name)
        self._orig_resolve = auth.resolve_store_path

        def _fake_resolve(**kw):  # noqa: ANN001
            return self.tmp / str(kw.get("store_id", "store")).replace(".", "_")

        auth.resolve_store_path = _fake_resolve  # type: ignore[assignment]

    def tearDown(self) -> None:
        auth.resolve_store_path = self._orig_resolve  # type: ignore[assignment]
        self._tmp.cleanup()


def _enqueue_patches(day: str):
    """Patch the heavy collaborators of `service.enqueue_generate`."""
    brand = BrandProfile(
        tenant_id="t01_tenant",
        business_name="Glow Salon",
        niche="salon",
        primary_color="#111111",
        accent_color="#ffcc00",
    )
    brief = CustomerVideoBrief(
        tenant_id="t01_tenant",
        objective="salon",
        platform="instagram",
        aspect_ratio="9:16",
        language="hinglish",
        brand=brand,
        offer="Bridal glow package",
        cta="Call karo",
    )
    return [
        mock.patch.object(
            service,
            "resolve_brief",
            return_value={"ok": True, "outcome": "ready", "brief": brief, "missing": [], "reason": "", "error": ""},
        ),
        mock.patch.object(service, "assert_provider_allowed", return_value={"ok": True, "snapshot": {}}),
        mock.patch.object(service, "count_attempts_today", return_value=0),
        mock.patch.object(service, "record_attempt", return_value={"ok": True}),
        mock.patch.object(service, "_enqueue_celery", return_value={"ok": True, "job_id": "job-x"}),
        mock.patch.object(service, "_utc_day", return_value=day),
    ]


# --------------------------------------------------------------------------- #
# V1 — novelty gate
# --------------------------------------------------------------------------- #
class TestV1NoveltyGate(_StoreRedirect):
    def test_first_ever_video_not_refused(self) -> None:
        verdict = novelty.check(_spec("t01_first"), "t01_first", n=7, day="2026-09-11")
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["against"], [])

    def test_empty_and_whitespace_scene_text_no_raise_no_divzero(self) -> None:
        scenes = [
            SceneSpec(index=0, role="hook", text=""),
            SceneSpec(index=1, role="offer", text="   "),
            SceneSpec(index=2, role="cta", text="\t\n "),
        ]
        spec = _spec("t01_empty", scenes=scenes)
        fp = novelty.scene_fingerprint(spec)
        self.assertEqual(fp["shingles"], [])
        self.assertEqual(novelty.jaccard([], []), 0.0)
        # A prior with real shingles must not blow up on an empty candidate.
        # (Different recipe/template and a non-consecutive day, so the ONLY thing
        # under test is that the empty fingerprint is safe.)
        novelty.accept(
            _spec("t01_empty", recipe="faq_reel", template_id="local_service_promo_v1"),
            "t01_empty", day="2026-09-05",
        )
        verdict = novelty.check(spec, "t01_empty", n=7, day="2026-09-11")
        self.assertTrue(verdict["ok"], verdict)

    def test_jaccard_boundary_is_ge_not_gt(self) -> None:
        """At exactly 0.6 the gate MUST refuse (design says `>= 0.6`)."""
        cand = {"a", "b", "c", "d"}
        prior = {"a", "b", "c", "e"}  # |∩|=3, |∪|=5 → 0.6 exactly
        self.assertEqual(novelty.jaccard(sorted(cand), sorted(prior)), 0.6)
        line = novelty.CreativeLineage(
            tenant_id="t01_bound",
            creative_id="cr_x",
            revision=0,
            day="2026-09-10",
            recipe="r1",
            template_id="tpl",
            hook_variant="h",
            spec_hash="s",
            scene_text_hash="h",
            shingles=sorted(prior),
            at=1.0,
        )
        with mock.patch.object(novelty, "scene_fingerprint", return_value={"shingles": sorted(cand), "scene_text_hash": "h"}), \
                mock.patch.object(novelty, "recent_lineage", return_value=[line]):
            verdict = novelty.check(_spec("t01_bound"), "t01_bound", n=7, day="2026-09-11")
        self.assertFalse(verdict["ok"], "jaccard == 0.6 must be refused (>= boundary)")
        self.assertEqual(verdict["outcome"], "near_duplicate")

    def test_jaccard_just_below_boundary_allowed(self) -> None:
        cand = {"a", "b", "c", "d"}
        prior = {"a", "b", "e", "f"}  # |∩|=2, |∪|=6 → 0.333
        line = novelty.CreativeLineage(
            tenant_id="t01_below",
            creative_id="cr_x",
            revision=0,
            day="2026-09-10",
            recipe="r1",
            template_id="tpl",
            hook_variant="h",
            spec_hash="s",
            scene_text_hash="h",
            shingles=sorted(prior),
            at=1.0,
        )
        with mock.patch.object(novelty, "scene_fingerprint", return_value={"shingles": sorted(cand), "scene_text_hash": "h"}), \
                mock.patch.object(novelty, "recent_lineage", return_value=[line]):
            verdict = novelty.check(_spec("t01_below"), "t01_below", n=7, day="2026-09-11")
        self.assertTrue(verdict["ok"], verdict)

    def test_rotation_exhaustion_returns_near_duplicate_and_persists_nothing(self) -> None:
        os.environ["CREATIVE_OS_ENABLED"] = "1"
        saved: list = []
        refuse = {"ok": False, "outcome": "near_duplicate", "reason": "test", "against": [], "cross_tenant": {}}
        patches = _enqueue_patches("2026-09-11")
        patches.append(mock.patch.object(service, "save_record", side_effect=lambda spec, extra=None: (saved.append(spec), {"ok": True})[1]))
        patches.append(mock.patch.object(novelty, "check", return_value=dict(refuse)))
        try:
            for p in patches:
                p.start()
            out = service.enqueue_generate(
                tenant_id="t01_exhaust", business_name="Glow Salon", recipe="offer_announcement",
                niche="salon", provider="deterministic",
            )
            for p in patches:
                p.stop()
            self.assertFalse(out["ok"], out)
            self.assertEqual(out.get("outcome"), "near_duplicate")
            self.assertIn("tried", out)
            self.assertEqual(len(out["tried"]), 7, "1 initial + 6 rotations = 7 attempts (K<=6)")
            # Rejected candidates must NOT be persisted: no record, no lineage.
            self.assertEqual(saved, [], "rejected candidates must never be saved")
            self.assertEqual(novelty.recent_lineage("t01_exhaust", n=50), [], "rejected candidates leaked into lineage")
        finally:
            os.environ.pop("CREATIVE_OS_ENABLED", None)

    def test_force_bypasses_flags_and_audits(self) -> None:
        os.environ["CREATIVE_OS_ENABLED"] = "1"
        saved: list = []
        refuse = {"ok": False, "outcome": "near_duplicate", "reason": "test", "against": [], "cross_tenant": {}}
        patches = _enqueue_patches("2026-09-11")
        patches.append(mock.patch.object(service, "save_record", side_effect=lambda spec, extra=None: (saved.append(spec), {"ok": True})[1]))
        patches.append(mock.patch.object(novelty, "check", return_value=dict(refuse)))
        try:
            for p in patches:
                p.start()
            out = service.enqueue_generate(
                tenant_id="t01_force", business_name="Glow Salon", recipe="offer_announcement",
                niche="salon", provider="deterministic", force=True,
            )
            for p in patches:
                p.stop()
            self.assertTrue(out["ok"], out)
            self.assertTrue(out.get("forced"), "force override not reported in the result")
            # The winner may be saved more than once (pre/post enqueue) but it must
            # be ONE distinct spec — rejected candidates must never appear.
            self.assertEqual(
                len({s.creative_id for s in saved}), 1,
                "force must persist exactly one distinct (winning) spec",
            )
            # (b) lineage line carries forced=True
            rows = novelty.recent_lineage("t01_force", n=5)
            self.assertEqual(len(rows), 1, rows)
            self.assertTrue(rows[-1].forced, "lineage line not marked forced")
            # (c) audit event emitted
            events = [e["event"] for e in delivery_ledger.timeline("t01_force", limit=20)]
            self.assertIn("novelty_blocked", events, "force override was not audited")
        finally:
            os.environ.pop("CREATIVE_OS_ENABLED", None)

    def test_cross_tenant_identical_spec_is_not_blocked(self) -> None:
        a = _spec("t01_tenant_a")
        novelty.accept(a, "t01_tenant_a", day="2026-09-10")
        # Identical content, different tenant, consecutive day → advisory only.
        b = _spec("t01_tenant_b")
        verdict = novelty.check(b, "t01_tenant_b", n=7, day="2026-09-11")
        self.assertTrue(verdict["ok"], "cross-tenant sameness must NOT be a refusal")
        # Same tenant, identical spec, next day IS refused.
        c = _spec("t01_tenant_a")
        verdict2 = novelty.check(c, "t01_tenant_a", n=7, day="2026-09-11")
        self.assertFalse(verdict2["ok"])

    def test_cross_tenant_advisory_mechanism(self) -> None:
        """§8.4 advisory. `spec_hash` embeds tenant_id, so with REAL specs the
        advisory can never fire; it only fires when the hash is forced equal."""
        a = _spec("t01_adv_a")
        b = _spec("t01_adv_b")
        novelty.accept(a, "t01_adv_a", day="2026-09-10")
        real = novelty.check(b, "t01_adv_b", n=7, day="2026-09-11")
        self.assertFalse(real["cross_tenant"]["shared"], "advisory fired for distinct spec_hash")
        # Force an identical hash → the mechanism itself is wired and fires.
        with mock.patch.object(CreativeSpec, "spec_hash", return_value="SAMEHASH"):
            novelty.accept(a, "t01_adv_a", day="2026-09-10")
            forced = novelty.check(b, "t01_adv_b", n=7, day="2026-09-11")
        self.assertTrue(forced["cross_tenant"]["shared"], "advisory mechanism broken")


# --------------------------------------------------------------------------- #
# V2 — the learning feed actually fires
# --------------------------------------------------------------------------- #
class TestV2LearningFeed(_StoreRedirect):
    def _rows(self, tenant: str) -> list[dict]:
        return learning_store.read_learning(tenant)

    def test_qa_feed_executes(self) -> None:
        tenant = "t01_qa_feed"
        os.environ["CREATIVE_OS_ENABLED"] = "1"
        spec = _spec(tenant)
        mp4 = self.tmp / "out.mp4"
        mp4.write_bytes(b"\x00" * 16)
        rec = {"tenant_id": tenant, "status": "queued", "spec": spec.to_dict()}

        async def _fake_generate(_spec):  # noqa: ANN001
            return {"ok": True, "assets": [{"path": str(mp4), "width": 720, "height": 1280}], "timing_ms": 1}

        patches = [
            mock.patch.object(service, "get_record", return_value={"ok": True, "record": rec}),
            mock.patch.object(service, "save_record", return_value={"ok": True}),
            mock.patch.object(service, "generate_with_fallback", side_effect=_fake_generate),
            mock.patch.object(service, "sha256_file", return_value="deadbeef"),
            mock.patch.object(service, "_path_authorized", return_value=True),
            mock.patch.object(service, "register_asset", return_value={"ok": True, "asset": {"asset_id": "as_1"}}),
            mock.patch.object(service, "run_qa", return_value={"ok": True, "blockers": [], "degraded": []}),
            mock.patch("app.marketing.creative_os.enterprise_qa.evaluate", return_value={"customer_approvable": True, "classification": "PREMIUM"}),
        ]
        try:
            for p in patches:
                p.start()
            out = service.process_generation(tenant, spec.creative_id)
            for p in patches:
                p.stop()
            self.assertTrue(out.get("ok"), out)
            rows = [r for r in self._rows(tenant) if r.get("kind") == "qa"]
            self.assertTrue(rows, f"QA learning feed did not fire; rows={self._rows(tenant)}")
            self.assertTrue(rows[-1]["verified"])
        finally:
            os.environ.pop("CREATIVE_OS_ENABLED", None)

    def test_approval_feed_executes(self) -> None:
        tenant = "t01_appr_feed"
        os.environ["CREATIVE_OS_ENABLED"] = "1"
        spec = _spec(tenant)
        rec = {"tenant_id": tenant, "status": "approval_pending", "spec": spec.to_dict()}
        patches = [
            mock.patch.object(service, "get_record", return_value={"ok": True, "record": rec}),
            mock.patch.object(service, "bind_approval", return_value={"ok": True, "approval": {"x": 1}}),
        ]
        try:
            for p in patches:
                p.start()
            out = service.approve_exact(tenant, spec.creative_id)
            for p in patches:
                p.stop()
            self.assertTrue(out.get("ok"), out)
            rows = [r for r in self._rows(tenant) if r.get("kind") == "approval"]
            self.assertTrue(rows, f"approval learning feed did not fire; rows={self._rows(tenant)}")
        finally:
            os.environ.pop("CREATIVE_OS_ENABLED", None)

    def test_rejection_feed_executes(self) -> None:
        tenant = "t01_rej_feed"
        os.environ["CREATIVE_OS_ENABLED"] = "1"
        spec = _spec(tenant)
        rec = {"tenant_id": tenant, "status": "approval_pending", "spec": spec.to_dict()}
        patches = [
            mock.patch.object(service, "get_record", return_value={"ok": True, "record": rec}),
            mock.patch.object(service, "save_record", return_value={"ok": True}),
            mock.patch.object(service, "count_attempts_today", return_value=0),
            mock.patch.object(service, "record_attempt", return_value={"ok": True}),
            mock.patch.object(service, "_enqueue_celery", return_value={"ok": True, "job_id": "j2"}),
        ]
        try:
            for p in patches:
                p.start()
            out = service.request_changes(tenant, spec.creative_id, note="hook too weak")
            for p in patches:
                p.stop()
            self.assertTrue(out.get("ok"), out)
            rows = [r for r in self._rows(tenant) if r.get("kind") == "rejection"]
            self.assertTrue(rows, f"rejection learning feed did not fire; rows={self._rows(tenant)}")
            self.assertEqual(rows[-1]["note"], "hook too weak")
        finally:
            os.environ.pop("CREATIVE_OS_ENABLED", None)

    def test_engagement_feed_executes(self) -> None:
        tenant = "t01_eng_feed"
        out = service.record_engagement(
            tenant, "cr_eng", revision=0, platform="instagram",
            metrics={"ctr": 0.02, "avg_watch_s": 3.1}, verified=True, source="postiz",
        )
        self.assertTrue(out.get("ok"), out)
        rows = [r for r in self._rows(tenant) if r.get("kind") == "engagement"]
        self.assertTrue(rows, f"engagement learning feed did not fire; rows={self._rows(tenant)}")


# --------------------------------------------------------------------------- #
# V3 — persistence survives a FRESH interpreter
# --------------------------------------------------------------------------- #
class TestV3RestartDurability(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t01restart_")
        self.tmp = Path(self._tmp.name)
        self._old = os.environ.get("CREATIVE_LEARNING_ROOT")
        os.environ["CREATIVE_LEARNING_ROOT"] = str(self.tmp)

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("CREATIVE_LEARNING_ROOT", None)
        else:
            os.environ["CREATIVE_LEARNING_ROOT"] = self._old
        self._tmp.cleanup()

    def test_fresh_process_reads_history(self) -> None:
        tenant = "t01_restart"
        link = learning.CreativeLearningLink(
            creative_id="cr_restart", revision=0, tenant_id=tenant,
            recipe="offer_announcement", kind="qa", verified=True, at=1.0, day="2026-09-11",
        )
        self.assertTrue(learning.record_learning(link)["ok"])
        on_disk = self.tmp / f"{tenant}.jsonl"
        self.assertTrue(on_disk.is_file(), f"ledger not on disk at {on_disk}")

        code = (
            "import json;"
            "from app.marketing.creative_os import learning_store;"
            f"rows=learning_store.read_learning({tenant!r});"
            "print('ROWS='+json.dumps([r.get('creative_id') for r in rows]))"
        )
        env = {**os.environ, "PYTHONPATH": str(REPO), "CREATIVE_LEARNING_ROOT": str(self.tmp)}
        proc = subprocess.run(
            [PY, "-c", code], cwd=str(REPO), env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("ROWS=")]
        self.assertTrue(marker, proc.stdout)
        ids = json.loads(marker[-1][len("ROWS="):])
        self.assertIn("cr_restart", ids, "fresh process could not read the persisted history")


# --------------------------------------------------------------------------- #
# V4 — compliance gate untouched
# --------------------------------------------------------------------------- #
class TestV4ComplianceGate(_StoreRedirect):
    def test_blocked_set_unchanged(self) -> None:
        self.assertEqual(recipes._BLOCKED_WITHOUT_SOURCE, frozenset({"before_after", "testimonial"}))

    def test_before_after_blocked_without_source_allowed_with(self) -> None:
        self.assertFalse(recipes.recipe_allowed("before_after")["ok"])
        self.assertTrue(recipes.recipe_allowed("before_after", source_asset_ids=["as_1"])["ok"])

    def test_testimonial_blocked_without_quote_allowed_with(self) -> None:
        self.assertFalse(recipes.recipe_allowed("testimonial")["ok"])
        self.assertFalse(recipes.recipe_allowed("testimonial", verified_quote="   ")["ok"])
        self.assertTrue(recipes.recipe_allowed("testimonial", verified_quote="Best in town")["ok"])

    def test_proof_params_are_keyword_only(self) -> None:
        params = inspect.signature(recipes.recipe_allowed).parameters
        self.assertEqual(params["source_asset_ids"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(params["verified_quote"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_recipe_allowed_source_identical_to_head(self) -> None:
        head = subprocess.run(
            ["git", "show", "HEAD:app/marketing/creative_os/recipes.py"],
            cwd=str(REPO), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(head.returncode, 0, head.stderr)
        now = Path(REPO, "app/marketing/creative_os/recipes.py").read_text(encoding="utf-8")

        def _fn_dump(src: str) -> str:
            tree = ast.parse(src)
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "recipe_allowed":
                    return ast.dump(node)
            raise AssertionError("recipe_allowed not found")

        self.assertEqual(_fn_dump(now), _fn_dump(head.stdout), "recipe_allowed body changed vs HEAD")


# --------------------------------------------------------------------------- #
# V5 — tenant isolation
# --------------------------------------------------------------------------- #
class TestV5TenantIsolation(_StoreRedirect):
    def test_social_profile_cross_tenant_returns_none(self) -> None:
        prof = social_profile.SocialProfile(
            tenant_id="t01_iso_a", profile_version="v1", source="owner_supplied",
            source_ref="", analysis_method="assisted", analyzed_at=1.0, tone="warm",
        )
        self.assertTrue(social_profile.save_profile(prof)["ok"])
        self.assertIsNotNone(social_profile.get_profile("t01_iso_a"))
        self.assertIsNone(social_profile.get_profile("t01_iso_b"))
        self.assertEqual(social_profile.get_profile_dict("t01_iso_b"), {})

    def test_social_profile_body_tenant_mismatch_refused(self) -> None:
        prof = social_profile.SocialProfile(
            tenant_id="t01_iso_a", profile_version="v1", source="owner_supplied",
            source_ref="", analysis_method="assisted", analyzed_at=1.0,
        )
        social_profile.save_profile(prof)
        # Tamper: same filename, body claims a different tenant.
        path = Path(social_profile._profile_path("t01_iso_a"))
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tenant_id"] = "t01_iso_b"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(social_profile.get_profile("t01_iso_a"))

    def test_novelty_cross_tenant_empty(self) -> None:
        novelty.accept(_spec("t01_niso_a"), "t01_niso_a", day="2026-09-10")
        self.assertEqual(novelty.recent_lineage("t01_niso_b"), [])
        self.assertNotEqual(
            novelty._lineage_path("t01_niso_a"), novelty._lineage_path("t01_niso_b")
        )

    def test_learning_store_cross_tenant_empty(self) -> None:
        learning_store.append_learning("t01_liso_a", {"creative_id": "cr_a", "kind": "qa"})
        self.assertEqual(learning_store.read_learning("t01_liso_b"), [])
        self.assertEqual(learning_store.count_learning("t01_liso_b"), 0)
        self.assertNotEqual(learning_store.learning_path("t01_liso_a"), learning_store.learning_path("t01_liso_b"))


# --------------------------------------------------------------------------- #
# V6 — "never raises"
# --------------------------------------------------------------------------- #
_GARBAGE = [None, "", "   ", 12345, "x" * 10000, {"a": 1}, ["x"], "\U0001f3ac\U0001f525", "a/b"]


class TestV6NeverRaises(_StoreRedirect):
    def test_dict_api_never_raises_on_garbage(self) -> None:
        failures: list[str] = []
        for g in _GARBAGE:
            cases = {
                f"novelty.check({g!r:.20})": lambda g=g: novelty.check(g, g),
                f"novelty.scene_fingerprint({g!r:.20})": lambda g=g: novelty.scene_fingerprint(g),
                f"novelty.accept({g!r:.20})": lambda g=g: novelty.accept(g, g),
                f"novelty.recent_lineage({g!r:.20})": lambda g=g: novelty.recent_lineage(g),
                f"novelty.append_lineage({g!r:.20})": lambda g=g: novelty.append_lineage(g),
                f"novelty.cross_tenant_warning({g!r:.20})": lambda g=g: novelty.cross_tenant_warning(g, g),
                f"selector.select_creative({g!r:.20})": lambda g=g: selector.select_creative(tenant_id=g, day=g),
                f"social_profile.analyze({g!r:.20})": lambda g=g: social_profile.analyze(g),
                f"social_profile.get_profile({g!r:.20})": lambda g=g: social_profile.get_profile(g),
                f"social_profile.get_profile_dict({g!r:.20})": lambda g=g: social_profile.get_profile_dict(g),
                f"social_profile.save_profile({g!r:.20})": lambda g=g: social_profile.save_profile(g),
                f"social_profile.apply_to_copy({g!r:.20})": lambda g=g: social_profile.apply_to_copy(g, g),
                f"learning.record_learning({g!r:.20})": lambda g=g: learning.record_learning(g),
                f"learning.get_learning_history({g!r:.20})": lambda g=g: learning.get_learning_history(g),
                f"learning_store.append_learning({g!r:.20})": lambda g=g: learning_store.append_learning(g, g),
                f"learning_store.read_learning({g!r:.20})": lambda g=g: learning_store.read_learning(g),
                f"learning_store.count_learning({g!r:.20})": lambda g=g: learning_store.count_learning(g),
                f"service.record_engagement({g!r:.20})": lambda g=g: service.record_engagement(g, g),
            }
            for label, fn in cases.items():
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{label} -> {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "public dict-API raised on garbage:\n" + "\n".join(failures))

    def test_typed_helpers_do_not_raise(self) -> None:
        """Pure helpers with narrow signatures must not explode on garbage.

        NOTE: `learning_store.learning_path` is deliberately excluded — it is a
        path-traversal guard that raises a *typed* `RuntimeDataError` on unsafe
        input (see `test_learning_path_refuses_unsafe_tenant_ids`). A typed
        refusal is not an explosion, so it is asserted separately.
        """
        failures: list[str] = []
        for g in _GARBAGE:
            for label, fn in {
                f"novelty.jaccard({g!r:.20}, [])": lambda g=g: novelty.jaccard(g, []),
                f"novelty.normalize_text({g!r:.20})": lambda g=g: novelty.normalize_text(g),
            }.items():
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{label} -> {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "typed helper raised on garbage:\n" + "\n".join(failures))

    def test_learning_path_refuses_unsafe_tenant_ids(self) -> None:
        """`learning_path` is a traversal guard: unsafe ids raise RuntimeDataError
        (a typed refusal), they do NOT silently fall back to a path.

        Verified behaviour (probe): only ids that are empty/whitespace or contain
        a separator raise. A non-string scalar/dict/list is *stringified* and, as
        it contains no separator, is accepted as a literal filename — so those are
        NOT asserted to raise.
        """
        from app.platform.runtime_data import RuntimeDataError

        for bad in [None, "", "   ", "a/b", "../etc/passwd", "..\\windows", "a\x00b"]:
            with self.assertRaises(RuntimeDataError):
                learning_store.learning_path(bad)
        # A safe id returns a normal, tenant-scoped path.
        good = learning_store.learning_path("jiya_makeover")
        self.assertTrue(good.endswith("jiya_makeover.jsonl"), good)
        # A non-separator scalar is stringified, not refused (documented behaviour).
        self.assertTrue(learning_store.learning_path(12345).endswith("12345.jsonl"))


# --------------------------------------------------------------------------- #
# V7 — store resolution at CALL time
# --------------------------------------------------------------------------- #
class TestV7CallTimeResolution(unittest.TestCase):
    ENVS = ("CREATIVE_NOVELTY_ROOT", "CREATIVE_LEARNING_ROOT", "CREATIVE_SOCIAL_PROFILE_ROOT")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t01calltime_")
        self.tmp = Path(self._tmp.name)
        self._saved = {k: os.environ.pop(k, None) for k in self.ENVS}

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def test_novelty_resolves_per_call(self) -> None:
        d1, d2 = self.tmp / "n1", self.tmp / "n2"
        os.environ["CREATIVE_NOVELTY_ROOT"] = str(d1)
        novelty.accept(_spec("t01_ct"), "t01_ct", day="2026-09-10")
        self.assertTrue((d1 / "t01_ct.jsonl").is_file(), "first write ignored the call-time override")
        os.environ["CREATIVE_NOVELTY_ROOT"] = str(d2)
        novelty.accept(_spec("t01_ct"), "t01_ct", day="2026-09-11")
        self.assertTrue((d2 / "t01_ct.jsonl").is_file(), "second write did not honour the NEW override (path frozen?)")
        self.assertEqual(len((d1 / "t01_ct.jsonl").read_text().splitlines()), 1)

    def test_learning_store_resolves_per_call(self) -> None:
        d1, d2 = self.tmp / "l1", self.tmp / "l2"
        os.environ["CREATIVE_LEARNING_ROOT"] = str(d1)
        learning_store.append_learning("t01_ct", {"creative_id": "cr_1", "kind": "qa"})
        self.assertTrue((d1 / "t01_ct.jsonl").is_file())
        os.environ["CREATIVE_LEARNING_ROOT"] = str(d2)
        learning_store.append_learning("t01_ct", {"creative_id": "cr_2", "kind": "qa"})
        self.assertTrue((d2 / "t01_ct.jsonl").is_file(), "learning store path frozen at import")
        self.assertEqual(len((d1 / "t01_ct.jsonl").read_text().splitlines()), 1)

    def test_social_profile_resolves_per_call(self) -> None:
        d1, d2 = self.tmp / "s1", self.tmp / "s2"
        prof = social_profile.SocialProfile(
            tenant_id="t01_ct", profile_version="v1", source="owner_supplied",
            source_ref="", analysis_method="assisted", analyzed_at=1.0,
        )
        os.environ["CREATIVE_SOCIAL_PROFILE_ROOT"] = str(d1)
        social_profile.save_profile(prof)
        self.assertTrue((d1 / "t01_ct.json").is_file())
        os.environ["CREATIVE_SOCIAL_PROFILE_ROOT"] = str(d2)
        social_profile.save_profile(prof)
        self.assertTrue((d2 / "t01_ct.json").is_file(), "social profile path frozen at import")


# --------------------------------------------------------------------------- #
# V8 — fail-closed flag defaults
# --------------------------------------------------------------------------- #
class TestV8FlagDefaults(unittest.TestCase):
    KEYS = ("CREATIVE_NOVELTY_ENABLED", "CREATIVE_SOCIAL_PROFILE_ENABLED", "CREATIVE_LEARNING_PERSIST_ENABLED")

    def setUp(self) -> None:
        self._saved = {k: os.environ.pop(k, None) for k in self.KEYS}

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_defaults(self) -> None:
        from app.marketing.creative_os import flags

        self.assertTrue(flags.novelty_enabled(), "CREATIVE_NOVELTY_ENABLED must default ON (safe state)")
        self.assertFalse(flags.social_profile_enabled(), "CREATIVE_SOCIAL_PROFILE_ENABLED must default OFF")
        self.assertTrue(flags.learning_persist_enabled(), "CREATIVE_LEARNING_PERSIST_ENABLED must default ON")

    def test_in_snapshot(self) -> None:
        from app.marketing.creative_os import flags

        snap = flags.flag_snapshot()
        self.assertIs(snap.get("CREATIVE_NOVELTY_ENABLED"), True)
        self.assertIs(snap.get("CREATIVE_SOCIAL_PROFILE_ENABLED"), False)
        self.assertIs(snap.get("CREATIVE_LEARNING_PERSIST_ENABLED"), True)


# --------------------------------------------------------------------------- #
# V9 — no new third-party dependency
# --------------------------------------------------------------------------- #
class TestV9NoNewDependency(unittest.TestCase):
    ALLOWED_EXTRA = {"__future__", "filelock"}

    def test_imports_are_stdlib_or_app(self) -> None:
        allowed = set(sys.stdlib_module_names) | self.ALLOWED_EXTRA
        offenders: list[str] = []
        for rel in TARGET_FILES:
            tree = ast.parse(Path(REPO, rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        continue  # relative import
                    roots = [(node.module or "").split(".")[0]]
                else:
                    continue
                for root in roots:
                    if not root or root == "app" or root in allowed:
                        continue
                    offenders.append(f"{rel}: {root}")
        self.assertEqual(offenders, [], "non-stdlib third-party imports introduced:\n" + "\n".join(offenders))


# --------------------------------------------------------------------------- #
# V10 — novelty_blocked event registration + persistence
# --------------------------------------------------------------------------- #
class TestV10NoveltyBlockedEvent(_StoreRedirect):
    def test_registered_and_readable(self) -> None:
        self.assertIn("novelty_blocked", delivery_ledger.EVENT_TYPES)
        self.assertIn("novelty_blocked", delivery_ledger.LABELS)
        wrote = delivery_ledger.log_event("t01_ledger", "novelty_blocked", detail="cr_x:forced", meta={"forced": True})
        self.assertTrue(wrote, "log_event returned False — event not registered")
        events = [e["event"] for e in delivery_ledger.timeline("t01_ledger", limit=20)]
        self.assertIn("novelty_blocked", events)
        admin = [e["event"] for e in delivery_ledger.admin_view("t01_ledger")["timeline"]]
        self.assertIn("novelty_blocked", admin)
        self.assertEqual(delivery_ledger.summary("t01_ledger")["counts"].get("novelty_blocked"), 1)
        cust = [e["event"] for e in delivery_ledger.timeline("t01_ledger", limit=20, customer_only=True)]
        self.assertNotIn("novelty_blocked", cust, "gate jargon must not be customer-visible")


if __name__ == "__main__":
    unittest.main(verbosity=2)
