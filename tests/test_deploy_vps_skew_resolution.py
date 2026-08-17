"""Contract tests: deploy_vps.sh skew check resolves via compose services.

RISKS B3 — hardcoded leadgen_app / leadgen_worker names false-FATAL when compose
uses project-prefixed/hashed container names even though /health SHA matches.
These are static text assertions (no docker required), same pattern as
test_deploy_vps_retention.py.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "deploy_vps.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _skew_block() -> str:
    t = _text()
    start = t.index("=== SKEW CHECK")
    end = t.index("exit 4", start)
    # include the closing fi after exit 4
    end = t.index("\nfi\n", end) + 4
    return t[start:end]


def test_skew_iterates_compose_services_not_bare_container_names():
    skew = _skew_block()
    assert "for svc in $ALL_ROLLOUT_SERVICES" in skew
    assert "for c in leadgen_app" not in skew
    assert "leadgen_worker_heavy" not in skew
    assert "leadgen_worker_video" not in skew


def test_skew_uses_compose_resolver_helper():
    t = _text()
    assert "_resolve_compose_container()" in t
    assert "_legacy_name_for_service()" in t
    skew = _skew_block()
    assert '_resolve_compose_container "$svc"' in skew


def test_resolver_prefers_compose_ps_and_service_label():
    t = _text()
    # extract resolve function body
    start = t.index("_resolve_compose_container() {")
    end = t.index("\n}\n", start)
    body = t[start:end]
    assert 'docker compose -f "$COMPOSE" --profile celery --profile dsh ps -q' in body
    assert "com.docker.compose.service=" in body
    # legacy bare names are fallback only (inside helper), not the sole path
    assert "_legacy_name_for_service" in body
    # compose ps must appear before legacy fallback
    assert body.index("docker compose -f") < body.index("_legacy_name_for_service")


def test_skew_fail_closed_on_missing_or_mismatched_sha():
    skew = _skew_block()
    assert "resolve=MISSING" in skew
    assert "SKEW=1" in skew
    assert "exit 4" in skew
    assert "FATAL: version skew" in skew


def test_skew_also_checks_image_tag_against_app_version():
    skew = _skew_block()
    assert ".Config.Image" in skew
    assert '*:"$VER"' in skew


def test_dsh_worker_is_built_recreated_and_skew_checked():
    t = _text()
    assert "BUILD hardened DSH runtime base" in t
    assert "deploy/dsh/Dockerfile" in t
    assert '--tag "$DSH_RUNTIME_IMAGE"' in t
    assert "--profile dsh" in t
    assert "build app $DSH_SERVICES" in t
    assert 'DSH_RUNTIME_IMAGE="$DSH_RUNTIME_IMAGE" docker compose' in t
    assert "up -d --no-deps $ALL_ROLLOUT_SERVICES" in t
    skew = _skew_block()
    assert "for svc in $ALL_ROLLOUT_SERVICES" in skew
    resolver_start = t.index("_legacy_name_for_service() {")
    resolver_end = t.index("\n}\n", resolver_start)
    resolver = t[resolver_start:resolver_end]
    assert "dsh-worker) echo leadgen_dsh_worker ;;" in resolver


def test_cleanup_ghosts_also_uses_compose_service_resolve():
    t = _text()
    start = t.index("_cleanup_recreate_ghosts() {")
    end = t.index("\n}\n", start)
    body = t[start:end]
    assert "for _svc in $ALL_ROLLOUT_SERVICES" in body
    assert "_resolve_compose_container" in body
    assert "for _c in leadgen_app" not in body


def test_safety_invariants_still_present():
    t = _text()
    assert "set -uo pipefail" in t
    assert 'SERVICES="app worker scheduler worker-heavy worker-video"' in t
    assert 'DSH_SERVICES="dsh-worker"' in t
    assert 'ALL_ROLLOUT_SERVICES="$SERVICES $DSH_SERVICES"' in t
    # APP_VERSION mandatory / latest refusal
    assert "refusing to deploy with APP_VERSION=" in t
    assert "provenance-less tag" in t or "ADR-097" in t
    # no bare skew loop left anywhere as primary check
    assert not re.search(
        r"for c in leadgen_app leadgen_worker leadgen_scheduler",
        t,
    )
