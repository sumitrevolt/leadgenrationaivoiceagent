"""Contract tests for the HyperFrames creative provider + enterprise gate.

These assert real behaviour, not mocked truthiness: videos are genuinely encoded
with FFmpeg and genuinely probed, the allowlist is exercised with hostile input,
and the subprocess contract is inspected as an argv list.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.marketing.creative_os import enterprise_qa, flags
from app.marketing.creative_os import hyperframes_provider as hp
from app.marketing.creative_os import hyperframes_templates as ht
from app.marketing.creative_os.assets import register_asset, revoke_asset
from app.marketing.creative_os.licence import assert_provider_allowed
from app.marketing.creative_os.providers import NO_SILENT_FALLBACK, get_provider
from app.marketing.creative_os.spec import CreativeSpec, SceneSpec

_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe unavailable")


# ------------------------------------------------------------------ fixtures
def _make_spec(**over) -> CreativeSpec:
    base = {
        "creative_id": "cr_testhf000001",
        "tenant_id": "jiya-makeover",
        "goal": "bridal makeup bookings",
        "audience": "Jiya Makeover Studio",
        "offer": "Studio appointment",
        "language": "hinglish",
        "platform": "instagram",
        "aspect_ratio": "9:16",
        "recipe": "offer_announcement",
        "provider": "hyperframes",
        "cta": "Aaj hi apni date confirm kijiye",
        "scenes": [
            SceneSpec(index=0, role="hook", text="Aapka big day, camera-ready look"),
            SceneSpec(index=1, role="body", text="Bridal Makeup"),
            SceneSpec(index=2, role="body", text="Event & Party Makeup"),
        ],
    }
    base.update(over)
    return CreativeSpec(**base)


_BRAND = {
    "business_name": "Jiya Makeover Studio",
    "city": "Mumbai",
    "primary_color": "#e63946",
    "accent_color": "#f1faee",
    "tagline": "Premium Bridal & Event Makeup",
}


def _encode(
    path: Path,
    *,
    w: int,
    h: int,
    seconds: float = 8.0,
    fps: int = 30,
    bitrate: str = "10M",
) -> Path:
    """Encode a REAL h264/yuv420p mp4 so ffprobe assertions are meaningful.

    ``bitrate`` mirrors the ``--video-bitrate`` the provider actually requests.
    Synthetic ``testsrc`` compresses far better than real motion-graphics, so an
    unconstrained encode lands near 160 kbps and would fail the bitrate floor for
    a reason that has nothing to do with the gate under test.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={w}x{h}:rate={fps}:duration={seconds}",
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            bitrate,
            "-movflags",
            "+faststart",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    return path


@pytest.fixture
def _clean_env(monkeypatch):
    for k in (
        "CREATIVE_OS_ENABLED",
        "CREATIVE_PROVIDER_HYPERFRAMES_ENABLED",
        "CREATIVE_HYPERFRAMES_CANARY_TENANTS",
    ):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# --------------------------------------------------------------- flags/gates
def test_provider_disabled_by_default(_clean_env):
    """Code being present must never mean the provider is live."""
    assert hp.provider_enabled() is False
    assert flags.provider_enabled("hyperframes") is False
    assert flags.flag_snapshot()["CREATIVE_PROVIDER_HYPERFRAMES_ENABLED"] is False


def test_provider_requires_both_os_and_provider_flag(_clean_env):
    _clean_env.setenv("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED", "1")
    assert hp.provider_enabled() is False, "provider flag alone must not enable it"
    _clean_env.setenv("CREATIVE_OS_ENABLED", "1")
    assert hp.provider_enabled() is True


def test_empty_canary_allowlist_is_fail_closed(_clean_env):
    """Unset allowlist must mean NO tenant, never every tenant."""
    assert hp.canary_tenants() == frozenset()
    assert hp.tenant_allowed("jiya-makeover") is False
    assert hp.tenant_allowed("") is False


def test_canary_allowlist_is_exact(_clean_env):
    _clean_env.setenv("CREATIVE_HYPERFRAMES_CANARY_TENANTS", "jiya-makeover")
    assert hp.tenant_allowed("jiya-makeover") is True
    assert hp.tenant_allowed("jiya-makeover-evil") is False
    assert hp.tenant_allowed("other-tenant") is False


