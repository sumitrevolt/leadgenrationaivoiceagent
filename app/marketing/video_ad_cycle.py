"""video_ad_cycle.py — har N din (default 5) per active marketing client ko 1 AI
video ad: generate -> client approval -> approve hone par multi-channel social
publish. Change-request -> naya (revised) video -> fresh approval (revision loop).

Lifecycle (data/video_ads.jsonl, append-on-update latest-line-wins):
  pending  --client approve-->  approved  --scheduler publish-->  published
           --client "change chahiye" (note)--> changes_requested --regen--> pending(rev+1)
           (max revisions ke baad changes_requested = held, agency ko ping)

Design rules (CLAUDE.md):
  * build_reel HEAVY CPU -> sirf scheduler/worker se (run_cycle); web request me NAHI.
  * approve-hook (web) sirf FAST file-mark karta (on_approved); actual publish
    scheduler `publish_due()` karta -- web process heavy job nahi chalata.
  * GATED `VIDEO_AD_CYCLE=1` (scheduler tick). Manual/admin generate isse alag.
  * Sab additive, free-stack, NEVER raises (error dicts).

Channels: Telegram native (free, sendVideo) + Postiz (FB/IG/YT/LinkedIn, gated
POSTIZ_API_KEY) + hamesha 1-click WA share fallback (content_approval se).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FILE = os.path.join("data", "video_ads.jsonl")
_STATE = os.path.join("data", ".video_ad_cycle.json")


# ------------------------------- config ----------------------------------- #
def enabled() -> bool:
    """Scheduler auto-cycle gate. Manual generate_for_client isse independent.

    Honours legacy ``VIDEO_AD_CYCLE`` OR the Video Production Cell alias
    ``VIDEO_DAILY_SCHEDULER_ENABLED`` (same contract as
    ``video_production.flags.daily_scheduler_enabled``). Prod had the cell
    flag ON while ``VIDEO_AD_CYCLE=0``, which left ``run_cycle`` inert and
    stopped own-brand video generation/publish.
    """
    return os.getenv("VIDEO_AD_CYCLE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    ) or os.getenv("VIDEO_DAILY_SCHEDULER_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _interval_days() -> int:
    try:
        return max(1, int(os.getenv("VIDEO_AD_INTERVAL_DAYS", "5")))
    except Exception:
        return 5


def _max_revisions() -> int:
    try:
        return max(1, int(os.getenv("VIDEO_AD_MAX_REVISIONS", "3")))
    except Exception:
        return 3


def _max_per_run() -> int:
    try:
        return max(1, int(os.getenv("VIDEO_AD_MAX_PER_RUN", "10")))
    except Exception:
        return 10


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ------------------------------- store ------------------------------------ #
# Stale reserved/inflight older than this become publish_outcome_unknown.
_DEFAULT_STALE_PUBLISH_SECONDS = 900


def _stale_publish_seconds() -> int:
    try:
        return max(
            0, int(os.getenv("VIDEO_AD_PUBLISH_STALE_SECONDS", str(_DEFAULT_STALE_PUBLISH_SECONDS)))
        )
    except Exception:
        return _DEFAULT_STALE_PUBLISH_SECONDS


def _store_lock():
    """Cross-process lock for publish reservation CAS. Fail-closed on import/timeout."""
    from filelock import FileLock

    return FileLock(f"{_FILE}.lock", timeout=15)


def _append(rec: dict[str, Any]) -> bool:
    """Append one JSONL line. Returns whether the write landed."""
    try:
        os.makedirs(os.path.dirname(_FILE) or ".", exist_ok=True)
        with open(_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[video_ad] append failed: {e}")
        return False


def _latest() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        if not os.path.isfile(_FILE):
            return out
        with open(_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                rid = str(rec.get("id") or "")
                if rid:
                    cur = out.get(rid) or {}
                    cur.update(rec)
                    out[rid] = cur
    except Exception as e:
        logger.debug(f"[video_ad] read skip: {e}")
    return out


def _update(rec_id: str, **fields: Any) -> bool:
    fields["id"] = rec_id
    return _append(fields)


def _parse_attempt_epoch(raw: str) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    cleaned = text.replace("Z", "")
    try:
        return time.mktime(time.strptime(cleaned[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return None


def _attempt_is_stale(rec: dict[str, Any]) -> bool:
    """True when reserved/inflight should be recovered as unknown (hard-kill / hang)."""
    epoch = _parse_attempt_epoch(str(rec.get("publish_attempt_at") or ""))
    if epoch is None:
        # Missing timestamp on an in-flight row is treated as stale: safer than
        # forever-held after a crash that never wrote the clock field.
        return True
    return (time.time() - epoch) >= float(_stale_publish_seconds())


def _cas_publish_state(
    rid: str,
    idem_key: str,
    *,
    from_states: set[str] | frozenset[str] | tuple[str, ...],
    to_state: str,
    identity: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Under the store lock: CAS attempt state for the owning publish key."""
    allowed = set(from_states)
    try:
        lock = _store_lock()
    except Exception as exc:
        return {
            "ok": False,
            "error": "publish_reservation_unavailable",
            "detail": str(exc)[:120],
        }
    try:
        with lock:
            current = dict(_latest().get(rid) or {})
            if str(current.get("publish_idempotency_key") or "") != idem_key:
                return {
                    "ok": False,
                    "error": "publish_cas_key_mismatch",
                    "durable_state": str(current.get("publish_attempt_state") or ""),
                }
            prior = str(current.get("publish_attempt_state") or "")
            if prior not in allowed:
                return {
                    "ok": False,
                    "error": "publish_cas_state_mismatch",
                    "durable_state": prior,
                }
            fields: dict[str, Any] = {
                "publish_idempotency_key": idem_key,
                "publish_attempt_state": to_state,
                "publish_attempt_at": _now(),
            }
            if identity is not None:
                fields["publish_attempt_identity"] = identity
            if result is not None:
                fields["publish_result"] = result
            if extra:
                fields.update(extra)
            if _update(rid, **fields) is False:
                return {"ok": False, "error": "publish_cas_write_failed"}
            after = dict(_latest().get(rid) or {})
            if str(after.get("publish_idempotency_key") or "") != idem_key:
                return {"ok": False, "error": "publish_cas_write_failed"}
            if str(after.get("publish_attempt_state") or "") != to_state:
                return {"ok": False, "error": "publish_cas_write_failed"}
            return {"ok": True, "state": to_state}
    except Exception as exc:
        logger.warning("[video_ad] publish CAS failed (%s): %s", rid[:40], exc)
        return {
            "ok": False,
            "error": "publish_reservation_unavailable",
            "detail": str(exc)[:120],
        }


