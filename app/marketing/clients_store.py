"""
clients_store.py — marketing CLIENT records (per-client social-media handling).
================================================================================

Har marketing client ka record `data/marketing_clients.jsonl` me — jsonl-first
(append-only, kabhi data lost nahi). Brand bhi brand_kit.save_brand() se save
hota hai taaki posters/posts auto-brand ho jaayein.

  add_client(business_name, niche, ...) -> dict   (uuid id, dedupe by phone/name)
  list_clients(status=None)             -> list
  get_client(cid)                       -> dict | None
  get_by_slug(slug)                     -> dict | None   (mini-site /b/{slug})
  set_status(cid, status)               -> bool
  update_client(cid, **fields)          -> dict | None

Har client ka ek unique `slug` (kebab-case business_name + 4-char id suffix)
hota hai — mini-site /b/{slug} ke liye. Slug idempotently backfill hota hai jab
client list/fetch hota hai (purane records bhi turant slug pa jaate hain).

Pure stdlib, file-based, KABHI raise nahi karta. Module-level path resolver
``_CLIENTS_FILE()`` test-monkeypatch ke liye exposed hai (call-time, not import-time).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _CLIENTS_FILE() -> str:
    """Marketing client registry — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="customers.identity",
            legacy_path=Path("data") / "marketing_clients.jsonl",
            target_segments=("customers", "marketing_clients.jsonl"),
        )
    )


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# brand_kit import-safe (na mile to bhi clients_store chale).
try:
    from app.marketing import brand_kit  # type: ignore
except Exception:  # pragma: no cover
    brand_kit = None  # type: ignore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digits(phone: Any) -> str:
    """Phone ke sirf last-10 digits (dedupe key)."""
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-10:] if len(d) >= 10 else d


def resolve_product(c: dict[str, Any]) -> str:
    """Product lane: marketing | voice | combo (legacy rows infer from plan key)."""
    prod = str(c.get("product") or "").strip().lower()
    if prod in ("both", "combo"):
        return "combo"
    if prod in ("marketing", "voice"):
        return prod
    plan = str(c.get("plan") or "").strip().lower()
    try:
        from app.marketing.combo_packages import is_combo_plan
        from app.marketing.voice_packages import is_voice_plan

        if is_combo_plan(plan) or plan.startswith("combo_"):
            return "combo"
        if is_voice_plan(plan) or plan.startswith("voice_"):
            return "voice"
    except Exception:
        pass
    return "marketing"


# Back-compat alias — callers/tests (e.g. video_ad_cycle._eligible_clients) use the
# older name `product_lane`. Kept pointing at resolve_product so the marketing/voice/
# combo lane logic stays single-sourced. (Missing attr was silently caught by a
# try/except at the call site → every client defaulted to "marketing".)
product_lane = resolve_product


def _clean_color(value: Any) -> str:
    c = str(value or "").strip()
    return c if _HEX_RE.match(c) else ""


def _norm_brand(brand: dict[str, Any] | None) -> dict[str, Any]:
    b = brand if isinstance(brand, dict) else {}
    return {
        "primary": _clean_color(b.get("primary")),
        "accent": _clean_color(b.get("accent")),
        "tagline": str(b.get("tagline") or "").strip()[:160],
        "logo_text": str(b.get("logo_text") or "").strip()[:40],
    }


def _norm_socials(socials: dict[str, Any] | None) -> dict[str, str]:
    s = socials if isinstance(socials, dict) else {}
    return {
        "instagram": str(s.get("instagram") or "").strip()[:200],
        "facebook": str(s.get("facebook") or "").strip()[:200],
        "gbp": str(s.get("gbp") or "").strip()[:300],
    }


_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: Any) -> str:
    """business_name → kebab-case slug base ('Sharma Solar!!' → 'sharma-solar')."""
    s = _SLUG_STRIP_RE.sub("-", str(text or "").strip().lower()).strip("-")
    return s[:48] or "business"