@pytest.mark.asyncio
async def test_generate_refuses_when_disabled(_clean_env):
    out = await get_provider("hyperframes").generate(_make_spec())
    assert out["ok"] is False
    assert out["error"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_generate_refuses_tenant_outside_allowlist(_clean_env):
    _clean_env.setenv("CREATIVE_OS_ENABLED", "1")
    _clean_env.setenv("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED", "1")
    _clean_env.setenv("CREATIVE_HYPERFRAMES_CANARY_TENANTS", "someone-else")
    out = await get_provider("hyperframes").generate(_make_spec())
    assert out["ok"] is False
    assert out["error"] == "tenant_not_in_canary_allowlist"


# ------------------------------------------------------------------ licence
def test_licence_is_pinned_and_production_eligible():
    got = assert_provider_allowed("hyperframes", "hyperframes-cli")
    assert got["ok"] is True
    snap = got["snapshot"]
    assert snap["software_licence"] == "Apache-2.0"
    assert snap["weight_licence"] == "n/a"
    assert snap["commercial_use"] is True
    assert snap["rollback_provider"] == "deterministic"


def test_pinned_version_matches_lockfile_dependency():
    """Provenance must come from the committed manifest, not a floating tag."""
    assert hp._pinned_version() == "0.7.87"
    pkg = ht.renderer_root() / "package.json"
    assert pkg.is_file()
    assert "^" not in pkg.read_text(encoding="utf-8").split('"hyperframes"')[1][:20]


def test_spec_accepts_hyperframes_provider():
    assert _make_spec().validate() == []


# ------------------------------------------------------------ template allowlist
@pytest.mark.parametrize(
    "hostile",
    [
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "beauty_luxury_offer_v1/../../../..",
        "/etc/passwd",
        "beauty_luxury_offer_v1 ",
        "BEAUTY_LUXURY_OFFER_V1",
        "",
        "unknown_template",
    ],
)
def test_template_allowlist_rejects_hostile_ids(hostile):
    assert ht.get_template(hostile) is None
    assert ht.template_dir(hostile) is None


def test_allowlisted_template_resolves_inside_renderer_root():
    d = ht.template_dir("beauty_luxury_offer_v1")
    assert d is not None
    assert (d / "index.html").is_file()
    d.relative_to(ht.renderer_root())  # raises if it escaped


def test_manifest_rejects_unknown_template():
    with pytest.raises(hp.RenderError) as e:
        hp.build_manifest(_make_spec(), brand=_BRAND, template_id="nope_v9")
    assert e.value.code == "template_not_allowlisted"


def test_manifest_rejects_unsupported_aspect():
    with pytest.raises(hp.RenderError) as e:
        hp.build_manifest(_make_spec(aspect_ratio="16:9"), brand=_BRAND)
    assert e.value.code == "aspect_not_supported_by_template"


# ---------------------------------------------------------------- manifest
def test_manifest_binds_verified_brand_facts():
    m = hp.build_manifest(_make_spec(), brand=_BRAND)
    v = m["variables"]
    assert m["width"] == 1080 and m["height"] == 1920 and m["fps"] == 30
    assert m["template_version"] == "1.0.0"
    assert v["business_name"] == "Jiya Makeover Studio"
    assert v["primary_color"] == "#e63946"
    assert v["monogram"] == "JM"
    assert set(v).issubset(set(ht.get_template("beauty_luxury_offer_v1")["variables"]))


def test_manifest_never_invents_social_proof():
    """A testimonial/rating must stay empty unless verified — never generated."""
    m = hp.build_manifest(_make_spec(), brand=_BRAND)
    assert m["variables"]["proof_line"] == ""


def test_manifest_needs_customer_input_when_brand_facts_missing():
    with pytest.raises(hp.RenderError) as e:
        hp.build_manifest(_make_spec(), brand={"business_name": "X"})
    assert e.value.code == "needs_customer_input"
    assert "primary_color" in e.value.detail


def test_manifest_rejects_non_hex_color_injection():
    """Colors land in CSS custom properties, so only hex literals may pass."""
    hostile = dict(_BRAND, primary_color="red; } body { display:none } :root{--x:")
    with pytest.raises(hp.RenderError) as e:
        hp.build_manifest(_make_spec(), brand=hostile)
    assert e.value.code == "needs_customer_input"


def test_manifest_strips_control_characters():
    m = hp.build_manifest(_make_spec(cta="Book\x00 now\x1b[31m"), brand=_BRAND)
    assert "\x00" not in m["variables"]["cta_text"]
    assert "\x1b" not in m["variables"]["cta_text"]


def test_manifest_hash_changes_when_copy_changes():
    a = hp.manifest_hash(hp.build_manifest(_make_spec(), brand=_BRAND))
    b = hp.manifest_hash(hp.build_manifest(_make_spec(cta="Different CTA"), brand=_BRAND))
    assert a != b


# ------------------------------------------------------- tenant isolation
def test_photo_resolution_is_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"0" * 4096)

    reg = register_asset(
        tenant_id="tenant-a",
        source_type="upload",
        ref=str(img),
        sha256="a" * 64,
        mime_type="image/jpeg",
        consent_status="granted",
    )
    aid = reg["asset"]["asset_id"]

    assert hp._resolve_photo("tenant-a", aid) == str(img.resolve())
    # Tenant B must never resolve tenant A's asset id.
    assert hp._resolve_photo("tenant-b", aid) is None


