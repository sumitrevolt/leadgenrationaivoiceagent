"""Agent checkpoints + rollback — Hermes/Kilo "snapshot before mutate" parity.

Kilo Code / Hermes-class agents data mutate karne se PEHLE ek checkpoint banate hain
taaki bad-edit ko ek click me rollback kiya ja sake. Is project me agents data/*.jsonl
+ data/skills_extra/ me write karte the par koi undo-net nahi tha.

Yeh module woh safety-net deta (shutil copy + manifest, never-raise, path-guarded):
  - `snapshot(paths, label)` → har existing path ko data/agent_checkpoints/<id>/ me
    relative-path preserve karke copy + manifest.json likhta.
  - `list_checkpoints(limit)` → recent checkpoints (newest-first).
  - `rollback(ckpt_id)` → files wapas apni jagah copy.

Design (project patterns + SAFETY):
  - **Path-guard**: SIRF repo-root ke andar `data/` aur `app/` relative paths allow;
    absolute path / `..` escape / kuch aur = REFUSE (traversal-safe).
  - never-raise: har public fn ANY exception pe {ok:False, error} deta.
  - `enabled()` sirf AUTOMATIC background snapshotting ko gate karta — default OFF =
    zero behaviour change. Teeno helpers khud flag-independent (admin endpoint ke liye).

Flag: AGENT_CHECKPOINTS=1
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CKPT_ROOT = Path("data/agent_checkpoints")
_ALLOWED_PREFIXES = ("data", "app")  # SIRF in repo-subtrees pe operate karo (safety)


def enabled() -> bool:
    """Gates AUTOMATIC background snapshotting. Helpers flag-independent."""
    return (os.getenv("AGENT_CHECKPOINTS") or "").strip().lower() in ("1", "true", "yes")


def _repo_root() -> Path:
    """Repo root = is file se 3 level upar (app/agents/agent_checkpoints.py)."""
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path(os.path.abspath("."))


def _safe_rel(path: str, root: Path) -> str | None:
    """Path ko repo-root-relative banao agar SAFE ho (data/ ya app/ ke andar).

    Reject: absolute outside-root, `..` escape, ya allowed-prefix ke bahar. None = unsafe.
    """
    if not path or not isinstance(path, str):
        return None
    p = path.strip().replace("\\", "/")
    if not p:
        return None
    try:
        cand = Path(p)
        # Absolute path ko root ke against resolve karke check karo
        full = (cand if cand.is_absolute() else (root / cand)).resolve()
        rel = full.relative_to(root)  # raises if escapes root
    except Exception:
        return None
    rel_str = rel.as_posix()
    top = rel_str.split("/", 1)[0]
    if top not in _ALLOWED_PREFIXES:
        return None
    if not rel_str or rel_str.startswith(".."):
        return None
    return rel_str


def snapshot(paths: list[str], label: str = "") -> dict[str, Any]:
    """Diye gaye existing paths ka checkpoint banao. Never raises.

    Har file/dir ko data/agent_checkpoints/<ckpt_id>/<relpath> me copy karta +
    manifest.json (id,label,paths,at). SIRF data/ aur app/ ke andar safe paths.

    Returns {ok, id, label, paths, at, skipped} (skipped = unsafe/missing entries).
    """
    if not paths:
        return {"ok": False, "error": "no paths"}
    root = _repo_root()
    ckpt_id = f"ck-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    dest_root = _CKPT_ROOT / ckpt_id
    saved: list[str] = []
    skipped: list[str] = []
    try:
        for raw in paths:
            rel = _safe_rel(str(raw), root)
            if not rel:
                skipped.append(str(raw))
                continue
            src = root / rel
            if not src.exists():
                skipped.append(rel)
                continue
            dst = dest_root / rel
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
                saved.append(rel)
            except Exception as e:  # pragma: no cover - per-path copy issue
                logger.debug(f"snapshot copy failed {rel}: {e}")
                skipped.append(rel)
        if not saved:
            # kuch save nahi hua → khaali ckpt dir mat chhodo
            try:
                if dest_root.exists():
                    shutil.rmtree(dest_root, ignore_errors=True)
            except Exception:
                pass
            return {"ok": False, "error": "no valid paths snapshotted", "skipped": skipped}
        manifest = {
            "id": ckpt_id,
            "label": str(label or "")[:200],
            "paths": saved,
            "at": time.time(),
        }
        try:
            (dest_root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:  # pragma: no cover
            logger.debug(f"manifest write failed: {e}")
        return {**manifest, "ok": True, "skipped": skipped}
    except Exception as e:  # pragma: no cover - blanket safety
        logger.debug(f"snapshot failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def list_checkpoints(limit: int = 50) -> list[dict[str, Any]]:
    """Recent checkpoints (newest-first) manifests se. Never raises."""
    try:
        if not _CKPT_ROOT.exists():
            return []
        items: list[dict[str, Any]] = []
        for d in _CKPT_ROOT.iterdir():
            if not d.is_dir():
                continue
            mf = d / "manifest.json"
            if not mf.exists():
                continue
            try:
                obj = json.loads(mf.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    items.append(obj)
            except Exception:
                continue
        items.sort(key=lambda x: x.get("at") or 0, reverse=True)
        return items[: max(1, int(limit or 50))]
    except Exception as e:  # pragma: no cover
        logger.debug(f"list_checkpoints failed: {e}")
        return []


def rollback(ckpt_id: str) -> dict[str, Any]:
    """Checkpoint ke files ko wapas unki original jagah copy karo. Never raises.

    Returns {ok, id, restored, skipped}. Path-guard rollback pe bhi enforce hota.
    """
    cid = (ckpt_id or "").strip()
    if not cid or "/" in cid or "\\" in cid or ".." in cid:
        return {"ok": False, "error": "invalid ckpt_id"}
    root = _repo_root()
    dest_root = _CKPT_ROOT / cid
    mf = dest_root / "manifest.json"
    if not mf.exists():
        return {"ok": False, "error": "checkpoint not found"}
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        rel_paths = manifest.get("paths") or []
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"manifest unreadable: {str(e)[:120]}"}
    restored: list[str] = []
    skipped: list[str] = []
    try:
        for rel in rel_paths:
            safe = _safe_rel(str(rel), root)
            if not safe:
                skipped.append(str(rel))
                continue
            src = dest_root / safe
            if not src.exists():
                skipped.append(safe)
                continue
            dst = root / safe
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
                restored.append(safe)
            except Exception as e:  # pragma: no cover
                logger.debug(f"rollback copy failed {safe}: {e}")
                skipped.append(safe)
        return {"ok": bool(restored), "id": cid, "restored": restored, "skipped": skipped}
    except Exception as e:  # pragma: no cover - blanket safety
        logger.debug(f"rollback failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["enabled", "snapshot", "list_checkpoints", "rollback"]