def _make_slug(business_name: Any, cid: Any) -> str:
    """Unique slug = kebab(business_name) + '-' + first 4 chars of id.

    id suffix se collision safe rehta hai (do same-naam businesses bhi alag).
    """
    base = _slugify(business_name)
    suffix = re.sub(r"[^a-z0-9]", "", str(cid or "").lower())[:4] or "x"
    return f"{base}-{suffix}"


def _read_all() -> list[dict[str, Any]]:
    """Saare client records (parse-safe; corrupt lines skip).

    Side-effect: slug missing ho to backfill karke file rewrite karta hai
    (idempotent — ek baar likhne ke baad dobara nahi). Backfill fail ho to bhi
    in-memory records me slug set ho jaata hai (read kabhi raise nahi).
    """
    rows: list[dict[str, Any]] = []
    try:
        # Resolver at each I/O site — binding to a local unbinds the allowlist (A3).
        if not os.path.isfile(_CLIENTS_FILE()):
            return rows
        with open(_CLIENTS_FILE(), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict) and rec.get("id"):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] read failed: {e}")
        return rows

    # --- slug backfill (idempotent) --- #
    changed = False
    seen: set[str] = set()
    for r in rows:
        slug = str(r.get("slug") or "").strip()
        if not slug:
            slug = _make_slug(r.get("business_name"), r.get("id"))
            r["slug"] = slug
            changed = True
        # de-dup safety: agar do records ka slug same nikla (legacy), suffix lamba karo
        if slug in seen:
            slug = _make_slug(r.get("business_name"), str(r.get("id") or "")[:8])
            r["slug"] = slug
            changed = True
        seen.add(slug)
    if changed:
        try:
            _rewrite(rows)
        except Exception as e:  # pragma: no cover - file lock etc.; in-mem slug kaafi hai
            logger.debug(f"[clients_store] slug backfill rewrite skip: {e}")
    return rows


