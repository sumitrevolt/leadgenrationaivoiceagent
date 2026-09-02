"""
product_catalog.py — per-mini-site PRODUCT catalog store (WhatsApp-store style).
=================================================================================

Dhanda/Interakt edge: client ke /b/{slug} mini-site pe products grid +
"WhatsApp pe order karein" 1-click buttons. Yeh module sirf STORE + CRUD hai;
rendering `mini_site.py` me hota hai (lazy import, empty = ZERO change).

NOTE: `app/marketing/catalog.py` PEHLE se exist karta hai — woh ek SVG
price-list CARD generator hai (/api/marketing/catalog). Isliye yeh alag naam.

Store: data/catalogs/<slug>.jsonl — append-only events:
  {"op":"add", "product":{id,name,price_inr,photo_url,desc,in_stock,added_at}}
  {"op":"delete", "id": "..."}
  {"op":"update", "id": "...", "fields": {...}}
list_products() events ko replay karke current state deta hai.

Pure stdlib, NEVER raises (error dicts / empty lists).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CAT_DIR = os.path.join("data", "catalogs")
_MAX_PRODUCTS = 60


def _safe_slug(slug: Any) -> str:
    s = re.sub(r"[^a-z0-9_-]", "", str(slug or "").strip().lower())[:80]
    return s


def _path(slug: Any) -> str:
    return os.path.join(_CAT_DIR, (_safe_slug(slug) or "_none") + ".jsonl")


def _price(raw: Any) -> float:
    """price_inr normalize → float >= 0 (invalid = 0)."""
    try:
        s = str(raw if raw is not None else "").replace("₹", "").replace(",", "").strip()
        v = float(s) if s else 0.0
        return round(v, 2) if v > 0 else 0.0
    except Exception:
        return 0.0


def _safe_url(raw: Any) -> str:
    """photo_url — sirf http(s) ya hamare relative paths allow (XSS/JS-url block)."""
    u = str(raw or "").strip()[:500]
    if not u:
        return ""
    if u.startswith(("https://", "http://", "/")):
        return u
    return ""


def _append(slug: str, event: dict[str, Any]) -> bool:
    try:
        os.makedirs(_CAT_DIR, exist_ok=True)
        with open(_path(slug), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[product_catalog] write failed for {slug}: {e}")
        return False


def _events(slug: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    path = _path(slug)
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if isinstance(ev, dict):
                        out.append(ev)
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"[product_catalog] read failed for {path}: {e}")
    return out


def list_products(slug: str, include_out_of_stock: bool = True) -> list[dict[str, Any]]:
    """Current products (events replay; insertion order). Never raises."""
    state: dict[str, dict[str, Any]] = {}
    try:
        for ev in _events(slug):
            op = ev.get("op")
            if op == "add" and isinstance(ev.get("product"), dict):
                p = ev["product"]
                pid = str(p.get("id") or "")
                if pid:
                    state[pid] = p
            elif op == "delete":
                state.pop(str(ev.get("id") or ""), None)
            elif op == "update":
                pid = str(ev.get("id") or "")
                if pid in state and isinstance(ev.get("fields"), dict):
                    for k in ("name", "price_inr", "photo_url", "desc", "in_stock"):
                        if k in ev["fields"]:
                            state[pid][k] = ev["fields"][k]
    except Exception as e:
        logger.warning(f"[product_catalog] list failed: {e}")
    items = list(state.values())
    if not include_out_of_stock:
        items = [p for p in items if p.get("in_stock", True)]
    return items


def add_product(
    slug: str,
    name: str,
    price_inr: Any = 0,
    photo_url: str = "",
    desc: str = "",
    in_stock: bool = True,
) -> dict[str, Any]:
    """Product add — {ok, product} ya {ok:False, error}. Never raises."""
    try:
        s = _safe_slug(slug)
        if not s:
            return {"ok": False, "error": "Sahi slug chahiye."}
        nm = str(name or "").strip()[:120]
        if not nm:
            return {"ok": False, "error": "Product ka naam zaroori hai."}
        if len(list_products(s)) >= _MAX_PRODUCTS:
            return {"ok": False, "error": f"Catalog full (max {_MAX_PRODUCTS} products)."}
        product = {
            "id": uuid.uuid4().hex[:12],
            "name": nm,
            "price_inr": _price(price_inr),
            "photo_url": _safe_url(photo_url),
            "desc": str(desc or "").strip()[:300],
            "in_stock": bool(in_stock),
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        if not _append(s, {"op": "add", "product": product}):
            return {"ok": False, "error": "Save nahi hua — dobara try karein."}
        return {"ok": True, "product": product, "total": len(list_products(s))}
    except Exception as e:
        logger.warning(f"[product_catalog] add failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def update_product(slug: str, product_id: str, **fields: Any) -> dict[str, Any]:
    """Partial update (name/price_inr/photo_url/desc/in_stock). Never raises."""
    try:
        s = _safe_slug(slug)
        pid = str(product_id or "").strip()
        existing = {p["id"] for p in list_products(s)}
        if pid not in existing:
            return {"ok": False, "error": "Product nahi mila."}
        clean: dict[str, Any] = {}
        if "name" in fields and str(fields["name"] or "").strip():
            clean["name"] = str(fields["name"]).strip()[:120]
        if "price_inr" in fields:
            clean["price_inr"] = _price(fields["price_inr"])
        if "photo_url" in fields:
            clean["photo_url"] = _safe_url(fields["photo_url"])
        if "desc" in fields:
            clean["desc"] = str(fields["desc"] or "").strip()[:300]
        if "in_stock" in fields:
            clean["in_stock"] = bool(fields["in_stock"])
        if not clean:
            return {"ok": False, "error": "Koi update field nahi mila."}
        if not _append(s, {"op": "update", "id": pid, "fields": clean}):
            return {"ok": False, "error": "Save nahi hua."}
        return {"ok": True, "id": pid, "updated": list(clean.keys())}
    except Exception as e:
        logger.warning(f"[product_catalog] update failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def delete_product(slug: str, product_id: str) -> dict[str, Any]:
    """Product delete (tombstone event). Never raises."""
    try:
        s = _safe_slug(slug)
        pid = str(product_id or "").strip()
        existing = {p["id"] for p in list_products(s)}
        if pid not in existing:
            return {"ok": False, "error": "Product nahi mila."}
        if not _append(s, {"op": "delete", "id": pid}):
            return {"ok": False, "error": "Save nahi hua."}
        return {"ok": True, "id": pid, "total": len(list_products(s))}
    except Exception as e:
        logger.warning(f"[product_catalog] delete failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def fmt_price(price_inr: Any) -> str:
    """Display: 249 -> '₹249', 249.5 -> '₹249.50', 0/invalid -> ''."""
    v = _price(price_inr)
    if v <= 0:
        return ""
    return f"₹{int(v)}" if abs(v - int(v)) < 1e-9 else f"₹{v:.2f}"


__all__ = ["add_product", "update_product", "delete_product", "list_products", "fmt_price"]
