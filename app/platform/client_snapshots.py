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
                    cond = dict(r.get("condition") or {})
                    acts = list(r.get("actions") or [])
                    if not src_id and target_client_id:
                        cond.setdefault("client_id", target_client_id)
                        acts = [
                            (
                                {
                                    **a,
                                    "params": {
                                        **(a.get("params") or {}),
                                        **(
                                            {"client_id": target_client_id}
                                            if isinstance(a.get("params"), dict)
                                            and "client_id" in json.dumps(a.get("params") or {})
                                            else {}
                                        ),
                                    },
                                }
                                if isinstance(a, dict)
                                else a
                            )
                            for a in acts
                        ]
                    blob = json.dumps({"condition": cond, "actions": acts}, ensure_ascii=False)
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


# --------------------------------------------------------------------------- #
# Niche templates — GHL-style 1-click niche clone (no golden client required)
# --------------------------------------------------------------------------- #
_NICHE_PALETTE: dict[str, str] = {
    "solar": "sunset",
    "real_estate": "royal",
    "dental": "ocean",
    "gym": "forest",
    "coaching": "violet",
    "hospital": "ocean",
    "salon": "violet",
    "restaurant": "sunset",
}


def _default_journey_templates() -> list[dict[str, Any]]:
    """Generic journey rules (no client_id) — apply pe target pe swap hota hai."""
    return [
        {
            "name": "Inquiry → WhatsApp + email follow-up draft",
            "trigger": "inquiry_received",
            "condition": {},
            "actions": [
                {"type": "draft_whatsapp", "params": {"topic": "naye inquiry ka turant follow-up"}},
                {"type": "draft_email", "params": {"topic": "inquiry thank-you + next step"}},
            ],
        },
        {
            "name": "Signup → welcome WhatsApp draft",
            "trigger": "signup",
            "condition": {},
            "actions": [
                {"type": "draft_whatsapp", "params": {"topic": "welcome + onboarding next step"}}
            ],
        },
    ]


def _default_widget_fields() -> list[dict[str, str]]:
    return [
        {"name": "name", "label": "Naam", "type": "text", "required": True},
        {"name": "phone", "label": "Phone", "type": "tel", "required": True},
        {"name": "message", "label": "Message", "type": "textarea", "required": False},
    ]


