"""Enterprise deliverable gate — decides what may be sold to a customer.

This layer sits ON TOP of `creative_os.qa.run_qa`; it does not replace it and it
does not fork the QA lifecycle. `run_qa` answers "is this file a valid, correctly
shaped, non-black video?". This module answers a different, commercial question:
"is this good enough to put in front of a paying customer as agency work?"

Separating them is the whole point. The deterministic FFmpeg provider's flat-text
720p output is a perfectly VALID video — it passes `run_qa` — but it is not an
enterprise deliverable. Folding the 1080 floor into `run_qa` would have failed
that provider outright and broken the existing pipeline; keeping it here lets the
same artifact be truthfully labelled DRAFT_ONLY instead.

Classification vocabulary (Phase 7 of the integration contract):

    CUSTOMER_APPROVABLE  — meets the full contract; may enter the approval queue
    DRAFT_ONLY           — a real video, but internal-grade only
    NEEDS_CUSTOMER_INPUT — blocked on a missing verified customer fact/asset
    QUARANTINED          — failed in a way that implies a defect or a policy breach

Nothing here approves or publishes anything; it only labels.
"""

from __future__ import annotations

import json
import os
import re
import subprocess  # noqa: S404 - fixed argv ffprobe, never shell=True
from typing import Any

CUSTOMER_APPROVABLE = "CUSTOMER_APPROVABLE"
DRAFT_ONLY = "DRAFT_ONLY"
NEEDS_CUSTOMER_INPUT = "NEEDS_CUSTOMER_INPUT"
QUARANTINED = "QUARANTINED"

# Full-HD floor. A vertical deliverable below this is a draft, not agency work.
MIN_PIXELS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

REQUIRED_VIDEO_CODEC = "h264"
REQUIRED_PIX_FMT = "yuv420p"
ALLOWED_PROFILES = frozenset({"High", "Main", "High 10"})
REQUIRED_FPS = 30.0
MIN_DURATION_S = 6.0
MAX_DURATION_S = 90.0
# 1080x1920 animated gradient content encodes efficiently; the floor catches a
# genuinely starved encode (the 22 kbps all-black failure this gate was built
# after), not merely an efficient one.
MIN_VIDEO_BITRATE_BPS = 600_000

# Internal identifiers that must never reach a customer's screen. `beauty_makeover`
# is jiya's niche KEY in clients_store — a real field name that reads as a slug.
_INTERNAL_TOKEN_RE = re.compile(
    r"\b(beauty_makeover|test_tenant|lorem ipsum|tbd|todo|placeholder|xxx|"
    r"undefined|null|nan|\{\{|\}\})\b",
    re.I,
)

_REMOTE_URL_RE = re.compile(r"\b(?:https?:)?//", re.I)


