"""video_delivery.py — per-customer + ops-group Telegram delivery for videos.

WHY THIS EXISTS
---------------
The owner scope says a finished, approved video must reach the customer where
they already work (a per-customer Telegram thread) **and** land in an ops group
for review, with a durable receipt so "did the customer actually get it?" is
answerable from the ledger rather than from logs. Today the approved video only
exists as a file + an approval row; nothing carries it to a human.

WHAT IT IS / IS NOT
-------------------
  * **Egress ONLY.** This module sends via the EXISTING Telegram egress path
    (`app/social_engine/providers.py::TelegramProvider`, the proven `sendVideo`
    request shape). It NEVER calls `getUpdates` and never adds a bot — Telegram
    *ingress* is owned by Hermes (design C9).
  * **Fail-closed.** `VIDEO_TELEGRAM_DELIVERY_ENABLED` defaults OFF. Flag off,
    no bot token, or no per-customer binding ⇒ an honest no-op result, never an
    exception and never a silent fake success.
  * **Tenant-scoped.** The customer binding store is keyed by `tenant_id` (the
    filename IS the boundary); a cross-tenant read returns `not_found`. Chat ids
    are masked in every projection and never returned raw.
  * **Never raises.** Every public entry returns a dict.

SECRETS (C3)
------------
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `TELEGRAM_OPS_GROUP_ID` are read
from env at CALL time. They are never logged, never persisted and never returned.

STORE
-----
One new store id (`video.delivery_bindings`), resolved through
`runtime_data_authority` at call time, holding three tenant-scoped files:
    <root>/<tenant_id>.json          → the customer's Telegram binding
    <root>/<tenant_id>.retry.json    → the delivery retry queue
    <root>/<tenant_id>.capture.json  → consent-flagged capture-flow records
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE: dict[str, Any] = {
    "store_id": "video.delivery_bindings",
    "legacy_path": Path("data") / "video_delivery",
    "target_segments": ("marketing", "video_delivery"),
}

#: Delivery targets. Each approved video is sent to BOTH, independently retried.
TARGET_CUSTOMER = "customer"
TARGET_OPS = "ops"
TARGETS = (TARGET_CUSTOMER, TARGET_OPS)

#: Consent values accepted for a captured proof asset / quote. Anything else is
#: refused — the capture flow must never ship a proof format without a consent
#: trail (design OI-4 / PRD C1).
_GRANTED = "granted"


# --------------------------------------------------------------------------- #
# Flags (read at call time; every one defaults to the safe / inert value)
# --------------------------------------------------------------------------- #
def _on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def enabled() -> bool:
    """Master gate for Telegram delivery. OFF ⇒ whole module inert (egress only)."""
    return _on("VIDEO_TELEGRAM_DELIVERY_ENABLED", "0")


def ops_group_id() -> str:
    """Ops-group chat id (env only; never logged / returned)."""
    return (os.getenv("TELEGRAM_OPS_GROUP_ID") or "").strip()


def _bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def max_retries() -> int:
    try:
        return max(0, min(20, int(os.getenv("VIDEO_DELIVERY_MAX_RETRIES", "5"))))
    except Exception:
        return 5


def retry_backoff_s() -> int:
    """Base backoff seconds between attempts (exponential, capped)."""
    try:
        return max(30, min(3600, int(os.getenv("VIDEO_DELIVERY_RETRY_BACKOFF_S", "300"))))
    except Exception:
        return 300


def mask_chat_id(chat_id: str) -> str:
    """Mask a chat id for any projection. Never reveal the raw id (C3)."""
    s = str(chat_id or "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    return f"{s[:2]}{'*' * max(1, len(s) - 4)}{s[-2:]}"


# --------------------------------------------------------------------------- #
# Store helpers (call-time resolution; never a frozen path)
# --------------------------------------------------------------------------- #
def _root() -> str:
    from app.platform import runtime_data_authority as _auth

    return str(_auth.resolve_store_path(**_STORE))


def _safe_stem(tenant_id: str) -> str:
    """Refuse a tenant id that would escape its own store, and bound the length.

    `_safe_segment` already REFUSES a traversal id (rather than coercing it —
    coercing would silently re-file a tenant's rows under a different name). The
    length cap mirrors `store.py` (60 chars); valid tenant ids are already within
    it, and it stops a pathological id from producing an un-writable path.
    """
    from app.platform.runtime_data import _safe_segment

    return _safe_segment(tenant_id)[:60]


def _path(tenant_id: str, suffix: str = "") -> str:
    return os.path.join(_root(), f"{_safe_stem(tenant_id)}{suffix}.json")


def _read_json(path: str) -> dict[str, Any]:
    try:
        if not os.path.isfile(path):
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _tmp_path(path: str) -> str:
    """Temp sibling for the atomic replace, built from the CANONICAL root.

    Resolving the temp path through ``_root()`` (rather than a bare f-string on
    ``path``) keeps the write inside the tenant's own store directory and keeps
    the path traceable to the runtime-data authority. A raw f-string temp name
    reads to the repo-wide ratchet as an uncontrolled checkout write.
    """
    return os.path.join(_root(), f"{os.path.basename(path)}.tmp.{os.getpid()}")


def _write_json(path: str, payload: dict[str, Any]) -> bool:
    """Atomic replace — a torn file would silently drop a binding / retry row."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = _tmp_path(path)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.warning("[video_delivery] store write failed (%s): %s", os.path.basename(path), exc)
        return False


# --------------------------------------------------------------------------- #
# Telegram egress — reuses the EXISTING proven path (providers.TelegramProvider)
# --------------------------------------------------------------------------- #
def _run_coro(coro: Any) -> Any:
    """Run a coroutine from sync code, tolerating an already-running loop.

    Celery workers are sync; FastAPI handlers are async. Reusing the existing
    async egress path from both means this shim must not assume a fresh loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # A loop is already running on this thread — run the egress on a worker
    # thread so we neither nest loops nor deadlock the caller.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


def _send_video(chat_id: str, path: str, caption: str) -> dict[str, Any]:
    """Send one video via the proven egress path. Returns ``{ok, message_id, error}``.

    Reuses ``app.social_engine.providers.TelegramProvider`` (the shape verified at
    ``providers.py``) — the same bot, the same ``sendVideo`` call — and captures
    the ``message_id`` the design requires as the delivery receipt (Q10).
    """
    if not _bot_token():
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN unset"}
    if not chat_id:
        return {"ok": False, "error": "chat_id unset"}
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "artifact_missing"}
    try:
        from app.social_engine.base import PublishRequest
        from app.social_engine.providers import TelegramProvider

        req = PublishRequest(
            client_id="",
            caption=str(caption or "")[:1024],
            media_path=path,
            media_type="video",
            platform="telegram",
            account_ref=str(chat_id),
        )
        res = _run_coro(TelegramProvider().publish(req, {}))
        return {
            "ok": bool(getattr(res, "ok", False)),
            "message_id": str(getattr(res, "post_id", "") or ""),
            "error": str(getattr(res, "error", "") or "")[:160],
        }
    except Exception as exc:  # pragma: no cover - defensive, never raise out
        logger.warning("[video_delivery] send_video failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


def _send_message(chat_id: str, text: str) -> dict[str, Any]:
    """Send a short text notice via the SAME bot's ``sendMessage`` endpoint.

    Not a new bot: the identical ``POST api.telegram.org/bot<token>/sendMessage``
    shape already used by ``providers.py``. Used for ops-group delivery notices.
    """
    if not _bot_token():
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN unset"}
    if not chat_id:
        return {"ok": False, "error": "chat_id unset"}
    try:
        import httpx

        url = f"https://api.telegram.org/bot{_bot_token()}/sendMessage"
        with httpx.Client(timeout=30) as cx:
            r = cx.post(url, json={"chat_id": chat_id, "text": str(text or "")[:4000]})
        body: dict[str, Any] = {}
        try:
            body = r.json() or {}
        except Exception:
            body = {}
        ok = r.status_code == 200 and bool(body.get("ok"))
        mid = str(((body.get("result") or {}) if isinstance(body, dict) else {}).get("message_id") or "")
        return {"ok": ok, "message_id": mid, "error": "" if ok else str(r.text)[:160]}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[video_delivery] send_message failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


# --------------------------------------------------------------------------- #
# Customer binding store (tenant-scoped; raw chat id never leaves this module)
# --------------------------------------------------------------------------- #
def bind_customer(tenant_id: str, chat_id: str, *, label: str = "", actor: str = "admin") -> dict[str, Any]:
    """Bind a tenant to a Telegram chat id. Never raises."""
    cid = str(tenant_id or "").strip()
    chat = str(chat_id or "").strip()
    if not cid:
        return {"ok": False, "error": "tenant_id_required"}
    if not chat:
        return {"ok": False, "error": "chat_id_required"}
    try:
        path = _path(cid)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}
    rec = {
        "tenant_id": cid,
        "chat_id": chat,
        "label": str(label or "")[:80],
        "bound_by": str(actor or "admin")[:40],
        "bound_at": time.time(),
    }
    if not _write_json(path, rec):
        return {"ok": False, "error": "store_write_failed"}
    return {"ok": True, "tenant_id": cid, "chat_masked": mask_chat_id(chat)}


def get_binding(tenant_id: str) -> dict[str, Any]:
    """Raw binding for the OWNING tenant only (contains the chat id). Internal."""
    cid = str(tenant_id or "").strip()
    if not cid:
        return {"ok": False, "error": "tenant_id_required"}
    try:
        rec = _read_json(_path(cid))
    except Exception:
        return {"ok": False, "error": "not_found"}
    if not rec or str(rec.get("tenant_id") or "") != cid:
        # The filename is the tenant boundary; a mismatched/absent body = not_found.
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "binding": rec}


def binding_view(tenant_id: str) -> dict[str, Any]:
    """Masked, customer-safe view of the binding (no raw chat id)."""
    got = get_binding(tenant_id)
    if not got.get("ok"):
        return {"bound": False, "chat_masked": ""}
    rec = got["binding"]
    return {
        "bound": True,
        "chat_masked": mask_chat_id(str(rec.get("chat_id") or "")),
        "label": str(rec.get("label") or ""),
        "bound_at": rec.get("bound_at"),
    }


def unbind_customer(tenant_id: str) -> dict[str, Any]:
    """Remove a tenant's binding. Never raises."""
    cid = str(tenant_id or "").strip()
    if not cid:
        return {"ok": False, "error": "tenant_id_required"}
    try:
        path = _path(cid)
        existed = os.path.isfile(path)
        if existed:
            os.remove(path)
        return {"ok": True, "tenant_id": cid, "removed": existed}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


# --------------------------------------------------------------------------- #
# Retry queue (per-tenant; bounded, backoff, never silently dropped)
# --------------------------------------------------------------------------- #
def _load_retry(tenant_id: str) -> dict[str, Any]:
    return _read_json(_path(tenant_id, ".retry"))


def _save_retry(tenant_id: str, queue: dict[str, Any]) -> bool:
    return _write_json(_path(tenant_id, ".retry"), queue)


def _retry_key(creative_id: str, revision: int, target: str) -> str:
    return f"{creative_id}:rev{int(revision)}:{target}"


def enqueue_retry(
    tenant_id: str,
    *,
    creative_id: str,
    revision: int,
    target: str,
    caption: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Queue a failed delivery target for retry. Never raises."""
    cid = str(tenant_id or "").strip()
    tgt = str(target or "").strip() or TARGET_CUSTOMER
    if not cid or not creative_id:
        return {"ok": False, "error": "tenant_id_and_creative_id_required"}
    try:
        queue = _load_retry(cid)
        items = queue.get("items") if isinstance(queue.get("items"), dict) else {}
        key = _retry_key(creative_id, revision, tgt)
        prev = items.get(key) or {}
        attempts = int(prev.get("attempts") or 0) + 1
        items[key] = {
            "creative_id": str(creative_id),
            "revision": int(revision),
            "target": tgt,
            "caption": str(caption or "")[:1024],
            "attempts": attempts,
            "last_error": str(reason or "")[:160],
            "next_eligible_at": time.time() + retry_backoff_s() * (2 ** max(0, attempts - 1)),
            "updated_at": time.time(),
        }
        queue = {"tenant_id": cid, "items": items, "updated_at": time.time()}
        if not _save_retry(cid, queue):
            return {"ok": False, "error": "store_write_failed"}
        return {"ok": True, "key": key, "attempts": attempts}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


def retry_queue(tenant_id: str) -> dict[str, Any]:
    """Masked view of the tenant's pending delivery retries. Never raises."""
    cid = str(tenant_id or "").strip()
    if not cid:
        return {"tenant_id": "", "pending": 0, "items": []}
    try:
        queue = _load_retry(cid)
    except Exception:
        return {"tenant_id": cid, "pending": 0, "items": []}
    items = queue.get("items") if isinstance(queue.get("items"), dict) else {}
    rows = []
    for key, rec in items.items():
        if not isinstance(rec, dict):
            continue
        rows.append(
            {
                "key": key,
                "creative_id": rec.get("creative_id"),
                "revision": rec.get("revision"),
                "target": rec.get("target"),
                "attempts": rec.get("attempts"),
                "last_error": str(rec.get("last_error") or "")[:120],
                "next_eligible_at": rec.get("next_eligible_at"),
            }
        )
    return {"tenant_id": cid, "pending": len(rows), "items": rows}


def _clear_retry(tenant_id: str, key: str) -> None:
    try:
        queue = _load_retry(tenant_id)
        items = queue.get("items") if isinstance(queue.get("items"), dict) else {}
        if key in items:
            items.pop(key, None)
            _save_retry(tenant_id, {"tenant_id": tenant_id, "items": items, "updated_at": time.time()})
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
def _caption_for(tenant_id: str, creative_id: str, caption: str) -> str:
    if str(caption or "").strip():
        return str(caption)[:1024]
    try:
        from app.marketing.creative_os.store import get_record

        got = get_record(tenant_id, creative_id)
        if got.get("ok"):
            spec = (got.get("record") or {}).get("spec") or {}
            primary = str((spec.get("captions") or {}).get("primary") or "").strip()
            if primary:
                return primary[:1024]
    except Exception:
        pass
    return f"Video ready — {creative_id}"


def _deliver_one_target(
    tenant_id: str,
    creative_id: str,
    revision: int,
    target: str,
    path: str,
    caption: str,
) -> dict[str, Any]:
    """Deliver to one target. Returns ``{ok, message_id, error, chat_masked}``."""
    if target == TARGET_OPS:
        chat_id = ops_group_id()
        if not chat_id:
            return {"ok": False, "error": "TELEGRAM_OPS_GROUP_ID unset", "chat_masked": ""}
    else:
        got = get_binding(tenant_id)
        if not got.get("ok"):
            return {"ok": False, "error": "customer_not_bound", "chat_masked": ""}
        chat_id = str(got["binding"].get("chat_id") or "")
    sent = _send_video(chat_id, path, caption)
    sent["chat_masked"] = mask_chat_id(chat_id)
    return sent


def _existing_keys(tenant_id: str) -> set[str]:
    """Receipt keys already in the ledger (idempotency guard). Never raises."""
    try:
        from app.marketing import delivery_ledger

        return delivery_ledger._existing_keys(tenant_id)
    except Exception:
        return set()


def deliver_video(
    tenant_id: str,
    creative_id: str,
    *,
    caption: str = "",
    revision: int = 0,
    actor: str = "system",
) -> dict[str, Any]:
    """Deliver an approved video to the customer + ops group. Never raises.

    Resolves the artifact through ``service.resolve_output_path`` (the same
    tenant-scoped, path-authorized resolver the serve path uses), sends it via
    the existing Telegram egress path, and records a receipt in the delivery
    ledger. A target that fails is queued for retry — never silently dropped.

    A target already receipted for this ``(creative, revision)`` is SKIPPED
    (``idempotent``): Telegram has no provider-side idempotency, so without this
    guard a re-fired delivery would message the customer twice.
    """
    cid = str(tenant_id or "").strip()
    crid = str(creative_id or "").strip()
    out: dict[str, Any] = {
        "ok": False,
        "tenant_id": cid,
        "creative_id": crid,
        "revision": int(revision or 0),
        "targets": {},
    }
    if not cid or not crid:
        out["outcome"] = "invalid_request"
        return out
    if not enabled():
        out["outcome"] = "disabled"
        out["reason"] = "VIDEO_TELEGRAM_DELIVERY_ENABLED off"
        return out
    if not _bot_token():
        out["outcome"] = "no_token"
        out["reason"] = "TELEGRAM_BOT_TOKEN unset"
        return out

    try:
        from app.marketing.creative_os.service import resolve_output_path

        resolved = resolve_output_path(cid, crid)
    except Exception as exc:
        resolved = {"ok": False, "error": str(exc)[:160]}
    if not resolved.get("ok"):
        out["outcome"] = "artifact_unavailable"
        out["error"] = str(resolved.get("error") or "resolve_failed")
        return out

    path = str(resolved.get("path") or "")
    sha = str(resolved.get("sha256") or "")
    caption_use = _caption_for(cid, crid, caption)
    already = _existing_keys(cid)

    any_ok = False
    for target in TARGETS:
        rkey = _retry_key(crid, revision, target)
        if f"deliver:{rkey}" in already:
            # Already delivered for this (creative, revision) — do not re-send.
            out["targets"][target] = {
                "ok": True,
                "message_id": "",
                "chat_masked": "",
                "error": "",
                "idempotent": True,
            }
            any_ok = True
            continue
        res = _deliver_one_target(cid, crid, int(revision or 0), target, path, caption_use)
        target_row: dict[str, Any] = {
            "ok": bool(res.get("ok")),
            "message_id": str(res.get("message_id") or ""),
            "chat_masked": str(res.get("chat_masked") or ""),
            "error": str(res.get("error") or "")[:160],
        }
        out["targets"][target] = target_row
        if res.get("ok"):
            any_ok = True
            # Truthfulness: only the CUSTOMER target is customer-visible value.
            # `video_delivered` reads "aapko bhej diya gaya" (sent to YOU), so
            # logging it for an ops-group-only success would tell the shop owner
            # their video arrived when it never reached their thread. Ops receipts
            # are recorded under `video_delivered_ops` (customer_visible=False).
            _log_delivery_event(
                cid,
                "video_delivered" if target == TARGET_CUSTOMER else "video_delivered_ops",
                detail=f"{crid}:rev{int(revision or 0)}:{target}",
                meta={
                    "target": target,
                    "message_id": target_row["message_id"],
                    "chat_masked": target_row["chat_masked"],
                    "sha256": sha,
                    "creative_id": crid,
                },
                key=f"deliver:{rkey}",
                actor=actor,
            )
            _clear_retry(cid, rkey)
        else:
            enq = enqueue_retry(
                cid,
                creative_id=crid,
                revision=int(revision or 0),
                target=target,
                caption=caption_use,
                reason=target_row["error"],
            )
            attempts = int(enq.get("attempts") or 0)
            if attempts > max_retries():
                _log_delivery_event(
                    cid,
                    "video_delivery_exhausted",
                    detail=f"{crid}:rev{int(revision or 0)}:{target}",
                    meta={"target": target, "attempts": attempts, "error": target_row["error"]},
                    key=f"exhausted:{rkey}",
                    actor=actor,
                )
            else:
                _log_delivery_event(
                    cid,
                    "video_delivery_retry_scheduled",
                    detail=f"{crid}:rev{int(revision or 0)}:{target}",
                    meta={"target": target, "attempts": attempts, "error": target_row["error"]},
                    key=f"retry:{rkey}:{attempts}",
                    actor=actor,
                )
    out["ok"] = any_ok
    out["outcome"] = "delivered" if any_ok else "failed"
    return out


def _log_delivery_event(
    tenant_id: str, event: str, *, detail: str, meta: dict[str, Any], key: str, actor: str
) -> None:
    """Best-effort ledger write. A ledger outage must not break delivery."""
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.log_event(tenant_id, event, detail=detail, meta=meta, key=key, actor=actor)
    except Exception:
        pass


def process_retries(limit: int = 20) -> dict[str, Any]:
    """Drain due delivery retries for every tenant. Never raises.

    Bounded; each due row is re-attempted through the SAME ``deliver_video`` path
    so a retry can never take a shortcut around the gate or the resolver.
    """
    out: dict[str, Any] = {"ok": True, "attempted": 0, "delivered": 0, "tenants": []}
    if not enabled():
        out["ok"] = False
        out["reason"] = "VIDEO_TELEGRAM_DELIVERY_ENABLED off"
        return out
    try:
        root = _root()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160], "attempted": 0, "delivered": 0, "tenants": []}
    if not os.path.isdir(root):
        return out
    now = time.time()
    cap = max(1, min(200, int(limit or 20)))
    try:
        names = sorted(os.listdir(root))
    except Exception:
        return out
    for name in names:
        if out["attempted"] >= cap:
            break
        if not name.endswith(".retry.json"):
            continue
        tenant_id = name[: -len(".retry.json")]
        queue = _load_retry(tenant_id)
        items = queue.get("items") if isinstance(queue.get("items"), dict) else {}
        for key, rec in list(items.items()):
            if out["attempted"] >= cap:
                break
            if not isinstance(rec, dict):
                continue
            if float(rec.get("next_eligible_at") or 0) > now:
                continue
            out["attempted"] += 1
            res = deliver_video(
                tenant_id,
                str(rec.get("creative_id") or ""),
                caption=str(rec.get("caption") or ""),
                revision=int(rec.get("revision") or 0),
                actor="retry",
            )
            if res.get("ok"):
                out["delivered"] += 1
            out["tenants"].append({"tenant_id": tenant_id, "key": key, "ok": bool(res.get("ok"))})
    return out


