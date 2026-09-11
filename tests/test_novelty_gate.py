"""Consecutive-day novelty-gate acceptance (T05).

The owner's complaint — "abhi same video roz customer ko ja raha hai" — is a
*correctness* requirement, not a nicety: two consecutive daily videos for one
tenant must not be near-duplicates. This suite pins the gate's three load-bearing
behaviours against the real ``app.marketing.creative_os.novelty`` module:

  (a) two genuinely DIFFERENT scene-text sets score ``jaccard < 0.6`` and are
      ACCEPTED — so rotation actually rotates;
  (b) a near-COPY scores ``jaccard >= 0.6`` and is REFUSED as ``near_duplicate``
      — so a re-run cannot ship yesterday's script again;
  (c) a SHORT text (< 3 tokens) does NOT collapse to a degenerate ``1.0``
      similarity. This was a real availability bug: a single whole-line shingle
      made two different short lines compare identical, so a short-copy tenant
      was refused every day — i.e. permanently NO video. The guard is that
      ``scene_fingerprint`` emits NO shingles for short text, so the empty union
      reads ``0.0`` and the tenant is never blocked by the similarity path.

Hermetic: no network, no app.main, no renderer. Persistence is redirected to a
per-test temp dir via ``CREATIVE_NOVELTY_ROOT`` (resolved at call time by
``runtime_data_authority``).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.marketing import delivery_ledger
from app.marketing.creative_os import flags, novelty

# --------------------------------------------------------------------- fixtures
_D0 = "2026-09-10"
_D1 = "2026-09-11"  # the consecutive day
_D2 = "2026-09-12"  # day 3 (day 2 skipped)
_D_GAP7 = "2026-09-17"  # day 8 = _D0 + 7 -> window boundary (W=7 => in window)
_D_GAP8 = "2026-09-18"  # day 9 = _D0 + 8 -> just outside the window
_D_FAR = "2026-09-20"  # _D0 + 10 -> well outside the window

# Genuinely different copy: the two sets share no 3-gram (jaccard ~0.0).
_DIFFERENT_A = [
    "bridal glow makeover booking open now at our studio",
    "book your appointment this wedding season today",
]
_DIFFERENT_B = [
    "premium hair spa treatment for busy professionals",
    "relax recharge and refresh your look every weekend",
]
# Near-copy of A: a couple of words appended, most 3-grams intact (jaccard ~0.67).
_NEAR_COPY_OF_A = [
    "bridal glow makeover booking open now at our studio today",
    "book your appointment this wedding season today now",
]
# Fewer than 3 tokens -> no fingerprint at all.
_SHORT = ["Bridal glow"]

# --- 4-scene fixtures for the rolling-window regression (a/b/c/c'/f) ----------
# v0: the accepted creative (day 1).
_CLONE_4 = [
    "bridal glow makeover booking open now at our studio today",
    "book your appointment this wedding season with our expert team",
    "premium hair spa treatment for busy professionals every weekend",
    "call now to reserve your slot and get a free consultation",
]
# v1: 3 of 4 scenes BYTE-IDENTICAL; only the closing hook line reworded.
# Measured jaccard vs _CLONE_4 = 0.5714 (< 0.6) — the similarity path alone
# does NOT catch it, so the STRUCTURAL rule is what must refuse it.
_CLONE_4_HOOK = [
    "bridal glow makeover booking open now at our studio today",
    "book your appointment this wedding season with our expert team",
    "premium hair spa treatment for busy professionals every weekend",
    "ring us today to lock your slot and enjoy a special discount",
]
# v1b: a second 3-of-4 hook reword (same measured band).
_CLONE_4_REWORDED = [
    "bridal glow makeover booking open now at our studio today",
    "book your appointment this wedding season with our expert team",
    "premium hair spa treatment for busy professionals every weekend",
    "message us today to book your slot and unlock a special offer",
]
# v1c: a 4-scene reword where only 2 of 4 scenes are BYTE/3-gram identical to
# v0 — scene_match_ratio = 0.5 (< 0.75) so the SCENE rule stays INERT — but the
# whole-text 3-gram jaccard vs v0 (~0.45) lands inside the (0.4, 0.6) band.
# This isolates the JACCARD path so the threshold-flag call-time read can be
# asserted without the (later-added) scene rule also refusing the candidate.
_CLONE_4_JACCARD = [
    "bridal glow makeover booking open now at our studio today",
    "book your appointment this wedding season with our expert team",
    "premium hair spa session for busy clients every weekend",
    "call now to reserve your seat and grab a free demo",
]
# Genuinely different copy (jaccard ~0.08): shares no 3-gram with v0.
_DIFFERENT_4 = [
    "premium hair spa treatment for busy professionals",
    "relax recharge and refresh your look every weekend",
    "walk in for a complimentary skin analysis today",
    "our stylists are ready to help you glow again",
]
# Same recipe/template, DIFFERENT offer. Heavily reworded so the similarity
# path reads ~0.02 (< 0.6) — the STRUCTURAL rule is the SOLE refuser.
_OFFER_20 = [
    "flat 20 percent off on all bridal packages this week",
    "book your appointment today and save more",
    "our team of experts is waiting to help you",
    "call now to reserve your slot",
]
_OFFER_30 = [
    "enjoy flat 30 percent discount on every bridal booking",
    "reserve your date soon and grab the offer",
    "experienced beauticians ready to pamper you",
    "dial us to confirm your appointment today",
]


class _Scene:
    def __init__(self, text: str, role: str = "body") -> None:
        self.text = text
        self.role = role


class _Spec:
    """Minimal stand-in for a CreativeSpec — the gate reads only these fields."""

    def __init__(
        self,
        texts: list[str],
        *,
        recipe: str = "offer_announcement",
        template_id: str = "local_service_promo_v1",
        creative_id: str = "cr_test",
        revision: int = 0,
        scene_dicts: bool = False,
    ) -> None:
        # `scene_dicts=True` models a JSON-round-tripped spec (scenes as plain
        # mappings, not objects) — the case that used to blind the gate.
        if scene_dicts:
            self.scenes = [{"text": t} for t in texts]
        else:
            self.scenes = [_Scene(t) for t in texts]
        self.recipe = recipe
        self.template_id = template_id
        self.creative_id = creative_id
        self.approval_revision = revision
        self.hook_variant = "question"

    def spec_hash(self) -> str:
        return "h" * 8


class _NoveltyCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="novelty_")
        self._env = mock.patch.dict(
            os.environ,
            {
                "CREATIVE_NOVELTY_ROOT": self._tmp.name,
                # The unverifiable alert writes to the owner feed; redirect it so
                # the suite never touches the repo's runtime data.
                "OWNER_FEED_PATH": os.path.join(self._tmp.name, "owner_feed.jsonl"),
            },
        )
        self._env.start()
        # The exhaustion audit writes to the delivery ledger; redirect it too.
        self._ledger_patch = mock.patch.object(
            delivery_ledger, "_LEDGER_DIR", lambda: os.path.join(self._tmp.name, "ledger")
        )
        self._ledger_patch.start()

    def tearDown(self) -> None:
        self._ledger_patch.stop()
        self._env.stop()
        self._tmp.cleanup()


class TestThreshold(_NoveltyCase):
    def test_acceptance_threshold_is_point_six(self) -> None:
        self.assertEqual(novelty.JACCARD_THRESHOLD, 0.6)


class TestDifferentTextsAreAccepted(_NoveltyCase):
    def test_different_sets_score_below_threshold(self) -> None:
        fa = novelty.scene_fingerprint(_Spec(_DIFFERENT_A))
        fb = novelty.scene_fingerprint(_Spec(_DIFFERENT_B))
        j = novelty.jaccard(fa["shingles"], fb["shingles"])
        self.assertLess(j, novelty.JACCARD_THRESHOLD, f"different copy scored {j}")

    def test_different_consecutive_day_candidate_is_accepted(self) -> None:
        a = _Spec(_DIFFERENT_A, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        b = _Spec(_DIFFERENT_B, recipe="service_showcase", template_id="salon_service_v1")
        self.assertTrue(novelty.accept(a, "tenant-1", day=_D0)["ok"])

        result = novelty.check(b, "tenant-1", day=_D1)
        self.assertTrue(result["ok"], f"a genuinely different video was refused: {result}")
        self.assertNotEqual(result.get("outcome"), "near_duplicate")
        self.assertEqual(result["against"], [])
        self.assertTrue(novelty.accept(b, "tenant-1", day=_D1)["ok"])
        self.assertEqual(len(novelty.recent_lineage("tenant-1", n=5)), 2)


class TestNearCopyIsRefused(_NoveltyCase):
    def test_near_copy_scores_at_or_above_threshold(self) -> None:
        fa = novelty.scene_fingerprint(_Spec(_DIFFERENT_A))
        fc = novelty.scene_fingerprint(_Spec(_NEAR_COPY_OF_A))
        j = novelty.jaccard(fa["shingles"], fc["shingles"])
        self.assertGreaterEqual(j, novelty.JACCARD_THRESHOLD, f"near-copy scored only {j}")

    def test_near_copy_is_refused_on_the_next_day(self) -> None:
        a = _Spec(_DIFFERENT_A, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        # A DIFFERENT (recipe, template) so the ONLY thing that can refuse is the
        # similarity rule — this isolates the jaccard path from the
        # same-recipe-template-as-yesterday rule.
        c = _Spec(_NEAR_COPY_OF_A, recipe="festival_local", template_id="bridal_package_v1")
        self.assertTrue(novelty.accept(a, "tenant-2", day=_D0)["ok"])

        result = novelty.check(c, "tenant-2", day=_D1)
        self.assertFalse(result["ok"], "a near-copy of yesterday's video was accepted")
        self.assertEqual(result["outcome"], "near_duplicate")
        self.assertIn("jaccard>=0.6", result["reason"])
        self.assertTrue(any(x["jaccard"] >= 0.6 for x in result["against"]))

    def test_force_override_is_audited_not_silent(self) -> None:
        a = _Spec(_DIFFERENT_A, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        c = _Spec(_NEAR_COPY_OF_A, recipe="festival_local", template_id="bridal_package_v1")
        novelty.accept(a, "tenant-3", day=_D0)
        forced = novelty.check(c, "tenant-3", day=_D1, force=True)
        self.assertTrue(forced["ok"])
        self.assertTrue(forced["forced"])


class TestShortTextIsNotDegenerate(_NoveltyCase):
    """The availability bug: short copy must not read as 100% identical."""

    def test_short_text_emits_no_shingles(self) -> None:
        fp = novelty.scene_fingerprint(_Spec(_SHORT))
        self.assertEqual(fp["shingles"], [], "short text produced a shingle -> degenerate similarity")

    def test_short_text_similarity_is_zero_not_one(self) -> None:
        fp = novelty.scene_fingerprint(_Spec(_SHORT))
        j = novelty.jaccard(fp["shingles"], fp["shingles"])
        self.assertEqual(j, 0.0)
        self.assertNotEqual(j, 1.0, "short text collapsed to a degenerate 1.0 similarity")

    def test_two_different_short_texts_are_not_identical(self) -> None:
        a = novelty.scene_fingerprint(_Spec(["Glow up"]))
        b = novelty.scene_fingerprint(_Spec(["Bridal glow"]))
        self.assertEqual(novelty.jaccard(a["shingles"], b["shingles"]), 0.0)

    def test_short_text_tenant_is_never_permanently_blocked(self) -> None:
        # Same recipe/template AND a short body: OUTSIDE the rolling window the
        # only thing that could block it is the similarity path — which reads
        # 0.0 for a short body. (The day moved from _D2 to _D_FAR when the
        # structural rule became a rolling window: inside the window a same
        # recipe/template entry IS now refused, which is the ruling's intent.)
        s1 = _Spec(_SHORT, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        s2 = _Spec(_SHORT, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        self.assertTrue(novelty.accept(s1, "tenant-4", day=_D0)["ok"])

        result = novelty.check(s2, "tenant-4", day=_D_FAR)
        self.assertTrue(result["ok"], f"short-copy tenant was blocked: {result}")
        self.assertEqual(result["against"], [])


# =========================================================================== #
# Ruling 2026-09-11 — rolling-window structural rule, labelled "unverifiable",
# and the mandatory starvation guard. Scenarios (a)–(g) from the ruling.
# =========================================================================== #
class TestRollingWindowBypassClosed(_NoveltyCase):
    """(a) the exact QA bypass: accept day 1, SKIP day 2, ship a near-clone on
    day 3. Pre-ruling this returned ``ok: True``; it must now be refused."""

    def test_a_three_of_four_scene_clone_on_day_three_is_refused(self) -> None:
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        v1 = _Spec(_CLONE_4_HOOK, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        self.assertTrue(novelty.accept(v0, "t-win-a", day=_D0)["ok"])

        # Prove the similarity path ALONE is below threshold: only the structural
        # rule can refuse this candidate.
        j = novelty.jaccard(
            novelty.scene_fingerprint(v1)["shingles"],
            novelty.scene_fingerprint(v0)["shingles"],
        )
        self.assertLess(j, novelty.JACCARD_THRESHOLD, f"fixture is not sub-threshold: j={j}")
        self.assertGreaterEqual(j, 0.5, f"fixture outside the measured variant band: j={j}")

        # day 3 (day 2 skipped). This is the bypass.
        result = novelty.check(v1, "t-win-a", day=_D2)
        self.assertFalse(result["ok"], f"day-3 near-clone shipped: {result}")
        self.assertEqual(result["outcome"], "near_duplicate")
        self.assertIn(novelty.REASON_SAME_RT_WINDOW, result["reason"])
        self.assertTrue(
            any(a["same_recipe_template"] and a["within_window"] for a in result["against"]),
            f"structural rule did not fire: {result['against']}",
        )

    def test_a_force_override_still_bypasses_the_window(self) -> None:
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        v1 = _Spec(_CLONE_4_HOOK, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        novelty.accept(v0, "t-force-win", day=_D0)
        forced = novelty.check(v1, "t-force-win", day=_D2, force=True)
        self.assertTrue(forced["ok"], forced)
        self.assertTrue(forced["forced"], "operator force override stopped working")


class TestRollingWindowVariants(_NoveltyCase):
    def test_b_reworded_near_clone_on_day_three_is_refused(self) -> None:
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        v1b = _Spec(_CLONE_4_REWORDED, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        self.assertTrue(novelty.accept(v0, "t-win-b", day=_D0)["ok"])
        result = novelty.check(v1b, "t-win-b", day=_D2)
        self.assertFalse(result["ok"], f"reworded near-clone shipped: {result}")
        self.assertEqual(result["outcome"], "near_duplicate")

    def test_c_same_niche_different_recipe_template_is_accepted(self) -> None:
        # Same niche (bridal/beauty), DIFFERENT recipe + template -> no structural
        # collision; genuinely different content -> accepted.
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        other = _Spec(_DIFFERENT_4, recipe="service_showcase", template_id="salon_service_v1")
        self.assertTrue(novelty.accept(v0, "t-win-c", day=_D0)["ok"])
        result = novelty.check(other, "t-win-c", day=_D2)
        self.assertTrue(result["ok"], f"a genuinely different recipe/template was refused: {result}")
        self.assertNotEqual(result.get("outcome"), "near_duplicate")
        self.assertEqual(result["against"], [])

    def test_c_prime_same_recipe_template_different_offer_is_refused(self) -> None:
        o20 = _Spec(_OFFER_20, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        o30 = _Spec(_OFFER_30, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        self.assertTrue(novelty.accept(o20, "t-win-cp", day=_D0)["ok"])
        # The offer text is reworded enough that the similarity path reads ~0.02;
        # the STRUCTURAL rule is the sole refuser.
        j = novelty.jaccard(
            novelty.scene_fingerprint(o30)["shingles"],
            novelty.scene_fingerprint(o20)["shingles"],
        )
        self.assertLess(j, novelty.JACCARD_THRESHOLD, f"offer fixtures too similar: j={j}")
        result = novelty.check(o30, "t-win-cp", day=_D2)
        self.assertFalse(result["ok"], f"same-recipe/template different-offer shipped: {result}")
        self.assertIn(novelty.REASON_SAME_RT_WINDOW, result["reason"])

    def test_f_window_boundary_gap7_refused_gap8_accepted(self) -> None:
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        self.assertTrue(novelty.accept(v0, "t-win-f", day=_D0)["ok"])
        # gap 7 (== W=7, in window): same recipe/template -> REFUSED even though
        # the content is genuinely different.
        inside = _Spec(_DIFFERENT_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        r_in = novelty.check(inside, "t-win-f", day=_D_GAP7)
        self.assertFalse(r_in["ok"], f"gap-7 same-rt accepted (boundary wrong): {r_in}")
        self.assertIn(novelty.REASON_SAME_RT_WINDOW, r_in["reason"])
        # gap 8 (> W=7): outside the window -> accepted.
        outside = _Spec(_DIFFERENT_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        r_out = novelty.check(outside, "t-win-f", day=_D_GAP8)
        self.assertTrue(r_out["ok"], f"gap-8 same-rt refused (window too wide): {r_out}")


class TestUnverifiableIsLabelled(_NoveltyCase):
    """(d)/(d') — "cannot evaluate" must be LABELLED, never a silent pass, and
    must NOT be a hard block (short text is legitimate)."""

    def test_d_short_text_pass_is_labelled_not_bare(self) -> None:
        spec = _Spec(_SHORT, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        result = novelty.check(spec, "t-unv-d", day=_D0)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result.get("novelty_unverifiable"), f"unlabelled pass: {result}")
        self.assertEqual(result.get("reason"), novelty.REASON_NO_FINGERPRINT)
        # Not a BARE pass: the label key is present.
        self.assertIn("novelty_unverifiable", result)
        # The owner-feed note was actually emitted (path redirected in setUp).
        self.assertTrue(
            Path(os.environ["OWNER_FEED_PATH"]).exists(),
            "owner-feed alert for an unverifiable candidate was not emitted",
        )

    def test_d_dict_scene_short_text_pass_is_labelled(self) -> None:
        spec = _Spec(
            _SHORT,
            recipe="offer_announcement",
            template_id="beauty_luxury_offer_v1",
            scene_dicts=True,
        )
        result = novelty.check(spec, "t-unv-d2", day=_D0)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result.get("novelty_unverifiable"), f"unlabelled pass: {result}")
        self.assertEqual(result.get("reason"), novelty.REASON_NO_FINGERPRINT)

    def test_dict_scene_is_fingerprinted_not_blind(self) -> None:
        """The coercion fix: a JSON-round-tripped dict scene must produce
        shingles. Before the fix ``getattr(sc, 'text', '')`` returned '' so every
        dict-scene candidate compared as 0.0 — blind."""
        fp = novelty.scene_fingerprint(_Spec(_CLONE_4, scene_dicts=True))
        self.assertNotEqual(fp["shingles"], [], "dict scene was not fingerprinted — gate is blind")
        # ...and a dict-scene near-clone is actually refused.
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1", scene_dicts=True)
        v1 = _Spec(_CLONE_4_HOOK, recipe="offer_announcement", template_id="beauty_luxury_offer_v1", scene_dicts=True)
        self.assertTrue(novelty.accept(v0, "t-dict", day=_D0)["ok"])
        result = novelty.check(v1, "t-dict", day=_D2)
        self.assertFalse(result["ok"], f"dict-scene near-clone shipped (blind gate): {result}")

    def test_d_prime_empty_fingerprint_still_fires_structural(self) -> None:
        s1 = _Spec(_SHORT, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        s2 = _Spec(_SHORT, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        self.assertTrue(novelty.accept(s1, "t-unv-dp", day=_D0)["ok"])
        # day 3, same recipe/template, inside the window -> REFUSED despite the
        # empty fingerprint.
        result = novelty.check(s2, "t-unv-dp", day=_D2)
        self.assertFalse(result["ok"], f"empty-fingerprint same-rt clone shipped: {result}")
        self.assertTrue(result.get("novelty_unverifiable"), result)
        self.assertIn(novelty.REASON_SAME_RT_WINDOW, result["reason"])

    def test_exception_path_is_labelled_not_silent(self) -> None:
        with mock.patch.object(novelty, "scene_fingerprint", side_effect=RuntimeError("boom")):
            result = novelty.check(_Spec(_CLONE_4), "t-exc", day=_D0)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result.get("novelty_unverifiable"), f"exception path was a silent pass: {result}")
        self.assertEqual(result.get("reason"), novelty.REASON_NO_FINGERPRINT)
        self.assertIn("error", result)


class TestStarvationGuard(_NoveltyCase):
    """(e) when ALL rotations are refused the tenant must STILL get a video."""

    def test_e_all_rotations_refused_still_ships_a_video(self) -> None:
        prior = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        self.assertTrue(novelty.accept(prior, "t-exhaust", day=_D0)["ok"])
        # K+1 refused candidates (all same recipe/template, all near-clones).
        candidates = [
            _Spec(
                _CLONE_4_HOOK,
                recipe="offer_announcement",
                template_id="beauty_luxury_offer_v1",
                creative_id=f"cr_{i}",
            )
            for i in range(7)
        ]
        for c in candidates:
            self.assertFalse(novelty.check(c, "t-exhaust", day=_D1)["ok"], "fixture not refused")

        emitted: list[str] = []
        with mock.patch.object(
            delivery_ledger,
            "log_event",
            side_effect=lambda cid, ev, **kw: (emitted.append(ev), True)[1],
        ):
            out = novelty.resolve_exhaustion(candidates, "t-exhaust", day=_D1)

        self.assertTrue(out["ok"], f"exhaustion blocked the tenant: {out}")
        self.assertTrue(out["forced"], out)
        self.assertEqual(out["outcome"], "novelty_exhausted")
        self.assertIsNotNone(out.get("spec"), "exhaustion returned NO spec — tenant starved")
        self.assertIn("novelty_exhausted", out["events"])
        self.assertIn("novelty_exhausted", emitted, "no delivery_ledger novelty_exhausted event emitted")
        # The forced winner is persisted (auditable) — the tenant is not starved.
        rows = novelty.recent_lineage("t-exhaust", n=5)
        self.assertEqual(len(rows), 2, rows)
        self.assertTrue(rows[-1].forced, "exhaustion winner not marked forced in lineage")

    def test_e_exhaustion_records_durable_ledger_evidence(self) -> None:
        prior = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        novelty.accept(prior, "t-exhaust2", day=_D0)
        candidates = [
            _Spec(_CLONE_4_HOOK, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
            for _ in range(3)
        ]
        out = novelty.resolve_exhaustion(candidates, "t-exhaust2", day=_D1)
        self.assertTrue(out["ok"], out)
        # Either the dedicated event landed, or the registered fallback carrying
        # the real event name in meta — never nothing.
        rows = delivery_ledger.timeline("t-exhaust2", limit=20, customer_only=False)
        self.assertTrue(
            any(
                r.get("event") == "novelty_exhausted"
                or (r.get("meta") or {}).get("novelty_event") == "novelty_exhausted"
                for r in rows
            ),
            f"no durable novelty_exhausted evidence in the ledger: {rows}",
        )

    def test_e_picks_the_least_similar_candidate(self) -> None:
        prior = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        novelty.accept(prior, "t-exhaust3", day=_D0)
        # Two candidates: an exact clone (j=1.0) and a much weaker clone. The
        # least-similar one must be chosen.
        clone = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1", creative_id="clone")
        weak = _Spec(
            _CLONE_4_REWORDED, recipe="offer_announcement", template_id="beauty_luxury_offer_v1", creative_id="weak"
        )
        out = novelty.resolve_exhaustion([clone, weak], "t-exhaust3", day=_D1)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["spec"].creative_id, "weak", out.get("candidates"))

    def test_e_empty_candidate_list_is_reported_not_crashed(self) -> None:
        out = novelty.resolve_exhaustion([], "t-exhaust4", day=_D1)
        self.assertFalse(out["ok"], out)
        self.assertEqual(out["outcome"], "novelty_exhausted")
        self.assertEqual(out["events"], [])


class TestNewFlagAccessors(_NoveltyCase):
    """(g) window clamp + the three other tunables + flag_snapshot coverage."""

    def test_g_window_zero_and_garbage_clamp_to_one(self) -> None:
        for raw in ("0", "garbage", "-5", ""):
            with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_WINDOW_DAYS": raw}):
                self.assertEqual(flags.novelty_window_days(), 1, f"raw={raw!r} did not clamp to 1")
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_WINDOW_DAYS": "999"}):
            self.assertEqual(flags.novelty_window_days(), 30)
        with mock.patch.dict(os.environ):
            os.environ.pop("CREATIVE_NOVELTY_WINDOW_DAYS", None)
            self.assertEqual(flags.novelty_window_days(), 7, "unset window must default to 7")

    def test_g_gate_stays_active_with_clamped_window(self) -> None:
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        # Different CONTENT so only the structural rule can refuse (j ~ 0.08).
        v1 = _Spec(_DIFFERENT_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        novelty.accept(v0, "t-g", day=_D0)
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_WINDOW_DAYS": "0"}):
            # window clamps to 1 -> a consecutive-day same-rt candidate is still
            # refused (the gate is never disabled by a 0 window).
            r = novelty.check(v1, "t-g", day=_D1)
            self.assertFalse(r["ok"], f"gate disabled by a 0 window: {r}")
            self.assertIn(novelty.REASON_SAME_RT_WINDOW, r["reason"])
            # ...but a gap-2 same-rt falls outside the (clamped) 1-day window.
            r2 = novelty.check(v1, "t-g", day=_D2)
            self.assertTrue(r2["ok"], r2)

    def test_threshold_clamp_prevents_extremes(self) -> None:
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_JACCARD_THRESHOLD": "0"}):
            self.assertEqual(flags.novelty_jaccard_threshold(), 0.4)
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_JACCARD_THRESHOLD": "1"}):
            self.assertEqual(flags.novelty_jaccard_threshold(), 0.9)
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_JACCARD_THRESHOLD": "garbage"}):
            self.assertEqual(flags.novelty_jaccard_threshold(), 0.6)

    def test_max_rotations_clamp(self) -> None:
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_MAX_ROTATIONS": "0"}):
            self.assertEqual(flags.novelty_max_rotations(), 1)
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_MAX_ROTATIONS": "99"}):
            self.assertEqual(flags.novelty_max_rotations(), 12)
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_MAX_ROTATIONS": "garbage"}):
            self.assertEqual(flags.novelty_max_rotations(), 6)

    def test_alert_defaults_on_and_all_four_in_snapshot(self) -> None:
        with mock.patch.dict(os.environ):
            os.environ.pop("CREATIVE_NOVELTY_ALERT_ON_UNVERIFIABLE", None)
            self.assertTrue(flags.novelty_alert_on_unverifiable(), "alert must default ON (fail-closed)")
        snap = flags.flag_snapshot()
        for key in (
            "CREATIVE_NOVELTY_WINDOW_DAYS",
            "CREATIVE_NOVELTY_JACCARD_THRESHOLD",
            "CREATIVE_NOVELTY_MAX_ROTATIONS",
            "CREATIVE_NOVELTY_ALERT_ON_UNVERIFIABLE",
        ):
            self.assertIn(key, snap, f"{key} missing from flag_snapshot()")

    def test_threshold_flag_read_at_call_time(self) -> None:
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        # DIFFERENT recipe/template (structural rule inert) AND only 2-of-4
        # scenes identical (scene_match_ratio 0.5 < 0.75, so the later-added
        # SCENE rule is also inert). That leaves JACCARD as the sole decider,
        # which is what this test must isolate to prove the flag is read at
        # call time rather than cached at import.
        v1 = _Spec(_CLONE_4_JACCARD, recipe="festival_local", template_id="bridal_package_v1")
        novelty.accept(v0, "t-thr", day=_D0)
        self.assertTrue(novelty.check(v1, "t-thr", day=_D2)["ok"], "j~0.45 should pass at threshold 0.6")
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_JACCARD_THRESHOLD": "0.4"}):
            r = novelty.check(v1, "t-thr", day=_D2)
            self.assertFalse(r["ok"], f"threshold flag not honoured at call time: {r}")

    def test_window_flag_read_at_call_time(self) -> None:
        v0 = _Spec(_CLONE_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        v1 = _Spec(_DIFFERENT_4, recipe="offer_announcement", template_id="beauty_luxury_offer_v1")
        novelty.accept(v0, "t-winflag", day=_D0)
        self.assertTrue(novelty.check(v1, "t-winflag", day=_D_GAP8)["ok"], "gap 8 > default W=7 must pass")
        with mock.patch.dict(os.environ, {"CREATIVE_NOVELTY_WINDOW_DAYS": "10"}):
            r = novelty.check(v1, "t-winflag", day=_D_GAP8)
            self.assertFalse(r["ok"], f"window flag not honoured at call time: {r}")


if __name__ == "__main__":
    unittest.main()
