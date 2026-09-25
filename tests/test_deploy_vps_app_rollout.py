"""Contract tests: deploy_vps.sh rolls the app via systemd, not compose.

Context (2026-09-15, owner decision: systemd is the authoritative serving path).
Production serves :8000 from the systemd unit `leadgen`
(EnvironmentFile=/opt/leadgen/.env, host uvicorn), NOT from a container. Three
consequences this file pins:

  1. `app` must NOT be in SERVICES / ALL_ROLLOUT_SERVICES. No `leadgen_app`
     container can exist while that unit holds the port (docker-compose.vps.yml
     still declares `127.0.0.1:8000:8080` for `app`, which can never bind), and
     leaving `app` in the list made the skew check fail closed on a service that
     cannot run.
  2. `.env:APP_VERSION` must be WRITTEN, not merely validated, after the live
     checkout moves. The .ENV GUARD only validated it, so every release left prod
     reporting the PREVIOUS version and the /health verify exited 3.
  3. The unit must be RESTARTED after the live checkout moves and before the
     /health verify. EnvironmentFile is a snapshot taken at process start and
     app/main.py never re-reads .env, so new code on disk is not live otherwise.

Also pins the resolver hardening. `docker compose ps -q app` is EMPTY -- `app` is
a declared-but-absent service, because the systemd unit holds :8000 -- so the
resolver falls through to its `label=com.docker.compose.service=<svc>` fallback.
Two ORPHAN containers, `leadgen_app_vobiz` (:8b7fd7c3) and `leadgen_app_staging`
(:28ba5d4e), genuinely carry that label: they were created by overlay/duplicate
deploys, not by this compose file. Proven on prod 2026-09-15: `app` resolved to
`leadgen_app_vobiz` (:8b7fd7c3), which poisoned the pre-deploy lineage capture and
forced `exit 4` on an otherwise-fine release. The resolver now reads the label
back and requires exact equality, and prefers an id whose image tag is `:$VER`.

  NOTE -- a correction, kept deliberately. An earlier revision of this docstring
  claimed Docker's `label=k=v` filter matches the value as a SUBSTRING, so
  `service=app` would also return `app_vobiz`. That is FALSE, and it was probed
  on prod: `docker ps -aq --filter "label=com.docker.compose.service=pp"` returns
  EMPTY. Had matching been substring-based, `pp` would have matched `app`. The
  filter is exact; the orphans carry the label for real. The exact-equality
  change is therefore DEFENSIVE hardening, not the fix for the `exit 4` bug --
  the fix for that is `app` no longer being in SERVICES at all.

Static text assertions (no docker / systemd required), same pattern as
test_deploy_vps_skew_resolution.py.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "deploy_vps.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _resolver_body() -> str:
    t = _text()
    start = t.index("_resolve_compose_container() {")
    end = t.index("\n}\n", start)
    return t[start:end]


# ---------------------------------------------------------------- app rollout


def test_app_is_not_in_the_compose_rollout_surface():
    t = _text()
    assert 'SERVICES="worker scheduler worker-heavy worker-video"' in t
    assert 'SERVICES="app ' not in t
    # dsh worker still deploys in lockstep
    assert 'DSH_SERVICES="dsh-worker"' in t
    assert 'ALL_ROLLOUT_SERVICES="$SERVICES $DSH_SERVICES"' in t


def test_env_app_version_is_written_in_place_not_appended():
    t = _text()
    assert 'sed -i "s/^APP_VERSION=.*/APP_VERSION=$VER/" "$REPO/.env"' in t
    # the old guard hint appended a SECOND key (EnvironmentFile is last-wins, so
    # it would appear to work while silently polluting .env)
    assert "echo 'APP_VERSION=$VER' >> .env" not in t


def test_app_version_is_written_after_the_live_checkout_moves():
    t = _text()
    pull = t.index("git pull --ff-only")
    write = t.index('sed -i "s/^APP_VERSION=.*/APP_VERSION=$VER/" "$REPO/.env"')
    assert pull < write, "APP_VERSION must be written after the gated pull"


def test_unit_is_restarted_after_pull_and_before_health_verify():
    t = _text()
    pull = t.index("git pull --ff-only")
    # Match the EXECUTABLE form. The phrase also appears in prose comments and in
    # the echo banner, both of which sit BEFORE the pull and would false-pass.
    m = re.search(r"if ! systemctl restart leadgen; then", t)
    assert m, "deploy_vps.sh must restart the systemd unit"
    health = t.index("curl -s -m 10 127.0.0.1:8000/health")
    assert pull < m.start() < health, (
        "systemctl restart leadgen must sit between the live pull and the "
        "/health verify, else /health reads a frozen APP_VERSION and exits 3"
    )


def test_restart_is_guarded_on_the_unit_existing():
    t = _text()
    assert "if systemctl cat leadgen >/dev/null 2>&1;" in t
    assert "no systemd unit 'leadgen' — app is container-managed" in t


def test_write_is_verified_before_restarting():
    t = _text()
    # a sed that silently matched nothing must not be followed by a restart
    write = t.index('sed -i "s/^APP_VERSION=.*/APP_VERSION=$VER/" "$REPO/.env"')
    verify = t.index('ENV_VER_NOW="$(grep -E')
    restart = re.search(r"if ! systemctl restart leadgen; then", t).start()
    assert '[ "$ENV_VER_NOW" != "$VER" ]' in t
    assert write < verify < restart


def test_rollout_failure_uses_a_distinct_exit_code():
    t = _text()
    # 10 must not collide with the pre-existing refusal exits (1-9, 91, 92)
    codes = sorted({int(m) for m in re.findall(r"^\s*exit (\d+)\s*$", t, re.MULTILINE)})
    assert codes == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 91, 92], codes
    assert len(re.findall(r"^\s*exit 10\s*$", t, re.MULTILINE)) == 4


# ------------------------------------------------------------------- resolver


def test_resolver_requires_exact_label_equality():
    body = _resolver_body()
    # Docker's label filter is substring-based; the label must be read back and
    # compared, or `app` silently resolves to app_vobiz / app_staging.
    assert "com.docker.compose.service" in body
    assert "index .Config.Labels" in body
    assert '[ "$_lbl" = "$svc" ] || continue' in body


def test_resolver_prefers_an_exact_match_already_on_ver():
    body = _resolver_body()
    assert "_exact_ver" in body
    assert '*:"$VER") _exact_ver="$id"' in body
    assert 'if [ -n "$_exact_ver" ]; then' in body
    assert 'if [ -n "$_exact" ]; then' in body


def test_resolver_still_keeps_legacy_fallback_after_labels():
    body = _resolver_body()
    assert "_legacy_name_for_service" in body
    # compose ps first, then labels, then the legacy bare-name fallback
    assert body.index("docker compose -f") < body.index("_legacy_name_for_service")
    assert body.index("index .Config.Labels") < body.index("_legacy_name_for_service")


# ------------------------------------------------- cross-file drift guard


def _load_retention():
    path = REPO_ROOT / "scripts" / "deploy_image_retention.py"
    name = "deploy_image_retention_for_drift_check"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_shell_services_match_the_retention_planner_expected_set():
    """The two service sets MUST agree, or every release dies with rc=2.

    deploy_vps.sh builds RUNNING_JSON by looping `for _svc in $SERVICES` and then
    calls `deploy_image_retention.py --assert-running-only --running-json`. That
    planner validates against its own hardcoded EXPECTED_SERVICES and raises
    "incomplete service mapping: missing=[...] extra=[...]" on any difference —
    aborting the deploy at `exit 2` AFTER the live checkout has already moved.

    This exact drift happened on 2026-09-15 when `app` was removed from $SERVICES
    but not from EXPECTED_SERVICES. This test makes that impossible to repeat.
    """
    t = _text()
    m = re.search(r'^SERVICES="([^"]+)"', t, re.MULTILINE)
    assert m, "SERVICES assignment not found in deploy_vps.sh"
    shell_services = set(m.group(1).split())

    planner = set(_load_retention().EXPECTED_SERVICES)

    assert shell_services == planner, (
        f"drift: deploy_vps.sh SERVICES={sorted(shell_services)} but "
        f"deploy_image_retention.EXPECTED_SERVICES={sorted(planner)}. "
        "The pre-deploy lineage capture passes exactly $SERVICES, so any "
        "difference makes EVERY release exit 2."
    )