def test_revoked_asset_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    img = tmp_path / "b.png"
    img.write_bytes(b"\x89PNG" + b"0" * 4096)
    reg = register_asset(
        tenant_id="tenant-a",
        source_type="upload",
        ref=str(img),
        sha256="b" * 64,
        mime_type="image/png",
        consent_status="granted",
    )
    aid = reg["asset"]["asset_id"]
    assert hp._resolve_photo("tenant-a", aid) is not None

    revoke_asset("tenant-a", aid)
    assert hp._resolve_photo("tenant-a", aid) is None, "revoked asset must block regeneration"


def test_unknown_asset_id_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    assert hp._resolve_photo("tenant-a", "asset_does_not_exist") is None


def test_remote_url_asset_ref_is_refused(tmp_path, monkeypatch):
    """A registry ref pointing at http(s) must never reach the renderer."""
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    reg = register_asset(
        tenant_id="tenant-a",
        source_type="import",
        ref="https://evil.example.com/x.jpg",
        sha256="c" * 64,
        mime_type="image/jpeg",
        consent_status="granted",
    )
    assert hp._resolve_photo("tenant-a", reg["asset"]["asset_id"]) is None


def test_disallowed_mime_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    f = tmp_path / "x.svg"
    f.write_text("<svg onload='alert(1)'/>", encoding="utf-8")
    reg = register_asset(
        tenant_id="tenant-a",
        source_type="upload",
        ref=str(f),
        sha256="d" * 64,
        mime_type="image/svg+xml",
        consent_status="granted",
    )
    assert hp._resolve_photo("tenant-a", reg["asset"]["asset_id"]) is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink creation")
def test_symlinked_asset_is_refused_real_symlink(tmp_path, monkeypatch):
    """Real-symlink version — only runs where symlinks can be created."""
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    real = tmp_path / "real.jpg"
    real.write_bytes(b"\xff\xd8\xff" + b"0" * 4096)
    link = tmp_path / "link.jpg"
    link.symlink_to(real)
    reg = register_asset(
        tenant_id="tenant-a",
        source_type="upload",
        ref=str(link),
        sha256="e" * 64,
        mime_type="image/jpeg",
        consent_status="granted",
    )
    assert hp._resolve_photo("tenant-a", reg["asset"]["asset_id"]) is None