def _file_lock(path: str):
    """Best-effort cross-process lock for `path` (web + worker + scheduler share
    the active runtime-data root). Falls back to a no-op contextmanager if `filelock`
    isn't installed or the lock can't be acquired in time — module contract is
    "never raise", so an unlocked write is preferred over a crash (production audit
    2026-07-01, F-DB5: closes the _append/_rewrite race, doesn't guarantee zero-race).

    Lock colocates with the ACTIVE ledger via ``resolve_lock_path`` when ``path``
    is the authority path; monkeypatched test paths keep ``path + ".lock"``.
    """
    try:
        from filelock import FileLock

        from app.platform import runtime_data_authority as _auth

        auth_store = str(
            _auth.resolve_store_path(
                store_id="customers.identity",
                legacy_path=Path("data") / "marketing_clients.jsonl",
                target_segments=("customers", "marketing_clients.jsonl"),
            )
        )
        try:
            same = os.path.normpath(path) == os.path.normpath(auth_store)
        except Exception:
            same = False
        if same:
            lock = str(
                _auth.resolve_lock_path(
                    store_id="customers.identity",
                    legacy_path=Path("data") / "marketing_clients.jsonl",
                    target_segments=("customers", "marketing_clients.jsonl"),
                )
            )
        else:
            lock = path + ".lock"
        return FileLock(lock, timeout=5)
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def _append(rec: dict[str, Any]) -> None:
    # Resolver at each I/O site — binding to a local unbinds the allowlist (A3).
    os.makedirs(os.path.dirname(_CLIENTS_FILE()) or ".", exist_ok=True)
    try:
        with _file_lock(_CLIENTS_FILE()):
            with open(_CLIENTS_FILE(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # lock timeout etc. — fall back to unlocked append
        logger.debug(f"[clients_store] _append lock skip: {e}")
        with open(_CLIENTS_FILE(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _rewrite(rows: list[dict[str, Any]]) -> None:
    """Poori file dobara likho (status/update ke liye). Atomic-ish."""
    from app.platform import runtime_data_authority as _auth

    # Active path resolved per call; tmp companion colocates via resolve_temp_path
    # when on the authority path, else follows a monkeypatched redirect.
    auth_store = str(
        _auth.resolve_store_path(
            store_id="customers.identity",
            legacy_path=Path("data") / "marketing_clients.jsonl",
            target_segments=("customers", "marketing_clients.jsonl"),
        )
    )
    os.makedirs(os.path.dirname(_CLIENTS_FILE()) or ".", exist_ok=True)
    try:
        same = os.path.normpath(_CLIENTS_FILE()) == os.path.normpath(auth_store)
    except Exception:
        same = False
    if same:
        tmp = str(
            _auth.resolve_temp_path(
                store_id="customers.identity",
                legacy_path=Path("data") / "marketing_clients.jsonl",
                target_segments=("customers", "marketing_clients.jsonl"),
            )
        )
    else:
        tmp = _CLIENTS_FILE() + ".tmp"

    def _do_write() -> None:
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, _CLIENTS_FILE())

    try:
        with _file_lock(_CLIENTS_FILE()):
            _do_write()
    except Exception as e:  # lock timeout etc. — fall back to unlocked rewrite
        logger.debug(f"[clients_store] _rewrite lock skip: {e}")
        _do_write()


def add_client(
    business_name: str,
    niche: str,
    city: str = "",
    phone: str = "",
    plan: str = "starter",
    brand: dict[str, Any] | None = None,
    socials: dict[str, Any] | None = None,
    product: str = "marketing",
) -> dict[str, Any]:
    """Naya marketing client banao (uuid id). Dedupe by phone (last-10) ya
    business_name (case-insensitive) — existing mile to wahi return (no dup).
    Brand bhi brand_kit me save hota hai (posters auto-brand). Kabhi raise nahi."""
    try:
        name = (business_name or "").strip()[:120] or "Aapka Business"
        niche_k = (niche or "general").strip().lower() or "general"
        ph_key = _digits(phone)
        name_key = name.lower()

        existing = _read_all()
        for r in existing:
            if ph_key and _digits(r.get("phone")) == ph_key:
                return r
            if not ph_key and str(r.get("business_name") or "").strip().lower() == name_key:
                return r

        cid = uuid.uuid4().hex[:12]
        brand_d = _norm_brand(brand)
        prod = (product or "marketing").strip().lower()
        if prod == "both":
            prod = "combo"
        if prod not in ("marketing", "voice", "combo"):
            prod = "marketing"
        rec: dict[str, Any] = {
            "id": cid,
            "business_name": name,
            "slug": _make_slug(name, cid),  # mini-site /b/{slug}
            "niche": niche_k,
            "city": (city or "").strip()[:80],
            "phone": str(phone or "").strip()[:40],
            "plan": (plan or "starter").strip().lower()[:40] or "starter",
            "product": prod,  # marketing | voice | combo (ADR-009 two-product split)
            "status": "active",
            "brand": brand_d,
            "socials": _norm_socials(socials),
            "created_at": _now(),
        }
        _append(rec)

        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(cid, "customer_created", detail=name, key="lc:created")
        except Exception as e:  # pragma: no cover
            logger.debug(f"[clients_store] ledger log skip: {e}")

        # Brand ko brand_kit me bhi mirror karo (posters/content-pack auto-brand).
        if brand_kit is not None:
            try:
                brand_kit.save_brand(
                    cid,
                    {
                        "business_name": name,
                        "tagline": brand_d.get("tagline", ""),
                        "phone": rec["phone"],
                        "colors": {
                            "primary": brand_d.get("primary", ""),
                            "accent": brand_d.get("accent", ""),
                        },
                        "logo_text": brand_d.get("logo_text", ""),
                    },
                )
            except Exception as e:  # pragma: no cover
                logger.debug(f"[clients_store] brand mirror skip: {e}")
        return rec
    except Exception as e:
        logger.warning(f"[clients_store] add_client failed: {e}")
        return {"error": str(e)}


def list_clients(status: str | None = None, product: str | None = None) -> list[dict[str, Any]]:
    """Saare clients (optional status / product filter). Newest first. Kabhi raise nahi."""
    try:
        rows = _read_all()
        if status:
            st = status.strip().lower()
            rows = [r for r in rows if str(r.get("status") or "").lower() == st]
        if product:
            want = product.strip().lower()
            if want in ("marketing", "voice", "combo"):
                rows = [r for r in rows if resolve_product(r) == want]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] list_clients failed: {e}")
        return []


def get_client(cid: str) -> dict[str, Any] | None:
    """Ek client by id (None agar na mile). Kabhi raise nahi."""
    try:
        key = (cid or "").strip()
        for r in _read_all():
            if str(r.get("id")) == key:
                return r
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] get_client failed: {e}")
    return None


def resolve_client(cid: str) -> dict[str, Any] | None:
    """Canonical marketing client by id OR billing alias (`billing_client_ids`).

    Invoice/subscription ids (e.g. `d79d690f61b3`) often differ from the marketing
    slug id (`jiya-makeover`). Reports/ledger must use the marketing id so proof
    lands on the customer the portal actually loads. Never raises.
    """
    try:
        key = (cid or "").strip()
        if not key:
            return None
        direct = get_client(key)
        if direct:
            return direct
        for r in _read_all():
            aliases = r.get("billing_client_ids") or []
            if not isinstance(aliases, list | tuple | set):
                continue
            if key in {str(a).strip() for a in aliases if str(a).strip()}:
                return r
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] resolve_client failed: {e}")
    return None


