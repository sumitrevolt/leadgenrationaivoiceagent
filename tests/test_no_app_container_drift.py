"""Ratchet: no script may roll `app` as a compose service again.

TOPOLOGY — ⚠️ CORRECTED 2026-09-20 against the live host, which outranks the
2026-09-15 owner note this file was written with. That note said the systemd unit
`leadgen` is the authoritative server for 127.0.0.1:8000 and that no
`leadgen_app` container exists. Neither is true now (read-only probe,
2026-09-20T12:23Z):

    systemctl is-active leadgen   -> active, but `activating (auto-restart)`
    systemctl show leadgen -p NRestarts -> NRestarts=5583, ExecMainStatus=203
    ls /opt/leadgen/.venv/bin/python    -> No such file or directory
    ss -ltnp | grep :8000               -> docker-proxy (NOT uvicorn on the host)
    docker ps               -> leadgen_app  ...:c691c8d1  Up (healthy)
                               127.0.0.1:8000->8080/tcp

So the unit cannot exec at all (203/EXEC = its interpreter is missing) and the
CONTAINER holds the port. `app` remains absent from deploy_vps.sh's SERVICES list,
which is an OWNER decision still on hold (see memory/incidents.md
"Partial deploy — alembic gate false-failed", ADR-194). This ratchet is
therefore still enforcing a decision whose premise has changed: it stops ad-hoc
scripts from rolling `app` while the canonical rollout path for the web tier is
unresolved. Do not "fix" this by deleting the ratchet — fix the topology.

WHY THE RULE STILL HOLDS: two processes cannot bind 127.0.0.1:8000. Whatever
holds it is what `/health` answers from. A script that recreates the `app`
service while something else owns the port produces a recreate failure next to a
200 response — a FALSE SUCCESS: the script reports a successful deploy/reload
when nothing moved. Thirty-four files did exactly this. Four of them
(`chaos_test.sh`, `vps_flywheel_deploy.sh`, `vps_deploy_fable.sh`,
`vps_deploy_selfimprove.sh`) ran without `set -e`, so the failure was completely
silent; two more (`set_kv.sh`, `infra_activate.sh`) failed loudly but the
operator still believed the flag they had just written into `.env` was live.
That false-live pattern is what produced the DND fail-open false alarm, so this
class is worth pinning.

This test needs no docker and no systemd: it parses the scripts and asserts the
`app` token never appears in an `up -d` service list. It is a ratchet -- it will
fail the moment someone reintroduces the pattern.

Deliberately NOT flagged:
  * `scripts/legacy/**` -- archived history; those files exist to record the old
    world, and rewriting them would destroy the record.
  * the RETIRED stubs and `vps_build_deploy.py` -- their comments/docstring
    quote the old command on purpose. Their behaviour is asserted separately.
  * `docker compose ... build app` -- wasteful under this topology (it builds an
    image nothing serves) but not a correctness bug, so it is out of scope here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
COMPOSE = REPO / "docker-compose.vps.yml"

# Files whose mention of `up -d ... app` is an intentional historical record.
ALLOWLIST = {
    "deploy_now.sh",  # RETIRED stub -- comment explains what it used to do
    "vps_app_container_swap.sh",  # RETIRED stub -- same
    "vps_build_deploy.py",  # docstring documents the pre-2026-09-15 chain
}

# Archived history is out of scope by design.
EXCLUDE_PREFIXES = ("legacy/",)

SCANNED_SUFFIXES = {".sh", ".py", ".bat"}

# Compose service names that actually exist in docker-compose.vps.yml.
SERVICE_SET = {"app", "worker", "scheduler", "worker-heavy", "worker-video"}

# Same token class the migration used: a service token can be glued to a closing
# quote/comma (e.g. `... app worker scheduler"`), and if those delimiters ride
# along the run stops one token early.
_TOKEN_RE = re.compile(r"""[^\s"'`,)\]};&|<>]+""")


def _app_in_up_d_service_run(line: str) -> bool:
    """True iff this line runs `up -d` with `app` in the service list."""
    toks = [(m.start(), m.end(), m.group()) for m in _TOKEN_RE.finditer(line)]
    for i in range(len(toks) - 1):
        if toks[i][2] != "up" or not toks[i + 1][2].startswith("-d"):
            continue
        j = i + 2
        while j < len(toks) and toks[j][2].startswith("-"):
            j += 1
        while j < len(toks) and toks[j][2] in SERVICE_SET:
            if toks[j][2] == "app":
                return True
            j += 1
    return False


def _scanned_files() -> list[Path]:
    out = []
    for p in sorted(SCRIPTS.rglob("*")):
        if not p.is_file() or p.suffix not in SCANNED_SUFFIXES:
            continue
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(SCRIPTS).as_posix()
        if rel.startswith(EXCLUDE_PREFIXES) or rel in ALLOWLIST:
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------- #
# the ratchet
# --------------------------------------------------------------------------- #


