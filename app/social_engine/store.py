"""social_engine.store — durable post-job queue + persistence.

PRIMARY (reliable, testable): data/social_post_jobs.jsonl (append, latest-line-per-id
wins — content_approval pattern). MIRROR (production query/analytics): Postgres table
`social_post_jobs` best-effort write-through (DB down/unset = inert, queue still chalta).

Job status: queued -> processing -> published | failed (-> retry) | dead (max attempts).

  enqueue(job) -> job_id
  claim_pending(limit) -> list[dict]      # queued -> processing (atomic-ish append)
  mark(job_id, status, **fields)
  list_jobs(client_id="", status="", limit=100)
  ensure_tables()                         # Postgres mirror table (idempotent)
NEVER raises.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "social_post_jobs.jsonl")
_MAX_ATTEMPTS = 4

# --------------------------------------------------------------------------- #
# Postgres mirror model (best-effort; queue isspe depend NAHI karta)
# --------------------------------------------------------------------------- #
_MODEL = None
_TABLES_READY = False


def _model():
    """Lazy SocialPostJob model (Base.metadata pe attach). DB optional."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from sqlalchemy import Column, DateTime, Integer, String, Text
        from sqlalchemy.sql import func

        from app.models.base import Base

        class SocialPostJob(Base):
            __tablename__ = "social_post_jobs"
            id = Column(String(40), primary_key=True)
            client_id = Column(String(64), index=True)
            platform = Column(String(32), index=True)
            account_ref = Column(String(255), default="")
            media_type = Column(String(16), default="video")
            media_path = Column(Text, default="")
            media_url = Column(Text, default="")
            caption = Column(Text, default="")
            status = Column(String(20), default="queued", index=True)
            attempts = Column(Integer, default=0)
            post_id = Column(String(255), default="")
            post_url = Column(Text, default="")
            last_error = Column(Text, default="")
            created_at = Column(DateTime(timezone=True), server_default=func.now())
            updated_at = Column(
                DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
            )

        _MODEL = SocialPostJob
    except Exception as e:
        logger.debug(f"[store] model unavailable: {e}")
        _MODEL = None
    return _MODEL


def ensure_tables() -> bool:
    """Postgres mirror table create (idempotent). DB na ho to False (queue fine)."""
    global _TABLES_READY
    if _TABLES_READY:
        return True
    try:
        from app.models.base import engine

        eng = engine()
        m = _model()
        if eng is None or m is None:
            return False
        m.__table__.create(bind=eng, checkfirst=True)
        _TABLES_READY = True
        return True
    except Exception as e:
        logger.debug(f"[store] ensure_tables skip: {e}")
        return False


def _mirror(job: dict[str, Any]) -> None:
    """Best-effort upsert to Postgres. Failure = silent (JSONL = source of truth)."""
    try:
        if not ensure_tables():
            return
        from app.models.base import get_db_session

        m = _model()
        with get_db_session() as db:
            row = db.get(m, job["id"])
            if row is None:
                row = m(id=job["id"])
                db.add(row)
            for k in (
                "client_id",
                "platform",
                "account_ref",
                "media_type",
                "media_path",
                "media_url",
                "caption",
                "status",
                "attempts",
                "post_id",
                "post_url",
                "last_error",
            ):
                if k in job and job[k] is not None:
                    setattr(row, k, job[k])
            db.commit()
    except Exception as e:
        logger.debug(f"[store] mirror skip: {e}")


# --------------------------------------------------------------------------- #
# JSONL primary store
# --------------------------------------------------------------------------- #
def _append(rec: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _latest() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        if not os.path.isfile(_PATH):
            return out
        with open(_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                jid = str(rec.get("id") or "")
                if jid:
                    cur = out.get(jid) or {}
                    cur.update(rec)
                    out[jid] = cur
    except Exception as e:
        logger.debug(f"[store] read skip: {e}")
    return out


def _norm_hashtags(raw: Any) -> list[str]:
    """Loop-social-9 (2026-07-11): coerce hashtags into a clean lowercase list.
    Accepts list, tuple, csv string, or space-separated string. Strips '#'."""
    if raw is None:
        return []
    if isinstance(raw, str):
        # Split on space / comma so both "#a #b" and "#a,#b" work.
        parts = [p for p in raw.replace(",", " ").split() if p]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p) for p in raw]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        p = p.strip().lstrip("#").lower()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out[:60]  # sane upper bound; platform validators enforce per-platform