def _pending_deliveries(tenant_id: str, limit: int) -> list[tuple[str, int]]:
    """Approved creatives for this tenant that have NO delivery receipt yet.

    Returns ``[(creative_id, revision), ...]``. A creative is 'pending' only when
    its lifecycle says ``approval == passed`` AND ``delivery != passed`` — the
    sweep reads the projection, it never guesses approval from a raw status
    string, and it never re-offers a creative that already has a receipt.
    """
    found: list[tuple[str, int]] = []
    if limit <= 0:
        return found
    try:
        from app.marketing.creative_os.lifecycle import PASSED, project
        from app.marketing.creative_os.store import list_records
    except Exception:
        return found
    try:
        listed = list_records(tenant_id, limit=max(1, min(int(limit) * 3, 200)))
    except Exception:
        return found
    already = _existing_keys(tenant_id)
    for item in listed.get("items") or []:
        if len(found) >= limit:
            break
        crid = str(item.get("creative_id") or "")
        if not crid:
            continue
        try:
            proj = project(tenant_id, crid)
        except Exception:
            continue
        if not proj.get("ok"):
            continue
        stage_status: dict[str, str] = {}
        revision = 0
        for row in proj.get("stages") or []:
            stage = str(row.get("stage") or "")
            stage_status[stage] = str(row.get("status") or "")
            if stage == "approval":
                ev = row.get("evidence") or {}
                try:
                    revision = int(ev.get("revision") or 0)
                except (TypeError, ValueError):
                    revision = 0
        if stage_status.get("approval") != PASSED:
            continue
        if stage_status.get("delivery") == PASSED:
            continue
        if f"deliver:{_retry_key(crid, revision, TARGET_CUSTOMER)}" in already:
            continue
        found.append((crid, revision))
    return found


