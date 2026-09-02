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
    agent_id: str = "",
    tenant_id: str = "",
    tool_name: str = "",
    tool_version: str = "",
    _enforce_gate: Any = None,
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

    # Enforcement mode resolution (INERT default). ENFORCE only under explicit
    # per-agent/per-loop/per-tool allowlists (AGENT_HARNESS_ENFORCE_* ); in every
    # other configuration this stays False and the legacy `fn` path is authoritative.
    _enforce = False
    _egate = None
    _ectx = None
    enforce_batch_item = None  # bound below only in ENFORCE mode
    try:
        from app.agents.harness.contracts import SYSTEM_TENANT as _SYS_TENANT
        from app.agents.harness.contracts import RunContext as _RunContext
        from app.agents.harness.enforce import EnforcementGate as _EnforcementGate
        from app.agents.harness.enforce import HarnessMode as _HarnessMode
        from app.agents.harness.enforce import enforce_batch_item as _enforce_item
        from app.agents.harness.enforce import resolve_mode as _resolve_mode

        _mode, _ = _resolve_mode(agent_id=agent_id, source_loop="batch_harness")
        if _mode is _HarnessMode.ENFORCE:
            _enforce = True
            enforce_batch_item = _enforce_item
            _egate = _enforce_gate or _EnforcementGate()
            _ectx = _RunContext(
                run_id=ckpt_id,
                task_id=ckpt_id,
                tenant_id=(tenant_id or _SYS_TENANT),
                agent=(agent_id or "").strip().lower(),
                actor_id="batch_runner",
                source_loop="batch_harness",
            )
    except Exception as _e:  # any resolver/import failure => safe legacy path
        _enforce = False
        logger.debug(f"batch_harness enforce-mode resolution skipped: {_e}")

    def _obs_batch(index, item, *, resumed, ok, summary, err, res, latency):
        """Record-only harness shadow of one batch item (INERT unless AGENT_HARNESS
        + AGENT_HARNESS_SHADOW on, agent_id in canary agents, batch_harness in
        canary loops). NEVER re-runs fn; observes AFTER the semaphore releases;
        never raises into the batch."""
        try:
            from app.agents.harness.adapters import observe_batch_item

            _op = getattr(fn, "__name__", "") or ""
            observe_batch_item(
                batch_run_id=ckpt_id,
                batch_name=(label or ckpt_id),
                item_id=_item_key(item),
                item_index=index,
                attempt=0,
                agent_id=agent_id,
                tenant_id=tenant_id,
                operation_name=_op,
                operation_arguments=(item if isinstance(item, dict) else {"item": _item_key(item)}),
                actual_executor=(_op or "batch.fn"),
                actual_result=(res if err is None else None),
                actual_error=err,
                latency_ms=round(latency, 1),
                checkpoint_state=(
                    "resume_skipped" if resumed else ("completed" if ok else "failed")
                ),
                resumed=resumed,
                tool_name=(tool_name or None),
                tool_version=(tool_version or None),
            )
        except Exception:
            pass

    async def _run_one(index: int, item: Any) -> None:
        nonlocal done, failed, skipped
        if index in already:
            skipped += 1
            _obs_batch(
                index, item, resumed=True, ok=None, summary="", err=None, res=None, latency=0.0
            )
            return
        import time as _time

        _t0 = _time.monotonic()
        ok = True
        summary = ""
        _err = None
        res = None
        async with sem:
            if _enforce:
                # ENFORCE mode: the caller-supplied `fn` is NOT authoritative and is
                # NEVER called. Only the registry-bound executor for the canonical
                # tool may run, and only if every gate passes. Denied/failed items
                # execute the bound executor zero times.
                try:
                    _eres = await enforce_batch_item(
                        ctx=_ectx,
                        batch_run_id=ckpt_id,
                        item_id=_item_key(item),
                        item_index=index,
                        attempt=0,
                        tool_name=tool_name,
                        tool_version=tool_version,
                        item=item,
                        gate=_egate,
                    )
                    res = _eres.get("result")
                    if _eres.get("ok"):
                        ok = True
                        summary = str((res or {}).get("summary") or (res or {}).get("value") or "")[
                            :_SUMMARY_CAP
                        ]
                    else:
                        ok = False
                        _err = (
                            _eres.get("error") or ("denied:" + ",".join(_eres.get("reasons") or []))
                        )[:200]
                        summary = f"error: {_err}"
                except Exception as e:  # gate must never crash the batch
                    ok = False
                    _err = f"enforce_gate_error: {str(e)[:180]}"
                    summary = f"error: {_err}"
                    logger.debug(f"batch_harness enforce item {index} ({label}) failed: {e}")
            else:
                try:
                    res = await fn(item)
                    if isinstance(res, dict):
                        ok = bool(res.get("ok", True))
                        summary = str(res.get("summary") or res.get("result") or "")[:_SUMMARY_CAP]
                    else:
                        summary = str(res)[:_SUMMARY_CAP]
                except Exception as e:  # per-item never-raise (one failure != batch death)
                    ok = False
                    _err = str(e)[:200]
                    summary = f"error: {_err}"
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
        # Observe AFTER releasing the semaphore (record-only; never re-runs fn).
        # SHADOW observation only — ENFORCE mode emits its own enforcement_* audit
        # events inside enforce_batch_item and must not also shadow-observe.
        if not _enforce:
            _obs_batch(
                index,
                item,
                resumed=False,
                ok=ok,
                summary=summary,
                err=_err,
                res=res,
                latency=(_time.monotonic() - _t0) * 1000.0,
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
