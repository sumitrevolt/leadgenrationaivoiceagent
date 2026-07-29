"""Call-time authority for where approved video bytes may legitimately live.

The publish gate has to answer one question — "is this path a real artifact this
system produced?" — and it must answer it the same way in a container, on a dev
box, and under a test that redirects the renderer's output directory.

Import-time, CWD-relative constants cannot do that: they freeze one answer at
process start and silently mis-resolve if the working directory differs. Every
root here is therefore resolved **per call**, from:

  1. ``runtime_data_authority`` — the canonical store-path authority (same seam
     ``runtime_recording_paths`` uses), when the store is declared there; else
  2. the renderer's own public accessor (``video_pipeline.output_root()``), so a
     runtime or test override of the render directory is honoured; else
  3. a REPOSITORY-anchored default derived from this module's location — never
     ``Path.cwd()``.
"""

from __future__ import annotations

from pathlib import Path

# app/marketing/video_media_paths.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_data(*segments: str) -> Path:
    return _REPO_ROOT.joinpath("data", *segments)


def _authority_path(store_id: str, legacy: Path, segments: tuple[str, ...]) -> Path | None:
    """Canonical store path, or None when the authority cannot resolve it."""
    try:
        from app.platform import runtime_data_authority as _auth

        return _auth.resolve_store_path(
            store_id=store_id, legacy_path=legacy, target_segments=segments
        )
    except Exception:
        return None


def reels_dir() -> Path:
    """Active render output directory (``video_pipeline`` writes here)."""
    try:
        from app.marketing import video_pipeline

        root = str(video_pipeline.output_root() or "").strip()
        if root:
            p = Path(root)
            return p if p.is_absolute() else (_REPO_ROOT / p)
    except Exception:
        pass
    return _authority_path("artifacts.reels", _repo_data("reels"), ("artifacts", "reels")) or (
        _repo_data("reels")
    )


def video_ads_dir() -> Path:
    """Video-ad artifact directory (``data/video_ads/`` in the manifest)."""
    return _authority_path(
        "artifacts.video_ads", _repo_data("video_ads"), ("artifacts", "video_ads")
    ) or _repo_data("video_ads")


def approved_media_dir() -> Path:
    """Immutable approved-snapshot root (TOCTOU follow-up slice)."""
    return video_ads_dir() / "_approved"


def media_roots() -> tuple[Path, ...]:
    """Every root an approvable artifact may live under — resolved NOW."""
    roots: list[Path] = []
    for fn in (video_ads_dir, reels_dir, approved_media_dir):
        try:
            r = fn().resolve()
        except Exception:
            continue
        if r not in roots:
            roots.append(r)
    return tuple(roots)


def resolve_video_media_file(path: str) -> Path | None:
    """THE resolver. Returns a trusted absolute Path, or None (refusal).

    Owns, in one place, everything every consumer needs:
      * call-time root lookup (never an import-time CWD snapshot),
      * strict resolution (``..`` collapsed, missing path refused),
      * containment inside a configured root,
      * regular-file validation (directories/fifos/sockets refused),
      * symlink-component policy,
      * a stable refusal contract: ``None`` means "not a trusted artifact",
        with no partial/ambiguous success value.

    Symlink policy: ANY symlink component between the configured root and the
    file is refused, not merely ones that currently escape the root — an in-root
    symlink can be retargeted after approval. NOTE this is *policy* validation,
    not race protection: the path can still change after this returns. Race
    safety belongs to the snapshot step (open once, copy and ``fstat`` through
    the same descriptor).
    """
    raw = str(path or "").strip()
    if not raw:
        return None

    roots = media_roots()
    if not roots:
        return None

    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            # WRITER CONTRACT (verified against all 36 production records):
            # a stored relative path always carries its media-root prefix, e.g.
            # "data/video_ads/x.mp4". A BARE name like "fixture.mp4" is not a
            # shape the canonical writer emits, so it is refused rather than
            # hunted for across roots — root discovery would be a new, wider
            # contract and could bind approval to the wrong tenant's file.
            if len(candidate.parts) < 2:
                return None
            # Anchor relatives to the repo, never to the process CWD.
            candidate = _REPO_ROOT / candidate
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None

    try:
        if not resolved.is_file():
            return None
    except OSError:
        return None

    contained = False
    for root in roots:
        try:
            resolved.relative_to(root)
            contained = True
            break
        except ValueError:
            continue
    if not contained:
        return None

    try:
        for part in (candidate, *candidate.parents):
            if part in roots:
                break
            if part.is_symlink():
                return None
    except OSError:
        return None

    return resolved


__all__ = [
    "approved_media_dir",
    "media_roots",
    "reels_dir",
    "resolve_video_media_file",
    "video_ads_dir",
]