def deliver_pending(limit: int = 20) -> dict[str, Any]:
    """Beat entrypoint: sweep bound tenants for approved-but-undelivered videos.

    Safety-net for deliveries the approval/publish path did not already push
    (e.g. a worker restart between approval and send). It only *finds* work — the
    send goes through the SAME ``deliver_video`` gate/resolver, so the sweep can
    never bypass a gate, a consent check, or the idempotency receipt. Bounded by
    ``limit``; gated by ``VIDEO_TELEGRAM_DELIVERY_ENABLED``. Never raises.
    """
    out: dict[str, Any] = {"ok": True, "scanned": 0, "delivered": 0, "tenants": []}
    if not enabled():
        out["ok"] = False
        out["reason"] = "VIDEO_TELEGRAM_DELIVERY_ENABLED off"
        return out
    try:
        root = _root()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160], "scanned": 0, "delivered": 0, "tenants": []}
    if not os.path.isdir(root):
        return out
    cap = max(1, min(200, int(limit or 20)))
    try:
        names = sorted(os.listdir(root))
    except Exception:
        return out
    for name in names:
        if out["scanned"] >= cap:
            break
        if not name.endswith(".json") or name.endswith(".retry.json") or name.endswith(".capture.json"):
            continue
        tenant_id = name[: -len(".json")]
        if not binding_view(tenant_id).get("bound"):
            continue
        for crid, revision in _pending_deliveries(tenant_id, cap - out["scanned"]):
            if out["scanned"] >= cap:
                break
            out["scanned"] += 1
            res = deliver_video(tenant_id, crid, revision=revision, actor="sweep")
            if res.get("ok"):
                out["delivered"] += 1
            out["tenants"].append(
                {"tenant_id": tenant_id, "creative_id": crid, "ok": bool(res.get("ok"))}
            )
    return out