def enqueue(job: dict[str, Any]) -> str:
    """Loop-social-9 (2026-07-11): extended post metadata schema (Phase 6).
    Additive — every new field defaults empty/zero so callers written for the
    pre-Loop-9 API continue to work verbatim. New fields:
      campaign_id, language, hashtags (list), cta, scheduled_time, timezone,
      created_by, reviewed_by, delivery_event_id, content_type.
    (retry_count is aliased to `attempts` — already tracked; last_error already
    written by drain.)"""
    try:
        jid = uuid.uuid4().hex[:16]
        rec = {
            "id": jid,
            "client_id": str(job.get("client_id") or ""),
            "platform": str(job.get("platform") or ""),
            "account_ref": str(job.get("account_ref") or ""),
            "media_type": str(job.get("media_type") or "video"),
            "media_path": str(job.get("media_path") or ""),
            "media_url": str(job.get("media_url") or ""),
            "caption": str(job.get("caption") or ""),
            "extra": job.get("extra") or {},
            "status": "queued",
            "attempts": 0,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            # Loop-social-9: canonical Phase-6 metadata (all optional).
            "campaign_id": str(job.get("campaign_id") or ""),
            "language": str(job.get("language") or ""),
            "hashtags": _norm_hashtags(job.get("hashtags")),
            "cta": str(job.get("cta") or ""),
            "scheduled_time": str(job.get("scheduled_time") or ""),
            "timezone": str(job.get("timezone") or ""),
            "created_by": str(job.get("created_by") or "system"),
            "reviewed_by": str(job.get("reviewed_by") or ""),
            "delivery_event_id": str(job.get("delivery_event_id") or ""),
            "content_type": str(job.get("content_type") or ""),
            # Loop-social-21 (2026-07-11): media_assets multi-asset support +
            # approval_status snapshot so the drain can honestly decline
            # publishing an unapproved job. Additive over media_path/media_url.
            "media_assets": (
                job.get("media_assets") if isinstance(job.get("media_assets"), list) else []
            ),
            "approval_status": str(job.get("approval_status") or "").lower(),
        }
        _append(rec)
        _mirror(rec)
        return jid
    except Exception as e:
        logger.warning(f"[store] enqueue failed: {e}")
        return ""


def claim_pending(limit: int = 20) -> list[dict[str, Any]]:
    """queued/retry jobs -> processing mark, return. Scheduler/worker drain."""
    claimed: list[dict[str, Any]] = []
    try:
        from app.utils.file_lock import file_lock

        # Lock the read+mark so two concurrent drainers (immediate celery drain +
        # inline run_cycle drain) can't both observe the same job as 'queued' and
        # double-publish it. The 2nd drainer reads after the 1st's processing-marks
        # are flushed and filters them out. _mirror (DB I/O) runs OUTSIDE to keep the
        # lock hold short.
        with file_lock(_PATH):
            rows = [r for r in _latest().values() if r.get("status") in ("queued", "retry")]
            rows.sort(key=lambda r: str(r.get("created_at") or ""))
            for r in rows[: max(1, int(limit))]:
                jid = str(r.get("id") or "")
                _append(
                    {
                        "id": jid,
                        "status": "processing",
                        "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                )
                r2 = dict(r)
                r2["status"] = "processing"
                claimed.append(r2)
        for c in claimed:
            _mirror({"id": c.get("id"), "status": "processing"})
    except Exception as e:
        logger.warning(f"[store] claim failed: {e}")
    return claimed


def mark(job_id: str, status: str, **fields: Any) -> None:
    try:
        jid = str(job_id or "")
        if not jid:
            return
        rec = {"id": jid, "status": status, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        rec.update({k: v for k, v in fields.items() if v is not None})
        _append(rec)
        _mirror(rec)
    except Exception as e:
        logger.warning(f"[store] mark failed: {e}")


def get(job_id: str) -> dict[str, Any] | None:
    return _latest().get(str(job_id or ""))


def list_jobs(client_id: str = "", status: str = "", limit: int = 100) -> list[dict[str, Any]]:
    cid = (client_id or "").strip()
    st = (status or "").strip()
    rows = [
        r
        for r in _latest().values()
        if (not cid or str(r.get("client_id") or "") == cid) and (not st or r.get("status") == st)
    ]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows[: max(1, min(int(limit or 100), 500))]


def publish_proof(client_id: str = "") -> dict[str, Any]:
    """Latest published job with a real provider post_id (not dry-run fabrications).

    Empty post_id or ``dry-*`` prefix = not proof. Used by admin status so
    operators don't chase a non-existent misconfiguration when jobs already
    drained successfully (ADR-098/099 class).
    """
    cid = (client_id or "").strip()
    best: dict[str, Any] | None = None
    try:
        for r in _latest().values():
            if cid and str(r.get("client_id") or "") != cid:
                continue
            if str(r.get("status") or "") != "published":
                continue
            pid = str(r.get("post_id") or "").strip()
            if not pid or pid.startswith("dry-"):
                continue
            if best is None or str(r.get("updated_at") or "") > str(best.get("updated_at") or ""):
                best = r
    except Exception as e:
        logger.debug(f"[store] publish_proof skip: {e}")
    if not best:
        return {
            "publish_proven": False,
            "last_real_post_id": "",
            "last_real_post_at": "",
            "last_job_id": "",
            "platform": "",
        }
    return {
        "publish_proven": True,
        "last_real_post_id": str(best.get("post_id") or ""),
        "last_real_post_at": str(best.get("updated_at") or best.get("created_at") or ""),
        "last_job_id": str(best.get("id") or ""),
        "platform": str(best.get("platform") or ""),
    }


def queue_counts() -> dict[str, int]:
    """Latest-wins status histogram for admin triage. Never raises."""
    out: dict[str, int] = {}
    try:
        for r in _latest().values():
            st = str(r.get("status") or "unknown")
            out[st] = out.get(st, 0) + 1
    except Exception as e:
        logger.debug(f"[store] queue_counts skip: {e}")
    return out


def max_attempts() -> int:
    return _MAX_ATTEMPTS