def _probe(path: str) -> dict[str, Any]:
    """Full ffprobe read. Failure is a refusal, never an assumed pass."""
    try:
        r = subprocess.run(  # noqa: S603 - fixed argv
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size,bit_rate,format_name:"
                "stream=codec_name,codec_type,profile,width,height,pix_fmt,"
                "r_frame_rate,bit_rate,sample_rate,channels",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if r.returncode != 0:
            return {"ok": False, "error": "ffprobe_failed"}
        data = json.loads(r.stdout or b"{}")
        fmt = data.get("format") or {}
        streams = data.get("streams") or []
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)

        fps = 0.0
        raw_fps = str(v.get("r_frame_rate") or "0/1")
        if "/" in raw_fps:
            num, den = raw_fps.split("/", 1)
            try:
                fps = float(num) / float(den) if float(den) else 0.0
            except (ValueError, ZeroDivisionError):
                fps = 0.0

        vbr = int(v.get("bit_rate") or 0)
        if not vbr:
            # Many muxers omit per-stream bitrate; derive from container size.
            try:
                dur = float(fmt.get("duration") or 0)
                vbr = int(int(fmt.get("size") or 0) * 8 / dur) if dur > 0 else 0
            except (ValueError, ZeroDivisionError):
                vbr = 0

        return {
            "ok": True,
            "duration": float(fmt.get("duration") or 0),
            "size": int(fmt.get("size") or 0),
            "format_name": str(fmt.get("format_name") or ""),
            "codec": str(v.get("codec_name") or ""),
            "profile": str(v.get("profile") or ""),
            "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0),
            "pix_fmt": str(v.get("pix_fmt") or ""),
            "fps": fps,
            "video_bitrate": vbr,
            "has_audio": a is not None,
            "audio_codec": str((a or {}).get("codec_name") or ""),
            "audio_sample_rate": int((a or {}).get("sample_rate") or 0),
            "audio_channels": int((a or {}).get("channels") or 0),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


def _c(name: str, ok: bool, detail: str = "", *, blocking: bool = True) -> dict[str, Any]:
    return {"name": name, "passed": bool(ok), "detail": detail, "blocking": bool(blocking)}


def evaluate(
    *,
    path: str,
    spec: Any,
    provider_asset: dict[str, Any] | None = None,
    require_audio: bool = False,
) -> dict[str, Any]:
    """Classify one rendered artifact against the enterprise contract.

    Returns ``{classification, customer_approvable, checks, blockers, probe}``.
    """
    asset = dict(provider_asset or {})
    checks: list[dict[str, Any]] = []

    if not path or not os.path.isfile(path):
        return _result(QUARANTINED, [_c("output_exists", False, "missing")], {})

    probe = _probe(path)
    if not probe.get("ok"):
        return _result(
            QUARANTINED,
            [_c("ffprobe", False, str(probe.get("error") or "probe_failed"))],
            {},
        )

    aspect = str(getattr(spec, "aspect_ratio", "") or "9:16")
    min_w, min_h = MIN_PIXELS.get(aspect, (0, 0))
    got_w, got_h = probe["width"], probe["height"]

    # --- resolution floor: THE line between a draft and a deliverable -------
    checks.append(
        _c(
            "fullhd_resolution",
            bool(min_w) and got_w >= min_w and got_h >= min_h,
            f"{got_w}x{got_h} vs min {min_w}x{min_h}",
        )
    )
    checks.append(_c("codec_h264", probe["codec"] == REQUIRED_VIDEO_CODEC, probe["codec"]))
    checks.append(_c("profile_allowed", probe["profile"] in ALLOWED_PROFILES, probe["profile"]))
    checks.append(_c("pix_fmt_yuv420p", probe["pix_fmt"] == REQUIRED_PIX_FMT, probe["pix_fmt"]))
    checks.append(_c("fps_30", abs(probe["fps"] - REQUIRED_FPS) < 0.05, f"{probe['fps']:.3f}"))
    checks.append(
        _c(
            "duration_bounds",
            MIN_DURATION_S <= probe["duration"] <= MAX_DURATION_S,
            f"{probe['duration']:.2f}s",
        )
    )
    checks.append(
        _c(
            "video_bitrate_floor",
            probe["video_bitrate"] >= MIN_VIDEO_BITRATE_BPS,
            f"{probe['video_bitrate']}bps",
        )
    )
    checks.append(_c("faststart_mp4", "mp4" in probe["format_name"], probe["format_name"]))

    # --- audio: only enforced when the deliverable is supposed to have it ---
    if require_audio:
        checks.append(_c("audio_present", probe["has_audio"], probe["audio_codec"]))
        checks.append(
            _c("audio_48k", probe["audio_sample_rate"] == 48_000, str(probe["audio_sample_rate"]))
        )
    else:
        checks.append(
            _c("audio_optional", True, "audio not required for this deliverable", blocking=False)
        )

    # --- design substance: separates real motion design from a text card ---
    scene_count = int(asset.get("scene_count") or 0)
    checks.append(_c("scene_count_min", scene_count >= 4, f"scenes={scene_count}"))
    checks.append(
        _c(
            "animated_template",
            bool(asset.get("template_id")) and bool(asset.get("template_version")),
            f"{asset.get('template_id')}@{asset.get('template_version')}",
        )
    )
    checks.append(
        _c("manifest_bound", bool(asset.get("manifest_hash")), "render manifest hash present")
    )

    # --- copy hygiene ------------------------------------------------------
    blob = " ".join(
        [
            str(getattr(spec, "script", "") or ""),
            str(getattr(spec, "cta", "") or ""),
            str(getattr(spec, "offer", "") or ""),
            " ".join(str(v) for v in (getattr(spec, "captions", {}) or {}).values()),
            " ".join(str(getattr(s, "text", "")) for s in (getattr(spec, "scenes", []) or [])),
        ]
    )
    internal = _INTERNAL_TOKEN_RE.findall(blob)
    checks.append(
        _c("no_internal_identifiers", not internal, ",".join(sorted(set(internal)))[:120])
    )
    checks.append(_c("cta_present", bool(str(getattr(spec, "cta", "") or "").strip()), ""))
    checks.append(
        _c(
            "no_remote_asset_url",
            not _REMOTE_URL_RE.search(blob),
            "copy references a remote URL",
        )
    )

    # --- provenance --------------------------------------------------------
    # A fallback provider reaching this gate means the customer asked for one
    # thing and got another; that is never silently approvable.
    fallback_from = str(getattr(spec, "fallback_from", "") or "")
    checks.append(_c("no_unexpected_fallback", not fallback_from, fallback_from))

    blockers = [c["name"] for c in checks if c["blocking"] and not c["passed"]]

    if not blockers:
        return _result(CUSTOMER_APPROVABLE, checks, probe)

    # A dimension/codec/substance miss is a legitimate-but-internal artifact.
    # A corrupt or policy-violating one is a quarantine.
    quarantine_triggers = {"no_internal_identifiers", "no_remote_asset_url", "faststart_mp4"}
    if quarantine_triggers.intersection(blockers):
        return _result(QUARANTINED, checks, probe)
    return _result(DRAFT_ONLY, checks, probe)


def _result(classification: str, checks: list[dict[str, Any]], probe: dict[str, Any]):
    return {
        "classification": classification,
        "customer_approvable": classification == CUSTOMER_APPROVABLE,
        "checks": checks,
        "blockers": [c["name"] for c in checks if c.get("blocking") and not c.get("passed")],
        "probe": probe,
    }


__all__ = [
    "CUSTOMER_APPROVABLE",
    "DRAFT_ONLY",
    "MIN_PIXELS",
    "NEEDS_CUSTOMER_INPUT",
    "QUARANTINED",
    "evaluate",
]