def _acquire_publish_reservation(
    rid: str,
    idem_key: str,
    identity: dict[str, Any],
) -> dict[str, Any]:
    """Atomically reserve one publish attempt (cross-process).

    Under the store lock: re-read durable state, recover stale inflight/reserved
    to ``publish_outcome_unknown``, short-circuit known terminals, append
    ``publish_reserved``, then CAS-confirm. Fail-closed when the lock or write
    does not stick — never proceed to the provider.
    """
    from app.marketing.video_production import publish_snapshot as ps

    try:
        lock = _store_lock()
    except Exception as exc:
        return {
            "ok": False,
            "error": "publish_reservation_unavailable",
            "detail": str(exc)[:120],
        }

    try:
        with lock:
            current = dict(_latest().get(rid) or {})
            prior_key = str(current.get("publish_idempotency_key") or "")
            prior_state = str(current.get("publish_attempt_state") or "")
            prior_result = current.get("publish_result")

            if (
                prior_key == idem_key
                and prior_state == ps.PUBLISHED
                and isinstance(prior_result, dict)
            ):
                return {
                    "ok": True,
                    "short_circuit": "published",
                    "channels": prior_result,
                }

            if prior_key == idem_key and prior_state == ps.PUBLISH_OUTCOME_UNKNOWN:
                return {"ok": False, "error": "publish_outcome_unknown"}

            if prior_key == idem_key and prior_state in (
                ps.PUBLISH_RESERVED,
                ps.PROVIDER_INFLIGHT,
            ):
                if _attempt_is_stale(current):
                    # Hard-kill / hung attempt → durable unknown (never retryable).
                    # Do NOT flip legacy status here — attempt-state alone blocks
                    # retries; outer publish_due/schedule_approved make status visible.
                    wrote = _update(
                        rid,
                        publish_idempotency_key=idem_key,
                        publish_attempt_state=ps.PUBLISH_OUTCOME_UNKNOWN,
                        publish_attempt_at=_now(),
                        publish_result={
                            "idempotency": {
                                "ok": False,
                                "error": "publish_outcome_unknown",
                                "remedy": (
                                    "stale provider_inflight/reserved recovered; "
                                    "provider reconciliation or operator decision required"
                                ),
                            }
                        },
                    )
                    if wrote is False:
                        return {"ok": False, "error": "publish_reservation_failed"}
                    return {"ok": False, "error": "publish_outcome_unknown"}
                return {"ok": False, "error": "publish_reservation_held"}

            wrote = _update(
                rid,
                publish_idempotency_key=idem_key,
                publish_attempt_state=ps.PUBLISH_RESERVED,
                publish_attempt_identity=identity,
                publish_attempt_at=_now(),
            )
            if wrote is False:
                return {"ok": False, "error": "publish_reservation_failed"}

            after = dict(_latest().get(rid) or {})
            if str(after.get("publish_idempotency_key") or "") != idem_key:
                return {"ok": False, "error": "publish_reservation_failed"}
            if str(after.get("publish_attempt_state") or "") != ps.PUBLISH_RESERVED:
                return {"ok": False, "error": "publish_reservation_failed"}
            return {"ok": True, "reserved": True}
    except Exception as exc:
        logger.warning("[video_ad] publish reservation lock/CAS failed (%s): %s", rid[:40], exc)
        return {
            "ok": False,
            "error": "publish_reservation_unavailable",
            "detail": str(exc)[:120],
        }


def _load_state() -> dict[str, str]:
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(state: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE) or ".", exist_ok=True)
        tmp = _STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, _STATE)
    except Exception as e:
        logger.warning(f"[video_ad] state save failed: {e}")


# ------------------------------- helpers ----------------------------------- #
def _eligible_clients() -> list[dict[str, Any]]:
    """Active marketing/combo clients (voice-only skip)."""
    try:
        from app.marketing import clients_store

        rows = clients_store.list_clients(status="active") or []
        out = []
        for c in rows:
            try:
                lane = clients_store.product_lane(c)
            except Exception:
                lane = "marketing"
            if lane in ("marketing", "combo"):
                out.append(c)
        return out
    except Exception as e:
        logger.warning(f"[video_ad] eligible failed: {e}")
        return []


