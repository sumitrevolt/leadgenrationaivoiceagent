"""Client snapshots (GHL-style) — ek client ka poora setup capture → naye pe apply.

Agency scale ka core trick: ek baar perfect setup banao (mini-site config, widget
form, journey rules, content-schedule pattern), snapshot lo, aur har naye client
pe 1-click apply karo (sub-account cloning, GoHighLevel "snapshots" jaisa).

  capture(client_id, name)            -> data/snapshots/<id>.json + index entry
  apply(snapshot_id, target_client_id) -> per-section best-effort apply
                                          (NAYE records append — source kabhi
                                          mutate nahi hota)
  list_snapshots() / get_snapshot(id)

Har section apna try/except — jo store khali/missing ho wo skip (best-effort).
Pure stdlib + file IO + existing stores (NO LLM, NO network). NEVER raises.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SNAP_DIR = os.path.join("data", "snapshots")
_INDEX_FILE = os.path.join(_SNAP_DIR, "index.jsonl")

# Client record ke sirf SETUP fields snapshot hote (PII jaise phone/email nahi).
_CLIENT_FIELDS = ("niche", "city", "brand", "upi_vpa", "offer", "tagline", "services")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _append_index(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(_SNAP_DIR, exist_ok=True)
        with open(_INDEX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[snapshots] index append failed: {e}")


def _read_index() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_INDEX_FILE):
            return out
        with open(_INDEX_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception as e:
        logger.debug(f"[snapshots] index read skip: {e}")
    return out


def _snap_path(snapshot_id: str) -> str:
    safe = "".join(ch for ch in str(snapshot_id or "") if ch.isalnum())[:32]
    return os.path.join(_SNAP_DIR, f"{safe}.json")


def _get_client(client_id: str) -> dict[str, Any]:
    try:
        from app.marketing import clients_store

        return clients_store.get_client(client_id) or {}
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# Capture — har section best-effort
# --------------------------------------------------------------------------- #
def capture(client_id: str, name: str = "") -> dict[str, Any]:
    """Client ka reusable setup snapshot. Never raises."""
    try:
        client_id = str(client_id or "").strip()
        if not client_id:
            return {"ok": False, "error": "client_id zaroori hai."}
        client = _get_client(client_id)
        slug = str(client.get("slug") or "").strip()

        sections: dict[str, Any] = {}
        captured: list[str] = []

        # 1) client setup fields (PII nahi)
        try:
            cs = {k: client[k] for k in _CLIENT_FIELDS if client.get(k) not in (None, "")}
            if cs:
                sections["client"] = cs
                captured.append("client")
        except Exception as e:
            logger.debug(f"[snapshots] client section skip: {e}")

        # 2) mini-site config (palette/layout/logo/colors)
        try:
            if slug:
                from app.api.minisite_builder import get_config

                cfg = get_config(slug) or {}
                cfg.pop("slug", None)
                sections["mini_site"] = cfg
                captured.append("mini_site")
        except Exception as e:
            logger.debug(f"[snapshots] mini_site section skip: {e}")

        # 3) widget form fields (embed_widget custom form, agar saved hai)
        try:
            if slug:
                from app.marketing.embed_widget import get_form_config

                fields = get_form_config(slug)
                if fields:
                    sections["widget_form"] = fields
                    captured.append("widget_form")
        except Exception as e:
            logger.debug(f"[snapshots] widget section skip: {e}")

        # 4) journey rules — is client se linked (condition/params me client_id)
        try:
            from app.marketing import journeys

            mine = []
            for r in journeys.list_journeys():
                blob = json.dumps(r.get("condition") or {}) + json.dumps(r.get("actions") or [])
                if client_id and client_id in blob:
                    mine.append(
                        {
                            "name": r.get("name"),
                            "trigger": r.get("trigger"),
                            "condition": r.get("condition") or {},
                            "actions": r.get("actions") or [],
                        }
                    )
            if mine:
                sections["journeys"] = mine
                captured.append("journeys")
        except Exception as e:
            logger.debug(f"[snapshots] journeys section skip: {e}")

        # 5) cadence template (global DEFAULT_CADENCE copy — reference ke liye)
        try:
            from app.marketing.cadence import DEFAULT_CADENCE

            sections["cadence_template"] = [dict(s) for s in DEFAULT_CADENCE]
            captured.append("cadence_template")
        except Exception as e:
            logger.debug(f"[snapshots] cadence section skip: {e}")

        # 6) content-schedule pattern (is client ke scheduled items ka shape)
        try:
            from app.marketing import content_schedule

            items = [
                {
                    "occasion": i.get("occasion") or "",
                    "offer": i.get("offer") or "",
                    "channel": i.get("channel") or "instagram",
                    "niche": i.get("niche") or "general",
                    "date": i.get("date") or "",
                }
                for i in content_schedule.list_scheduled()
                if str(i.get("client_id") or "") == client_id
            ]
            if items:
                sections["content_schedule"] = items[:50]
                captured.append("content_schedule")
        except Exception as e:
            logger.debug(f"[snapshots] schedule section skip: {e}")

        snap = {
            "id": uuid.uuid4().hex[:12],
            "name": (
                str(name or "").strip() or f"Snapshot of {client.get('business_name') or client_id}"
            )[:120],
            "source_client_id": client_id,
            "source_slug": slug,
            "created_at": _now(),
            "sections": sections,
        }
        os.makedirs(_SNAP_DIR, exist_ok=True)
        with open(_snap_path(snap["id"]), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
        _append_index(
            {
                "id": snap["id"],
                "name": snap["name"],
                "source_client_id": client_id,
                "created_at": snap["created_at"],
                "sections": captured,
            }
        )
        return {"ok": True, "snapshot_id": snap["id"], "sections": captured, "snapshot": snap}
    except Exception as e:
        logger.warning(f"[snapshots] capture failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    try:
        path = _snap_path(snapshot_id)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def list_snapshots(limit: int = 100) -> list[dict[str, Any]]:
    try:
        rows = _read_index()
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit or 100), 500))]
    except Exception as e:
        logger.warning(f"[snapshots] list failed: {e}")
        return []


# --------------------------------------------------------------------------- #
# Apply — har section best-effort; NAYE records append, source untouched
# --------------------------------------------------------------------------- #
def apply(snapshot_id: str, target_client_id: str) -> dict[str, Any]:
    """Snapshot sections target client pe lagao. Never raises."""
    try:
        snap = get_snapshot(snapshot_id)
        if snap is None:
            return {"ok": False, "error": "snapshot nahi mila."}
        target_client_id = str(target_client_id or "").strip()
        if not target_client_id:
            return {"ok": False, "error": "target_client_id zaroori hai."}
        target = _get_client(target_client_id)
        target_slug = str(target.get("slug") or "").strip()
        sections: dict[str, Any] = snap.get("sections") or {}
        results: dict[str, Any] = {}

        # mini-site config → target slug pe naya append (set_config = append store)
        try:
            cfg = sections.get("mini_site")
            if cfg and target_slug:
                from app.api.minisite_builder import set_config

                set_config(
                    target_slug,
                    palette=cfg.get("palette"),
                    layout=cfg.get("layout"),
                    logo_url=None,  # logo source-client ka hai — copy NAHI karte
                    primary=cfg.get("primary"),
                    accent=cfg.get("accent"),
                )
                results["mini_site"] = "applied"
            elif cfg:
                results["mini_site"] = "skipped (target ka slug nahi)"
        except Exception as e:
            results["mini_site"] = f"error: {str(e)[:80]}"

        # widget form fields → target slug
        try:
            fields = sections.get("widget_form")
            if fields and target_slug:
                from app.marketing.embed_widget import save_form_config

                save_form_config(target_slug, fields)
                results["widget_form"] = "applied"
            elif fields:
                results["widget_form"] = "skipped (target ka slug nahi)"
        except Exception as e:
            results["widget_form"] = f"error: {str(e)[:80]}"

        # journeys → NAYE rules (new ids, disabled — review karke on karo)
        try:
            rules = sections.get("journeys") or []
            if rules:
                from app.marketing import journeys

                src_id = str(snap.get("source_client_id") or "")
                added = 0
                for r in rules:
                    blob = json.dumps(
                        {"condition": r.get("condition") or {}, "actions": r.get("actions") or []},
                        ensure_ascii=False,
                    )
                    if src_id:
                        blob = blob.replace(src_id, target_client_id)
                    swapped = json.loads(blob)
                    created = journeys.add_journey(
                        name=f"{r.get('name') or 'Rule'} (snapshot)",
                        trigger=str(r.get("trigger") or "manual"),
                        actions=swapped.get("actions") or [],
                        condition=swapped.get("condition") or {},
                        enabled=False,
                    )
                    if created.get("id"):
                        added += 1
                results["journeys"] = f"applied ({added} rules, disabled — review karke on karo)"
        except Exception as e:
            results["journeys"] = f"error: {str(e)[:80]}"

        # content-schedule pattern → sirf FUTURE dates re-schedule
        try:
            items = sections.get("content_schedule") or []
            if items:
                from app.marketing import content_schedule

                today = date.today().isoformat()
                biz = str(target.get("business_name") or "Aapka Business")
                niche = str(target.get("niche") or "general")
                added = 0
                for it in items:
                    d = str(it.get("date") or "")
                    if d and d >= today:
                        content_schedule.schedule(
                            business_name=biz,
                            niche=niche,
                            date_iso=d,
                            occasion=str(it.get("occasion") or ""),
                            offer=str(it.get("offer") or ""),
                            channel=str(it.get("channel") or "instagram"),
                            client_id=target_client_id,
                        )
                        added += 1
                results["content_schedule"] = f"applied ({added} future items)"
        except Exception as e:
            results["content_schedule"] = f"error: {str(e)[:80]}"

        # cadence_template = global DEFAULT_CADENCE — apply ki zaroorat nahi
        if "cadence_template" in sections:
            results["cadence_template"] = "info-only (global template, apply not needed)"
        if "client" in sections:
            results["client"] = "info-only (client fields reference — manual merge)"

        return {
            "ok": True,
            "snapshot_id": snap.get("id"),
            "target_client_id": target_client_id,
            "results": results,
        }
    except Exception as e:
        logger.warning(f"[snapshots] apply failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


__all__ = ["capture", "apply", "list_snapshots", "get_snapshot"]
