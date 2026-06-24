"""Batch harness — async callable ko many inputs pe PARALLEL chalao + checkpoint/resume.

Ruflo/Hermes "batch run" parity (free-stack). Koi bhi `async def fn(item) -> dict`
ko list-of-items pe bounded concurrency me chalata, har completed item ka progress
checkpoint karta (data/batch_runs/<ckpt_id>.jsonl), aur same ckpt_id pe RESUME karne
pe already-done indices SKIP karta (idempotent restart). Ek item fail = poora batch
nahi marta — har item never-raise wrapper me chalta.

Design (project patterns):
  - `enabled()` sirf info-flag (BATCH_HARNESS) — run_batch khud hamesha safe-callable
    (programmatic callers + admin demo endpoint dono use karte). Flag default OFF.
  - Concurrency [1,16] me bound (resource-safety; asyncio.Semaphore).
  - Per-item hard never-raise: exception → {ok:False} record, batch continue.
  - Checkpoint = append-only jsonl (one line per completed index). Resume = read
    done-indices, skip. Crash-safe (har item ke baad flush).
  - Import-safe, kabhi raise nahi (top-level helpers defensive).

Flag: BATCH_HARNESS=1
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = os.path.join("data", "batch_runs")
_SUMMARY_CAP = 400  # result_summary truncate (checkpoint line bloat na ho)


def enabled() -> bool:
    """Info-flag only — run_batch flag-independent safe-callable hai (admin/programmatic)."""
    return (os.getenv("BATCH_HARNESS") or "").strip().lower() in ("1", "true", "yes")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ckpt_path(ckpt_id: str) -> str:
    return os.path.join(_DIR, f"{ckpt_id}.jsonl")


def _item_key(item: Any) -> str:
    """Stable-ish human key for an item (logging/checkpoint only — not a uniqueness id)."""
    try:
        if isinstance(item, dict):
            for k in ("id", "key", "name", "url", "email", "slug"):
                if item.get(k):
                    return str(item[k])[:120]
        return str(item)[:120]
    except Exception:
        return "?"


def _done_indices(ckpt_id: str) -> set[int]:
    """Resume support — already-completed indices padho (corrupt lines skip)."""
    done: set[int] = set()
    path = _ckpt_path(ckpt_id)
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        idx = rec.get("index")
                        if isinstance(idx, int):
                            done.add(idx)
                    except Exception:
                        continue
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"batch_harness done_indices read failed: {e}")
    return done


def _append_ckpt(ckpt_id: str, rec: dict[str, Any]) -> None:
    """Ek completed item ka checkpoint line append (never-raise; crash-safe flush)."""
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_ckpt_path(ckpt_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"batch_harness ckpt append failed: {e}")


async def run_batch(
    fn: Callable[[Any], Awaitable[dict[str, Any]]],
    items: list[Any],
    concurrency: int = 4,
    ckpt_id: str | None = None,
    label: str = "",
) -> dict[str, Any]:
    """`fn` (async def fn(item)->dict) ko `items` pe bounded-parallel chalao.

    - concurrency [1,16] me clamp; asyncio.Semaphore se gate.
    - Har item never-raise wrapper me — ek failure batch ko nahi marti.
    - ckpt_id diya → progress data/batch_runs/<ckpt_id>.jsonl me; same ckpt_id pe
      dobara call = already-done indices SKIP (resume).
    Returns {ok, total, done, failed, skipped, ckpt_id, label}.
    """
    try:
        items = list(items or [])
    except Exception:
        items = []
    total = len(items)
    try:
        conc = max(1, min(int(concurrency or 4), 16))
    except Exception:
        conc = 4

    if not ckpt_id:
        ckpt_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    already = _done_indices(ckpt_id)
    sem = asyncio.Semaphore(conc)
    done = 0
    failed = 0
    skipped = 0

    async def _run_one(index: int, item: Any) -> None:
        nonlocal done, failed, skipped
        if index in already:
            skipped += 1
            return
        async with sem:
            ok = True
            summary = ""
            try:
                res = await fn(item)
                if isinstance(res, dict):
                    ok = bool(res.get("ok", True))
                    summary = str(res.get("summary") or res.get("result") or "")[:_SUMMARY_CAP]
                else:
                    summary = str(res)[:_SUMMARY_CAP]
            except Exception as e:  # per-item never-raise (one failure != batch death)
                ok = False
                summary = f"error: {str(e)[:200]}"
                logger.debug(f"batch_harness item {index} ({label}) failed: {e}")
            if ok:
                done += 1
            else:
                failed += 1
            _append_ckpt(
                ckpt_id,
                {
                    "index": index,
                    "item_key": _item_key(item),
                    "ok": ok,
                    "result_summary": summary,
                    "at": _now_iso(),
                },
            )

    try:
        await asyncio.gather(*(_run_one(i, it) for i, it in enumerate(items)))
    except Exception as e:  # pragma: no cover - gather itself never-raise (children guarded)
        logger.debug(f"batch_harness gather failed ({label}): {e}")

    return {
        "ok": failed == 0,
        "total": total,
        "done": done,
        "failed": failed,
        "skipped": skipped,
        "ckpt_id": ckpt_id,
        "label": label,
    }


def list_batches(limit: int = 50) -> list[dict[str, Any]]:
    """Recent checkpoint runs (file-level summary) — newest first. Never-raise."""
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isdir(_DIR):
            return out
        files = [f for f in os.listdir(_DIR) if f.endswith(".jsonl")]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(_DIR, f)), reverse=True)
        for f in files[: max(1, int(limit or 50))]:
            path = os.path.join(_DIR, f)
            ok = 0
            fail = 0
            try:
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            if rec.get("ok"):
                                ok += 1
                            else:
                                fail += 1
                        except Exception:
                            continue
            except Exception:
                continue
            out.append(
                {
                    "ckpt_id": f[:-6],  # strip .jsonl
                    "completed": ok + fail,
                    "ok": ok,
                    "failed": fail,
                    "mtime": datetime.fromtimestamp(
                        os.path.getmtime(path), tz=timezone.utc
                    ).isoformat(),
                }
            )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"batch_harness list_batches failed: {e}")
    return out


__all__ = ["enabled", "run_batch", "list_batches"]