def test_symlinked_asset_is_refused_on_every_platform(tmp_path, monkeypatch):
    """Same boundary, exercised WITHOUT needing OS symlink support.

    The real-symlink test above skips on Windows, which would leave this
    security branch with zero executed coverage on a dev box. Here the symlink
    signal itself is faked so the provider's REFUSAL LOGIC is what gets tested,
    not the filesystem's ability to make links.
    """
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    img = tmp_path / "swappable.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"0" * 4096)
    reg = register_asset(
        tenant_id="tenant-a",
        source_type="upload",
        ref=str(img),
        sha256="f" * 64,
        mime_type="image/jpeg",
        consent_status="granted",
    )
    aid = reg["asset"]["asset_id"]
    # Sanity: it resolves while it is a regular file...
    assert hp._resolve_photo("tenant-a", aid) is not None

    # ...and is refused the moment THAT path looks like a symlink. Only the exact
    # target is faked: a blanket `is_symlink -> True` would also pass against an
    # implementation that only inspects the RESOLVED path, which is precisely the
    # bug this guards (Path.resolve follows links, so the resolved path is never
    # a symlink and the check silently never fires).
    real_is_symlink = Path.is_symlink

    def _fake(self):
        return str(self) == str(img) or real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _fake)
    assert hp._resolve_photo("tenant-a", aid) is None


# ------------------------------------------------------------- subprocess
@pytest.fixture
def stub_renderer(tmp_path, monkeypatch):
    """A renderer root containing only the CLI entrypoint.

    These tests exercise HOW the child is invoked, not whether npm has run. CI
    checks out the repo without `node_modules`, so pointing at the real root made
    every one of them fail with `renderer_not_installed` — masking the argv,
    exit-code and timeout contracts they exist to protect.
    """
    root = tmp_path / "renderer"
    cli = root / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text("// stub", encoding="utf-8")
    monkeypatch.setattr(hp, "renderer_root", lambda: root)
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return project


def test_renderer_refuses_when_cli_is_absent(tmp_path, monkeypatch):
    """The installed-check itself must still fail closed."""
    monkeypatch.setattr(hp, "renderer_root", lambda: tmp_path / "empty")
    with pytest.raises(hp.RenderError) as e:
        hp._run_renderer(
            project_dir=tmp_path,
            manifest_path=tmp_path / "m.json",
            output_path=tmp_path / "o.mp4",
            preset="portrait",
            timeout_s=60,
        )
    assert e.value.code == "renderer_not_installed"


def test_renderer_invocation_is_argv_not_shell(monkeypatch, tmp_path, stub_renderer):
    """No shell=True and no interpolated command string, ever."""
    captured: dict = {}

    class _P:
        pid = 4242
        returncode = 0

        def communicate(self, timeout=None):
            return (b"", b"")

        def poll(self):
            return 0

    def _fake_popen(argv, **kw):
        captured["argv"] = argv
        captured["kw"] = kw
        return _P()

    monkeypatch.setattr(hp.subprocess, "Popen", _fake_popen)
    hp._run_renderer(
        project_dir=stub_renderer,
        manifest_path=tmp_path / "m.json",
        output_path=tmp_path / "o.mp4",
        preset="portrait",
        timeout_s=60,
    )

    assert isinstance(captured["argv"], list), "argv must be a list, never a string"
    assert captured["kw"]["shell"] is False
    assert "--variables-file" in captured["argv"]
    assert "--no-best-effort" in captured["argv"], "must fail on unready media, not degrade"
    assert "--resolution" in captured["argv"]
    # Cloud/publish subcommands must never be reachable from a render.
    for banned in ("cloud", "lambda", "cloudrun", "publish", "auth"):
        assert banned not in captured["argv"]


def test_renderer_env_disables_telemetry_and_downloads(monkeypatch):
    env = hp._hermetic_env()
    assert env["HYPERFRAMES_NO_TELEMETRY"] == "1"
    assert env["HYPERFRAMES_NO_UPDATE_CHECK"] == "1"
    assert env["HYPERFRAMES_NO_AUTO_INSTALL"] == "1"
    assert env["DO_NOT_TRACK"] == "1"
    assert env["HYPERFRAMES_API_KEY"] == "", "a render must never authenticate to cloud"


def test_renderer_nonzero_exit_maps_to_render_error(monkeypatch, tmp_path, stub_renderer):
    class _P:
        pid = 1
        returncode = 3

        def communicate(self, timeout=None):
            return (b"", b"boom")

        def poll(self):
            return 3

    monkeypatch.setattr(hp.subprocess, "Popen", lambda *a, **k: _P())
    with pytest.raises(hp.RenderError) as e:
        hp._run_renderer(
            project_dir=stub_renderer,
            manifest_path=tmp_path / "m.json",
            output_path=tmp_path / "o.mp4",
            preset="portrait",
            timeout_s=60,
        )
    assert e.value.code == "renderer_exit_nonzero"


