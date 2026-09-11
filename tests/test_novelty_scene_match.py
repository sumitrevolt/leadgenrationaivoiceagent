"""Regression: the scene-level match rule catches the Jaccard-DILUTION clone.

The novelty gate refuses a candidate when ANY of:
  * jaccard >= 0.6, OR
  * same (recipe, template) within the 7-day window, OR
  * scene_match_ratio >= 0.75  (NEW — this file).

The third rule is the one this file locks in. A clone that swaps 1 of 4 scenes
keeps the whole-text Jaccard near/below 0.6 (the other 3 scenes are verbatim),
so the global-shingle rule misses it — yet the viewer sees a near-duplicate.
Swapping the recipe/template_id so the structural rule stays silent makes this
the exact escape the adversarial QA found.

Run:  python -m unittest tests.test_novelty_scene_match
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import app.platform.runtime_data_authority as auth
from app.marketing.creative_os import novelty


class _StoreRedirect(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="novelty_scene_")
        self.tmp = Path(self._tmp.name)
        self._orig = auth.resolve_store_path

        def _fake_resolve(**kw):
            return self.tmp / str(kw.get("store_id", "store")).replace(".", "_")

        auth.resolve_store_path = _fake_resolve  # type: ignore[assignment]

    def tearDown(self) -> None:
        auth.resolve_store_path = self._orig  # type: ignore[assignment]
        self._tmp.cleanup()


def _spec(tenant_id: str, recipe: str, template_id: str, scenes_text: list[str]) -> dict:
    return {
        "tenant_id": tenant_id,
        "creative_id": "c_" + tenant_id,
        "recipe": recipe,
        "template_id": template_id,
        "hook_variant": "",
        "scenes": [
            {"index": i, "role": f"s{i}", "text": t} for i, t in enumerate(scenes_text)
        ],
    }


_BASE = [
    "Opening line for the salon offer available today only",
    "Second scene describing the bridal glow package in detail",
    "Third scene with a short happy customer testimonial here",
    "Final scene with the clear call to action for booking now",
]

# 3 of 4 scenes identical (A,B,C); 4th scene is long and completely distinct so
# the whole-text Jaccard stays well under 0.6 even though 3/4 scenes are verbatim.
_CLONE_SCENES = [
    "Opening line for the salon offer available today only",
    "Second scene describing the bridal glow package in detail",
    "Third scene with a short happy customer testimonial here",
    "Entirely unrelated fourth scene carrying brand new wording that shares no "
    "phrasing with the original final scene whatsoever and keeps going with "
    "more unique vocabulary so the global Jaccard stays safely below the "
    "refusal threshold while three of the four scenes remain byte identical",
]


class TestSceneMatchRatio(_StoreRedirect):
    def _accept_base(self, tid: str) -> None:
        novelty.accept(_spec(tid, "offer_announcement", "local_service_promo_v1", _BASE), tid, day="2026-09-10")

    def _clone_verdict(self, tid: str, threshold: float):
        prev = os.environ.get("CREATIVE_NOVELTY_SCENE_MATCH_RATIO")
        os.environ["CREATIVE_NOVELTY_SCENE_MATCH_RATIO"] = str(threshold)
        try:
            return novelty.check(
                _spec(tid, "problem_solution", "salon_service_v1", _CLONE_SCENES),
                tid,
                n=7,
                day="2026-09-11",
            )
        finally:
            if prev is None:
                os.environ.pop("CREATIVE_NOVELTY_SCENE_MATCH_RATIO", None)
            else:
                os.environ["CREATIVE_NOVELTY_SCENE_MATCH_RATIO"] = prev

    def test_three_of_four_clone_refused_by_scene_rule(self) -> None:
        tid = "scene_clone_tenant"
        self._accept_base(tid)
        verdict = self._clone_verdict(tid, 0.75)
        self.assertFalse(verdict["ok"], f"dilution clone must be refused, got {verdict}")
        self.assertIn(
            "scene_match_ratio",
            verdict["reason"],
            f"scene rule must be the trigger, got {verdict}",
        )

    def test_scene_rule_is_inert_above_threshold(self) -> None:
        # Raising the ratio threshold to 1.0 means a 0.75 clone can no longer trip
        # the scene rule; with a distinct recipe/template and a low Jaccard the
        # gate must now accept (proves the scene rule — not Jaccard/structural —
        # was what refused it at 0.75).
        tid = "scene_thr_tenant"
        self._accept_base(tid)
        verdict = self._clone_verdict(tid, 1.0)
        self.assertTrue(verdict["ok"], f"0.75 clone must pass at threshold 1.0, got {verdict}")


class TestSceneMatchRatioBackwardCompatible(_StoreRedirect):
    def test_two_of_four_clone_passes_scene_rule(self) -> None:
        # Only 2 of 4 scenes identical -> ratio 0.5 < 0.75, different recipe/template
        # so structural is silent; gate should accept (Jaccard also low).
        tid = "scene_pass_tenant"
        base = [
            "Alpha scene text for the marketing video intro",
            "Bravo scene text describing the core service clearly",
            "Charlie scene presenting a couple of proof points",
            "Delta scene ending with the closing call to action",
        ]
        novelty.accept(_spec(tid, "offer_announcement", "local_service_promo_v1", base), tid, day="2026-09-10")
        clone = [
            "Alpha scene text for the marketing video intro",
            "Bravo scene text describing the core service clearly",
            "Zulu completely different third scene wording here now and longer",
            "Yankee completely different fourth scene wording here as well longer",
        ]
        verdict = novelty.check(
            _spec(tid, "problem_solution", "salon_service_v1", clone), tid, n=7, day="2026-09-11"
        )
        self.assertTrue(verdict["ok"], f"2/4 clone should pass, got {verdict}")
