"""Staging compose containment contract (2026-08-08, OOM/capacity containment).

The staging stack mirrors prod but must NEVER be started by a bare `up -d`, must
never bind outside loopback, and must never leak onto production resources. It
also carries the memory-containment controls from
`docs/capacity/OOM_CAPACITY_REPORT_2026-08-08.md`.

Offline/pure — parses the compose files with PyYAML, no docker daemon required.
The live daemon-level checks (profile gating, fail-closed APP_VERSION, loopback
host_ip) were verified with `docker compose config` at authoring time; these
tests pin the file-level contract so a regression cannot silently ship.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
STAGING = REPO / "deploy" / "compose" / "docker-compose.staging.yml"
VPS = REPO / "docker-compose.vps.yml"


def _staging() -> dict:
    return yaml.safe_load(STAGING.read_text(encoding="utf-8"))


def _vps() -> dict:
    return yaml.safe_load(VPS.read_text(encoding="utf-8"))


def test_staging_has_all_three_services():
    services = _staging()["services"]
    assert set(services) == {"app_staging", "db_staging", "redis_staging"}


def test_every_staging_service_is_profile_gated():
    """Bare `up -d` (no `--profile staging`) must start NOTHING.

    Compose omits profile-listed services unless the profile is enabled, so if
    every service carries the profile the default invocation is inert.
    """
    services = _staging()["services"]
    for name, svc in services.items():
        profiles = svc.get("profiles") or []
        assert "staging" in profiles, f"{name} must be profile-gated (profiles: [staging])"


def test_staging_host_ports_are_loopback_only():
    """Host binding must be 127.0.0.1 — staging is never reachable off-box."""
    app = _staging()["services"]["app_staging"]
    ports = app.get("ports") or []
    assert ports, "app_staging must publish a port"
    for port in ports:
        assert str(port).startswith("127.0.0.1:"), f"non-loopback staging port: {port!r}"


def test_staging_image_is_pinned_fail_closed_no_latest():
    """ADR-097: mutable :latest is forbidden; APP_VERSION is mandatory.

    The gate is the image TAG itself: fail-closed `${APP_VERSION:?...}` must be
    present and there must be NO `${APP_VERSION:-latest}` default fallback (a
    `:latest` mention inside the `:?...` error message is prose, not a tag).
    """
    text = STAGING.read_text(encoding="utf-8")
    assert "${APP_VERSION:?" in text, "staging must require APP_VERSION (fail-closed)"
    # APP_VERSION pinning applies to OUR image (app_staging). db/redis are
    # pinned third-party base images (postgres:16-alpine / redis:7-alpine).
    app_image = _staging()["services"]["app_staging"]["image"]
    assert "${APP_VERSION:?" in app_image, "app_staging image must fail closed via APP_VERSION:?"
    assert "${APP_VERSION:-" not in app_image, "app_staging image must not default to :latest"


def test_staging_network_and_volumes_are_isolated():
    data = _staging()
    services = data["services"]
    for name, svc in services.items():
        nets = svc.get("networks") or []
        assert "staging_net" in nets, f"{name} not on isolated staging_net"
        for vol in svc.get("volumes") or []:
            assert str(vol).startswith("pgdata_staging"), f"{name} volume not isolated: {vol!r}"
    # Staging may not share the production network or volume set.
    assert set(data.get("networks") or {}) == {"staging_net"}
    assert "leadgen_net" not in (data.get("networks") or {})
    assert "pgdata" not in (data.get("volumes") or {})


def test_staging_absent_from_prod_service_set():
    """Staging is a separate compose file — no overlap with the prod service set."""
    staging_names = set(_staging()["services"])
    prod_names = set(_vps()["services"])
    assert not (staging_names & prod_names), staging_names & prod_names
    # Container names must not collide either (prod: leadgen_app etc.).
    staging_containers = {svc["container_name"] for svc in _staging()["services"].values()}
    prod_containers = {svc.get("container_name") for svc in _vps()["services"].values()}
    assert not (staging_containers & prod_containers)


def test_staging_resource_containment_controls_present():
    """Memory-containment keys from the capacity report — additive & reversible."""
    services = _staging()["services"]

    app = services["app_staging"]
    assert app.get("mem_limit") == "3g"
    assert app.get("mem_reservation") == "1g"
    assert app.get("pids_limit") == 512
    assert int(str(app.get("oom_score_adj"))) > 0  # app dies first at host OOM

    db = services["db_staging"]
    assert db.get("mem_limit") == "2g"
    assert int(str(db.get("oom_score_adj"))) < 0  # data integrity protected

    redis = services["redis_staging"]
    assert redis.get("mem_limit") == "512m"
    assert int(str(redis.get("oom_score_adj"))) < 0  # broker protected


def test_staging_has_no_heavy_worker_marker():
    """incidents.md rule (2026-07-16): CELERY_HEAVY_WORKER is exclusive to
    worker-heavy. Staging has no worker-heavy, so no staging service may carry
    the marker or it would imply a duplicate warm-up path."""
    for name, svc in _staging()["services"].items():
        env = svc.get("environment") or {}
        assert env.get("CELERY_HEAVY_WORKER") != "1", f"{name} must not run heavy warm-up"


def test_staging_automation_is_disabled():
    """Staging must never fire real emails/scrapes or the in-process scheduler."""
    app = _staging()["services"]["app_staging"]
    env = app.get("environment") or {}
    assert env.get("RUN_IN_PROCESS_SCHEDULER") == "0"
    assert env.get("AUTO_EMAIL_OUTREACH") == "false"
    assert env.get("APP_ENV") == "staging"
