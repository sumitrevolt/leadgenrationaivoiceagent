"""Deploy-surface contract for the HyperFrames video worker.

Two things are easy to break silently here and expensive to discover in prod:
the render toolchain leaking into the web/scheduler images, and the three nested
render timeouts drifting out of order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO = Path(__file__).resolve().parents[1]
_BASE = _REPO / "docker-compose.vps.yml"
_OVERLAY = _REPO / "deploy" / "compose" / "docker-compose.video.yml"
_DOCKERFILE = _REPO / "Dockerfile.video"

# Every service that shares the ONE application image and is checked for tag
# skew by scripts/deploy_vps.sh.
_APP_IMAGE_SERVICES = ("app", "worker", "scheduler", "worker-heavy", "worker-video")


def _load(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_overlay_and_dockerfile_exist():
    assert _OVERLAY.is_file()
    assert _DOCKERFILE.is_file()


def test_overlay_touches_only_worker_video():
    """The browser toolchain must not grow the web/scheduler/general-worker images."""
    overlay = _load(_OVERLAY)
    assert set(overlay["services"]) == {"worker-video"}


def test_base_compose_is_unchanged_for_app_services():
    """Every runtime role resolves to one canonical app image."""
    base = _load(_BASE)
    images = set()
    for svc in _APP_IMAGE_SERVICES:
        image = base["services"][svc]["image"]
        assert "-video:" not in image, f"{svc} must not use the video image by default"
        assert "APP_IMAGE_REPOSITORY" in image
        assert "APP_VERSION:?" in image
        images.add(image)
    assert len(images) == 1
    assert base["services"]["app"]["build"]["dockerfile"] == "Dockerfile.lock"
    for svc in set(_APP_IMAGE_SERVICES) - {"app"}:
        assert "build" not in base["services"][svc], f"{svc} must reuse app's one build"


def test_overlay_image_tag_still_satisfies_deploy_skew_check():
    """deploy_vps.sh refuses any image whose tag is not :$APP_VERSION."""
    overlay = _load(_OVERLAY)
    image = overlay["services"]["worker-video"]["image"]
    assert image.endswith(":${APP_VERSION:?set APP_VERSION to the immutable git SHA}")
    args = overlay["services"]["worker-video"]["build"]["args"]
    assert args["APP_IMAGE"].endswith(
        ":${APP_VERSION:?set APP_VERSION to the immutable git SHA}"
    ), "video image must be built FROM the same-sha app image, not a floating tag"


def test_video_dockerfile_derives_from_app_image():
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG APP_IMAGE\n" in text
    assert "FROM ${APP_IMAGE}" in text
    assert "npm ci" in text, "must install the committed lockfile, not `npm install`"
    assert "browser ensure" in text, "Chrome must be fetched at BUILD time, not render time"


def test_video_dockerfile_disables_telemetry_and_runtime_downloads():
    text = _DOCKERFILE.read_text(encoding="utf-8")
    for flag in (
        "HYPERFRAMES_NO_TELEMETRY=1",
        "HYPERFRAMES_NO_UPDATE_CHECK=1",
        "HYPERFRAMES_NO_AUTO_INSTALL=1",
        "DO_NOT_TRACK=1",
    ):
        assert flag in text


def test_renderer_root_is_outside_the_app_bind_mount():
    """compose bind-mounts ./data and code over /app; the renderer must survive."""
    overlay = _load(_OVERLAY)
    env = overlay["services"]["worker-video"]["environment"]
    assert env["CREATIVE_HYPERFRAMES_ROOT"].startswith("/opt/")


def test_lockfile_is_committed_and_pins_exact_version():
    lock = _REPO / "video_renderer" / "hyperframes" / "package-lock.json"
    assert lock.is_file(), "package-lock.json must be committed for reproducible builds"
    pkg = _REPO / "video_renderer" / "hyperframes" / "package.json"
    import json

    deps = json.loads(pkg.read_text(encoding="utf-8"))["dependencies"]
    for name, ver in deps.items():
        assert ver[0].isdigit(), f"{name} must be pinned exactly, got {ver!r}"


# ------------------------------------------------------------- timeout order
def test_nested_render_timeouts_decrease_inward(monkeypatch):
    """subprocess < creative-OS worker deadline < Celery soft limit.

    If this inverts, the outer killer fires first and the provider never reaps
    its Chrome grandchildren.
    """
    from app.marketing.creative_os import flags
    from app.marketing.creative_os import hyperframes_provider as hp
    from app.tasks.video_jobs import _render_soft_limit

    monkeypatch.setenv("CREATIVE_WORKER_TIMEOUT_S", "900")
    monkeypatch.setenv("CREATIVE_HYPERFRAMES_TIMEOUT_S", "900")

    subprocess_deadline = hp.render_timeout_s()
    worker_deadline = flags.worker_timeout_s()
    celery_deadline = _render_soft_limit()

    assert subprocess_deadline < worker_deadline < celery_deadline, (
        f"{subprocess_deadline} < {worker_deadline} < {celery_deadline}"
    )


def test_render_timeout_is_clamped_even_when_misconfigured(monkeypatch):
    """A too-large subprocess timeout must be clamped, not trusted."""
    from app.marketing.creative_os import hyperframes_provider as hp

    monkeypatch.setenv("CREATIVE_WORKER_TIMEOUT_S", "300")
    monkeypatch.setenv("CREATIVE_HYPERFRAMES_TIMEOUT_S", "1800")
    assert hp.render_timeout_s() < 300


def test_celery_soft_limit_exceeds_a_real_fullhd_render():
    """A measured 1080x1920 render took ~116s; 300s left no margin."""
    from app.tasks.video_jobs import _render_soft_limit

    assert _render_soft_limit() >= 600
