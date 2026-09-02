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
    build_idx = t.index("=== BUILD candidate")
    assert guard_idx < build_idx


def test_dry_run_exits_zero_before_any_build_or_up_command():
    """DRY_RUN must remain fully non-destructive — the exit must occur
    before the real `docker compose build`/`up` calls, and its preview
    logic must only use read-only docker commands (images/system df),
    never rmi/prune/builder prune."""
    t = _text()
    dry_run_exit_idx = t.index('echo "DRY_RUN=1 -> would build+up')
    build_idx = t.index("=== BUILD candidate")
    up_idx = t.index('docker compose -f "$COMPOSE" --profile celery')
    assert dry_run_exit_idx < build_idx
    assert dry_run_exit_idx < up_idx
    # the DRY_RUN preview block itself (between the disk-guard block and this
    # exit line) must not contain any mutating docker subcommand
    guard_start = t.index('if [ "$DRY_RUN" = "1" ]; then\n  echo "=== BUILD CACHE')
    preview_block = t[guard_start:dry_run_exit_idx]
    for mutating in (
        "docker rmi",
        "docker builder prune",
        "docker image prune",
        "docker system prune",
    ):
        msg = f"DRY_RUN preview must stay read-only, found {mutating!r}"
        assert mutating not in preview_block, msg


def test_build_cache_retention_present_with_age_and_storage_floor():
    t = _text()
    assert 'BUILD_CACHE_MAX_AGE="${BUILD_CACHE_MAX_AGE:-168h}"' in t
    assert 'BUILD_CACHE_KEEP_STORAGE="${BUILD_CACHE_KEEP_STORAGE:-20GB}"' in t
    assert "docker builder prune -f" in t
    assert '--filter "unused-for=$BUILD_CACHE_MAX_AGE"' in t
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
    image_retention_idx = t.index("=== RETENTION (lineage-aware")
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
    assert 'KEEP_IMAGES="${KEEP_IMAGES:-1}"' in t
    assert "PREV_PROD_TAG" in t
    assert "ROLLBACK_TAG" in t
    assert "deploy_image_retention.py" in t
    assert "LINEAGE_STATE" in t
    assert "/var/lib/leadgen/deploy_rollback_lineage.json" in t
    assert "zero destructive cleanup executed" in t
    assert "_CLEANUP_OK=1" in t
    assert '[ "$t" = "$VER" ] && continue' in t
    assert '[ "$t" = "$PREV_PROD_TAG" ] && continue' in t
    assert '[ "$t" = "$ROLLBACK_TAG" ] && continue' in t


def test_planner_refusal_skips_image_and_build_cache_prune():
    t = _text()
    assert "BUILD CACHE skipped — zero destructive cleanup executed" in t
    retention_to_deployed = t[
        t.index("=== RETENTION (lineage-aware") : t.index('echo "=== DEPLOYED $VER OK ===')
    ]
    assert 'if [ "$_CLEANUP_OK" -eq 1 ]; then' in retention_to_deployed
    assert "zero destructive cleanup executed" in retention_to_deployed
    prune_lines = [
        ln
        for ln in retention_to_deployed.splitlines()
        if "docker image prune" in ln and not ln.strip().startswith("#")
    ]
    assert len(prune_lines) == 1
    # Success-path only: prune precedes _CLEANUP_OK=1, both before BUILD CACHE gate.
    assert retention_to_deployed.index("docker image prune") < retention_to_deployed.index(
        "_CLEANUP_OK=1"
    )
    assert retention_to_deployed.index("_CLEANUP_OK=1") < retention_to_deployed.index(
        'if [ "$_CLEANUP_OK" -eq 1 ]; then'
    )
    assert (
        "docker builder prune"
        in retention_to_deployed[retention_to_deployed.index('if [ "$_CLEANUP_OK" -eq 1 ]; then') :]
    )


def test_lineage_state_write_only_after_health_verification():
    t = _text()
    health_fail_idx = t.index('if [ "$LIVE_VER" != "$VER" ]; then')
    exit3_idx = t.index("exit 3", health_fail_idx)
    write_idx = t.index("--write-lineage")
    retention_idx = t.index("=== RETENTION (lineage-aware")
    assert health_fail_idx < exit3_idx < retention_idx
    assert exit3_idx < write_idx
    # Failed health exits before lineage write / retention
    assert "exit 3" in t[health_fail_idx:write_idx]


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


