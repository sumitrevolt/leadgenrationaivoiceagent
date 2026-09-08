"""Weekly client KB contextual re-ingest (USE_CONTEXTUAL_INGEST companion).

Har hafte thode clients ki website → KB dubara seed (cursor rotate).
GATED: KB_WEEKLY_REFRESH=1 ya USE_CONTEXTUAL_INGEST=1. Kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CURSOR = os.path.join("data", "kb_refresh_cursor.json")


def enabled() -> bool:
    if os.environ.get("KB_WEEKLY_REFRESH", "0").strip().lower() in ("1", "true", "yes"):
        return True
    return os.environ.get("USE_CONTEXTUAL_INGEST", "0").strip().lower() in ("1", "true", "yes")


def _load_cursor() -> int:
    try:
        if os.path.exists(_CURSOR):
            return int(json.loads(open(_CURSOR, encoding="utf-8").read()).get("idx", 0))
    except Exception:
        pass
    return 0


def _save_cursor(idx: int) -> None:
    try:
        os.makedirs(os.path.dirname(_CURSOR) or ".", exist_ok=True)
        with open(_CURSOR, "w", encoding="utf-8") as f:
            json.dump({"idx": idx}, f)
    except Exception as e:
        logger.debug(f"[kb_refresh] cursor save skip: {e}")


async def run_weekly_if_enabled(limit: int = 5) -> dict[str, Any]:
    if not enabled():
        return {"ok": True, "skipped": "disabled"}
    try:
        from app.marketing import clients_store, onboarding
        from app.platform import team

        clients = [
            c for c in (clients_store.list_clients() or []) if (c.get("website") or "").strip()
        ]
        if not clients:
            return {"ok": True, "processed": 0, "reason": "no clients with website"}

        start = _load_cursor() % len(clients)
        batch = []
        for i in range(min(limit, len(clients))):
            batch.append(clients[(start + i) % len(clients)])

        done = 0
        chunks = 0
        for c in batch:
            cid = c.get("id") or c.get("client_id")
            web = (c.get("website") or "").strip()
            if not cid or not web:
                continue
            try:
                out = await onboarding._seed_kb_from_website(str(cid), web)
                done += 1
                chunks += int(out.get("kb_chunks") or 0)
            except Exception as e:
                logger.debug(f"[kb_refresh] client {cid} skip: {e}")

        next_idx = (start + len(batch)) % len(clients)
        _save_cursor(next_idx)
        if done:
            team.log_event(
                "dev",
                "kb_refresh",
                f"📚 weekly re-ingest {done} clients · {chunks} KB chunks",
                status="ok",
            )
        return {"ok": True, "processed": done, "kb_chunks": chunks, "cursor": next_idx}
    except Exception as e:
        logger.warning(f"[kb_refresh] weekly failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["enabled", "run_weekly_if_enabled"]
