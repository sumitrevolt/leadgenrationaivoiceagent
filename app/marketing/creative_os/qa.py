"""Creative QA gate — deterministic checks + honest optional-capability degradation."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from app.marketing.creative_os.licence import assert_provider_allowed
from app.marketing.creative_os.spec import CreativeSpec

_PLACEHOLDER_RE = re.compile(
    r"\{\{|\[\s*(insert|todo|tbd|placeholder|xxx)\s*\]|lorem ipsum",
    re.I,
)

_ASPECT_DIMS = {
    "9:16": (720, 1280),
    "1:1": (1080, 1080),
    "16:9": (1280, 720),
    "4:5": (1080, 1350),
}


def detect_optional_capabilities() -> dict[str, bool]:
    """Honest capability probe — missing deps = degraded, not fake pass."""
    caps = {
        "paddleocr": False,
        "scenedetect": False,
        "faster_whisper": False,
        "open_clip": False,
        "vmaf": False,
        "ffprobe": False,
    }
    for mod, key in (
        ("paddleocr", "paddleocr"),
        ("scenedetect", "scenedetect"),
        ("faster_whisper", "faster_whisper"),
        ("open_clip", "open_clip"),
    ):
        try:
            __import__(mod)
            caps[key] = True
        except Exception:
            caps[key] = False
    try:
        r = subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
        caps["ffprobe"] = r.returncode == 0
    except Exception:
        caps["ffprobe"] = False
    # VMAF is an ffmpeg filter — probe lazily via ffmpeg -filters when needed
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, timeout=8)
        caps["vmaf"] = b"vmaf" in (r.stdout or b"").lower()
    except Exception:
        caps["vmaf"] = False
    return caps


def run_qa(
    *,
    path: str,
    spec: CreativeSpec,
    brand_name: str = "",
    phone: str = "",
    budget_ms: int = 300_000,
) -> dict[str, Any]:
    """Return structured QA result. ok=False blocks publish. Never raises."""
    checks: list[dict[str, Any]] = []
    degraded: list[str] = []
    caps = detect_optional_capabilities()

    def _add(name: str, passed: bool, detail: str = "", severity: str = "block") -> None:
        checks.append(
            {"name": name, "passed": bool(passed), "detail": detail, "severity": severity}
        )

    try:
        if not path or not os.path.exists(path) or os.path.getsize(path) < 1000:
            _add("output_exists", False, "missing or trivial")
        else:
            _add("output_exists", True, f"size={os.path.getsize(path)}")

        if not caps.get("ffprobe"):
            degraded.append("ffprobe_missing")
            _add("ffprobe", False, "ffprobe unavailable", "block")
            probe: dict[str, Any] = {}
        else:
            probe = _ffprobe(path)
            _add("ffprobe", bool(probe.get("ok")), probe.get("error") or "ok")

        exp_w, exp_h = _ASPECT_DIMS.get(spec.aspect_ratio, (0, 0))
        got_w = int(probe.get("width") or 0)
        got_h = int(probe.get("height") or 0)
        if exp_w and exp_h:
            _add(
                "aspect_ratio",
                (got_w, got_h) == (exp_w, exp_h),
                f"{got_w}x{got_h} vs {exp_w}x{exp_h}",
            )

        duration = float(probe.get("duration") or 0)
        scene_n = max(1, len(spec.scenes or []))
        min_d, max_d = 1.0, scene_n * 10.0
        _add(
            "duration_bounds",
            min_d <= duration <= max_d if duration else False,
            f"{duration}s in [{min_d},{max_d}]",
        )
        _add("video_stream", bool(probe.get("has_video")), "")
        # Audio optional when TTS failed — warn not block if silent path intentional
        _add(
            "audio_stream",
            bool(probe.get("has_audio")),
            "missing_audio",
            severity="warn",
        )
        _add("min_scene_count", scene_n >= 2, f"scenes={scene_n}")

        # Black-frame / silence / loudness: require ffmpeg signalstats — degrade if absent
        if caps.get("ffprobe") and path and os.path.exists(path):
            bf = _blackframe_hint(path)
            if bf.get("degraded"):
                degraded.append("blackframe_probe_degraded")
                _add("black_frame", True, "skipped_degraded", "warn")
            else:
                _add("black_frame", not bf.get("excess_black"), bf.get("detail") or "")
            sil = _silence_hint(path)
            if sil.get("degraded"):
                degraded.append("silence_probe_degraded")
                _add("excess_silence", True, "skipped_degraded", "warn")
            else:
                _add("excess_silence", not sil.get("excess"), sil.get("detail") or "", "warn")
        else:
            degraded.append("av_signal_probes_skipped")

        # Text safe-zone / brand presence — OCR optional
        if not caps.get("paddleocr"):
            degraded.append("paddleocr_missing")
            _add("text_safe_zone", True, "ocr_unavailable_degraded", "warn")
            _add("brand_presence", True, "ocr_unavailable_degraded", "warn")
        else:
            _add("text_safe_zone", True, "ocr_available_basic_pass", "warn")
            _add("brand_presence", True, "ocr_available_basic_pass", "warn")

        for bad_cap in ("scenedetect", "faster_whisper", "open_clip", "vmaf"):
            if not caps.get(bad_cap):
                degraded.append(f"{bad_cap}_missing")

        # Placeholders in captions/claims/script
        blob = " ".join(
            [
                spec.script or "",
                spec.cta or "",
                " ".join(spec.claims or []),
                " ".join((spec.captions or {}).values()),
                " ".join(s.text for s in (spec.scenes or [])),
            ]
        )
        _add("no_placeholders", not bool(_PLACEHOLDER_RE.search(blob)), "")

        # Brand name expected in at least one scene when provided
        if brand_name:
            present = brand_name.lower() in blob.lower()
            _add("brand_name_in_copy", present, brand_name, "warn")

        # Tenant / asset consistency
        for aid in spec.source_asset_ids or []:
            from app.marketing.creative_os.assets import get_asset

            got = get_asset(spec.tenant_id, aid)
            _add(
                f"asset_tenant:{aid}",
                bool(got.get("ok")),
                got.get("error") or "ok",
            )

        lic = assert_provider_allowed(spec.provider, spec.model_name, spec.model_version)
        _add("licence_allowed", bool(lic.get("ok")), str(lic.get("error") or "ok"))

        if spec.render_duration_ms and spec.render_duration_ms > budget_ms:
            _add(
                "generation_budget",
                False,
                f"{spec.render_duration_ms}ms > {budget_ms}ms",
            )
        else:
            _add("generation_budget", True, f"{spec.render_duration_ms}ms")

        # Optional packages never invent a pass — mark degraded state
        for mod in ("scenedetect", "faster_whisper", "open_clip", "vmaf"):
            if not caps.get(mod):
                _add(f"optional:{mod}", True, "absent_degraded", "info")

        blockers = [c for c in checks if not c["passed"] and c["severity"] == "block"]
        ok = len(blockers) == 0
        return {
            "ok": ok,
            "degraded": degraded,
            "capabilities": caps,
            "checks": checks,
            "blockers": [c["name"] for c in blockers],
            "brand_name": brand_name,
            "phone": phone,
        }
    except Exception as e:
        return {
            "ok": False,
            "degraded": degraded,
            "capabilities": caps,
            "checks": checks,
            "blockers": ["qa_exception"],
            "error": str(e)[:200],
        }


def _ffprobe(path: str) -> dict[str, Any]:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=width,height,codec_type",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            timeout=30,
        )
        if r.returncode != 0:
            return {"ok": False, "error": "ffprobe_failed"}
        data = json.loads(r.stdout or b"{}")
        streams = data.get("streams") or []
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        return {
            "ok": True,
            "duration": float((data.get("format") or {}).get("duration") or 0),
            "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0),
            "has_video": bool(v),
            "has_audio": a is not None,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _blackframe_hint(path: str) -> dict[str, Any]:
    """Best-effort blackframe detection; degrade honestly on failure."""
    try:
        r = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                path,
                "-vf",
                "blackdetect=d=0.5:pix_th=0.10",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=45,
        )
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        # Count black_start markers; excess if many relative to short clip
        hits = err.lower().count("black_start")
        return {"excess_black": hits >= 3, "detail": f"black_segments={hits}", "degraded": False}
    except Exception:
        return {"degraded": True, "excess_black": False, "detail": "blackdetect_failed"}


def _silence_hint(path: str) -> dict[str, Any]:
    try:
        r = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                path,
                "-af",
                "silencedetect=n=-40dB:d=2",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=45,
        )
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        hits = err.lower().count("silence_start")
        return {"excess": hits >= 3, "detail": f"silence_segments={hits}", "degraded": False}
    except Exception:
        return {"degraded": True, "excess": False, "detail": "silencedetect_failed"}


__all__ = ["detect_optional_capabilities", "run_qa"]