def canonical_client_id(cid: str) -> str:
    """Return marketing client id for any id/alias; fallback to input stripped."""
    try:
        rec = resolve_client(cid)
        if rec and str(rec.get("id") or "").strip():
            return str(rec.get("id")).strip()
    except Exception:
        pass
    return str(cid or "").strip()


def link_billing_alias(
    marketing_id: str,
    billing_id: str,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """Idempotently attach ``billing_id`` to a marketing record's ``billing_client_ids``.

    Used after activation/provisioning so a UPI/subscription id (or a recreated
    legacy invoice owner id) can resolve back to the marketing tenant the portal
    and content pipeline already use. Never silently steals an alias owned by
    another tenant. Never raises.

    Returns ``{ok, linked, reason, marketing_id, billing_id}``.
    """
    mid = str(marketing_id or "").strip()
    bid = str(billing_id or "").strip()
    out: dict[str, Any] = {
        "ok": False,
        "linked": False,
        "reason": "unknown",
        "marketing_id": mid,
        "billing_id": bid,
        "actor": str(actor or "system")[:80],
    }
    try:
        if not mid or not bid:
            out["reason"] = "missing_ids"
            return out
        if mid == bid:
            out.update({"ok": True, "reason": "same_id"})
            return out

        # Already resolvable to this marketing id → idempotent success.
        existing = resolve_client(bid)
        if existing and str(existing.get("id") or "").strip() == mid:
            out.update({"ok": True, "reason": "already_linked"})
            return out
        # Alias (or direct id) owned by a different marketing tenant → refuse.
        if existing and str(existing.get("id") or "").strip() not in ("", mid):
            out.update(
                {
                    "reason": "conflict",
                    "owner": str(existing.get("id") or "").strip(),
                }
            )
            return out

        # billing_id is itself another marketing client's primary id → refuse.
        direct = get_client(bid)
        if direct and str(direct.get("id") or "").strip() not in ("", mid):
            out.update(
                {
                    "reason": "conflict_direct",
                    "owner": str(direct.get("id") or "").strip(),
                }
            )
            return out

        mrec = get_client(mid)
        if not mrec:
            out["reason"] = "marketing_not_found"
            return out

        aliases = [
            str(a).strip() for a in (mrec.get("billing_client_ids") or []) if str(a or "").strip()
        ]
        if bid in aliases:
            out.update({"ok": True, "reason": "already_linked"})
            return out

        new_aliases = list(dict.fromkeys([*aliases, bid]))[:10]
        updated = update_client(mid, billing_client_ids=new_aliases)
        if updated is None:
            out["reason"] = "update_failed"
            return out

        out.update({"ok": True, "linked": True, "reason": "linked"})
        try:
            logger.info(
                "[clients_store] link_billing_alias ok marketing=%s billing=%s actor=%s",
                mid,
                bid,
                out["actor"],
            )
        except Exception:
            pass
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                mid,
                "identity_alias_linked",
                detail=f"billing_alias:{bid}",
                actor=str(out["actor"])[:40],
                key=f"alias:{mid}:{bid}",
            )
        except Exception:
            pass
        return out
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] link_billing_alias failed: {e}")
        out["reason"] = "error"
        return out


