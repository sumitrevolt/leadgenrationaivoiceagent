#!/usr/bin/env python3
"""LeadGen AI — Telegram enterprise setup API (fail-closed).

Scoped, owner-chosen admin surface that mirrors ``config/telegram/setup_spec.yaml``
(the canonical single source of truth) and drives the Bot-API bootstrap in
``scripts/telegram_setup.py``.

FAIL-CLOSED (never weakens a compliance gate)
---------------------------------------------
* READ (GET) is always allowed — it only reflects the spec. When writes are
  disabled it still returns the data but advertises ``write_enabled: false``.
* PATCH (edit chat_id / invite_link) is REFUSED with 403 unless
  ``TELEGRAM_SETUP_ENABLED == "1"``.
* POST /apply (live Bot-API bootstrap) is REFUSED with 503 unless BOTH
  ``TELEGRAM_SETUP_ENABLED == "1"`` AND ``TELEGRAM_BOT_TOKEN`` are set.
* Apply NEVER talks to the network directly. It shells out to
  ``scripts/telegram_setup.py --apply`` (which is itself fail-closed and
  refuses to touch Telegram without the token + enabled flag).
* No Dapr. No cross-tenant data. No app.* imports (import-safe / isolated).

# To mount: in app/main.py add:
#     from app.api.telegram_setup import router as telegram_setup_router
#     app.include_router(telegram_setup_router)
# This include is OWNER-GATED on purpose — left commented out by default.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException

# repo_root = two levels up from this file (app/api/telegram_setup.py -> app -> repo_root)
REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "config" / "telegram" / "setup_spec.yaml"

router = APIRouter(prefix="/telegram/setup", tags=["telegram-setup"])


# --------------------------------------------------------------------------- #
# Gating helpers
# --------------------------------------------------------------------------- #
def _write_enabled() -> bool:
    return os.environ.get("TELEGRAM_SETUP_ENABLED", "0") == "1"


def _bot_token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN") or None


def _load_spec() -> dict[str, Any]:
    if not SPEC_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Spec not found: {SPEC_PATH}")
    with open(SPEC_PATH, "r", encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    if not isinstance(spec, dict):
        raise HTTPException(status_code=500, detail="Spec is not a mapping.")
    return spec


def _group_id(product_id: str, key: str) -> str:
    return f"{product_id}.{key}"


def _find_group(spec: dict[str, Any], group_id: str) -> dict[str, Any] | None:
    for prod in spec.get("products", []) or []:
        pid = prod.get("id")
        if pid is None:
            continue
        for g in prod.get("groups", []) or []:
            if _group_id(str(pid), str(g.get("key"))) == group_id:
                return g
    for g in spec.get("cross_product", []) or []:
        if _group_id("cross", str(g.get("key"))) == group_id:
            return g
    return None


def _annotated_group(product_id: str, group: dict[str, Any]) -> dict[str, Any]:
    """Return a group dict with its canonical `id` (product.key) attached."""
    return {**group, "id": _group_id(product_id, str(group.get("key")))}


def _atomic_write(spec: dict[str, Any]) -> None:
    """Write the spec back atomically: temp file then os.replace."""
    fd, tmp = tempfile.mkstemp(dir=str(SPEC_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(spec, fh, sort_keys=False, allow_unicode=True)
        os.replace(tmp, SPEC_PATH)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("")
@router.get("/")
def read_setup() -> dict[str, Any]:
    """Read-only mirror of the spec, flattened to the canonical group-list shape.

    Always allowed (read-only). Advertises ``write_enabled`` so the dashboard can
    disable the edit/apply controls when writes are gated off.
    """
    spec = _load_spec()
    products = [
        {
            "id": prod.get("id"),
            "name": prod.get("name"),
            "pricing": prod.get("pricing"),
            "groups": [
                _annotated_group(str(prod.get("id")), g) for g in (prod.get("groups", []) or [])
            ],
        }
        for prod in (spec.get("products", []) or [])
    ]
    cross_product = [
        _annotated_group("cross", g) for g in (spec.get("cross_product", []) or [])
    ]
    return {
        "version": spec.get("version"),
        "write_enabled": _write_enabled(),
        "products": products,
        "cross_product": cross_product,
        "admin_roles": spec.get("admin_roles", {}),
    }


@router.patch("/groups/{group_id}")
def update_group(
    group_id: str,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Owner-editable fields only: chat_id / invite_link (pasted after manual creation).

    REFUSED (403) unless TELEGRAM_SETUP_ENABLED == "1".
    """
    if not _write_enabled():
        raise HTTPException(
            status_code=403,
            detail="Telegram setup write is disabled (set TELEGRAM_SETUP_ENABLED=1).",
        )

    spec = _load_spec()
    group = _find_group(spec, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Unknown Telegram group '{group_id}'.")

    changed = False
    if "chat_id" in body:
        group["chat_id"] = body["chat_id"]
        changed = True
    if "invite_link" in body:
        group["invite_link"] = body["invite_link"]
        changed = True

    if changed:
        _atomic_write(spec)

    return _annotated_group(
        "cross" if group_id.startswith("cross.") else group_id.split(".", 1)[0],
        group,
    )


@router.post("/apply")
def apply_setup() -> dict[str, Any]:
    """Run the live Bot-API bootstrap via scripts/telegram_setup.py --apply.

    REFUSED (503) unless BOTH TELEGRAM_SETUP_ENABLED == "1" AND TELEGRAM_BOT_TOKEN
    are present. This endpoint never makes a network call itself.
    """
    if not _write_enabled() or not _bot_token():
        raise HTTPException(
            status_code=503,
            detail="Apply disabled: set TELEGRAM_SETUP_ENABLED=1 and TELEGRAM_BOT_TOKEN.",
        )

    script = REPO_ROOT / "scripts" / "telegram_setup.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--apply"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Bootstrap script missing: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"Apply timed out after 120s: {exc}") from exc

    return {
        "mode": "live",
        "applied": True,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