def test_render_timeout_kills_process_tree(monkeypatch, tmp_path, stub_renderer):
    killed: dict = {}

    class _P:
        pid = 777
        returncode = None

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="render", timeout=timeout or 1)

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(hp.subprocess, "Popen", lambda *a, **k: _P())
    monkeypatch.setattr(hp, "_kill_tree", lambda p: killed.setdefault("pid", p.pid))

    with pytest.raises(hp.RenderError) as e:
        hp._run_renderer(
            project_dir=stub_renderer,
            manifest_path=tmp_path / "m.json",
            output_path=tmp_path / "o.mp4",
            preset="portrait",
            timeout_s=1,
        )
    assert e.value.code == "render_timeout"
    assert killed.get("pid") == 777, "timeout must terminate the child, not orphan Chrome"


# -------------------------------------------------------- enterprise gate
@needs_ffmpeg
def test_enterprise_gate_accepts_1080x1920(tmp_path):
    mp4 = _encode(tmp_path / "ok.mp4", w=1080, h=1920)
    got = enterprise_qa.evaluate(
        path=str(mp4),
        spec=_make_spec(),
        provider_asset={
            "template_id": "beauty_luxury_offer_v1",
            "template_version": "1.0.0",
            "manifest_hash": "f" * 64,
            "scene_count": 6,
        },
    )
    assert got["classification"] == enterprise_qa.CUSTOMER_APPROVABLE, got["blockers"]
    assert got["customer_approvable"] is True
    assert got["probe"]["width"] == 1080 and got["probe"]["height"] == 1920


@needs_ffmpeg
def test_enterprise_gate_rejects_720p_as_draft_only(tmp_path):
    """The existing flat-text provider's shape is a draft, not a deliverable."""
    mp4 = _encode(tmp_path / "small.mp4", w=720, h=1280)
    got = enterprise_qa.evaluate(
        path=str(mp4),
        spec=_make_spec(),
        provider_asset={
            "template_id": "beauty_luxury_offer_v1",
            "template_version": "1.0.0",
            "manifest_hash": "f" * 64,
            "scene_count": 6,
        },
    )
    assert got["classification"] == enterprise_qa.DRAFT_ONLY
    assert got["customer_approvable"] is False
    assert "fullhd_resolution" in got["blockers"]


@needs_ffmpeg
def test_starved_encode_is_not_customer_approvable(tmp_path):
    """Right shape, right codec, but a quality-starved encode is still a draft."""
    mp4 = _encode(tmp_path / "starved.mp4", w=1080, h=1920, bitrate="120k")
    got = enterprise_qa.evaluate(
        path=str(mp4),
        spec=_make_spec(),
        provider_asset={
            "template_id": "beauty_luxury_offer_v1",
            "template_version": "1.0.0",
            "manifest_hash": "f" * 64,
            "scene_count": 6,
        },
    )
    assert got["customer_approvable"] is False
    assert "video_bitrate_floor" in got["blockers"]


@needs_ffmpeg
def test_low_substance_render_is_not_customer_approvable(tmp_path):
    """A 1080p file with no template/scene substance is still not sellable."""
    mp4 = _encode(tmp_path / "flat.mp4", w=1080, h=1920)
    got = enterprise_qa.evaluate(path=str(mp4), spec=_make_spec(), provider_asset={})
    assert got["customer_approvable"] is False
    assert {"scene_count_min", "animated_template", "manifest_bound"} & set(got["blockers"])


@needs_ffmpeg
def test_enterprise_gate_quarantines_internal_identifiers(tmp_path):
    """`beauty_makeover` is a real internal field key — never customer-facing."""
    mp4 = _encode(tmp_path / "leak.mp4", w=1080, h=1920)
    spec = _make_spec(goal="beauty_makeover", script="beauty_makeover special")
    got = enterprise_qa.evaluate(
        path=str(mp4),
        spec=spec,
        provider_asset={
            "template_id": "beauty_luxury_offer_v1",
            "template_version": "1.0.0",
            "manifest_hash": "f" * 64,
            "scene_count": 6,
        },
    )
    assert got["classification"] == enterprise_qa.QUARANTINED
    assert "no_internal_identifiers" in got["blockers"]