def get_by_slug(slug: str) -> dict[str, Any] | None:
    """Ek client by slug — mini-site /b/{slug} ke liye. None agar na mile.

    _read_all() pehle missing slugs backfill karta hai, isliye purane records
    bhi match ho jaate hain. Case-insensitive. Kabhi raise nahi."""
    try:
        key = (slug or "").strip().lower()
        if not key:
            return None
        for r in _read_all():
            if str(r.get("slug") or "").strip().lower() == key:
                return r
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] get_by_slug failed: {e}")
    return None


def set_status(cid: str, status: str) -> bool:
    """Client ka status badlo (active/paused/dead). True agar update hua."""
    return update_client(cid, status=(status or "").strip().lower()) is not None


_ALLOWED_FIELDS = {
    "business_name",
    "niche",
    "city",
    "phone",
    "email",
    "contact_email",
    "plan",
    "status",
    "brand",
    "socials",
    "trial",  # free-trial flag (bool) — conversion funnel
    "trial_expires",  # ISO timestamp — trial khatam kab
    "upi_vpa",  # client ka UPI ID (naam@bank) — payment QR poster (engage/upi-qr)
    "setup_done",  # bool — onboarding complete (idempotency guard for AUTO_ONBOARD sweep)
    "setup_at",  # ISO timestamp — onboarding kab hua
    "crm",  # dict — per-client Zoho/HubSpot config (crm_sync.save_client_config)
    "wizard_setup",  # dict — onboard wizard: custom opening_line + services/offer/business_type/niche
    "offer",  # str — wizard/niche offer line (posters + voice copy)
    "website",  # business site URL — AUTO_ONBOARD website→KB seed (audit 2026-07-04: was whitelist-blocked)
    "awaiting_kb_interview",  # bool — no website at onboarding; WhatsApp business-info
    # reply still pending (onboarding.py welcome message + wa selfhost webhook capture)
    "delivery_state",  # str — value-delivery state machine (paid/assets_built/delivered/
    # acknowledged); customer_delivery.py. Whitelist-block = re-send spam (2026-07-05).
    "delivered_at",  # ISO timestamp — value delivered to customer kab
    "acknowledged_at",  # ISO timestamp — customer ne reply/engage karke acknowledge kiya
    "services",  # description of services/products
    "target_area",  # local target areas/neighborhoods
    "whatsapp_phone",  # WhatsApp connection phone
    "approval_preference",  # "auto" or "manual" post approvals
    "billing_client_ids",  # legacy/recreated IDs that own immutable invoices
    "social_error",  # customer-facing connection status / error text
    "blocked_reason",  # admin-facing tech error / reason blocked
    "email_notifications",  # approval/report email delivery preference
    "approval_email_opt_out",  # explicit approval-reminder opt-out
    "trial_nudge_stage",  # str — last trial nudge stage ("expiring"/"expired") — trial_nudge.py idempotency (BLK-02)
    "trial_nudge_at",  # ISO timestamp — last trial nudge kab gaya
    "trial_nudge_count",  # int — lifetime trial-nudge count (cap enforcement)
}


