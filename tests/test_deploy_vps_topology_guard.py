"""The live serving topology must be checked before deployment changes anything."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deploy_vps.sh"


def _guard() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("_systemd_app_active=0")
    end = source.index(
        "# ---------------------------------------------------- runtime-data guard", start
    )
    assert end < source.index("candidate_add")
    return source[start:end]


def _run_guard(
    *,
    systemd_active: bool,
    docker_running: bool,
    rollback_compatible: bool = False,
) -> subprocess.CompletedProcess:
    st = 0 if systemd_active else 3
    value = "true" if docker_running else "false"
    fake = f"systemctl() {{ return {st}; }}\ndocker() {{ echo {value}; }}\n"
    bash = "bash"
    if os.name == "nt":
        git_bash = (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
        )
        if git_bash.is_file():
            bash = str(git_bash)
    env = dict(os.environ)
    if rollback_compatible:
        env["ROLLBACK_DB_COMPATIBLE"] = "1"
    else:
        env.pop("ROLLBACK_DB_COMPATIBLE", None)
    return subprocess.run(
        [bash, "-c", fake + _guard() + "\necho RELEASE_CONTINUES"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_docker_serving_host_selects_compose_cohort_when_rollback_is_acknowledged():
    result = _run_guard(
        systemd_active=False,
        docker_running=True,
        rollback_compatible=True,
    )
    assert result.returncode == 0
    assert "WEB_TOPOLOGY=compose" in result.stdout
    assert "RELEASE_CONTINUES" in result.stdout


def test_docker_serving_host_refuses_without_rollback_acknowledgement():
    result = _run_guard(systemd_active=False, docker_running=True)
    assert result.returncode == 11
    assert "ROLLBACK_DB_COMPATIBLE=1" in result.stdout
    assert "RELEASE_CONTINUES" not in result.stdout


def test_ambiguous_dual_and_absent_topologies_refuse():
    for systemd, docker in ((True, True), (False, False)):
        result = _run_guard(systemd_active=systemd, docker_running=docker)
        assert result.returncode == 10
        assert "ambiguous or absent web-serving topology" in result.stdout
        assert "RELEASE_CONTINUES" not in result.stdout


def test_existing_systemd_serving_path_can_continue():
    result = _run_guard(systemd_active=True, docker_running=False)
    assert result.returncode == 0
    assert "WEB_TOPOLOGY=systemd" in result.stdout
    assert "RELEASE_CONTINUES" in result.stdout