@needs_ffmpeg
def test_enterprise_gate_blocks_unexpected_fallback(tmp_path):
    mp4 = _encode(tmp_path / "fb.mp4", w=1080, h=1920)
    spec = _make_spec()
    spec.fallback_from = "hyperframes"
    got = enterprise_qa.evaluate(
        path=str(mp4),
        spec=spec,
        provider_asset={
            "template_id": "beauty_luxury_offer_v1",
            "template_version": "1.0.0",
            "manifest_hash": "f" * 64,
            "scene_count": 6,
        },
    )
    assert got["customer_approvable"] is False
    assert "no_unexpected_fallback" in got["blockers"]


def test_enterprise_gate_quarantines_missing_output(tmp_path):
    got = enterprise_qa.evaluate(path=str(tmp_path / "nope.mp4"), spec=_make_spec())
    assert got["classification"] == enterprise_qa.QUARANTINED


@needs_ffmpeg
def test_enterprise_gate_quarantines_corrupt_output(tmp_path):
    bad = tmp_path / "corrupt.mp4"
    bad.write_bytes(b"not an mp4" * 500)
    got = enterprise_qa.evaluate(path=str(bad), spec=_make_spec())
    assert got["classification"] == enterprise_qa.QUARANTINED


# ------------------------------------------------------- no silent fallback
def test_hyperframes_is_excluded_from_silent_fallback():
    assert "hyperframes" in NO_SILENT_FALLBACK
    assert "deterministic" not in NO_SILENT_FALLBACK


@pytest.mark.asyncio
async def test_failed_hyperframes_never_returns_deterministic_output(_clean_env):
    """The core anti-downgrade guarantee."""
    from app.marketing.creative_os.providers import generate_with_fallback

    _clean_env.setenv("CREATIVE_OS_ENABLED", "1")
    # provider flag deliberately OFF -> hyperframes fails
    spec = _make_spec()
    out = await generate_with_fallback(spec)

    assert out["ok"] is False
    assert out.get("fallback_suppressed") is True
    assert out["provider"] == "hyperframes"
    assert not out.get("assets"), "a failed deliverable must not carry a fallback asset"
    assert spec.provider == "hyperframes", "spec must not be rewritten to the fallback"
    assert any("no_silent_fallback" in w for w in out.get("warnings") or [])


# ------------------------------------------------- multi-template contract
ALL_TEMPLATES = ("beauty_luxury_offer_v1", "local_service_promo_v1", "agency_product_launch_v1")


@pytest.mark.parametrize("tid", ALL_TEMPLATES)
def test_every_registered_template_is_self_contained(tid):
    """No `../` escapes and fonts bundled per template — a shared parent dir
    404s in HyperFrames and silently drops the stylesheet."""
    d = ht.template_dir(tid)
    assert d is not None, tid
    html = (d / "index.html").read_text(encoding="utf-8")
    assert "../" not in html, f"{tid} references a parent-relative asset"
    assert (d / "assets" / "base.css").is_file()
    fonts = list((d / "assets" / "fonts").glob("*.woff2"))
    assert len(fonts) >= 4, f"{tid} missing bundled fonts"
    assert any("devanagari" in f.name for f in fonts), f"{tid} lacks Devanagari coverage"


@pytest.mark.parametrize("tid", ALL_TEMPLATES)
def test_templates_declare_required_composition_contract(tid):
    d = ht.template_dir(tid)
    html = (d / "index.html").read_text(encoding="utf-8")
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'data-start="0"' in html
    assert "data-no-timeline" in html, "no GSAP timeline -> must skip the 45s poll"
    assert 'data-width="1080"' in html and 'data-height="1920"' in html