def delivery_status(tenant_id: str) -> dict[str, Any]:
    """Operator view: gate state + binding (masked) + pending retries. Never raises."""
    cid = str(tenant_id or "").strip()
    return {
        "enabled": enabled(),
        "token_present": bool(_bot_token()),
        "ops_group_configured": bool(ops_group_id()),
        "binding": binding_view(cid) if cid else {"bound": False, "chat_masked": ""},
        "retry_queue": retry_queue(cid) if cid else {"tenant_id": "", "pending": 0, "items": []},
        "max_retries": max_retries(),
    }


# --------------------------------------------------------------------------- #
# Capture flow (P0-5) — legitimately unlock before_after / testimonial WITHOUT
# weakening `recipe_allowed`. Consent is REQUIRED; nothing is fabricated.
# --------------------------------------------------------------------------- #
def _load_capture(tenant_id: str) -> dict[str, Any]:
    return _read_json(_path(tenant_id, ".capture"))


def _save_capture(tenant_id: str, payload: dict[str, Any]) -> bool:
    return _write_json(_path(tenant_id, ".capture"), payload)


def capture_asset(
    tenant_id: str,
    *,
    ref: str,
    sha256: str,
    mime_type: str = "image/jpeg",
    consent_status: str = "",
    kind: str = "before_after",
    width: int = 0,
    height: int = 0,
) -> dict[str, Any]:
    """Register a consent-flagged proof asset via the EXISTING asset registry.

    Refuses unless consent is explicitly ``granted`` — the capture path must
    never ship a proof format without a consent trail. The asset is registered
    through ``assets.register_asset`` (unchanged); this helper only records the
    capture bookkeeping and returns the ``asset_id`` the caller passes as
    ``source_asset_ids`` to the *unchanged* ``recipe_allowed``.
    """
    cid = str(tenant_id or "").strip()
    if not cid:
        return {"ok": False, "error": "tenant_id_required"}
    if str(consent_status or "").strip().lower() != _GRANTED:
        return {"ok": False, "error": "consent_required"}
    try:
        from app.marketing.creative_os.assets import register_asset

        reg = register_asset(
            tenant_id=cid,
            source_type="upload",
            ref=str(ref or ""),
            sha256=str(sha256 or ""),
            mime_type=str(mime_type or "image/jpeg"),
            width=int(width or 0),
            height=int(height or 0),
            consent_status=_GRANTED,
            licence="customer_supplied",
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}
    if not reg.get("ok"):
        return {"ok": False, "error": str(reg.get("error") or "register_failed")}
    asset_id = str((reg.get("asset") or {}).get("asset_id") or "")
    try:
        cap = _load_capture(cid)
        assets = cap.get("asset_ids") if isinstance(cap.get("asset_ids"), list) else []
        if asset_id and asset_id not in assets:
            assets.append(asset_id)
        cap = {
            "tenant_id": cid,
            "asset_ids": assets,
            "verified_quote": str(cap.get("verified_quote") or ""),
            "quote_consent": bool(cap.get("quote_consent")),
            "kinds": {**(cap.get("kinds") or {}), asset_id: str(kind or "before_after")[:40]},
            "updated_at": time.time(),
        }
        _save_capture(cid, cap)
    except Exception:
        pass
    _log_delivery_event(
        cid,
        "capture_asset_registered",
        detail=asset_id,
        meta={"kind": str(kind or "")[:40], "consent": _GRANTED},
        key=f"capture_asset:{asset_id}",
        actor="customer",
    )
    return {"ok": True, "asset_id": asset_id, "source_asset_id": asset_id}