def update_client(cid: str, **fields: Any) -> dict[str, Any] | None:
    """Client ke fields update karo (whitelist). Updated dict ya None. Kabhi
    raise nahi. Brand/socials dict-merge hote hain; brand change brand_kit me
    bhi mirror hota hai."""
    try:
        key = (cid or "").strip()
        rows = _read_all()
        found: dict[str, Any] | None = None
        for r in rows:
            if str(r.get("id")) == key:
                found = r
                break
        if found is None:
            return None

        for k, v in fields.items():
            if k not in _ALLOWED_FIELDS:
                continue
            if k == "brand":
                found["brand"] = _norm_brand(v)
            elif k == "socials":
                found["socials"] = _norm_socials(v)
            elif k == "status":
                found["status"] = str(v or "").strip().lower()[:30] or found.get("status", "active")
            elif k == "niche":
                found["niche"] = str(v or "").strip().lower()[:80] or found.get("niche", "general")
            elif k == "trial":
                found["trial"] = bool(v)
            elif k in ("email_notifications", "approval_email_opt_out"):
                found[k] = bool(v)
            elif k == "setup_done":
                found["setup_done"] = bool(v)  # bool, NOT str("True") — idempotency guard
            elif k == "awaiting_kb_interview":
                found["awaiting_kb_interview"] = bool(v)
            elif k in ("crm", "wizard_setup"):
                # per-client config dicts — store as-is (generic else would str() it)
                found[k] = dict(v) if isinstance(v, dict) else found.get(k, {})
            elif k == "billing_client_ids":
                vals = v if isinstance(v, list | tuple | set) else []
                clean = (str(x or "").strip()[:120] for x in vals)
                found[k] = list(dict.fromkeys(x for x in clean if x))[:10]
            elif k in ("email", "contact_email"):
                found[k] = str(v or "").strip().lower()[:255]
            else:
                found[k] = str(v or "").strip()[:120]
        found["updated_at"] = _now()
        _rewrite(rows)

        if "brand" in fields and brand_kit is not None:
            try:
                b = found["brand"]
                brand_kit.save_brand(
                    key,
                    {
                        "business_name": found.get("business_name", ""),
                        "tagline": b.get("tagline", ""),
                        "phone": found.get("phone", ""),
                        "colors": {"primary": b.get("primary", ""), "accent": b.get("accent", "")},
                        "logo_text": b.get("logo_text", ""),
                    },
                )
            except Exception:  # pragma: no cover
                pass
        return found
    except Exception as e:
        logger.warning(f"[clients_store] update_client failed: {e}")
        return None


def delete_client(cid: str) -> bool:
    """Ek client record permanently hatao (admin cleanup — test/junk). True agar
    mila + hata. Never-raise. (Irreversible — UI confirm pe hi call karein.)"""
    try:
        key = (cid or "").strip()
        if not key:
            return False
        rows = _read_all()
        new_rows = [r for r in rows if str(r.get("id")) != key]
        if len(new_rows) == len(rows):
            return False
        _rewrite(new_rows)
        return True
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] delete_client failed: {e}")
        return False


def dedupe_clients() -> dict[str, Any]:
    """Exact-duplicate client records hatao — same phone (last-10), ya (phone na ho
    to) same business_name. Newest rakho. Returns {removed, kept}. Never-raise."""
    try:
        rows = _read_all()
        rows_sorted = sorted(rows, key=lambda r: str(r.get("created_at") or ""), reverse=True)
        seen: set[str] = set()
        keep: list[dict[str, Any]] = []
        removed = 0
        for r in rows_sorted:
            ph = _digits(r.get("phone"))
            dkey = (
                ("ph:" + ph) if ph else ("nm:" + str(r.get("business_name") or "").strip().lower())
            )
            if dkey in seen:
                removed += 1
                continue
            seen.add(dkey)
            keep.append(r)
        if removed:
            _rewrite(keep)
        return {"removed": removed, "kept": len(keep)}
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] dedupe_clients failed: {e}")
        return {"removed": 0, "kept": 0, "error": str(e)}


__all__ = [
    "add_client",
    "list_clients",
    "get_client",
    "resolve_client",
    "canonical_client_id",
    "link_billing_alias",
    "get_by_slug",
    "set_status",
    "update_client",
    "delete_client",
    "dedupe_clients",
]
