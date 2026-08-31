"""
content_os.inbox_watcher — VPS-side Celery task.

Scans MEDIA_INBOX periodically. Anything sitting in a folder that has a
brief.json + at least one .mp4 (per aspect) is registered as a MediaAsset
and pushed to Postiz as a *draft* (NOT published). The owner bot then
asks in Telegram for Approve/Recreate/Skip; only on Approve do we move
the draft to scheduled.

This keeps the GATING intent intact: nothing ever gets posted without
explicit human sign-off. And the auto part still runs 24/7 — drafts
accumulate automatically, owner only needs to approve.
"""
from __future__ import annotations

import os
import json
import time
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MEDIA_INBOX = Path(os.getenv("CONTENT_OS_INBOX", "/opt/leadgen/media/inbox"))
DB_PATH = Path(os.getenv("CONTENT_OS_DB", "/opt/leadgen/media/content_os/media.db"))


# --------------------------------------------------------------------------- #
# Tiny local DB (sqlite, append-only by virtue of IGNORE inserts).
# --------------------------------------------------------------------------- #
def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id          TEXT PRIMARY KEY,
            owner_kind  TEXT,
            owner_slug  TEXT,
            niche       TEXT,
            title       TEXT,
            hook        TEXT,
            cta_url     TEXT,
            manifest    TEXT,
            state       TEXT,  -- pending | approved | recreated | skipped | posted
            created_at  TEXT,
            approved_at TEXT,
            postiz_id   TEXT
        )
    """)
    c.commit()
    return c


def _upsert_asset(brief: dict, media_dir: Path, state: str = "pending") -> str:
    conn = _conn()
    aid = f"{brief['owner_slug']}/{brief['brief_id']}"
    conn.execute(
        "INSERT OR IGNORE INTO assets(id, owner_kind, owner_slug, niche, title, hook, cta_url, manifest, state, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            aid,
            brief.get("owner_kind", ""),
            brief.get("owner_slug", ""),
            brief.get("niche", ""),
            brief.get("title", ""),
            brief.get("hook", ""),
            brief.get("cta_url", ""),
            json.dumps({"dir": str(media_dir), "brief": brief}, ensure_ascii=False),
            state,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return aid


def _set_state(asset_id: str, state: str, **fields):
    conn = _conn()
    if fields:
        sets = ",".join(f"{k}=?" for k in fields.keys())
        vals = list(fields.values()) + [state, asset_id]
    else:
        sets, vals = "state=?", [state, asset_id]
    conn.execute(f"UPDATE assets SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def find_asset(asset_id: str) -> dict | None:
    conn = _conn()
    cur = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.close()
    return dict(zip(cols, row)) if row else None


def list_pending(limit: int = 25) -> list[dict]:
    conn = _conn()
    cur = conn.execute(
        "SELECT id, owner_kind, owner_slug, niche, title, hook, cta_url, state, created_at "
        "FROM assets WHERE state=? ORDER BY created_at DESC LIMIT ?",
        ("pending", limit),
    )
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


# --------------------------------------------------------------------------- #
# Main scan
# --------------------------------------------------------------------------- #
def scan_inbox() -> dict:
    """Celery task body (also importable as plain function for tests)."""
    if not MEDIA_INBOX.exists():
        return {"ok": True, "scanned": 0, "note": "inbox_missing"}

    scanned = 0
    pending = 0
    for mp4 in MEDIA_INBOX.rglob("*.mp4"):
        media_dir = mp4.parent
        brief_p = media_dir / "brief.json"
        approved_marker = media_dir / ".approved"
        if not brief_p.exists():
            continue
        scanned += 1
        try:
            brief = json.loads(brief_p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[content_os] bad brief.json at %s: %s", media_dir, e)
            continue
        asset_id = _upsert_asset(brief, media_dir, state="pending")
        # Mark 'em so we don't re-queue forever; Postiz draft happens on Approve.
        if not approved_marker.exists():
            pending += 1

    return {"ok": True, "scanned": scanned, "pending": pending}


# --------------------------------------------------------------------------- #
# Approval actions
# --------------------------------------------------------------------------- #
def approve(asset_id: str) -> dict:
    """Mark approved; if Postiz reachable publish, else stage draft + ntfy."""
    asset = find_asset(asset_id)
    if not asset:
        return {"ok": False, "error": "unknown_asset"}

    media_dir = Path(json.loads(asset["manifest"])["dir"])
    (media_dir / ".approved").write_text("ok", encoding="utf-8")

    # Push to Postiz (draft or scheduled). Falls back to local schedule file
    # if Postiz not configured.
    postiz_id = None
    try:
        from app.integrations.postiz import PostizClient  # type: ignore
        client = PostizClient()
        postiz_id = client.queue_creative(
            media_dir=str(media_dir),
            title=asset["title"],
            caption=f"{asset['hook']}\n{asset['cta_url']}",
            aspects=["9x16", "1x1", "16x9"],
        )
    except Exception as e:
        logger.info("[content_os] Postiz unavailable (%s); staging local schedule", e)
        schedule_p = media_dir / ".postiz_schedule.json"
        schedule_p.write_text(json.dumps({
            "title": asset["title"],
            "caption": f"{asset['hook']}\n{asset['cta_url']}",
            "aspects": ["9x16", "1x1", "16x9"],
            "queue_when": "manual_or_postiz_recovery",
        }, ensure_ascii=False), encoding="utf-8")

    _set_state(asset_id, "approved",
               approved_at=datetime.now(timezone.utc).isoformat(),
               postiz_id=str(postiz_id) if postiz_id else "")

    # Notify owner (best-effort ntfy push).
    _notify_owner(f"✅ Asset APPROVED: {asset['title']} → Postiz{' id='+postiz_id if postiz_id else ' (queued local)'}")
    return {"ok": True, "asset_id": asset_id, "postiz_id": postiz_id}


def recreate(asset_id: str, feedback: str = "") -> dict:
    asset = find_asset(asset_id)
    if not asset:
        return {"ok": False, "error": "unknown_asset"}

    media_dir = Path(json.loads(asset["manifest"])["dir"])
    (media_dir / ".recreate").write_text(feedback or "owner wants changes", encoding="utf-8")

    _set_state(asset_id, "recreated")
    _notify_owner(f"🔁 Asset RECREATE queued: {asset['title']} — feedback='{feedback[:80]}'")
    return {"ok": True, "asset_id": asset_id}


def skip(asset_id: str) -> dict:
    asset = find_asset(asset_id)
    if not asset:
        return {"ok": False, "error": "unknown_asset"}

    media_dir = Path(json.loads(asset["manifest"])["dir"])
    try:
        for f in media_dir.iterdir():
            f.unlink(missing_ok=True)
        media_dir.rmdir()
    except Exception:
        pass
    _set_state(asset_id, "skipped")
    _notify_owner(f"⏭ Asset SKIPPED: {asset['title']}")
    return {"ok": True, "asset_id": asset_id}


def _notify_owner(msg: str):
    """Best-effort ntfy push. Never raises."""
    try:
        from app.integrations.ntfy import push  # type: ignore
        push(topic="leadgen-owner", message=msg, priority="default")
    except Exception:
        pass
