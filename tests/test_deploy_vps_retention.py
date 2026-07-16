"""ADR-104 Phase C (2026-07-15) — scripts/deploy_vps.sh pre-build disk guard +
build-cache retention.

This is the canonical, high-blast-radius deploy script (CLAUDE.md ⁠"docker
commands haath se mat likho" — this script IS the deploy). No shell test
runner is assumed to be on PATH in every environment, so these tests are
pure text/structure assertions (same pattern this repo already uses for
docker-compose.*.yml in test_celery_queue_routing.py) rather than executing
the script — cheap, portable, and still catches the concrete regressions
that matter: guard missing, guard placed after the build already started,
DRY_RUN accidentally deleting something, or the two retention steps
colliding/duplicated.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "deploy_vps.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists_and_has_shebang():
    assert SCRIPT.exists()
    assert _text().splitlines()[0].startswith("#!/usr/bin/env bash")


def test_disk_guard_present_with_sane_default_thresholds():
    t = _text()
    assert 'DISK_WARN_PCT="${DISK_WARN_PCT:-80}"' in t
    assert 'DISK_HARD_PCT="${DISK_HARD_PCT:-90}"' in t
    # warn must be strictly below hard-stop, else the warn branch is dead code
    assert 80 < 90


def test_disk_guard_hard_stop_exits_nonzero_outside_dry_run():
    t = _text()
    assert "exit 5" in t
    guard_idx = t.index("DISK GUARD")
    exit5_idx = t.index("exit 5")
    dry_run_check_idx = t.index('if [ "$DRY_RUN" != "1" ]', guard_idx)
    assert guard_idx < dry_run_check_idx < exit5_idx


def test_disk_guard_runs_before_the_actual_build():
    """The whole point of a PRE-build guard is that it runs before `docker
    compose build` — a guard placed after the build started only reports a
    problem that already happened."""
    t = _text()
    guard_idx = t.index("=== DISK GUARD")
    build_idx = t.index("docker compose -f \"$COMPOSE\" build app")
    assert guard_idx < build_idx


def test_dry_run_exits_zero_before_any_build_or_up_command():
    """DRY_RUN must remain fully non-destructive — the exit must occur
    before the real `docker compose build`/`up` calls, and its preview
    logic must only use read-only docker commands (images/system df),
    never rmi/prune/builder prune."""
    t = _text()
    dry_run_exit_idx = t.index('echo "DRY_RUN=1 -> would build+up')
    build_idx = t.index('docker compose -f "$COMPOSE" build app')
    up_idx = t.index('docker compose -f "$COMPOSE" --profile celery')
    assert dry_run_exit_idx < build_idx
    assert dry_run_exit_idx < up_idx
    # the DRY_RUN preview block itself (between the disk-guard block and this
    # exit line) must not contain any mutating docker subcommand
    guard_start = t.index('if [ "$DRY_RUN" = "1" ]; then\n  echo "=== BUILD CACHE')
    preview_block = t[guard_start:dry_run_exit_idx]
    for mutating in ("docker rmi", "docker builder prune", "docker image prune", "docker system prune"):
        assert mutating not in preview_block, f"DRY_RUN preview must stay read-only, found {mutating!r}"


def test_build_cache_retention_present_with_age_and_storage_floor():
    t = _text()
    assert 'BUILD_CACHE_MAX_AGE="${BUILD_CACHE_MAX_AGE:-168h}"' in t
    assert 'BUILD_CACHE_KEEP_STORAGE="${BUILD_CACHE_KEEP_STORAGE:-20GB}"' in t
    assert "docker builder prune -f" in t
    assert "--filter \"unused-for=$BUILD_CACHE_MAX_AGE\"" in t
    # `--keep-storage` is deprecated on Docker 29.4.3 (verified live: silently
    # reclaimed 0B against a real 40GB-reclaimable cache) -- `--max-used-space`
    # is the confirmed working successor (docker builder prune --help). The
    # env VAR name stays BUILD_CACHE_KEEP_STORAGE (its value is just passed to
    # the new flag) -- only the actual command-line flag must never be the
    # deprecated one.
    assert '--max-used-space "$BUILD_CACHE_KEEP_STORAGE"' in t
    command_lines = [ln for ln in t.splitlines() if not ln.strip().startswith("#")]
    assert "--keep-storage" not in "\n".join(command_lines)


def test_build_cache_retention_runs_after_verified_deploy_not_before():
    """Must run after health/skew/smoke verification, same precedence as the
    existing image-tag retention — never as a pre-build step (that would
    risk evicting cache the CURRENT build still needs)."""
    t = _text()
    smoke_idx = t.index("=== SMOKE")
    image_retention_idx = t.index("=== RETENTION (keep newest")
    build_cache_idx = t.index("=== BUILD CACHE (before)")
    deployed_ok_idx = t.index('echo "=== DEPLOYED $VER OK ===')
    assert smoke_idx < image_retention_idx < build_cache_idx < deployed_ok_idx


def test_build_cache_prune_never_uses_bare_dash_a():
    """`docker builder prune -a` (or `docker system prune -a`) would nuke ALL
    cache regardless of age/size — that's the "unsafe broad deletion" this
    phase explicitly must avoid. Only the filtered, floor-bounded form is
    allowed."""
    t = _text()
    assert "docker builder prune -af" not in t
    assert "docker system prune -a" not in t
    assert "docker builder prune -f --filter" in t


def test_image_retention_never_removes_the_just_deployed_tag():
    t = _text()
    # both the real retention loop and the dry-run preview loop must guard this
    assert t.count('[ "$t" = "$VER" ] && continue') == 2


def test_retention_never_uses_rmi_force_flag():
    """`docker rmi -f` bypasses docker's own "still referenced" safety check
    — the existing retention comment explicitly calls this out as a rule
    (and that same comment's PROSE contains the substring "rmi -f", so this
    checks actual command invocations, not comment text, to avoid a false
    positive against the rule's own explanation)."""
    t = _text()
    command_lines = [ln for ln in t.splitlines() if not ln.strip().startswith("#")]
    joined = "\n".join(command_lines)
    assert "docker rmi -f" not in joined
    assert "docker rmi --force" not in joined


def test_pull_fail_aborts_before_build():
    """2026-07-16: pull-fail used to fall through and rebuild stale HEAD while
    the log header claimed a different APP_VERSION. Abort must precede build."""
    t = _text()
    assert "git pull --ff-only failed" in t
    assert "refusing to deploy stale" in t
    pull_fail_idx = t.index("git pull --ff-only failed")
    build_idx = t.index('docker compose -f "$COMPOSE" build app')
    assert pull_fail_idx < build_idx
    # Must not mask pull exit via `| tail` (pipefail alone is not enough without -e)
    resolve = t[t.index("resolve sha") : build_idx]
    assert "git pull --ff-only 2>&1 | tail" not in resolve


def test_sha_arg_must_match_repo_head():
    """Explicit APP_VERSION arg that does not match HEAD = abort (no silent skew)."""
    t = _text()
    assert "requested APP_VERSION=" in t
    assert "Refusing silent code/tag skew" in t
    assert 'REPO_SHA != APP_VERSION' in t or "REPO_SHA != APP_VERSION" in t


def test_compose_up_has_bounded_recreate_retry():
    """2026-07-16: compose recreate race left prod down — cleanup+retry must exist."""
    t = _text()
    assert "_cleanup_recreate_ghosts" in t
    assert "UP_RETRY_RC" in t
    assert "compose recreate conflict detected" in t
    cleanup_idx = t.index("_cleanup_recreate_ghosts")
    verify_idx = t.index("=== VERIFY /health")
    assert cleanup_idx < verify_idx