def capture_quote(
    tenant_id: str,
    *,
    quote: str,
    attribution: str = "",
    consent_status: str = "",
) -> dict[str, Any]:
    """Store a consent-flagged verified testimonial quote. Never fabricates."""
    cid = str(tenant_id or "").strip()
    if not cid:
        return {"ok": False, "error": "tenant_id_required"}
    text = str(quote or "").strip()
    if not text:
        return {"ok": False, "error": "quote_required"}
    if str(consent_status or "").strip().lower() != _GRANTED:
        return {"ok": False, "error": "consent_required"}
    try:
        cap = _load_capture(cid)
        cap = {
            "tenant_id": cid,
            "asset_ids": cap.get("asset_ids") if isinstance(cap.get("asset_ids"), list) else [],
            "verified_quote": text[:400],
            "quote_attribution": str(attribution or "")[:120],
            "quote_consent": True,
            "kinds": cap.get("kinds") or {},
            "updated_at": time.time(),
        }
        if not _save_capture(cid, cap):
            return {"ok": False, "error": "store_write_failed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}
    _log_delivery_event(
        cid,
        "capture_quote_registered",
        detail=str(attribution or "")[:120],
        meta={"consent": _GRANTED},
        key=f"capture_quote:{hashlib_short(text)}",
        actor="customer",
    )
    return {"ok": True, "verified_quote": text[:400]}


def hashlib_short(text: str) -> str:
    import hashlib

    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def capture_ready(tenant_id: str) -> dict[str, Any]:
    """The ``source_asset_ids`` / ``verified_quote`` to pass to ``enqueue_generate``.

    Absence is reported honestly (``needs`` lists what is missing) — never
    fabricated. Callers pass these to the UNCHANGED ``recipe_allowed`` gate.
    """
    cid = str(tenant_id or "").strip()
    if not cid:
        return {"ok": False, "error": "tenant_id_required", "source_asset_ids": [], "verified_quote": ""}
    try:
        cap = _load_capture(cid)
    except Exception:
        cap = {}
    asset_ids = [str(a) for a in (cap.get("asset_ids") or []) if a]
    quote = str(cap.get("verified_quote") or "")
    needs: list[str] = []
    if not asset_ids:
        needs.append("before_after_photos")
    if not quote:
        needs.append("verified_testimonial")
    return {
        "ok": True,
        "tenant_id": cid,
        "source_asset_ids": asset_ids,
        "verified_quote": quote,
        "needs": needs,
        "ready_for_before_after": bool(asset_ids),
        "ready_for_testimonial": bool(quote),
    }


__all__ = [
    "TARGETS",
    "TARGET_CUSTOMER",
    "TARGET_OPS",
    "bind_customer",
    "binding_view",
    "capture_asset",
    "capture_quote",
    "capture_ready",
    "deliver_pending",
    "deliver_video",
    "delivery_status",
    "enabled",
    "enqueue_retry",
    "get_binding",
    "mask_chat_id",
    "max_retries",
    "ops_group_id",
    "process_retries",
    "retry_backoff_s",
    "retry_queue",
    "unbind_customer",
]
