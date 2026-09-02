"""Creative QA gate — truthful evidence; optional checks never fake-pass."""

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

# Every dimension pair that is a CORRECTLY-SHAPED render for an aspect ratio.
# This gate only answers "is the frame the right shape?" — the deterministic
# provider's 720x1280 and a HyperFrames 1080x1920 are both legitimately 9:16.
# It deliberately does NOT decide "is this good enough to sell": the 1080 floor
# for a customer deliverable lives in `enterprise_qa`, which is what keeps a
# 720p draft out of the approvable path without failing it here.
_ASPECT_DIMS: dict[str, tuple[tuple[int, int], ...]] = {
    "9:16": ((720, 1280), (1080, 1920)),
    "1:1": ((1080, 1080),),
    "16:9": ((1280, 720), (1920, 1080)),
    "4:5": ((1080, 1350),),
}

# Phase-1 blocking policy: only these severities fail the gate when result=failed
_BLOCK_ON = frozenset({"block"})


def detect_optional_capabilities() -> dict[str, bool]:
    """Presence-only probe — never import heavy native stacks (torch/paddle/clip).

    Phase-1 evaluators are not wired; callers must treat optional ML caps as
    ``not_evaluated`` when present, never as a fake pass. ``find_spec`` avoids
    loading native extensions that have segfaulted CI TestClient lifespans.
    """
    import importlib.util

    caps = {
        "paddleocr": False,
        "scenedetect": False,
        "faster_whisper": False,
        "open_clip": False,
        "vmaf": False,
        "ffprobe": False,
        "ffmpeg": False,
    }
    for mod, key in (
        ("paddleocr", "paddleocr"),
        ("scenedetect", "scenedetect"),
        ("faster_whisper", "faster_whisper"),
        ("open_clip", "open_clip"),
    ):
        try:
            caps[key] = importlib.util.find_spec(mod) is not None
        except Exception:
            caps[key] = False
    try:
        r = subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
        caps["ffprobe"] = r.returncode == 0
    except Exception:
        caps["ffprobe"] = False
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        caps["ffmpeg"] = r.returncode == 0
    except Exception:
        caps["ffmpeg"] = False
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, timeout=8)
        caps["vmaf"] = b"vmaf" in (r.stdout or b"").lower()
    except Exception:
        caps["vmaf"] = False
    return caps