def capture_from_niche(niche_key: str, name: str = "") -> dict[str, Any]:
    """Niche se reusable setup snapshot (mini-site palette, journeys, festivals). Never raises."""
    try:
        niche_key = str(niche_key or "").strip().lower()
        if not niche_key:
            return {"ok": False, "error": "niche zaroori hai."}
        try:
            from app.niches import NICHES

            cfg = NICHES.get(niche_key) or {}
        except Exception:
            cfg = {}
        if not cfg:
            return {"ok": False, "error": f"niche '{niche_key}' nahi mila."}

        niche_name = str(cfg.get("name") or niche_key.replace("_", " ").title())
        palette = _NICHE_PALETTE.get(niche_key, "violet")
        sections: dict[str, Any] = {}
        captured: list[str] = []

        sections["client"] = {
            "niche": niche_key,
            "offer": str(cfg.get("pitch_hook") or "")[:160],
            "tagline": str(cfg.get("pitch_hook") or "")[:120],
            "services": ", ".join(
                str(x) for x in (cfg.get("content_focus") or [])[:4] if str(x).strip()
            ),
        }
        captured.append("client")

        sections["mini_site"] = {
            "palette": palette,
            "layout": "classic",
            "primary": "",
            "accent": "",
        }
        captured.append("mini_site")

        sections["widget_form"] = _default_widget_fields()
        captured.append("widget_form")

        sections["journeys"] = _default_journey_templates()
        captured.append("journeys")

        try:
            from app.marketing.cadence import DEFAULT_CADENCE

            sections["cadence_template"] = [dict(s) for s in DEFAULT_CADENCE]
            captured.append("cadence_template")
        except Exception:
            pass

        try:
            from app.marketing import festivals

            items = []
            for f in festivals.upcoming(120)[:8]:
                items.append(
                    {
                        "occasion": str(f.get("name") or ""),
                        "offer": str(f.get("marketing_angle") or "")[:120],
                        "channel": "instagram",
                        "niche": niche_key,
                        "date": str(f.get("date") or ""),
                    }
                )
            if items:
                sections["content_schedule"] = items
                captured.append("content_schedule")
        except Exception as e:
            logger.debug(f"[snapshots] niche festival schedule skip: {e}")

        sections["niche_meta"] = {
            "niche_key": niche_key,
            "niche_name": niche_name,
            "lead_band": str(cfg.get("lead_band") or cfg.get("tier") or ""),
            "content_focus": list(cfg.get("content_focus") or [])[:6],
            "keywords": list(cfg.get("keywords") or [])[:8],
        }
        captured.append("niche_meta")

        snap = {
            "id": uuid.uuid4().hex[:12],
            "kind": "niche_template",
            "name": (str(name or "").strip() or f"{niche_name} template")[:120],
            "niche_key": niche_key,
            "source_client_id": "",
            "source_slug": "",
            "created_at": _now(),
            "sections": sections,
        }
        os.makedirs(_SNAP_DIR, exist_ok=True)
        with open(_snap_path(snap["id"]), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
        _append_index(
            {
                "id": snap["id"],
                "kind": "niche_template",
                "name": snap["name"],
                "niche_key": niche_key,
                "source_client_id": "",
                "created_at": snap["created_at"],
                "sections": captured,
            }
        )
        return {
            "ok": True,
            "snapshot_id": snap["id"],
            "niche_key": niche_key,
            "sections": captured,
            "snapshot": snap,
        }
    except Exception as e:
        logger.warning(f"[snapshots] capture_from_niche failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def find_niche_snapshot(niche_key: str) -> str | None:
    """Latest niche_template snapshot id for niche, else None."""
    try:
        niche_key = str(niche_key or "").strip().lower()
        for row in list_snapshots(limit=200):
            if str(row.get("niche_key") or "").lower() != niche_key:
                continue
            if row.get("kind") != "niche_template":
                continue
            sid = str(row.get("id") or "") or None
            # Index/file drift guard (2026-08-17): file missing ho to stale id
            # mat do — capture_from_niche fresh banayega (warna "snapshot nahi
            # mila" pe apply fail hota).
            if sid and get_snapshot(sid) is not None:
                return sid
        return None
    except Exception:
        return None


def apply_niche_to_client(client_id: str, niche_key: str | None = None) -> dict[str, Any]:
    """Niche template snapshot target client pe lagao (find ya auto-capture). Never raises."""
    try:
        client_id = str(client_id or "").strip()
        if not client_id:
            return {"ok": False, "error": "client_id zaroori hai."}
        client = _get_client(client_id)
        nk = str(niche_key or client.get("niche") or "").strip().lower()
        if not nk:
            return {"ok": False, "error": "niche nahi mila (client ya param)."}
        sid = find_niche_snapshot(nk)
        auto_captured = False
        if not sid:
            cap = capture_from_niche(nk)
            if not cap.get("ok"):
                return cap
            sid = str(cap.get("snapshot_id") or "")
            auto_captured = True
        if not sid:
            return {"ok": False, "error": "niche snapshot ban nahi paya."}
        out = apply(sid, client_id)
        out["niche_key"] = nk
        out["auto_captured"] = auto_captured
        return out
    except Exception as e:
        logger.warning(f"[snapshots] apply_niche_to_client failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


__all__ = [
    "capture",
    "capture_from_niche",
    "apply",
    "apply_niche_to_client",
    "find_niche_snapshot",
    "list_snapshots",
    "get_snapshot",
]
