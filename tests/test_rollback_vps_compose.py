"""Behavioral contract for the Docker-serving VPS rollback command."""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rollback_vps_compose.sh"


def _bash() -> str | None:
    for candidate in (
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
        shutil.which("bash"),
    ):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


BASH = _bash()
requires_bash = pytest.mark.skipif(BASH is None, reason="bash unavailable")


def _write(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _sandbox(
    tmp_path: Path, *, fail_target: bool = False, missing_image: bool = False
) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    repo.mkdir()
    bin_dir.mkdir()
    (repo / ".env").write_text("APP_VERSION=1111111\n", encoding="utf-8")
    (repo / "docker-compose.vps.yml").write_text("services: {}\n", encoding="utf-8")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")

    _write(bin_dir / "systemctl", "#!/usr/bin/env bash\nexit 3\n")
    _write(
        bin_dir / "docker",
        f"""\
        #!/usr/bin/env bash
        echo "docker $* APP_VERSION=${{APP_VERSION:-}}" >> {log.as_posix()!r}
        case "$*" in
          *"compose"*"ps -q"*) echo "cid-${{@:$#}}" ;;
          *".State.Running"*) echo true ;;
          *".Config.Image"*)
            last="${{!#}}"
            if [ "$last" = "leadgen_app" ]; then
              echo repo/app:1111111
            else
              tag="$(sed -n 's/^APP_VERSION=//p' "$REPO/.env")"
              echo repo/app:$tag
            fi
            ;;
          *"config --images"*) echo repo/app:${{APP_VERSION}} ;;
          "image inspect "*) exit {int(missing_image)} ;;
          *"up -d --no-deps"*)
            if [ "${{APP_VERSION}}" = "2222222" ] && [ "{int(fail_target)}" = "1" ]; then
              exit 1
            fi
            ;;
        esac
        exit 0
        """,
    )
    _write(
        bin_dir / "curl",
        f"""\
        #!/usr/bin/env bash
        tag="$(sed -n 's/^APP_VERSION=//p' {repo.as_posix()!r}/.env)"
        printf '{{"version":"%s"}}\n' "$tag"
        """,
    )
    _write(bin_dir / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    return repo, log


def _run(repo: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{(tmp_path / 'bin').as_posix()}:/usr/bin:/bin",
            "REPO": repo.as_posix(),
            "ROLLBACK_DB_COMPATIBLE": "1",
            "HEALTH_MAX_ATTEMPTS": "1",
        }
    )
    return subprocess.run(
        [str(BASH), str(SCRIPT), "2222222"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )


@requires_bash
def test_verified_rollback_pins_tag_and_rolls_full_cohort(tmp_path: Path) -> None:
    repo, log = _sandbox(tmp_path)
    result = _run(repo, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ROLLBACK VERIFIED" in result.stdout
    assert (repo / ".env").read_text(encoding="utf-8") == "APP_VERSION=2222222\n"
    calls = log.read_text(encoding="utf-8")
    assert "up -d --no-deps app worker scheduler worker-heavy worker-video dsh-worker" in calls


@requires_bash
def test_failed_target_recreates_and_verifies_previous_cohort(tmp_path: Path) -> None:
    repo, log = _sandbox(tmp_path, fail_target=True)
    result = _run(repo, tmp_path)
    assert result.returncode == 20, result.stdout + result.stderr
    assert "previous cohort restored" in result.stdout
    assert (repo / ".env").read_text(encoding="utf-8") == "APP_VERSION=1111111\n"
    calls = log.read_text(encoding="utf-8")
    assert "APP_VERSION=2222222" in calls
    assert "APP_VERSION=1111111" in calls


@requires_bash
def test_migration_compatibility_ack_is_required_before_mutation(tmp_path: Path) -> None:
    repo, log = _sandbox(tmp_path)
    env = dict(os.environ)
    env.update({"PATH": f"{(tmp_path / 'bin').as_posix()}:/usr/bin:/bin", "REPO": str(repo)})
    result = subprocess.run(
        [str(BASH), str(SCRIPT), "2222222"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    assert result.returncode == 11
    assert log.read_text(encoding="utf-8") == ""


@requires_bash
def test_missing_rollback_artifact_refuses_before_env_or_container_change(tmp_path: Path) -> None:
    repo, log = _sandbox(tmp_path, missing_image=True)
    result = _run(repo, tmp_path)
    assert result.returncode == 12
    assert "required rollback image is missing" in result.stdout
    assert (repo / ".env").read_text(encoding="utf-8") == "APP_VERSION=1111111\n"
    assert "up -d --no-deps" not in log.read_text(encoding="utf-8")
