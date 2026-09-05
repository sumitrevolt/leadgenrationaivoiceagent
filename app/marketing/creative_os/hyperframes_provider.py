"""HyperFrames creative provider — professional animated 1080p renders.

Additive provider for the existing Creative Automation OS. It does NOT replace
the CreativeSpec contract, the brief/brand-fact gate, the asset registry, the QA
lifecycle, exact-revision approval, or the publish gate — it plugs in where the
deterministic FFmpeg provider already plugs in, and every one of those gates
still runs afterwards.

Execution model: the Python worker stays the orchestrator and shells out to the
pinned HyperFrames CLI as a child process, passing a validated JSON manifest
file rather than free-form arguments. There is no shell, no string
interpolation into a command line, and no network access during a render.

Failure policy is deliberately loud. If a customer asked for a HyperFrames
deliverable and HyperFrames fails, this returns an error — it never quietly
hands back the low-quality flat-text fallback dressed up as the real thing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # noqa: S404 - fixed argv, never shell=True (see _run_renderer)
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from app.marketing.creative_os import flags
from app.marketing.creative_os.assets import get_asset
from app.marketing.creative_os.hyperframes_templates import (
    RESOLUTION_PRESETS,
    get_template,
    renderer_root,
    template_dir,
)
from app.marketing.creative_os.licence import assert_provider_allowed
from app.marketing.creative_os.spec import CreativeSpec
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

PROVIDER_NAME = "hyperframes"
MODEL_NAME = "hyperframes-cli"

MANIFEST_VERSION = "1.0"

# Only these image types may be bound into a composition. A tenant asset with
# any other mime never reaches Chrome.
_ALLOWED_PHOTO_MIME = frozenset({"image/jpeg", "image/png", "image/webp"})

# Colors are injected into CSS custom properties, so anything that is not a
# plain hex literal is refused — this is the stylesheet-injection boundary.
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# Copy is bound with textContent (never innerHTML), so markup cannot execute.
# Control characters are still stripped so they cannot corrupt the manifest.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class RenderError(Exception):
    """Renderer failed in a way the caller must surface, never paper over."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------- flags
def provider_enabled() -> bool:
    """Master gate. OFF unless BOTH the OS and this provider are enabled."""
    return flags.os_enabled() and _env_on("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED")


def _env_on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def canary_tenants() -> frozenset[str]:
    raw = os.getenv("CREATIVE_HYPERFRAMES_CANARY_TENANTS", "")
    return frozenset(t.strip() for t in raw.split(",") if t.strip())


def tenant_allowed(tenant_id: str) -> bool:
    """Empty allowlist = NO tenant (fail-closed), not 'everyone'.

    An unset allowlist meaning "all tenants" is how a canary silently becomes a
    fleet-wide rollout, so the empty case refuses.
    """
    allow = canary_tenants()
    if not allow:
        return False
    return str(tenant_id or "").strip() in allow


def render_timeout_s() -> int:
    """Subprocess deadline, always strictly INSIDE the worker's own deadline.

    Three timeouts are nested here: this subprocess timeout, the orchestrator's
    ``asyncio.wait_for(flags.worker_timeout_s())``, and Celery's
    ``soft_time_limit``. They must decrease inward. If the outer one fires first
    the provider never runs its cleanup, and the Chrome grandchildren are
    orphaned rather than reaped — so the configured value is clamped below the
    worker deadline instead of trusting two env vars to be set consistently.
    """
    try:
        configured = int(os.getenv("CREATIVE_HYPERFRAMES_TIMEOUT_S", "900"))
    except Exception:
        configured = 900
    configured = max(60, min(1800, configured))
    try:
        outer = int(flags.worker_timeout_s())
    except Exception:
        outer = configured + 60
    # Leave headroom for manifest write, ffprobe validation and cleanup.
    return max(30, min(configured, outer - 30))


def max_output_mb() -> int:
    try:
        return max(1, min(2048, int(os.getenv("CREATIVE_HYPERFRAMES_MAX_OUTPUT_MB", "220"))))
    except Exception:
        return 220