def test_no_script_rolls_app_as_a_compose_service():
    offenders: list[str] = []
    for p in _scanned_files():
        for n, line in enumerate(
            p.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if _app_in_up_d_service_run(line):
                offenders.append(f"{p.relative_to(REPO).as_posix()}:{n}: {line.strip()}")

    assert not offenders, (
        "`app` must not be rolled by an ad-hoc script: only one process can hold "
        "127.0.0.1:8000, so a script that recreates it beside the current holder "
        "gets a recreate failure AND a 200 from /health (false success). The "
        "canonical release path is `bash scripts/deploy_vps.sh`; whether the web "
        "tier should roll as a container or as the systemd unit is an OPEN OWNER "
        "DECISION (the unit currently crash-loops at 203/EXEC — see this file's "
        "docstring), and no script may pre-empt it.\n\nOffending lines:\n"
        + "\n".join(offenders)
    )


def test_allowlisted_files_still_exist():
    """Keep the allowlist from rotting into a silent bypass after a rename."""
    for rel in ALLOWLIST:
        assert (SCRIPTS / rel).exists(), (
            f"allowlisted file scripts/{rel} no longer exists -- remove it from "
            "ALLOWLIST so the exclusion does not hide a future offender"
        )


# --------------------------------------------------------------------------- #
# anti-vacuity: prove the detector actually detects
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "line",
    [
        "docker compose -f docker-compose.vps.yml up -d --no-deps app",
        "  docker compose -f \"$COMPOSE_FILE\" up -d app >/dev/null 2>&1",
        '$CF up -d app worker worker-heavy scheduler 2>&1 | tail -25',
        'docker compose -f docker-compose.vps.yml up -d --no-deps --force-recreate app worker scheduler',
        'echo "  docker compose -f docker-compose.vps.yml up -d --no-deps app worker scheduler"',
        '                "cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker worker-heavy",',
        "#     && docker compose -f docker-compose.vps.yml up -d --no-deps app",
        '# Usage (VPS pe, /opt/leadgen se, `up -d --no-deps app` se PEHLE):',
    ],
)
def test_detector_flags_the_patterns_that_were_found_in_the_wild(line):
    assert _app_in_up_d_service_run(line) is True, line


@pytest.mark.parametrize(
    "line",
    [
        # the fixed form
        "docker compose -f docker-compose.vps.yml up -d --no-deps worker scheduler && systemctl restart leadgen",
        "systemctl restart leadgen",
        "  systemctl restart leadgen >/dev/null 2>&1",
        # `build app` is out of scope, not a service list
        '"%SSH%" %HOST% "cd /opt/leadgen && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps worker && systemctl restart leadgen"',
        # a different service whose name merely CONTAINS app
        "docker compose -f docker-compose.vps.yml up -d --no-deps app-proxy worker",
        # app mentioned without any up -d
        "docker exec leadgen_app python -c 'print(1)'",
        # up -d for something else entirely
        "docker compose -f docker-compose.vps.yml up -d --no-deps worker-heavy",
    ],
)
def test_detector_does_not_flag_lookalikes(line):
    assert _app_in_up_d_service_run(line) is False, line


# --------------------------------------------------------------------------- #
# the retired stubs must actually refuse
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "rel",
    ["vps_app_container_swap.sh", "deploy_now.sh", "refresh_typesafe_env.sh"],
)
def test_retired_stubs_refuse_to_run(rel):
    p = SCRIPTS / rel
    text = p.read_text(encoding="utf-8")

    assert "RETIRED" in text

    # The comment block AND the refusal message legitimately name the old
    # dangerous commands -- that is the record, and the operator needs to read
    # it. What matters is that no line still INVOKES them, so match only at
    # command position.
    code = "\n".join(
        ln
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
    assert not re.search(r"^\s*systemctl\s+stop\s+leadgen\b", code, re.M), (
        f"{rel} must not stop the authoritative unit any more"
    )
    assert not re.search(r"^\s*systemctl\s+disable\s+leadgen\b", code, re.M), (
        f"{rel} must not disable the authoritative unit -- that breaks every "
        "later deploy, which now rolls the app with `systemctl restart leadgen`"
    )
    assert not re.search(
        r"^\s*(?:docker[\s-]compose|\$COMPOSE|\$CF)[^\n]*\bup\s+-d\b", code, re.M
    ), f"{rel} must not roll any compose service any more"
    assert re.search(r"^\s*exit\s+1\s*$", code, re.M), f"{rel} must exit non-zero"

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    r = subprocess.run(
        [bash, str(p)], capture_output=True, text=True, timeout=60, cwd=str(REPO)
    )
    assert r.returncode != 0, f"{rel} must exit non-zero"
    combined = (r.stdout or "") + (r.stderr or "")
    assert "RETIRED" in combined, combined
    assert "deploy_vps.sh" in combined, "the refusal must point at the canonical path"


# --------------------------------------------------------------------------- #
# document WHY the ratchet exists, so it cannot be silently mooted
# --------------------------------------------------------------------------- #


def test_compose_app_service_still_publishes_the_port_systemd_owns():
    """If this ever fails, revisit the ratchet -- its premise changed.

    The whole reason `up -d app` is a guaranteed false success is that compose
    maps `app` onto 127.0.0.1:8000 — the port something else already holds. On
    2026-09-15 that was the systemd unit; the 2026-09-20 probe says it is the
    running `leadgen_app` container itself. Either way the collision, and so
    this ratchet, stands. Only the fix changes with it, which is why the
    topology is an explicit owner decision rather than an assumption baked into
    a comment.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"^  app:\s*$", text, re.M), "compose no longer declares `app`"
    assert "127.0.0.1:8000:8080" in text, (
        "compose no longer publishes :8000 for `app` -- the false-success "
        "mechanism documented in this file has changed; re-derive the ratchet"
    )