def _check(
    name: str,
    result: str,
    *,
    detail: str = "",
    severity: str = "block",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """result ∈ passed|failed|degraded_missing_dependency|not_evaluated"""
    return {
        "name": name,
        "result": result,
        "passed": result == "passed",
        "detail": detail,
        "severity": severity,
        "evidence": evidence or {},
    }


def run_qa(
    *,
    path: str,
    spec: CreativeSpec,
    brand_name: str = "",
    phone: str = "",
    budget_ms: int = 300_000,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    degraded: list[str] = []
    caps = detect_optional_capabilities()

    try:
        if not path or not os.path.exists(path) or os.path.getsize(path) < 1000:
            checks.append(_check("output_exists", "failed", detail="missing or trivial"))
        else:
            checks.append(
                _check(
                    "output_exists",
                    "passed",
                    detail=f"size={os.path.getsize(path)}",
                    evidence={"bytes": os.path.getsize(path)},
                )
            )

        if not caps.get("ffprobe"):
            degraded.append("ffprobe_missing")
            checks.append(
                _check(
                    "ffprobe",
                    "degraded_missing_dependency",
                    detail="ffprobe unavailable",
                    severity="block",
                )
            )
            probe: dict[str, Any] = {}
        else:
            probe = _ffprobe(path)
            checks.append(
                _check(
                    "ffprobe",
                    "passed" if probe.get("ok") else "failed",
                    detail=probe.get("error") or "ok",
                    evidence=probe,
                )
            )

        allowed_dims = _ASPECT_DIMS.get(spec.aspect_ratio, ())
        got_w = int(probe.get("width") or 0)
        got_h = int(probe.get("height") or 0)
        if allowed_dims:
            expected_str = " or ".join(f"{w}x{h}" for w, h in allowed_dims)
            checks.append(
                _check(
                    "aspect_ratio",
                    "passed" if (got_w, got_h) in allowed_dims else "failed",
                    detail=f"{got_w}x{got_h} vs {expected_str}",
                    evidence={
                        "got": [got_w, got_h],
                        "allowed": [list(d) for d in allowed_dims],
                    },
                )
            )

        duration = float(probe.get("duration") or 0)
        scene_n = max(1, len(spec.scenes or []))
        min_d, max_d = 1.0, scene_n * 10.0
        checks.append(
            _check(
                "duration_bounds",
                "passed" if duration and min_d <= duration <= max_d else "failed",
                detail=f"{duration}s in [{min_d},{max_d}]",
                evidence={"duration_s": duration},
            )
        )
        checks.append(
            _check("video_stream", "passed" if probe.get("has_video") else "failed", detail="")
        )
        checks.append(
            _check(
                "audio_stream",
                "passed" if probe.get("has_audio") else "failed",
                detail="missing_audio",
                severity="warn",
            )
        )
        checks.append(
            _check(
                "min_scene_count",
                "passed" if scene_n >= 2 else "failed",
                detail=f"scenes={scene_n}",
            )
        )

        # Black-frame with info-level logs so markers are visible
        if caps.get("ffmpeg") and path and os.path.exists(path):
            bf = _blackframe_probe(path, duration)
            checks.append(
                _check(
                    "black_frame",
                    bf["result"],
                    detail=bf.get("detail") or "",
                    severity="block",
                    evidence=bf.get("evidence"),
                )
            )
            if bf["result"] == "degraded_missing_dependency":
                degraded.append("blackframe_probe_degraded")
            sil = _silence_probe(path, duration, has_audio=bool(probe.get("has_audio")))
            checks.append(
                _check(
                    "excess_silence",
                    sil["result"],
                    detail=sil.get("detail") or "",
                    severity="warn",
                    evidence=sil.get("evidence"),
                )
            )
            if sil["result"] == "degraded_missing_dependency":
                degraded.append("silence_probe_degraded")
        else:
            degraded.append("ffmpeg_missing")
            checks.append(
                _check(
                    "black_frame",
                    "degraded_missing_dependency",
                    detail="ffmpeg unavailable",
                    severity="block",
                )
            )
            checks.append(
                _check(
                    "excess_silence",
                    "degraded_missing_dependency",
                    detail="ffmpeg unavailable",
                    severity="warn",
                )
            )

        # Optional OCR / scene / whisper / clip / vmaf — never fake pass
        for name, key in (
            ("text_safe_zone", "paddleocr"),
            ("brand_presence_ocr", "paddleocr"),
            ("scenedetect", "scenedetect"),
            ("faster_whisper", "faster_whisper"),
            ("open_clip", "open_clip"),
            ("vmaf", "vmaf"),
        ):
            if not caps.get(key):
                degraded.append(f"{key}_missing")
                checks.append(
                    _check(
                        name,
                        "degraded_missing_dependency",
                        detail=f"{key} absent",
                        severity="info",
                    )
                )
            else:
                # Installed but Phase-1 evaluation not implemented → not_evaluated
                checks.append(
                    _check(
                        name,
                        "not_evaluated",
                        detail=f"{key} installed; phase1 evaluator not wired",
                        severity="info",
                    )
                )

        blob = " ".join(
            [
                spec.script or "",
                spec.cta or "",
                " ".join(spec.claims or []),
                " ".join((spec.captions or {}).values()),
                " ".join(s.text for s in (spec.scenes or [])),
            ]
        )
        checks.append(
            _check(
                "no_placeholders",
                "passed" if not _PLACEHOLDER_RE.search(blob) else "failed",
                detail="",
            )
        )
        if brand_name:
            checks.append(
                _check(
                    "brand_name_in_copy",
                    "passed" if brand_name.lower() in blob.lower() else "failed",
                    detail=brand_name,
                    severity="warn",
                )
            )

        for aid in spec.source_asset_ids or []:
            from app.marketing.creative_os.assets import get_asset

            got = get_asset(spec.tenant_id, aid)
            checks.append(
                _check(
                    f"asset_tenant:{aid}",
                    "passed" if got.get("ok") else "failed",
                    detail=str(got.get("error") or "ok"),
                )
            )

        lic = assert_provider_allowed(spec.provider, spec.model_name, spec.model_version)
        checks.append(
            _check(
                "licence_allowed",
                "passed" if lic.get("ok") else "failed",
                detail=str(lic.get("error") or "ok"),
                evidence={"snapshot": lic.get("snapshot") or {}},
            )
        )

        if spec.render_duration_ms and spec.render_duration_ms > budget_ms:
            checks.append(
                _check(
                    "generation_budget",
                    "failed",
                    detail=f"{spec.render_duration_ms}ms > {budget_ms}ms",
                )
            )
        else:
            checks.append(
                _check(
                    "generation_budget",
                    "passed",
                    detail=f"{spec.render_duration_ms}ms",
                )
            )

        blockers = [
            c["name"] for c in checks if c["result"] == "failed" and c["severity"] in _BLOCK_ON
        ]
        # Missing ffprobe/ffmpeg for block-severity probes also blocks
        blockers += [
            c["name"]
            for c in checks
            if c["result"] == "degraded_missing_dependency"
            and c["severity"] in _BLOCK_ON
            and c["name"] in ("ffprobe", "black_frame", "output_exists")
        ]
        ok = len(blockers) == 0
        return {
            "ok": ok,
            "degraded": degraded,
            "capabilities": caps,
            "checks": checks,
            "blockers": blockers,
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
            return {"ok": False, "error": "ffprobe_failed", "returncode": r.returncode}
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
            "returncode": r.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _blackframe_probe(path: str, duration_s: float) -> dict[str, Any]:
    """Use info log level so blackdetect markers are emitted."""
    try:
        r = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "info",
                "-i",
                path,
                "-vf",
                "blackdetect=d=0.5:pix_th=0.10",
                "-an",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=60,
        )
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        if r.returncode not in (0,):
            # null mux often returns 0; non-zero = real failure
            if "blackdetect" not in err.lower() and r.returncode != 0:
                return {
                    "result": "degraded_missing_dependency",
                    "detail": f"ffmpeg_rc={r.returncode}",
                    "evidence": {"returncode": r.returncode, "stderr_tail": err[-400:]},
                }
        # Parse black_start / black_duration markers
        import re as _re

        segs = []
        for m in _re.finditer(
            r"black_start:(?P<start>[0-9.]+)\s+black_end:(?P<end>[0-9.]+)\s+black_duration:(?P<dur>[0-9.]+)",
            err,
        ):
            segs.append(float(m.group("dur")))
        # Fallback: count starts if duration form missing
        if not segs:
            starts = err.lower().count("black_start")
            # Without parseable durations, do NOT treat as pass — not_evaluated-ish fail-soft warn
            if starts == 0 and "blackdetect" in err.lower():
                # filter ran, no black — pass
                total_black = 0.0
            elif starts == 0:
                return {
                    "result": "degraded_missing_dependency",
                    "detail": "no_blackdetect_markers_in_log",
                    "evidence": {"returncode": r.returncode, "stderr_tail": err[-400:]},
                }
            else:
                total_black = float(starts) * 0.5  # conservative lower bound
        else:
            total_black = sum(segs)
        pct = (total_black / duration_s * 100.0) if duration_s > 0 else 0.0
        excess = pct >= 40.0 or total_black >= max(2.0, duration_s * 0.4)
        return {
            "result": "failed" if excess else "passed",
            "detail": f"black_s={total_black:.2f} pct={pct:.1f}",
            "evidence": {
                "returncode": r.returncode,
                "black_duration_s": total_black,
                "black_pct": pct,
                "segments": len(segs),
            },
        }
    except Exception as e:
        return {
            "result": "degraded_missing_dependency",
            "detail": str(e)[:120],
            "evidence": {},
        }


def _silence_probe(path: str, duration_s: float, *, has_audio: bool) -> dict[str, Any]:
    if not has_audio:
        return {
            "result": "not_evaluated",
            "detail": "no_audio_stream",
            "evidence": {"has_audio": False},
        }
    try:
        r = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "info",
                "-i",
                path,
                "-af",
                "silencedetect=n=-40dB:d=1",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=60,
        )
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        import re as _re

        durs = [float(x) for x in _re.findall(r"silence_duration:\s*([0-9.]+)", err)]
        if not durs and "silencedetect" not in err.lower() and "silence_start" not in err.lower():
            return {
                "result": "degraded_missing_dependency",
                "detail": "no_silencedetect_markers_in_log",
                "evidence": {"returncode": r.returncode, "stderr_tail": err[-400:]},
            }
        total = sum(durs) if durs else 0.0
        pct = (total / duration_s * 100.0) if duration_s > 0 else 0.0
        excess = pct >= 50.0
        return {
            "result": "failed" if excess else "passed",
            "detail": f"silence_s={total:.2f} pct={pct:.1f}",
            "evidence": {
                "returncode": r.returncode,
                "silence_duration_s": total,
                "silence_pct": pct,
                "intervals": len(durs),
            },
        }
    except Exception as e:
        return {
            "result": "degraded_missing_dependency",
            "detail": str(e)[:120],
            "evidence": {},
        }


__all__ = ["detect_optional_capabilities", "run_qa"]