def network_disabled() -> bool:
    """Default ON: a production render must not touch the network."""
    return os.getenv("CREATIVE_HYPERFRAMES_NETWORK_DISABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def default_template() -> str:
    return os.getenv("CREATIVE_HYPERFRAMES_DEFAULT_TEMPLATE", "beauty_luxury_offer_v1").strip()


# ------------------------------------------------------------------ helpers
def _clean(text: Any, limit: int = 400) -> str:
    return _CTRL_RE.sub("", str(text or "")).strip()[:limit]


def _safe_color(value: str, fallback: str) -> str:
    v = str(value or "").strip()
    return v if _HEX_COLOR_RE.match(v) else fallback


def output_root() -> Path:
    """Canonical media root. MUST be a root the publish gate also trusts.

    ``video_media_paths.media_roots()`` — which the approval snapshot and the
    Postiz publish gate resolve against — does not include ``data/creative_os``,
    so writing there would pass creative-OS QA and then be refused at publish.
    Renders therefore land under the video-ads root, which both authorities
    accept.
    """
    from app.marketing.video_media_paths import video_ads_dir

    return video_ads_dir()


def _resolve_photo(tenant_id: str, asset_id: str) -> str | None:
    """Tenant-scoped, consent-checked, existence-checked photo path.

    Returns None for anything not provably this tenant's live asset. Cross-tenant
    and revoked ids resolve to None inside ``get_asset``.
    """
    got = get_asset(tenant_id, asset_id)
    if not got.get("ok"):
        return None
    asset = got.get("asset") or {}
    if str(asset.get("tenant_id") or "") != str(tenant_id):
        return None
    if str(asset.get("mime_type") or "").lower() not in _ALLOWED_PHOTO_MIME:
        return None
    ref = str(asset.get("ref") or "").strip()
    if not ref:
        return None
    try:
        candidate = Path(ref)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate

        # Symlink policy, checked on the UNRESOLVED path. `Path.resolve()` follows
        # every link, so testing `resolved.is_symlink()` is always False and
        # silently accepts a symlinked asset — the check has to happen before
        # resolution, and on every parent component, because an in-path link can
        # be retargeted after the consent check passed.
        for part in (candidate, *candidate.parents):
            if part.is_symlink():
                return None

        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    return str(resolved)


# ------------------------------------------------------- per-template binders
# One binder per template. Each returns the EXACT variable set that template
# declares — `build_manifest` then rejects any key outside the registry's
# declared list and any missing required key, so a template/binder mismatch is
# an error rather than a video that renders with silently blank slots.
#
# Rule shared by all of them: a fact we cannot evidence stays "" and the
# composition drops that element. None of them invent a rating, review count,
# price, metric or testimonial.


def _bind_beauty(c: dict[str, Any]) -> dict[str, str]:
    return {
        "business_name": c["business_name"],
        "monogram": c["monogram"],
        "tagline": c["tagline"][:120],
        "city": c["city"],
        "primary_color": c["primary"],
        "accent_color": c["accent"],
        "hook_line": c["hook"],
        "hook_sub": c["tagline"] if c["hook"] else "",
        "services_json": json.dumps(c["body_items"], ensure_ascii=False),
        "showcase_line": c["showcase"],
        "proof_line": "",
        "offer_title": _clean(c["brand"].get("offer_badge"), 40),
        "offer_sub": c["offer_sub"],
        "cta_text": c["cta_text"],
        "cta_channel": c["channel"],
        "contact_display": _clean(c["brand"].get("contact_display"), 80) or c["cta_text"],
        "photos_json": c["photos_json"],
        "footer_note": c["footer"],
    }


def _bind_local_service(c: dict[str, Any]) -> dict[str, str]:
    # The problem/solution spine reuses the scene plan: the hook IS the problem
    # statement and the tagline carries the solution promise.
    return {
        "business_name": c["business_name"],
        "monogram": c["monogram"],
        "tagline": c["tagline"][:120],
        "city": c["city"],
        "primary_color": c["primary"],
        "accent_color": c["accent"],
        "problem_line": c["hook"],
        "problem_strike": _clean(c["brand"].get("problem_strike"), 90),
        "solution_line": c["tagline"] or c["showcase"],
        "solution_sub": c["showcase"] if c["tagline"] else "",
        "steps_json": json.dumps(c["body_items"], ensure_ascii=False),
        # Trust chips carry claims, so they come ONLY from an explicitly
        # verified list on the brand record — never derived from scene copy.
        "trust_json": json.dumps(
            [_clean(x, 40) for x in (c["brand"].get("verified_trust") or []) if _clean(x, 40)][:3],
            ensure_ascii=False,
        ),
        "proof_line": "",
        "offer_title": _clean(c["brand"].get("offer_badge"), 40),
        "offer_sub": c["offer_sub"],
        "cta_text": c["cta_text"],
        "cta_channel": c["channel"],
        "contact_display": _clean(c["brand"].get("contact_display"), 80) or c["cta_text"],
        "photos_json": c["photos_json"],
        "footer_note": c["footer"],
    }


def _bind_agency(c: dict[str, Any]) -> dict[str, str]:
    return {
        "product_name": c["business_name"],
        "monogram": c["monogram"],
        "tagline": c["tagline"][:140],
        "eyebrow": _clean(c["brand"].get("eyebrow"), 40),
        "primary_color": c["primary"],
        "accent_color": c["accent"],
        "hook_line": c["hook"],
        "hook_sub": c["showcase"],
        "showcase_line": _clean(c["brand"].get("showcase_line"), 120),
        "features_json": json.dumps(c["body_items"], ensure_ascii=False),
        "workflow_json": json.dumps(
            [_clean(x, 28) for x in (c["brand"].get("workflow") or []) if _clean(x, 28)][:4],
            ensure_ascii=False,
        ),
        # Metrics are marketing CLAIMS. Only an explicitly verified list is
        # emitted; there is no derivation and no default, so an unproven launch
        # simply renders without the metrics row.
        "metrics_json": json.dumps(
            [
                {"value": _clean(m.get("value"), 12), "label": _clean(m.get("label"), 40)}
                for m in (c["brand"].get("verified_metrics") or [])
                if isinstance(m, dict) and _clean(m.get("value"), 12)
            ][:3],
            ensure_ascii=False,
        ),
        "cta_text": c["cta_text"],
        "contact_display": _clean(c["brand"].get("contact_display"), 80) or c["cta_text"],
        "photos_json": c["photos_json"],
        "footer_note": c["footer"],
    }


_BINDERS: dict[str, Any] = {
    "beauty_luxury_offer_v1": _bind_beauty,
    "local_service_promo_v1": _bind_local_service,
    "agency_product_launch_v1": _bind_agency,
}


# ----------------------------------------------------------------- manifest
def build_manifest(
    spec: CreativeSpec,
    *,
    brand: dict[str, Any] | None = None,
    template_id: str = "",
    photo_asset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Bind a validated CreativeSpec + verified brand facts into a render manifest.

    Raises ``RenderError`` rather than returning a half-bound manifest, because a
    partially-bound composition renders as a video with blank slots — which is
    exactly the "professional-looking but wrong" output this system must not ship.
    """
    tpl_id = str(template_id or default_template()).strip()
    tpl = get_template(tpl_id)
    if not tpl:
        raise RenderError("template_not_allowlisted", tpl_id)

    if spec.aspect_ratio not in tpl["aspect_ratios"]:
        raise RenderError("aspect_not_supported_by_template", f"{spec.aspect_ratio}:{tpl_id}")
    preset = RESOLUTION_PRESETS.get(spec.aspect_ratio)
    if not preset:
        raise RenderError("aspect_not_supported", spec.aspect_ratio)

    b = dict(brand or {})
    business_name = _clean(b.get("business_name") or spec.audience, 90)
    primary = _safe_color(b.get("primary_color"), "")
    accent = _safe_color(b.get("accent_color"), "")

    # Scene text comes from the recipe-built scene plan, which the brief gate has
    # already checked for unverified prices and placeholders.
    scenes = list(spec.scenes or [])

    def scene_text(role: str, index: int = -1) -> str:
        for sc in scenes:
            sc_role = getattr(sc, "role", None) or (sc.get("role") if isinstance(sc, dict) else "")
            if str(sc_role).lower() == role:
                t = getattr(sc, "text", None) or (sc.get("text") if isinstance(sc, dict) else "")
                return _clean(t, 220)
        if 0 <= index < len(scenes):
            sc = scenes[index]
            t = getattr(sc, "text", None) or (sc.get("text") if isinstance(sc, dict) else "")
            return _clean(t, 220)
        return ""

    hook = scene_text("hook", 0) or scene_text("problem", 0)
    # Prefer the verified tagline: scene index 1 is usually the FIRST service,
    # which would make the showcase card repeat a line the services scene just
    # showed. Falls back to scene copy when the tenant has no tagline.
    showcase = _clean(b.get("tagline"), 160) or scene_text("proof", 1) or scene_text("body", 1)
    offer_sub = _clean(spec.offer, 220) or scene_text("offer", -1)
    cta_text = _clean(spec.cta, 160)

    body_items = []
    for sc in scenes:
        role = getattr(sc, "role", None) or (sc.get("role") if isinstance(sc, dict) else "")
        if str(role).lower() in ("service", "benefit", "body", "step", "feature"):
            title = getattr(sc, "text", None) or (sc.get("text") if isinstance(sc, dict) else "")
            title = _clean(title, 60)
            if title:
                body_items.append({"title": title, "subtitle": ""})
    if not body_items and b.get("services"):
        for svc in b.get("services", [])[:4]:
            if isinstance(svc, dict) and svc.get("name"):
                name = _clean(svc.get("name"), 40)
                price = svc.get("price_inr")
                sub = f"₹{price}" if price else ""
                body_items.append({"title": name, "subtitle": sub})
    if not body_items and b.get("kb_facts"):
        for fact in b.get("kb_facts", [])[:3]:
            short_fact = _clean(str(fact).split(".")[0].split("—")[0], 40)
            if short_fact:
                body_items.append({"title": short_fact, "subtitle": ""})
    body_items = body_items[:4]

    photos: list[str] = []
    for aid in list(photo_asset_ids or spec.source_asset_ids or []):
        got = _resolve_photo(spec.tenant_id, aid)
        if got:
            photos.append(got)
    photos = photos[:3]

    monogram = "".join(w[0] for w in business_name.split()[:2] if w).upper()
    tagline = _clean(b.get("tagline"), 160)
    city = _clean(b.get("city"), 60)
    photos_json = json.dumps(photos, ensure_ascii=False)
    footer = " · ".join(x for x in (business_name, city) if x)
    channel = "call" if "call" in cta_text.lower() else "whatsapp"

    ctx = {
        "business_name": business_name,
        "monogram": monogram,
        "tagline": tagline,
        "city": city,
        "primary": primary,
        "accent": accent,
        "hook": hook,
        "showcase": showcase,
        "offer_sub": offer_sub,
        "cta_text": cta_text,
        "channel": channel,
        "body_items": body_items,
        "photos_json": photos_json,
        "footer": footer,
        "brand": b,
    }

    binder = _BINDERS.get(tpl["template_id"])
    if binder is None:
        raise RenderError("no_variable_binder", tpl["template_id"])
    variables = binder(ctx)

    unknown = set(variables) - set(tpl["variables"])
    if unknown:
        raise RenderError("manifest_unknown_variables", ",".join(sorted(unknown)))

    missing = [k for k in tpl["required_variables"] if not variables.get(k)]
    if missing:
        raise RenderError("needs_customer_input", ",".join(sorted(missing)))

    return {
        "manifest_version": MANIFEST_VERSION,
        "tenant_id": spec.tenant_id,
        "creative_id": spec.creative_id,
        "revision": int(spec.approval_revision or 0),
        "template_id": tpl["template_id"],
        "template_version": tpl["template_version"],
        "aspect_ratio": spec.aspect_ratio,
        "resolution_preset": preset[0],
        "width": preset[1],
        "height": preset[2],
        "fps": 30,
        "language": spec.language,
        "platform": spec.platform,
        "seed": int(spec.seed or 0),
        "spec_hash": spec.spec_hash(),
        "input_hashes": dict(spec.input_hashes or {}),
        "photo_asset_ids": list(photo_asset_ids or spec.source_asset_ids or [])[:3],
        "variables": variables,
    }


def manifest_hash(manifest: dict[str, Any]) -> str:
    import hashlib

    payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- subprocess
def _hermetic_env() -> dict[str, str]:
    """Environment for the child: telemetry off, no update check, no downloads."""
    env = dict(os.environ)
    env.update(
        {
            "HYPERFRAMES_NO_TELEMETRY": "1",
            "HYPERFRAMES_NO_UPDATE_CHECK": "1",
            "HYPERFRAMES_NO_FEEDBACK": "1",
            "HYPERFRAMES_NO_AUTO_INSTALL": "1",
            "HYPERFRAMES_SKIP_SKILLS": "1",
            "DO_NOT_TRACK": "1",
            "NODE_ENV": "production",
            # Never let a render authenticate or reach HeyGen cloud.
            "HYPERFRAMES_API_KEY": "",
        }
    )
    for key in ("npm_config_registry", "NPM_TOKEN"):
        env.pop(key, None)
    return env


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    """Kill the renderer AND its Chrome children on both platforms.

    Chrome is a grandchild of the CLI, so killing only the direct child orphans
    it and leaks memory until the container dies. POSIX gets a process-group
    signal; Windows has no killpg, so taskkill /T walks the tree instead
    (os.kill on Windows sends CTRL_C and is unreliable here).
    """
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(  # noqa: S603 - fixed argv, pid is an int
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=30,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), 9)
    except Exception as exc:
        logger.warning("[hyperframes] kill_tree failed pid=%s: %s", proc.pid, exc)
    finally:
        try:
            proc.wait(timeout=15)
        except Exception:
            pass


def _node_bin() -> str:
    return os.getenv("CREATIVE_HYPERFRAMES_NODE", "").strip() or (shutil.which("node") or "node")


def _run_renderer(
    *,
    project_dir: Path,
    manifest_path: Path,
    output_path: Path,
    preset: str,
    timeout_s: int,
) -> dict[str, Any]:
    """Invoke the pinned CLI with a FIXED argv. No shell, ever."""
    root = renderer_root()
    cli = root / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    if not cli.is_file():
        raise RenderError("renderer_not_installed", str(cli))

    argv = [
        _node_bin(),
        str(cli),
        "render",
        str(project_dir),
        "--variables-file",
        str(manifest_path),
        "--resolution",
        preset,
        "--fps",
        "30",
        "--quality",
        "high",
        "--video-bitrate",
        "10M",
        "--workers",
        "1",
        "--no-best-effort",  # missing/unready media must FAIL, not degrade
        "--quiet",
        "--output",
        str(output_path),
    ]

    popen_kw: dict[str, Any] = {}
    if sys.platform == "win32":
        popen_kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kw["start_new_session"] = True

    t0 = time.time()
    proc = subprocess.Popen(  # noqa: S603 - fixed argv list, shell=False
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(root),
        env=_hermetic_env(),
        shell=False,
        **popen_kw,
    )
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise RenderError("render_timeout", f"{timeout_s}s") from None
    except BaseException:
        _kill_tree(proc)
        raise

    elapsed_ms = int((time.time() - t0) * 1000)
    if proc.returncode != 0:
        tail = (err or b"").decode("utf-8", "replace")[-600:]
        raise RenderError("renderer_exit_nonzero", f"rc={proc.returncode} {tail}")
    return {
        "elapsed_ms": elapsed_ms,
        "stdout_tail": (out or b"").decode("utf-8", "replace")[-400:],
    }


# ------------------------------------------------------------------ provider
class HyperFramesProvider:
    """Creative OS provider contract: ``generate(spec) -> normalized_response``."""

    name = PROVIDER_NAME

    async def generate(self, spec: CreativeSpec) -> dict[str, Any]:
        from app.marketing.creative_os.providers import normalized_response

        t0 = time.time()

        def fail(code: str, detail: str = "", warnings: list[str] | None = None):
            return normalized_response(
                ok=False,
                provider=self.name,
                model=MODEL_NAME,
                model_revision=_pinned_version(),
                error=code,
                warnings=(warnings or []) + ([detail] if detail else []),
                timing_ms=int((time.time() - t0) * 1000),
            )

        lic = assert_provider_allowed(PROVIDER_NAME, MODEL_NAME)
        if not lic.get("ok"):
            return fail(str(lic.get("error") or "licence_blocked"))
        if not provider_enabled():
            return fail("provider_unavailable", "CREATIVE_PROVIDER_HYPERFRAMES_ENABLED off")
        if not tenant_allowed(spec.tenant_id):
            return fail("tenant_not_in_canary_allowlist")

        try:
            brand = _brand_facts(spec.tenant_id)
        except Exception as exc:
            logger.warning("[hyperframes] brand lookup failed: %s", exc)
            return fail("brand_lookup_failed")

        try:
            manifest = build_manifest(spec, brand=brand, template_id=_template_for(spec))
        except RenderError as exc:
            return fail(exc.code, exc.detail)

        tpl_dir = template_dir(manifest["template_id"])
        if tpl_dir is None:
            return fail("template_not_allowlisted", manifest["template_id"])

        out_dir = output_root()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return fail("output_dir_unavailable", str(exc)[:120])

        stem = f"hf_{_slug(spec.creative_id)}_r{int(spec.approval_revision or 0)}"
        output_path = (out_dir / f"{stem}.mp4").resolve()
        try:
            output_path.relative_to(out_dir.resolve())
        except ValueError:
            return fail("output_path_escapes_root")

        tmpdir = tempfile.mkdtemp(prefix="hfman_", dir=str(out_dir))
        manifest_path = Path(tmpdir) / "manifest.json"
        try:
            # Atomic write so a crashed worker cannot leave a half-parsed manifest.
            tmp = manifest_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(manifest["variables"], ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, manifest_path)

            run = _run_renderer(
                project_dir=tpl_dir,
                manifest_path=manifest_path,
                output_path=output_path,
                preset=manifest["resolution_preset"],
                timeout_s=render_timeout_s(),
            )
        except RenderError as exc:
            _unlink(output_path)
            return fail(exc.code, exc.detail)
        except Exception as exc:
            logger.warning("[hyperframes] render crashed: %s", exc)
            _unlink(output_path)
            return fail("render_exception", str(exc)[:160])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        if not output_path.is_file():
            return fail("output_missing")
        size_mb = output_path.stat().st_size / (1024 * 1024)
        if size_mb > max_output_mb():
            _unlink(output_path)
            return fail("output_too_large", f"{size_mb:.1f}MB")
        if output_path.stat().st_size < 50_000:
            _unlink(output_path)
            return fail("output_trivial", f"{output_path.stat().st_size}B")

        asset = {
            "path": str(output_path),
            "aspect_ratio": spec.aspect_ratio,
            "width": manifest["width"],
            "height": manifest["height"],
            "size_kb": int(output_path.stat().st_size / 1024),
            "template_id": manifest["template_id"],
            "template_version": manifest["template_version"],
            "manifest_hash": manifest_hash(manifest),
            "scene_count": (get_template(manifest["template_id"]) or {}).get("scene_count", 0),
            "photo_count": len(json.loads(manifest["variables"]["photos_json"] or "[]")),
            "renderer_version": _pinned_version(),
        }
        return normalized_response(
            ok=True,
            provider=self.name,
            model=MODEL_NAME,
            model_revision=_pinned_version(),
            assets=[asset],
            timing_ms=int(run.get("elapsed_ms") or (time.time() - t0) * 1000),
            cost_units=0,
        )


def _unlink(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(text or ""))[:48] or uuid.uuid4().hex[:12]


def _template_for(spec: CreativeSpec) -> str:
    """Caller-selected template, validated against the exact allowlist.

    An unrecognised value falls back to the configured default rather than
    reaching the renderer — `spec.template_id` is customer-adjacent input and
    must never behave like a path.
    """
    requested = str(getattr(spec, "template_id", "") or "")
    if requested and get_template(requested):
        return requested
    return default_template()


def _pinned_version() -> str:
    """Version read from the committed lockfile — the real pinned truth."""
    try:
        pkg = renderer_root() / "package.json"
        data = json.loads(pkg.read_text(encoding="utf-8"))
        return str((data.get("dependencies") or {}).get("hyperframes") or "unpinned")
    except Exception:
        return "unpinned"


def _brand_facts(tenant_id: str) -> dict[str, Any]:
    """Verified brand facts only — reuses the existing brief resolver.

    Nothing is invented here: every field either comes from the tenant's own
    record via ``brief.resolve_brand_profile`` or stays empty.
    """
    from app.marketing.creative_os.brief import resolve_brand_profile

    prof = resolve_brand_profile(tenant_id)
    contact = (
        prof.contact_display
        or prof.phone
        or (prof.socials.get("whatsapp") if prof.socials else "")
        or (prof.socials.get("instagram") if prof.socials else "")
    )
    return {
        "business_name": prof.business_name,
        "city": prof.city,
        "primary_color": prof.primary_color,
        "accent_color": prof.accent_color,
        "tagline": prof.tagline,
        "logo_text": prof.logo_text,
        "contact_display": contact,
        "offer_badge": prof.offer_badge,
        "verified_trust": prof.verified_trust,
        "verified_metrics": prof.verified_metrics,
        "kb_facts": prof.kb_facts,
        "services": prof.services,
    }


__all__ = [
    "MANIFEST_VERSION",
    "MODEL_NAME",
    "PROVIDER_NAME",
    "HyperFramesProvider",
    "RenderError",
    "build_manifest",
    "canary_tenants",
    "manifest_hash",
    "max_output_mb",
    "network_disabled",
    "output_root",
    "provider_enabled",
    "render_timeout_s",
    "tenant_allowed",
]