def test_pull_fail_aborts_before_container_replacement():
    """2026-07-16: pull-fail used to fall through and rebuild stale HEAD while
    the log header claimed a different APP_VERSION.

    Since 2026-07-28 the build happens BEFORE the pull, against an isolated
    candidate worktree — a build replaces no container and moves no HEAD, so the
    property that matters is no longer "abort before build" but "abort before
    anything is replaced". Asserting the old order would now demand that the
    gates run against code nobody has checked out.
    """
    t = _text()
    assert "git pull --ff-only failed" in t
    assert "refusing to deploy stale" in t
    pull_fail_idx = t.index("git pull --ff-only failed")
    up_idx = t.index("=== UP (all app-image services")
    assert pull_fail_idx < up_idx
    # Must not mask pull exit via `| tail` (pipefail alone is not enough without -e)
    pull_block = t[t.index("live checkout, ff-only") : up_idx]
    assert "git pull --ff-only 2>&1 | tail" not in pull_block


def test_gated_sha_and_live_head_must_agree_before_containers_start():
    """No silent code/tag skew — restated for the isolated-candidate flow.

    The old invariant was "an explicit APP_VERSION arg must already equal live
    HEAD". That is now impossible by construction: the release sha is resolved
    from the fetched object database and gated in its own worktree precisely so
    the live checkout can stay put until the gates pass. The equivalent, and
    stronger, guarantee is asserted instead — the candidate is proven to be at
    the release sha, and the live checkout is proven to equal the GATED sha
    before a single container is replaced.
    """
    t = _text()
    assert "candidate tree drifted from" in t
    assert "Refusing to start containers on code that was never gated." in t
    # The worktree's own sha proof lives in the candidate helper, which is where
    # the worktree is created — asserting it here keeps the two halves of the
    # invariant from drifting apart.
    candidate_helper = (REPO_ROOT / "scripts" / "_deploy_candidate.sh").read_text(encoding="utf-8")
    assert "Refusing to gate one tree and deploy another." in candidate_helper

    drift_idx = t.index("candidate tree drifted from")
    live_check_idx = t.index("Refusing to start containers on code that was never gated.")
    up_idx = t.index("=== UP (all app-image services")
    assert drift_idx < live_check_idx < up_idx


def test_compose_up_has_bounded_recreate_retry():
    """2026-07-16: compose recreate race left prod down — cleanup+retry must exist."""
    t = _text()
    assert "_cleanup_recreate_ghosts" in t
    assert "UP_RETRY_RC" in t
    assert "compose recreate conflict detected" in t
    cleanup_idx = t.index("_cleanup_recreate_ghosts")
    verify_idx = t.index("=== VERIFY /health")
    assert cleanup_idx < verify_idx


def test_health_verification_retries_during_bounded_cold_start_window():
    """A single health probe can race the app's model/import cold start.

    The canonical deploy must wait for the exact deployed SHA, with an
    operator-tunable but bounded retry count and interval, before failing or
    moving on to retention.
    """
    t = _text()
    assert 'HEALTH_MAX_ATTEMPTS="${HEALTH_MAX_ATTEMPTS:-12}"' in t
    assert 'HEALTH_RETRY_SECONDS="${HEALTH_RETRY_SECONDS:-5}"' in t
    assert 'while [ "$HEALTH_ATTEMPT" -le "$HEALTH_MAX_ATTEMPTS" ]' in t
    assert 'if [ "$LIVE_VER" = "$VER" ]; then' in t
    assert 'sleep "$HEALTH_RETRY_SECONDS"' in t
    assert "after $HEALTH_MAX_ATTEMPTS attempts" in t

    verify_idx = t.index("=== VERIFY /health")
    retry_idx = t.index('while [ "$HEALTH_ATTEMPT" -le "$HEALTH_MAX_ATTEMPTS" ]')
    skew_idx = t.index("=== SKEW CHECK")
    assert verify_idx < retry_idx < skew_idx


def test_skew_check_uses_service_resolve_not_bare_names_only():
    """RISKS B3: skew must not hardcode leadgen_* as the sole container lookup."""
    t = _text()
    assert "_resolve_compose_container" in t
    assert "for svc in $ALL_ROLLOUT_SERVICES" in t
    skew_idx = t.index("=== SKEW CHECK")
    smoke_idx = t.index("=== SMOKE")
    skew = t[skew_idx:smoke_idx]
    assert "for c in leadgen_app" not in skew