def _channels_for(client: dict[str, Any]) -> list[str]:
    ch: list[str] = []
    # telegram REMOVED 2026-06-28 (ban-risk) — never publish to telegram (publish code below now dead)
    try:
        from app.marketing import postiz_publish

        if postiz_publish.enabled():
            ch.append("postiz")
    except Exception:
        pass
    ch.append("share")  # hamesha 1-click WA/manual share (FB/IG human post)
    return ch


async def _caption_slides(client: dict[str, Any], note: str = "") -> tuple[str, list[str]]:
    business = str(client.get("business_name") or "Aapka Business")
    niche = str(client.get("niche") or "general")
    offer = str(client.get("offer") or "").strip()
    hint = (offer + (" | " + note if note else "")).strip(" |")
    caption = ""
    try:
        from app.marketing import post_generator

        post = await post_generator.generate_post(business, niche=niche, offer=hint)
        caption = str(post.get("caption") or post.get("post_text") or "").strip()
    except Exception:
        caption = ""
    if not caption:
        caption = (
            f"{business} — {offer or f'aapke area ka bharosemand {niche}'}. Inquiry: WhatsApp/Call."
        )
    slides = [
        business,
        offer or f"Aapke area ka bharosemand {niche} expert",
        "Call ya WhatsApp karo — turant response milega",
    ]
    return caption, slides


