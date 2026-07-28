"""`prod_check.py --deployment` — the canonical deployment preflight.

Two modes, one checker:

    python scripts/prod_check.py               general repository readiness
    python scripts/prod_check.py --deployment  actual pre-deploy gate

The voice-kill ENV gate runs ONLY in deployment mode. Wiring it
unconditionally would make every local and CI readiness run red on an unset
variable; leaving it unwired would ship a gate that never executes. Neither is
acceptable, so the context is explicit and testable.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from scripts import prod_check

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "prod_check.py"


def _main(monkeypatch, argv, env_value):
    """Call the real main() with a controlled argv and ENV class."""
    if env_value is None:
        monkeypatch.delenv("VOICE_LAUNCH_KILL", raising=False)
    else:
        monkeypatch.setenv("VOICE_LAUNCH_KILL", env_value)
    monkeypatch.setattr(prod_check, "PROBLEMS", [], raising=False)
    monkeypatch.setattr(prod_check, "WARNINGS", [], raising=False)
    calls: list = []
    real = prod_check.check_voice_launch_kill_env

    def spy():
        calls.append(1)
        return real()

    monkeypatch.setattr(prod_check, "check_voice_launch_kill_env", spy)
    # Only the voice-kill wiring is under test; the heavy repo checks are not.
    for name in (
        "check_sources_parse",
        "check_stale_pycache",
        "check_app_imports",
        "check_routes",
        "check_production_config",
        "check_frontend_wiring",
        "check_explorer_drift",
        "check_api_docs_drift",
        "check_dev_control_invariants",
    ):
        monkeypatch.setattr(prod_check, name, lambda: None, raising=False)
    rc = prod_check.main(argv)
    vk = [p for p in prod_check.PROBLEMS if "voice_launch_kill_env" in p]
    return rc, len(calls), vk


def test_general_mode_does_not_run_the_deployment_gate(monkeypatch):
    rc, calls, vk = _main(monkeypatch, [], None)
    assert calls == 0, "deployment-only gate ran in general mode"
    assert vk == []
    assert rc == 0


def test_deployment_mode_true_token_passes(monkeypatch):
    rc, calls, vk = _main(monkeypatch, ["--deployment"], "true")
    assert calls == 1, "gate must run exactly once"
    assert vk == []
    assert rc == 0


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "ENV_NOT_CONFIGURED"),
        ("false", "ENV_EXPLICITLY_DISENGAGED"),
        ("maybe", "ENV_INVALID"),
    ],
)
def test_deployment_mode_blocks_unsafe_env(monkeypatch, value, reason):
    rc, calls, vk = _main(monkeypatch, ["--deployment"], value)
    assert calls == 1
    assert len(vk) == 1, vk
    assert reason in vk[0]
    assert rc != 0, "deployment preflight must fail closed"


def test_unknown_argument_is_rejected(monkeypatch):
    """An unrecognised flag must never silently degrade to general mode."""
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, ["--deploymnet"], None)  # typo on purpose
    assert exc.value.code != 0


@pytest.mark.parametrize("value", ["s3cr3t-token-value", "off"])
def test_cli_output_leaks_no_raw_token(monkeypatch, capsys, value):
    _main(monkeypatch, ["--deployment"], value)
    blob = capsys.readouterr().out + " ".join(prod_check.PROBLEMS)
    assert value not in blob
    assert "VOICE_LAUNCH_KILL=" not in blob
    assert "voice_launch_kill.json" not in blob


def test_real_cli_accepts_the_deployment_flag():
    """The published interface must exist on the actual script, not just main()."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=180,
    )
    assert "--deployment" in (r.stdout + r.stderr)


# --------------------------------------------- deploy_vps.sh ordering proof


def _deploy_lines():
    """Executable lines only — a commented mention must not count as a gate."""
    raw = (REPO / "scripts" / "deploy_vps.sh").read_text(encoding="utf-8").splitlines()
    return [
        (i + 1, ln) for i, ln in enumerate(raw) if ln.strip() and not ln.strip().startswith("#")
    ]


def _preflight_invocations():
    """Real invocations only — an `echo` that merely names the command is not a gate."""
    return [
        (n, ln)
        for n, ln in _deploy_lines()
        if "scripts/prod_check.py --deployment" in ln and not ln.strip().startswith("echo")
    ]


def test_deploy_invokes_the_canonical_preflight_exactly_once():
    hits = _preflight_invocations()
    assert len(hits) == 1, hits
    # Since 2026-07-28 the gate runs inside the CANDIDATE image rather than on
    # the host, because the host has never had fastapi/pydantic and the gate
    # could therefore only ever fail closed. The invocation is a container
    # runner, and `python` is the interpreter it hands the script to.
    assert "gate_run_image" in hits[0][1], hits[0][1]
    runner = (REPO / "scripts" / "_deploy_gate_container.sh").read_text(encoding="utf-8")
    assert "docker run --rm" in runner and "python " in runner


def test_preflight_precedes_every_destructive_operation():
    """The gate must precede everything that MUTATES production.

    `git fetch` (object database), the candidate worktree and the candidate
    image build are deliberately excluded: none of them moves the live checkout
    or replaces a container, and requiring the gate before them would mean
    gating code that has not been fetched yet — which is how the gate ended up
    unable to run at all.
    """
    lines = _deploy_lines()
    gate = _preflight_invocations()[0][0]
    mutators = [
        (n, ln)
        for n, ln in lines
        for pat in (
            "git pull",
            "git reset",
            "git clean",
            "docker compose up",
            "_compose_up",
            "docker push",
            "ssh ",
            "scp ",
            "rsync ",
        )
        if pat in ln
    ]
    assert mutators, "no mutating operations found — parser is wrong"
    first = min(n for n, _ in mutators)
    assert gate < first, f"preflight at {gate} runs after mutation at {first}"


def test_runtime_data_guard_precedes_the_deployment_gate_and_the_build():
    """Ordering the isolated-candidate flow depends on.

    The runtime-data guard is the FIRST decision: it is what stands between the
    release and the ledgers that still live inside the checkout. Building an
    image before it has spoken would be wasteful; pulling before it has spoken
    would be the incident this whole workstream exists to prevent.
    """
    lines = _deploy_lines()
    guard = next(
        n for n, ln in lines if "_runtime_data_guard.sh" in ln and ln.strip().startswith(".")
    )
    build = next(n for n, ln in lines if "BUILD candidate" in ln)
    gate = _preflight_invocations()[0][0]
    pull = next(
        n for n, ln in lines if "git pull --ff-only" in ln and not ln.strip().startswith("echo")
    )
    assert guard < build < gate < pull, (guard, build, gate, pull)
