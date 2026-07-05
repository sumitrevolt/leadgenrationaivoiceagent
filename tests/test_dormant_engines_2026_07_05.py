"""Dormant/untested platform-engine coverage — R-29 (docs/GAP_REGISTER_2026_07_05.md).

Five completely-untested modules, all flag-gated OR simply never exercised by the
suite. Bar per module: (a) import-smoke, (b) flag-OFF inertness (never raises, no
network), (c) flag-ON contract with all external I/O mocked (LLM/HTTP/DB), (d) for
the admin router — REAL auth enforcement (not the harness's open-auth mock).

Modules:
  1. app.platform.gtm_targeting   (flag GTM_TARGETING)      — city×niche coverage ledger
  2. app.platform.udyam_pipeline  (flag UDYAM_PIPELINE)      — Udyam-primary lead source
  3. app.platform.gap_analyzer    (no flag, pure logic)      — competitive gap scoring
  4. app.platform.icp_generator   (no flag, LLM-backed)      — /api/growth/icp/generate
  5. app.api.niche_db             (router /api/niche/*)      — admin-gated prospect DB

Convention: monkeypatch module-level path consts to tmp_path (never touch real
data/), monkeypatch free_ai.chat / any network-touching helper, security assertions
strip the harness's mock-admin overrides (mirrors tests/security/conftest.py) so
401/403 is proven for real instead of assumed.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ============================================================================
# 1. gtm_targeting — GTM_TARGETING flag, paced city×niche coverage ledger
# ============================================================================
class TestGtmTargeting:
    def test_import_smoke(self):
        from app.platform import gtm_targeting  # noqa: F401

    def test_flag_off_next_targets_empty_never_raises(self, monkeypatch, tmp_path):
        from app.platform import gtm_targeting as gtm

        monkeypatch.delenv("GTM_TARGETING", raising=False)
        monkeypatch.setattr(gtm, "_STATE", str(tmp_path / "gtm_coverage.json"))
        assert gtm.enabled() is False
        assert gtm.next_targets(n=5) == []

    def test_flag_explicit_zero_also_inert(self, monkeypatch, tmp_path):
        from app.platform import gtm_targeting as gtm

        monkeypatch.setenv("GTM_TARGETING", "0")
        monkeypatch.setattr(gtm, "_STATE", str(tmp_path / "gtm_coverage.json"))
        assert gtm.next_targets(n=5) == []

    def test_coverage_summary_safe_even_flag_off(self, monkeypatch, tmp_path):
        """Admin view must never raise regardless of flag state."""
        from app.platform import gtm_targeting as gtm

        monkeypatch.delenv("GTM_TARGETING", raising=False)
        monkeypatch.setattr(gtm, "_STATE", str(tmp_path / "gtm_coverage.json"))
        summary = gtm.coverage_summary()
        assert summary["enabled"] is False
        assert summary["total_pairs"] > 0  # matrix is pure data, builds regardless
        assert summary["covered_pairs"] == 0

    def test_build_matrix_pure_sorted_by_priority(self):
        from app.platform import gtm_targeting as gtm

        matrix = gtm.build_matrix()
        assert isinstance(matrix, list) and len(matrix) > 0
        for p in matrix[:3]:
            assert {"city", "state", "tier", "niche", "query", "band", "priority"} <= set(p.keys())
        prios = [p["priority"] for p in matrix]
        assert prios == sorted(prios, reverse=True)

    def test_flag_on_next_targets_and_mark_covered_reprioritises(self, monkeypatch, tmp_path):
        from app.platform import gtm_targeting as gtm

        state_path = tmp_path / "gtm_coverage.json"
        monkeypatch.setenv("GTM_TARGETING", "1")
        monkeypatch.setattr(gtm, "_STATE", str(state_path))
        assert gtm.enabled() is True

        first_batch = gtm.next_targets(n=1)
        assert len(first_batch) == 1
        top_pair = first_batch[0]
        top_key = gtm._pair_key(top_pair)

        gtm.mark_covered(top_pair, yield_count=4, ts=1000.0)
        assert state_path.exists()  # persisted, idempotent state file

        second_batch = gtm.next_targets(n=1)
        assert gtm._pair_key(second_batch[0]) != top_key  # covered pair no longer first

        summary = gtm.coverage_summary()
        assert summary["covered_pairs"] == 1
        assert summary["total_leads_harvested"] == 4

    def test_mark_covered_never_raises_on_bad_input(self, monkeypatch, tmp_path):
        from app.platform import gtm_targeting as gtm

        monkeypatch.setattr(gtm, "_STATE", str(tmp_path / "gtm_coverage.json"))
        gtm.mark_covered({})  # falsy pair -> no-op, no raise
        gtm.mark_covered(None)  # type: ignore[arg-type]


# ============================================================================
# 2. udyam_pipeline — UDYAM_PIPELINE flag, Udyam-primary -> Maps/web enrich -> persist
# ============================================================================
class TestUdyamPipeline:
    def test_import_smoke(self):
        from app.platform import udyam_pipeline  # noqa: F401

    async def test_flag_off_inert(self, monkeypatch):
        from app.platform import udyam_pipeline as up

        monkeypatch.delenv("UDYAM_PIPELINE", raising=False)
        assert up.enabled() is False
        out = await up.run(limit=10, city="Mumbai", niche="general")
        assert out == {"enabled": False}

    async def test_flag_on_no_datagov_key_short_circuits_before_network(self, monkeypatch):
        """Flag ON but DATA_GOV_IN_API_KEY/RESOURCE_ID unset -> the REAL
        `_src_opendata` returns immediately with zero seeds and never opens a
        socket (checked BEFORE building the URL) — thin real path, no mocking
        needed to prove this branch is network-safe."""
        from app.platform import udyam_pipeline as up

        monkeypatch.setenv("UDYAM_PIPELINE", "1")
        monkeypatch.delenv("DATA_GOV_IN_API_KEY", raising=False)
        monkeypatch.delenv("DATA_GOV_RESOURCE_ID", raising=False)
        out = await up.run(limit=5, city="Pune", niche="general")
        assert out["enabled"] is True
        assert out["seeds"] == 0
        assert out["new"] == 0
        assert "no Udyam seeds" in out.get("note", "")

    async def test_flag_on_enriched_seed_persists_with_reclassified_niche(self, monkeypatch):
        """Full enrich+dedupe+persist contract with every external call mocked:
        seed source, Maps/OSM enrich, and the prospector store."""
        from app.platform import lead_harvester, prospector
        from app.platform import udyam_pipeline as up

        monkeypatch.setenv("UDYAM_PIPELINE", "1")
        monkeypatch.delenv("OPENCORPORATES_API_TOKEN", raising=False)

        async def _fake_seeds(city, limit):
            return [
                {
                    "business_name": "Sharma Solar Pvt Ltd",
                    "city": city,
                    "pincode": "411001",
                    "major_activity": "solar panel installation",
                }
            ]

        async def _fake_enrich(name, city, pincode=""):
            return {
                "phone": "9876543210",
                "website": "",
                "address": "MG Road",
                "rating": 4.3,
                "email": "",
            }

        recorded: list[dict] = []

        def _fake_append(rec):
            recorded.append(rec)
            return True

        monkeypatch.setattr(up, "_udyam_seeds", _fake_seeds)
        monkeypatch.setattr(up, "_maps_enrich", _fake_enrich)
        monkeypatch.setattr(lead_harvester, "_existing_keys", lambda: (set(), set()))
        monkeypatch.setattr(prospector, "_append", _fake_append)

        out = await up.run(limit=5, city="Pune", niche="general")

        assert out["enabled"] is True
        assert out["seeds"] == 1
        assert out["enriched"] == 1
        assert out["new"] == 1
        assert len(recorded) == 1
        rec = recorded[0]
        assert rec["business_name"] == "Sharma Solar Pvt Ltd"
        assert rec["phone"] == "+919876543210"
        assert rec["source"] == "udyam_enriched"
        # classify_from_text re-tags from Udyam MajorActivity instead of the
        # generic default niche passed in — this was the whole point of the fn.
        assert rec["niche"] == "solar_residential"

    async def test_flag_on_dedupes_known_phone_skips_persist(self, monkeypatch):
        from app.platform import lead_harvester, prospector
        from app.platform import udyam_pipeline as up

        monkeypatch.setenv("UDYAM_PIPELINE", "1")

        async def _fake_seeds(city, limit):
            return [{"business_name": "Known Biz", "city": city}]

        async def _fake_enrich(name, city, pincode=""):
            return {"phone": "9876543210"}

        append_called = {"value": False}

        monkeypatch.setattr(up, "_udyam_seeds", _fake_seeds)
        monkeypatch.setattr(up, "_maps_enrich", _fake_enrich)
        monkeypatch.setattr(lead_harvester, "_existing_keys", lambda: ({"9876543210"}, set()))
        monkeypatch.setattr(
            prospector, "_append", lambda rec: append_called.__setitem__("value", True) or True
        )

        out = await up.run(limit=5, city="Pune", niche="general")
        assert out["new"] == 0
        assert out["skipped"] == 1
        assert append_called["value"] is False


# ============================================================================
# 3. gap_analyzer — competitive feature-gap scoring (pure logic, real data file)
# ============================================================================
class TestGapAnalyzer:
    def test_import_smoke(self):
        from app.platform import gap_analyzer  # noqa: F401

    def test_competitive_feature_count_matches_data_file(self):
        from app.platform import gap_analyzer as ga

        with open(ga.COMPETITIVE_FEATURES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        expected_customer = sum(len(v) for v in raw["customer_dashboard"].values())
        expected_admin = sum(len(v) for v in raw["admin_dashboard"].values())
        assert ga.competitive_feature_count("customer") == expected_customer
        assert ga.competitive_feature_count("admin") == expected_admin

    def test_identify_gaps_empty_inventory_flags_every_competitive_feature(self):
        from app.platform import gap_analyzer as ga

        gaps = ga.identify_gaps({"features": []}, "customer")
        assert len(gaps) == ga.competitive_feature_count("customer")
        assert all(g.dashboard == "customer" for g in gaps)
        assert len({g.id for g in gaps}) == len(gaps)  # unique ids

    def test_identify_gaps_detects_matching_feature_excludes_it(self):
        from app.platform import gap_analyzer as ga

        inventory = {
            "features": [
                {
                    "feature_name": "Global search bar with instant filter",
                    "description": "search leads by name",
                },
            ]
        }
        gaps = ga.identify_gaps(inventory, "customer")
        gap_names = {g.name.lower() for g in gaps}
        assert "global search bar" not in gap_names
        assert len(gaps) < ga.competitive_feature_count("customer")

    def test_calculate_parity_score(self):
        from app.platform import gap_analyzer as ga
        from app.platform.assessment_models import Gap

        assert ga.calculate_parity_score([], 10) == 100.0
        gaps = [Gap(id=f"g{i}", name="x", dashboard="customer") for i in range(4)]
        assert ga.calculate_parity_score(gaps, 10) == 60.0
        assert ga.calculate_parity_score([], 0) == 100.0  # no benchmark -> full parity

    def test_score_gap_impact_thresholds(self):
        from app.platform import gap_analyzer as ga
        from app.platform.assessment_models import Gap, Impact

        assert ga.score_gap_impact(Gap(id="g", name="x", dashboard="c", prevalence=6)) == Impact.HIGH
        assert ga.score_gap_impact(Gap(id="g", name="x", dashboard="c", prevalence=3)) == Impact.MEDIUM
        assert ga.score_gap_impact(Gap(id="g", name="x", dashboard="c", prevalence=1)) == Impact.LOW

    def test_estimate_effort(self):
        from app.platform import gap_analyzer as ga
        from app.platform.assessment_models import Effort, Gap

        assert ga.estimate_effort(Gap(id="g", name="Anything", dashboard="c"), True) == Effort.HIGH
        css_gap = Gap(id="g", name="Dark mode toggle", dashboard="c")
        assert ga.estimate_effort(css_gap, backend_dependency=False) == Effort.LOW
        other_gap = Gap(id="g", name="Something totally novel", dashboard="c")
        assert ga.estimate_effort(other_gap, backend_dependency=False) == Effort.MEDIUM

    def test_load_competitive_features_missing_file_raises(self, monkeypatch, tmp_path):
        """Documented contract: malformed/missing data file -> RuntimeError (not
        a silent empty dict) so a bad deploy is loud, not quietly wrong."""
        from app.platform import gap_analyzer as ga

        monkeypatch.setattr(ga, "COMPETITIVE_FEATURES_PATH", tmp_path / "missing.json")
        with pytest.raises(RuntimeError):
            ga._load_competitive_features()

    def test_get_all_gaps_covers_both_dashboards(self):
        from app.platform import gap_analyzer as ga

        result = ga.get_all_gaps({"features": []}, {"features": []})
        assert set(result.keys()) == {"customer", "admin"}
        assert len(result["customer"]) == ga.competitive_feature_count("customer")
        assert len(result["admin"]) == ga.competitive_feature_count("admin")


# ============================================================================
# 4. icp_generator — backs the LIVE /api/growth/icp/generate endpoint
# ============================================================================
class TestIcpGenerator:
    def test_import_smoke(self):
        from app.platform import icp_generator  # noqa: F401

    async def test_generate_happy_path_merges_llm_json(self, monkeypatch, tmp_path):
        from app.platform import icp_generator as icp
        from app.platform import team as team_mod
        from app.voice_agent import free_ai

        monkeypatch.setattr(icp, "_DIR", str(tmp_path / "icp"))
        monkeypatch.setattr(team_mod, "log_event", lambda *a, **k: None)

        fixed_json = json.dumps(
            {
                "title": "Local Salon Owners",
                "industries": ["beauty", "wellness"],
                "pain_points": ["low footfall"],
                "pitch_angle": "Fill your empty chairs",
            }
        )

        async def _fake_chat(system, messages, max_tokens=90, temperature=0.6):
            return (f"Here is the ICP:\n{fixed_json}\nThanks.", "stub")

        monkeypatch.setattr(free_ai, "chat", _fake_chat)

        result = await icp.generate(
            client_id="client-1",
            business_name="Glow Salon",
            niche="general",
            city="Pune",
            brief="local salon lead gen",
        )

        assert result["ok"] is True
        out_icp = result["icp"]
        assert out_icp["title"] == "Local Salon Owners"
        assert out_icp["industries"] == ["beauty", "wellness"]
        assert out_icp["client_id"] == "client-1"
        assert "fallback" not in out_icp

        saved = icp.get("client-1")
        assert saved["title"] == "Local Salon Owners"

    async def test_generate_never_raises_llm_failure_falls_back_to_niche_data(
        self, monkeypatch, tmp_path
    ):
        from app.platform import icp_generator as icp
        from app.platform import team as team_mod
        from app.voice_agent import free_ai

        monkeypatch.setattr(icp, "_DIR", str(tmp_path / "icp"))
        monkeypatch.setattr(team_mod, "log_event", lambda *a, **k: None)

        async def _boom(*a, **k):
            raise RuntimeError("llm down")

        monkeypatch.setattr(free_ai, "chat", _boom)

        result = await icp.generate(
            client_id="client-2",
            business_name="Solar Co",
            niche="solar_residential",
            city="Nashik",
            brief="",
        )
        assert result["ok"] is True
        out_icp = result["icp"]
        assert out_icp["fallback"] is True
        assert out_icp["pain_points"]
        assert out_icp["prospect_keywords"]
        assert "llm down" in out_icp["error"]

    def test_get_missing_client_returns_empty_dict(self, monkeypatch, tmp_path):
        from app.platform import icp_generator as icp

        monkeypatch.setattr(icp, "_DIR", str(tmp_path / "icp"))
        assert icp.get("no-such-client-xyz") == {}


# ============================================================================
# 5. niche_db router — /api/niche/* (admin-gated except two documented public GETs)
# ============================================================================
class TestNicheDbRouter:
    @pytest.fixture
    def real_auth_client(self):
        """Strip the harness's mock-admin auth overrides for real 401/403
        enforcement, mirroring tests/security/conftest.py's pattern (the
        false-confidence bug that pattern was written to prevent)."""
        from app.api.auth_deps import (
            get_current_user,
            require_admin,
            require_agent,
            require_manager,
            require_super_admin,
        )

        auth_deps = (
            get_current_user,
            require_admin,
            require_agent,
            require_manager,
            require_super_admin,
        )
        saved = {d: app.dependency_overrides[d] for d in auth_deps if d in app.dependency_overrides}
        for d in auth_deps:
            app.dependency_overrides.pop(d, None)
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.update(saved)

    def test_router_mounted_with_expected_routes(self):
        """Pins the actual registered surface: 10 route objects / 9 distinct
        paths (GET+POST share /api/niche/prospects)."""
        niche_routes = [
            (r.path, tuple(sorted(getattr(r, "methods", []) or [])))
            for r in app.routes
            if getattr(r, "path", "").startswith("/api/niche")
        ]
        expected = {
            ("/api/niche/schema/{niche_key}", ("GET",)),
            ("/api/niche/schemas", ("GET",)),
            ("/api/niche/prospects", ("POST",)),
            ("/api/niche/prospects/bulk", ("POST",)),
            ("/api/niche/prospects", ("GET",)),
            ("/api/niche/prospects/next-to-call", ("GET",)),
            ("/api/niche/prospects/{lead_id}", ("PATCH",)),
            ("/api/niche/stats", ("GET",)),
            ("/api/niche/voice-niches", ("GET",)),
            ("/api/niche/queue-call", ("POST",)),
        }
        assert set(niche_routes) == expected
        assert len(niche_routes) == 10
        assert len({p for p, _ in niche_routes}) == 9

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("get", "/api/niche/schemas", None),
            ("post", "/api/niche/prospects", {}),
            ("post", "/api/niche/prospects/bulk", {}),
            ("get", "/api/niche/prospects?client_id=c1", None),
            ("get", "/api/niche/prospects/next-to-call?client_id=c1&niche=general", None),
            ("patch", "/api/niche/prospects/lead-1", {"outcome": "qualified"}),
            ("get", "/api/niche/stats?client_id=c1", None),
            ("post", "/api/niche/queue-call", {}),
        ],
    )
    def test_admin_gated_routes_reject_unauthenticated(self, real_auth_client, method, path, body):
        if body is None:
            resp = getattr(real_auth_client, method)(path)
        else:
            resp = getattr(real_auth_client, method)(path, json=body)
        assert resp.status_code in (401, 403), (
            f"{method.upper()} {path} returned {resp.status_code} without auth "
            f"(must be 401/403). Body: {resp.text[:200]}"
        )

    def test_schema_and_voice_niches_are_intentionally_public(self, real_auth_client):
        """These two GETs have no `Depends(require_admin)` in the source — the
        AI dialer/other services can introspect niche schemas without an admin
        token. This test locks that as an intentional contract, not an oversight."""
        r1 = real_auth_client.get("/api/niche/schema/general")
        assert r1.status_code == 200
        assert r1.json()["ok"] is True

        r2 = real_auth_client.get("/api/niche/voice-niches")
        assert r2.status_code == 200
        assert r2.json()["ok"] is True