# ------------------------------- generate ---------------------------------- #
async def generate_for_client(
    client_id: str, note: str = "", revision: int = 0, supersedes: str = ""
) -> dict[str, Any]:
    """1 video ad banao + client approval me daalo. HEAVY (build_reel) — scheduler/
    worker se call karo. Returns {ok, id, approval, wa_link} ya {ok:False,error}."""
    try:
        from app.marketing import clients_store, content_approval, video_pipeline

        client = clients_store.get_client(client_id) or {}
        if not client:
            return {"ok": False, "error": "client nahi mila"}
        caption, slides = await _caption_slides(client, note)
        built = await video_pipeline.render_creative_video(
            recipe="generic",
            business_name=str(client.get("business_name") or "Aapka Business"),
            niche=str(client.get("niche") or "general"),
            slides=slides,
            offer=str(client.get("offer") or ""),
            client_id=client_id,
        )
        if built.get("error"):
            return {"ok": False, "error": f"video gen fail: {built['error']}", "detail": built}
        video_path = built.get("path") or ""
        if not str(video_path).strip():
            return {"ok": False, "error": "video gen fail: empty path"}
        channels = _channels_for(client)
        content = {
            "type": "video_ad",
            "title": "Naya video ad",
            "caption": caption,
            "video_path": video_path,
            "channels": channels,
            "revision": revision,
        }
        sub = content_approval.submit(client_id, content)
        if not sub.get("ok"):
            return {"ok": False, "error": sub.get("error") or "approval submit fail"}
        appr = sub.get("approval") or {}
        rid = uuid.uuid4().hex[:12]
        _append(
            {
                "id": rid,
                "client_id": client_id,
                "approval_id": appr.get("id"),
                "token": appr.get("token"),
                "status": "pending",
                "workflow_state": "CLIENT_REVIEW_PENDING",
                "revision": revision,
                "note": note,
                "video_path": video_path,
                "caption": caption,
                "channels": channels,
                "supersedes": supersedes,
                "final_approved": False,
                "created_at": _now(),
            }
        )
        if supersedes:
            _update(supersedes, status="superseded", superseded_by=rid)
        st = _load_state()
        st[client_id] = time.strftime("%Y-%m-%d")
        _save_state(st)
        try:
            from app.platform import team

            team.log_event(
                "isha",
                "video_ad_generated",
                f"{client.get('business_name')} ka video ad rev{revision} approval ko bheja",
                meta={"video_ad_id": rid, "approval_id": appr.get("id")},
            )
        except Exception:
            pass
        return {
            "ok": True,
            "id": rid,
            "approval": appr,
            "approve_url": sub.get("approve_url"),
            "reject_url": sub.get("reject_url"),
            "wa_link": sub.get("wa_link"),
            "video_path": video_path,
        }
    except Exception as e:
        logger.warning(f"[video_ad] generate failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


# ------------------------------- approve / change hooks --------------------- #

# Canonical actor identities. An approval always has SOMEONE behind it; storing
# an empty actor would make the audit trail lie, so callers that cannot resolve
# a richer identity use one of these explicit contracts.
APPROVAL_ACTOR_TOKEN = "customer:approval_token"  # signed review-link holder
APPROVAL_ACTOR_ADMIN = "admin"  # admin acting on behalf of the customer


def record_approval(rec_id: str, revision: int, *, actor: str) -> dict[str, Any]:
    """THE approval writer. Every approval path must go through this function.

    Loads the authoritative record by id, takes ``video_path`` from that record
    (never from a caller argument), validates it against the canonical media
    roots, streams a SHA-256 of the exact approval-time bytes, and persists the
    approval atomically through ``_update``.

    Fails WITHOUT marking approval when the content cannot be verified — a
    record we cannot hash must not become publishable.
    """
    from app.marketing.video_production import states
    from app.marketing.video_production.publish_gate import hash_video_file

    rid = str(rec_id or "").strip()
    who = str(actor or "").strip()
    if not rid:
        return {"ok": False, "error": "rec_id required"}
    if not who:
        return {"ok": False, "error": "approver_identity_required"}

    rec = _latest().get(rid)
    if not rec:
        return {"ok": False, "error": "video_ad_not_found"}

    digest, size = hash_video_file(str(rec.get("video_path") or ""))
    if not digest:
        return {"ok": False, "error": "content_unverifiable"}

    _update(
        rid,
        status="approved",
        workflow_state=states.APPROVED,
        approved_version=int(revision),
        final_approved=True,
        approved_content_sha256=digest,
        approved_content_bytes=size,
        approved_by=who[:64],
        approved_at=_now(),
        decided_at=_now(),
    )
    return {
        "ok": True,
        "revision": int(revision),
        "content_sha256": digest,
        "content_bytes": size,
        "approved_by": who[:64],
    }


def on_approved(approval_rec: dict[str, Any]) -> bool:
    """content_approval._decide(approved) se call (FAST, sync). Hamare video_ad rec
    ko approved (pending-publish) mark karta — actual publish scheduler karta.

    Delegates to :func:`record_approval` — this function must never write
    approval fields itself, or the content hash silently stops being recorded.
    """
    try:
        aid = str(approval_rec.get("id") or "")
        if not aid:
            return False
        for rid, rec in _latest().items():
            if str(rec.get("approval_id") or "") != aid:
                continue
            # A saga-coordinated request already owns this record. Do NOT
            # silently no-op: report explicitly that the coordinator handled it,
            # with the transaction as evidence, so a caller can tell
            # "already coordinated" apart from "nothing matched".
            txn_state = str(rec.get("approval_txn_state") or "")
            if txn_state:
                logger.info(
                    "[video_ad] on_approved skipped — already coordinated (%s, txn_state=%s)",
                    str(rid)[:40],
                    txn_state,
                )
                return True
            # CONTAINMENT (Stage 3B-close). This branch used to call
            # record_approval for an UNCOORDINATED transaction, which made every
            # caller of content_approval._decide a full approval authority:
            # the unauthenticated GET /api/clientops/approve/{token} link,
            # decide_for_client (customer portal + boss_council) and
            # decide_by_id (product_one_delivery automation). Four entrypoints,
            # no principal, no snapshot, and a hash taken at approval time
            # rather than of the bytes anyone previewed.
            #
            # on_approved is the single choke point for all four, so the refusal
            # lives here rather than on any one route. Video approval may only
            # be finalized by approval_saga.approve().
            logger.warning(
                "[video_ad] on_approved REFUSED — uncoordinated approval (%s); "
                "video approval must go through approval_saga.approve",
                str(rid)[:40],
            )
            return False
        return False
    except Exception as e:
        logger.debug(f"[video_ad] on_approved skip: {e}")
        return False


def on_changes_requested(approval_rec: dict[str, Any]) -> bool:
    """content_approval._decide(rejected) se call (FAST, sync). Video-ad ko
    changes_requested mark karta — scheduler `_regen_due()` naya version banata.
    (content_approval ne reject already kar diya — yahan sirf state mark.)"""
    try:
        aid = str(approval_rec.get("id") or "")
        if not aid:
            return False
        note = str(approval_rec.get("note") or "")
        for rid, rec in _latest().items():
            if str(rec.get("approval_id") or "") == aid and rec.get("status") == "pending":
                _update(
                    rid,
                    status="changes_requested",
                    workflow_state="CHANGES_REQUESTED",
                    final_approved=False,
                    note=note,
                    changes_at=_now(),
                )
                return True
        return False
    except Exception as e:
        logger.debug(f"[video_ad] on_changes_requested skip: {e}")
        return False


async def request_changes(approval_id: str, note: str = "") -> dict[str, Any]:
    """Admin/support entry: client ne 'change chahiye' bola — reject + changes_requested
    mark. Regeneration scheduler `_regen_due()` karta. Returns {ok, status}."""
    try:
        from app.marketing import content_approval

        target = None
        for rid, rec in _latest().items():
            if str(rec.get("approval_id") or "") == str(approval_id or ""):
                target = (rid, rec)
                break
        if not target:
            return {"ok": False, "error": "video ad nahi mila"}
        rid, rec = target
        tok = str(rec.get("token") or "")
        if tok:
            content_approval.reject(tok, note)
        _update(rid, status="changes_requested", note=note, changes_at=_now())
        try:
            from app.platform import team

            team.log_event(
                "isha",
                "video_ad_changes",
                f"Client ne video ad change maanga — note: {note[:120]}",
                meta={"video_ad_id": rid},
            )
        except Exception:
            pass
        return {"ok": True, "status": "changes_requested", "id": rid}
    except Exception as e:
        logger.warning(f"[video_ad] request_changes failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


# ------------------------------- publish ------------------------------------ #
async def _tg_send_video(
    chat_id: str,
    video_path: str = "",
    caption: str = "",
    *,
    video_file: Any | None = None,
    filename: str = "video.mp4",
) -> dict[str, Any]:
    """Telegram Bot API sendVideo. Prefer ``video_file`` (verified descriptor)."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {
            "sent": False,
            "outcome": "failed",
            "reason": "TELEGRAM_BOT_TOKEN unset",
        }
    if not chat_id or (video_file is None and (not video_path or not os.path.isfile(video_path))):
        return {"sent": False, "outcome": "failed", "reason": "chat_id/video missing"}
    owns = False
    fh = video_file
    try:
        import httpx

        if fh is None:
            fh = open(video_path, "rb")
            owns = True
            name = os.path.basename(video_path)
        else:
            try:
                fh.seek(0)
            except (OSError, AttributeError):
                return {
                    "sent": False,
                    "outcome": "failed",
                    "reason": "snapshot_unseekable",
                }
            name = filename or (os.path.basename(video_path) if video_path else "video.mp4")
        api = f"https://api.telegram.org/bot{token}/sendVideo"
        async with httpx.AsyncClient(timeout=120) as cx:
            r = await cx.post(
                api,
                data={"chat_id": chat_id, "caption": (caption or "")[:1024]},
                files={"video": (name, fh, "video/mp4")},
            )
        code = int(r.status_code)
        if code >= 500:
            return {
                "sent": False,
                "outcome": "unknown",
                "reason": f"{code}: {r.text[:160]}",
            }
        ok = code == 200 and bool((r.json() or {}).get("ok"))
        if ok:
            return {"sent": True, "outcome": "published"}
        if code // 100 == 4:
            return {"sent": False, "outcome": "failed", "reason": r.text[:160]}
        return {"sent": False, "outcome": "unknown", "reason": r.text[:160]}
    except Exception as e:
        return {"sent": False, "outcome": "unknown", "reason": str(e)[:120]}
    finally:
        if owns and fh is not None:
            try:
                fh.close()
            except Exception:
                pass


def _resolve_publish_client(cid: str) -> dict[str, Any] | None:
    """Resolve the publish tenant, distinguishing "no client" from "not found".

    Returns ``{}`` when there is genuinely no client id on the record (the
    own-brand / admin publish context that ``postiz_publish._is_own_brand``
    expects), and ``None`` when a REAL id was present but resolved to nothing.
    That second case previously collapsed into ``{}`` via
    ``get_client(cid) or {}``, which downstream reads as own-brand — the
    cross-customer leak this function exists to prevent.

    A lookup that RAISES is also ``None``: an unverifiable tenant is not a
    licence to publish.
    """
    cid = str(cid or "").strip()
    if not cid:
        return {}
    try:
        from app.marketing import clients_store

        rec = clients_store.resolve_client(cid) or clients_store.get_client(cid)
    except Exception as exc:
        logger.warning(f"[video_ad] tenant lookup failed ({cid[:40]}): {exc}")
        return None
    return rec or None


async def _publish_one(rec: dict[str, Any]) -> dict[str, Any]:
    """Publish ONE approved video through Postiz/Telegram/engine.

    Stage 3C (descriptor-bound) contract:
      * gate must be finalized + snapshot-bound
      * ``open_verified_snapshot`` opens once (O_NOFOLLOW); provider streams that fd
      * mutable ``video_path`` is never opened for upload
      * local states: publish_reserved → provider_inflight → published
        (or publish_outcome_unknown / publish_refused / publish_failed)
      * Postiz has no provider idempotency — never claim exactly-once externally
    """
    from app.marketing.video_production import publish_snapshot as ps

    # Publish gate: when Video Production Cell master is ON → fail-closed on
    # gate errors. When OFF → refuse rather than open a mutable path.
    _prod_cell = False
    try:
        from app.marketing.video_production import flags as _vflags

        _prod_cell = bool(_vflags.production_enabled())
    except Exception:
        _prod_cell = False
    try:
        from app.marketing.video_production.publish_gate import assert_can_publish

        gate = assert_can_publish(rec)
        if not gate.get("ok"):
            return {"any_sent": False, "channels": {"gate": gate}, "provider_calls": 0}
    except Exception as e:
        logger.warning(f"[video_ad] publish_gate fail-closed: {e}")
        return {
            "any_sent": False,
            "channels": {"gate": {"ok": False, "error": f"gate_exception:{str(e)[:120]}"}},
            "provider_calls": 0,
        }

    cid = str(rec.get("client_id") or "")
    client = _resolve_publish_client(cid)
    if client is None:
        logger.warning(f"[video_ad] publish refused — unresolved tenant: {cid[:40]}")
        return {
            "any_sent": False,
            "channels": {"tenant": {"ok": False, "error": "unresolved_tenant"}},
            "provider_calls": 0,
        }

    snap_path = str(gate.get("snapshot_path") or "")
    snap_sha = str(gate.get("content_sha256") or "")
    snap_bytes = int(gate.get("content_bytes") or 0)
    rid = str(rec.get("id") or "")
    caption = str(rec.get("caption") or "")

    identity = ps.canonical_publish_identity(
        tenant=cid,
        video_id=rid,
        approval_txn=str(gate.get("approval_txn") or rec.get("approval_txn") or ""),
        revision=int(gate.get("version") or rec.get("revision") or 0),
        snapshot_sha256=snap_sha,
        snapshot_bytes=snap_bytes,
        channel="postiz",
    )
    idem_key = ps.publish_idempotency_key(identity)

    reserved = _acquire_publish_reservation(rid, idem_key, identity)
    if reserved.get("short_circuit") == "published":
        return {
            "any_sent": True,
            "channels": reserved.get("channels") or {},
            "idempotent_local": True,
            "provider_calls": 0,
            "publish_idempotency_key": idem_key,
            "external_exactly_once": False,
        }
    if not reserved.get("ok"):
        err = str(reserved.get("error") or "publish_reservation_failed")
        return {
            "any_sent": False,
            "channels": {
                "idempotency": {
                    "ok": False,
                    "error": err,
                    **(
                        {
                            "remedy": (
                                "provider reconciliation or explicit operator " "decision required"
                            )
                        }
                        if err == "publish_outcome_unknown"
                        else {}
                    ),
                }
            },
            "provider_calls": 0,
            "publish_idempotency_key": idem_key,
            "external_exactly_once": False,
        }

    opened = ps.open_verified_snapshot(
        snapshot_path=snap_path,
        expected_sha256=snap_sha,
        expected_bytes=snap_bytes,
    )
    if not opened.get("ok"):
        _finalize_publish_attempt(
            rid,
            idem_key,
            identity,
            {"any_sent": False, "channels": {"snapshot": opened}, "provider_calls": 0},
            state=ps.PUBLISH_REFUSED,
        )
        return {
            "any_sent": False,
            "channels": {"snapshot": opened},
            "provider_calls": 0,
            "publish_idempotency_key": idem_key,
            "external_exactly_once": False,
        }

    fh = opened["fh"]
    provider_calls = 0
    result: dict[str, Any] = {}
    any_sent = False
    provider_started = False
    filename = os.path.basename(str(opened.get("snapshot_path") or "video.mp4")) or "video.mp4"

    # P0-B: durable provider_inflight BEFORE any provider invocation.
    marked = _cas_publish_state(
        rid,
        idem_key,
        from_states={ps.PUBLISH_RESERVED},
        to_state=ps.PROVIDER_INFLIGHT,
        identity=identity,
    )
    if not marked.get("ok"):
        return {
            "any_sent": False,
            "channels": {
                "idempotency": {
                    "ok": False,
                    "error": str(marked.get("error") or "publish_inflight_failed"),
                }
            },
            "provider_calls": 0,
            "publish_idempotency_key": idem_key,
            "external_exactly_once": False,
        }

    try:
        # Prefer Postiz when enabled — stream verified descriptor (no path reopen).
        from app.marketing import postiz_publish

        if postiz_publish.enabled():
            provider_started = True
            try:
                fh.seek(0)
            except (OSError, AttributeError):
                _finalize_publish_attempt(
                    rid,
                    idem_key,
                    identity,
                    {
                        "any_sent": False,
                        "channels": {"snapshot": {"ok": False, "error": "snapshot_unseekable"}},
                        "provider_calls": 0,
                    },
                    state=ps.PUBLISH_REFUSED,
                )
                return {
                    "any_sent": False,
                    "channels": {"snapshot": {"ok": False, "error": "snapshot_unseekable"}},
                    "provider_calls": 0,
                    "publish_idempotency_key": idem_key,
                    "external_exactly_once": False,
                }
            pz = await postiz_publish.publish_video(
                client,
                caption,
                video_file=fh,
                filename=filename,
                idempotency_key=idem_key,
            )
            provider_calls += 1
            result["postiz"] = pz
            any_sent = any_sent or bool(pz.get("sent"))
            provider_outcome = str(pz.get("outcome") or "")
        else:
            # Telegram fallback — same verified descriptor.
            chat_id = str(client.get("telegram_chat_id") or "").strip()
            provider_outcome = ""
            if chat_id:
                provider_started = True
                try:
                    fh.seek(0)
                except (OSError, AttributeError):
                    _finalize_publish_attempt(
                        rid,
                        idem_key,
                        identity,
                        {
                            "any_sent": False,
                            "channels": {"snapshot": {"ok": False, "error": "snapshot_unseekable"}},
                            "provider_calls": 0,
                        },
                        state=ps.PUBLISH_REFUSED,
                    )
                    return {
                        "any_sent": False,
                        "channels": {"snapshot": {"ok": False, "error": "snapshot_unseekable"}},
                        "provider_calls": 0,
                        "publish_idempotency_key": idem_key,
                        "external_exactly_once": False,
                    }
                tg = await _tg_send_video(
                    chat_id, caption=caption, video_file=fh, filename=filename
                )
                provider_calls += 1
                result["telegram"] = tg
                any_sent = any_sent or bool(tg.get("sent"))
                provider_outcome = str(tg.get("outcome") or "")

        if any_sent:
            final_state = ps.PUBLISHED
        elif provider_started and provider_outcome != "failed":
            # Missing/unknown outcome after invocation → never blind-retry.
            final_state = ps.PUBLISH_OUTCOME_UNKNOWN
        else:
            final_state = ps.PUBLISH_FAILED

        out = {
            "any_sent": any_sent,
            "channels": result,
            "provider_calls": provider_calls,
            "publish_idempotency_key": idem_key,
            "publish_identity": identity,
            "external_exactly_once": False,
            "provider_idempotency": bool(ps.PROVIDER_ACCEPTS_IDEMPOTENCY_KEY),
            "publish_attempt_state": final_state,
        }
        finalized = _finalize_publish_attempt(
            rid,
            idem_key,
            identity,
            out,
            state=final_state,
        )
        if (
            not finalized.get("ok")
            and provider_started
            and final_state != ps.PUBLISH_OUTCOME_UNKNOWN
        ):
            # Persistence uncertainty after provider call → durable unknown.
            out["publish_attempt_state"] = ps.PUBLISH_OUTCOME_UNKNOWN
            out["any_sent"] = False
            _finalize_publish_attempt(
                rid,
                idem_key,
                identity,
                out,
                state=ps.PUBLISH_OUTCOME_UNKNOWN,
            )
        return out
    except Exception as e:
        # Crash/exception after provider invocation → unknown outcome; no blind retry.
        logger.warning("[video_ad] provider invocation raised (%s): %s", rid[:40], e)
        out = {
            "any_sent": False,
            "channels": {"provider": {"ok": False, "error": str(e)[:160]}},
            "provider_calls": provider_calls,
            "publish_idempotency_key": idem_key,
            "external_exactly_once": False,
            "publish_attempt_state": (
                ps.PUBLISH_OUTCOME_UNKNOWN if provider_started else ps.PUBLISH_FAILED
            ),
        }
        st = ps.PUBLISH_OUTCOME_UNKNOWN if provider_started else ps.PUBLISH_FAILED
        _finalize_publish_attempt(rid, idem_key, identity, out, state=st)
        return out
    finally:
        try:
            fh.close()
        except Exception:
            pass
        _ = _prod_cell  # retained for future cell-gated diagnostics


def _finalize_publish_attempt(
    rid: str,
    idem_key: str,
    identity: dict[str, Any],
    out: dict[str, Any],
    *,
    state: str | None = None,
) -> dict[str, Any]:
    """Persist attempt evidence under the publish-store lock. Returns CAS result."""
    from app.marketing.video_production import publish_snapshot as ps

    st = state or (ps.PUBLISHED if out.get("any_sent") else ps.PUBLISH_FAILED)
    # Owning attempt may still be reserved (pre-provider refuse) or inflight.
    cas = _cas_publish_state(
        rid,
        idem_key,
        from_states={ps.PUBLISH_RESERVED, ps.PROVIDER_INFLIGHT},
        to_state=st,
        identity=identity,
        result=out.get("channels") or {},
    )
    if not cas.get("ok"):
        logger.warning(
            "[video_ad] publish finalize CAS failed (%s): %s",
            rid[:40],
            cas.get("error"),
        )
        return cas

    # Only durable success writes post_published. Unknown outcomes must not
    # look like published evidence.
    if st == ps.PUBLISH_OUTCOME_UNKNOWN:
        return cas
    if st in (ps.PUBLISH_REFUSED, ps.PUBLISH_FAILED) or not out.get("any_sent"):
        if st != ps.PUBLISHED:
            try:
                from app.marketing.delivery_ledger import log_event

                log_event(
                    str(identity.get("tenant") or ""),
                    "post_failed",
                    detail=f"video:{identity.get('video_id')}:r{identity.get('revision')}",
                    meta={
                        "publish_idempotency_key": idem_key,
                        "publish_attempt_state": st,
                        "provider_calls": out.get("provider_calls"),
                    },
                    actor="video_ad_publish",
                    key=f"{idem_key[:140]}:fail",
                )
            except Exception:
                pass
            return cas
    try:
        from app.marketing.delivery_ledger import log_event

        log_event(
            str(identity.get("tenant") or ""),
            "post_published",
            detail=f"video:{identity.get('video_id')}:r{identity.get('revision')}",
            meta={
                "publish_idempotency_key": idem_key,
                "snapshot_sha256": identity.get("snapshot_sha256"),
                "approval_txn": identity.get("approval_txn"),
                "provider_calls": out.get("provider_calls"),
                "external_exactly_once": False,
            },
            actor="video_ad_publish",
            key=idem_key[:160],
        )
    except Exception as exc:
        logger.debug("[video_ad] delivery_ledger publish evidence skip: %s", exc)
    return cas


async def publish_due(limit: int = 20) -> dict[str, Any]:
    """Approved (pending-publish) video ads ko channels pe bhejo. Scheduler se."""
    published = failed = 0
    held = unknown = 0
    try:
        # Own-brand canary (flag-gated, default OFF): auto-approve own-brand
        # CLIENT_REVIEW_PENDING videos so own-brand social actually publishes.
        try:
            from app.marketing.video_production import cell as _cell

            _auto = _cell.auto_approve_own_brand_pending()
            if _auto.get("ran"):
                logger.info(f"[video_ad] own-brand auto-approve: {_auto}")
        except Exception as e:
            logger.debug(f"[video_ad] own-brand auto-approve skip: {e}")
        rows = [r for r in _latest().values() if r.get("status") == "approved"]
        rows.sort(key=lambda r: str(r.get("decided_at") or r.get("created_at") or ""))
        for rec in rows[: max(1, int(limit))]:
            rid = str(rec.get("id") or "")
            res = await _publish_one(rec)
            if res.get("any_sent"):
                _update(
                    rid,
                    status="published",
                    workflow_state="PUBLISHED",
                    published_at=_now(),
                    publish_result=res["channels"],
                )
                published += 1
                continue
            idem_err = str(
                ((res.get("channels") or {}).get("idempotency") or {}).get("error") or ""
            )
            attempt = str(res.get("publish_attempt_state") or "")
            # Do NOT normalize unknown/held into ordinary publish_failed (retry bait).
            if idem_err == "publish_reservation_held":
                held += 1
                continue
            if idem_err == "publish_outcome_unknown" or attempt == "publish_outcome_unknown":
                _update(
                    rid,
                    status="publish_outcome_unknown",
                    workflow_state="PUBLISH_OUTCOME_UNKNOWN",
                    publish_result=res.get("channels") or {},
                )
                unknown += 1
                continue
            _update(
                rid,
                status="publish_failed",
                workflow_state="PUBLISH_FAILED",
                publish_result=res["channels"],
                failed_at=_now(),
            )
            failed += 1
        return {
            "ran": True,
            "published": published,
            "failed": failed,
            "held": held,
            "unknown": unknown,
        }
    except Exception as e:
        logger.warning(f"[video_ad] publish_due failed: {e}")
        return {"ran": False, "reason": str(e)[:150]}


async def _regen_due(limit: int = 10) -> int:
    """changes_requested items ko (max-revisions tak) regenerate karo."""
    regen = 0
    try:
        rows = [r for r in _latest().values() if r.get("status") == "changes_requested"]
        for rec in rows[: max(1, int(limit))]:
            rid = str(rec.get("id") or "")
            rev = int(rec.get("revision") or 0)
            if rev + 1 > _max_revisions():
                _update(rid, status="held_max_revisions")
                continue
            r = await generate_for_client(
                str(rec.get("client_id") or ""),
                note=str(rec.get("note") or ""),
                revision=rev + 1,
                supersedes=rid,
            )
            if r.get("ok"):
                regen += 1
        return regen
    except Exception as e:
        logger.warning(f"[video_ad] regen failed: {e}")
        return 0


# ------------------------------- scheduler tick ----------------------------- #
async def run_cycle() -> dict[str, Any]:
    """Scheduler entrypoint (GATED VIDEO_AD_CYCLE / VIDEO_DAILY_SCHEDULER_ENABLED).

    3 kaam: due clients ke naye ads, change-requests regen, approved ads publish.
    Flag off = inert. NEVER raises."""
    if not enabled():
        return {"ran": False, "reason": "VIDEO_AD_CYCLE/VIDEO_DAILY_SCHEDULER off"}
    out: dict[str, Any] = {"ran": True}
    try:
        # Stuck rows: pending without a render path can never be approved/shared.
        # Mark failed so the next due cycle can regenerate (audit 2026-07-17).
        repaired = 0
        try:
            for rid, rec in list(_latest().items()):
                if (
                    str(rec.get("status") or "") == "pending"
                    and not str(rec.get("video_path") or "").strip()
                ):
                    _update(rid, status="failed", error="missing_video_path", failed_at=_now())
                    repaired += 1
        except Exception as e:
            logger.debug(f"[video_ad] stuck-pending repair skip: {e}")
        out["repaired_missing_path"] = repaired
        out["regenerated"] = await _regen_due()
        interval = _interval_days()
        st = _load_state()
        gen = 0
        cap = _max_per_run()
        # Cadence ownership: when the DAILY producer manages a client, this
        # every-N-day loop must NOT also generate for them — otherwise the client
        # gets two videos (and two approval requests) on every 5th day. regen,
        # publish and the stuck-row repair above still run for ALL clients; only
        # the *generation* step defers.
        try:
            from app.marketing import daily_video as _daily

            _daily_on = _daily.enabled()
        except Exception as e:
            logger.debug(f"[video_ad] daily_video ownership check skip: {e}")
            _daily = None
            _daily_on = False
        deferred_to_daily = 0
        for c in _eligible_clients():
            if gen >= cap:
                break
            cid = str(c.get("id") or "")
            if not cid:
                continue
            if _daily_on and _daily is not None and _daily.client_allowed(cid):
                deferred_to_daily += 1
                continue
            last = st.get(cid)
            due = True
            if last:
                try:
                    last_t = time.mktime(time.strptime(last, "%Y-%m-%d"))
                    due = (time.time() - last_t) >= (interval * 86400 - 3600)
                except Exception:
                    due = True
            if due:
                r = await generate_for_client(cid)
                if r.get("ok"):
                    gen += 1
        out["generated"] = gen
        out["deferred_to_daily_video"] = deferred_to_daily
        out["publish"] = await publish_due()
        # durable social-engine queue bhi drain karo (gated SOCIAL_ENGINE; off = inert)
        try:
            from app.social_engine import engine as _social_engine

            out["engine"] = await _social_engine.process_queue()
        except Exception as e:
            logger.debug(f"[video_ad] engine drain skip: {e}")
        return out
    except Exception as e:
        logger.warning(f"[video_ad] run_cycle failed: {e}")
        return {"ran": False, "reason": str(e)[:150]}


# ------------------------------- read API ----------------------------------- #
def list_for_client(client_id: str, limit: int = 50) -> list[dict[str, Any]]:
    cid = str(client_id or "").strip()
    rows = [r for r in _latest().values() if not cid or str(r.get("client_id") or "") == cid]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows[: max(1, min(int(limit or 50), 200))]


def list_all(limit: int = 100) -> list[dict[str, Any]]:
    return list_for_client("", limit)


__all__ = [
    "enabled",
    "generate_for_client",
    "on_approved",
    "on_changes_requested",
    "request_changes",
    "publish_due",
    "run_cycle",
    "list_for_client",
    "list_all",
]
