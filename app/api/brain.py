"""Operator-facing Second Brain — admin search/browse over the Obsidian vault.

The agents accumulate notes (Decisions/Leads/Sessions/Agents/System…) in
`data/obsidian_staging/` and read them back via `obsidian_sync.recall()`, but the
OPERATOR had no in-app surface — so the brain felt "unused". This router exposes
it: search (recall), recent, and stats. Read-only, admin-gated, never raises.
Self-gating: when OBSIDIAN_SYNC is unset, `recall()` returns [] (brain disabled).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/admin/brain", tags=["Brain"])


def _excerpt(txt: str, n: int = 300) -> str:
    body = txt
    if txt.startswith("---"):
        end = txt.find("---", 3)
        if end != -1:
            body = txt[end + 3 :].lstrip()
    return body[:n].replace("\n", " ").strip()


def _fmt(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@router.get("/search", summary="Search the second brain (word-overlap over vault notes)")
async def brain_search(q: str = "", k: int = 8, _user=Depends(require_admin)) -> dict[str, Any]:
    from app.platform import obsidian_sync

    if not (q or "").strip():
        return {"query": q, "enabled": obsidian_sync._enabled(), "results": []}
    results = obsidian_sync.recall(q, max(1, min(int(k or 8), 25)))
    return {"query": q, "enabled": obsidian_sync._enabled(), "results": results}


@router.get("/recent", summary="Recently-written brain notes (optional folder filter)")
async def brain_recent(
    folder: str = "", limit: int = 20, _user=Depends(require_admin)
) -> dict[str, Any]:
    from app.platform import obsidian_sync

    v: Path = obsidian_sync._VAULT
    out: list[dict[str, Any]] = []
    try:
        if v.exists():
            files = [p for p in v.rglob("*.md") if p.parent != v]
            if folder:
                files = [p for p in files if p.parent.name.lower() == folder.strip().lower()]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for p in files[: max(1, min(int(limit or 20), 100))]:
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    out.append(
                        {
                            "folder": p.parent.name,
                            "slug": p.stem,
                            "excerpt": _excerpt(txt),
                            "updated": _fmt(p.stat().st_mtime),
                        }
                    )
                except Exception:
                    continue
    except Exception:
        pass
    return {"folder": folder, "notes": out}


@router.get("/stats", summary="Brain health: note counts per folder + freshness")
async def brain_stats(_user=Depends(require_admin)) -> dict[str, Any]:
    from app.platform import obsidian_sync

    v: Path = obsidian_sync._VAULT
    folders: dict[str, int] = {}
    total = 0
    newest: float | None = None
    try:
        if v.exists():
            for p in v.rglob("*.md"):
                if p.parent == v:
                    continue
                total += 1
                folders[p.parent.name] = folders.get(p.parent.name, 0) + 1
                m = p.stat().st_mtime
                if newest is None or m > newest:
                    newest = m
    except Exception:
        pass
    return {
        "enabled": obsidian_sync._enabled(),
        "git_remote_set": bool(os.environ.get("OBSIDIAN_GIT_REMOTE", "")),
        "total_notes": total,
        "folders": dict(sorted(folders.items(), key=lambda kv: -kv[1])),
        "newest": _fmt(newest) if newest else None,
    }


__all__ = ["router"]
