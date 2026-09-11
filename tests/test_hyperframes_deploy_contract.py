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


def test_overlay_touches_only_render_plane_services():
    """The browser toolchain must not grow the web/scheduler/general-worker images.

    T07 (design §9.1 / §12 A3) moved the toolchain out of `worker-video` and into
    the netless `renderer`; the opt-in overlay therefore touches exactly the two
    render-plane services. It must never name app/worker/scheduler/worker-heavy —
    that is the invariant that keeps the heavy image off the general fleet.
    """
    overlay = _load(_OVERLAY)
    assert set(overlay["services"]) == {"worker-video", "renderer"}
    assert not ({"app", "worker", "scheduler", "worker-heavy"} & set(overlay["services"]))


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
    """deploy_vps.sh refuses any image whose tag is not :$APP_VERSION.

    The toolchain image now belongs to `renderer` (T07); `worker-video` is pinned
    back to the BASE app image so the demotion cannot be undone by file ordering.
    """
    overlay = _load(_OVERLAY)
    sentinel = ":${APP_VERSION:?set APP_VERSION to the immutable git SHA}"

    renderer = overlay["services"]["renderer"]
    assert renderer["image"].endswith(sentinel)
    args = renderer["build"]["args"]
    assert args["APP_IMAGE"].endswith(sentinel), (
        "video image must be built FROM the same-sha app image, not a floating tag"
    )

    # Demotion contract: worker-video must NOT carry the -video toolchain image.
    worker_video_image = overlay["services"]["worker-video"]["image"]
    assert worker_video_image.endswith(sentinel)
    assert "-video:" not in worker_video_image, "worker-video must stay on the base app image"


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
    env = overlay["services"]["renderer"]["environment"]
    assert env["CREATIVE_HYPERFRAMES_ROOT"].startswith("/opt/")


def test_renderer_is_netless_and_declares_the_rc5_fact():
    """T07 §9.1 / §12 A3 — the RC5 primitive is a container with NO network.

    The isolation is provided by the container runtime, so it must be asserted on
    the service definition, not merely claimed by an env flag: `network_mode: none`
    (and NO `networks:` key, which would silently re-attach a NIC), a full cap
    drop, and the runtime-asserted `CREATIVE_RENDER_NETLESS=1` fact that
    `network_guard.build_isolation()` reads to report `enforced is True`.
    """
    base = _load(_BASE)
    renderer = base["services"]["renderer"]
    assert renderer["network_mode"] == "none", "the renderer must have no network interface"
    assert "networks" not in renderer, "`networks:` is incompatible with network_mode and re-attaches a NIC"
    assert renderer["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in renderer["security_opt"]
    assert renderer["environment"]["CREATIVE_RENDER_NETLESS"] == "1"

    # The overlay must not weaken the primitive it points the toolchain at.
    overlay = _load(_OVERLAY)["services"].get("renderer", {})
    assert overlay.get("network_mode", "none") == "none"
    assert "networks" not in overlay


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