@pytest.mark.parametrize("tid", ALL_TEMPLATES)
def test_templates_have_no_network_dependency(tid):
    """A CDN script/font/image would break the zero-network render guarantee."""
    d = ht.template_dir(tid)
    for f in (d / "index.html", d / "assets" / "base.css"):
        text = f.read_text(encoding="utf-8")
        for bad in ("http://", "https://", "//cdn", "@import url(http"):
            assert bad not in text, f"{tid}:{f.name} references {bad}"


@pytest.mark.parametrize("tid", ALL_TEMPLATES)
def test_templates_use_only_finite_animation(tid):
    """`infinite` has no computable end time and cannot be seeked."""
    css = (ht.template_dir(tid) / "assets" / "base.css").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in css.splitlines() if not ln.strip().startswith("*"))
    assert "infinite" not in body, f"{tid} has an infinite animation"


@pytest.mark.parametrize("tid", ALL_TEMPLATES)
def test_every_template_has_a_binder_producing_declared_variables(tid):
    """Binder output must match the registry EXACTLY — an extra key raises and a
    missing required key is NEEDS_CUSTOMER_INPUT, so a template/binder drift can
    never render as silently blank slots."""
    tpl = ht.get_template(tid)
    assert tid in hp._BINDERS, f"{tid} has no variable binder"
    spec = _make_spec(template_id=tid)
    m = hp.build_manifest(spec, brand=_BRAND, template_id=tid)
    assert set(m["variables"]) <= set(tpl["variables"])
    for req in tpl["required_variables"]:
        assert m["variables"].get(req), f"{tid} required var {req} unbound"
    assert m["width"] == 1080 and m["height"] == 1920 and m["fps"] == 30


@pytest.mark.parametrize("tid", ALL_TEMPLATES)
def test_unverified_trust_and_metrics_stay_empty(tid):
    """Ratings/review counts/launch metrics are CLAIMS: absent unless verified."""
    m = hp.build_manifest(_make_spec(template_id=tid), brand=_BRAND, template_id=tid)
    v = m["variables"]
    assert json.loads(v.get("trust_json", "[]")) == []
    assert json.loads(v.get("metrics_json", "[]")) == []
    assert v.get("proof_line", "") == ""


def test_verified_trust_and_metrics_are_emitted_when_present():
    """The empty case must be a REFUSAL, not a broken binder."""
    brand = dict(
        _BRAND,
        verified_trust=["Licensed", "5 saal experience"],
        verified_metrics=[{"value": "500", "label": "minutes included"}],
    )
    local = hp.build_manifest(
        _make_spec(template_id="local_service_promo_v1"),
        brand=brand,
        template_id="local_service_promo_v1",
    )
    assert json.loads(local["variables"]["trust_json"]) == ["Licensed", "5 saal experience"]

    agency = hp.build_manifest(
        _make_spec(template_id="agency_product_launch_v1"),
        brand=brand,
        template_id="agency_product_launch_v1",
    )
    assert json.loads(agency["variables"]["metrics_json"])[0]["value"] == "500"


def test_template_id_selects_template_and_bad_value_falls_back():
    assert hp._template_for(_make_spec(template_id="local_service_promo_v1")) == (
        "local_service_promo_v1"
    )
    # Hostile / unknown values must never reach the renderer as a path.
    for bad in ("../../etc", "unknown_v9", ""):
        assert hp._template_for(_make_spec(template_id=bad)) == hp.default_template()


def test_manifest_hash_differs_per_template():
    hashes = {
        tid: hp.manifest_hash(
            hp.build_manifest(_make_spec(template_id=tid), brand=_BRAND, template_id=tid)
        )
        for tid in ALL_TEMPLATES
    }
    assert len(set(hashes.values())) == len(ALL_TEMPLATES)


# -------------------------------------------------------------- regression
def test_deterministic_provider_still_registered_and_unchanged():
    assert get_provider("deterministic").name == "deterministic"
    assert assert_provider_allowed("deterministic", "ffmpeg-template")["ok"] is True


def test_unknown_provider_still_falls_back_to_deterministic():
    assert get_provider("totally-unknown").name == "deterministic"


def test_output_root_is_a_publish_trusted_root():
    """Renders must land where the publish gate will still accept them."""
    from app.marketing.video_media_paths import media_roots

    root = hp.output_root().resolve()
    assert any(root == r or root.is_relative_to(r) for r in media_roots())
