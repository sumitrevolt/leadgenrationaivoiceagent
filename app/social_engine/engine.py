"""social_engine.engine — enqueue + dispatch core. GATED `SOCIAL_ENGINE`.

  enqueue_publish(client_id, caption, media_path/url, platforms, account_refs) -> [job_ids]
  process_queue(limit) -> queued jobs claim -> provider dispatch -> published/retry/dead/skipped
Scheduler (run_cycle) AUR Celery task dono process_queue() call kar sakte (claim idempotent-ish).
NEVER raises.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

from . import store, vault
from .base import PublishRequest, PublishResult
from .providers import default_providers

logger = setup_logger(__name__)

_REGISTRY: dict[str, Any] | None = None


def registry() -> dict[str, Any]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = default_providers()
    return _REGISTRY


def enabled() -> bool:
    """Master gate. OFF = video_ad_cycle current inline path use karta (engine inert).

    Env explicit = final (0 = hard kill-switch); env UNSET par bind-mounted
    data/social_engine.json {"enabled": true} bhi chalega — running containers
    docker-cp drift carry karte (recreate = hotfix loss), isliye naya env var
    recreate ke bina inject nahi hota (same pattern: platform_dial/upi_config)."""
    v = os.getenv("SOCIAL_ENGINE", "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    try:
        import json as _json

        with open(
            os.getenv("SOCIAL_ENGINE_CONFIG", "data/social_engine.json"), encoding="utf-8"
        ) as fh:
            return bool((_json.load(fh) or {}).get("enabled"))
    except Exception:
        return False


def _client_phone(client_id: str) -> str:
    """Client record ka apna business phone (digits/formatted jaise stored). Never raises."""
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        return str(c.get("phone") or "").strip()
    except Exception:
        return ""


def _resolve_account(client_id: str, platform: str, account_ref: str) -> dict[str, Any]:
    acct = vault.get(client_id, platform, account_ref) or {}
    if platform == "telegram" and not (acct.get("account_ref") or account_ref):
        try:
            from app.marketing import clients_store

            c = clients_store.get_client(client_id) or {}
            chat = str(c.get("telegram_chat_id") or "").strip()
            if chat:
                acct = {"token": "", "account_ref": chat, "meta": {}}
        except Exception:
            pass
    elif platform == "whatsapp" and not (acct.get("account_ref") or account_ref):
        # WhatsApp delivery = client ke APNE business phone pe 1-to-1 (ban-safe). Vault me
        # koi WA account_ref na ho to client-record phone use karo (jaise telegram chat_id).
        phone = _client_phone(client_id)
        if phone:
            acct = {"token": "", "account_ref": phone, "meta": {}}
    return acct


def _default_platforms(client_id: str) -> list[str]:
    """Sirf configured providers (whatsapp agar client-phone + WA backend / postiz /
    vault me jo accounts hain). Empty-socials wale client (jaise jiya) ke liye whatsapp
    default candidate ban jaata hai — approved post uske apne number pe 1-to-1 deliver hota."""
    out: list[str] = []
    reg = registry()
    try:
        # telegram REMOVED 2026-06-28 (ban-risk) — no longer a default platform
        # WhatsApp = default candidate jab client ka apna phone ho + WA backend configured ho.
        wa = reg.get("whatsapp")
        if wa is not None and _client_phone(client_id):
            acct = {"account_ref": _client_phone(client_id)}
            if wa.configured(acct):
                out.append("whatsapp")
        # Postiz only when THIS client has own channel ids (or own-brand global).
        # Global POSTIZ_API_KEY alone must NOT enqueue customer jobs onto corporate
        # LeadsGenAI FB/IG (audit 2026-07-17 tenant contamination).
        try:
            from app.marketing import clients_store, postiz_publish

            crec = clients_store.get_client(client_id) or {"id": client_id}
            if postiz_publish.enabled() and postiz_publish.effective_integration_ids(crec):
                out.append("postiz")
        except Exception:
            pass
        for a in vault.list_accounts(client_id):
            p = str(a.get("platform") or "")
            if p in reg and p not in out:
                out.append(p)
    except Exception as e:
        logger.debug(f"[engine] default_platforms skip: {e}")
    return out


def enqueue_publish(
    client_id: str,
    caption: str = "",
    media_path: str = "",
    media_url: str = "",
    media_type: str = "video",
    platforms: list[str] | None = None,
    account_refs: dict[str, str] | None = None,
) -> list[str]:
    """Ek post ko target platforms ke liye queue karo (1 job/platform). Returns job-ids.

    Zero channel + koi phone bhi nahi (empty-socials client): silent success ki jagah
    "koi channel connected nahi" ko logs + team-feed pe SURFACE karta hai (approve path
    ko pata chale ki post kahin deliver nahi hoga), aur khali list return karta."""
    try:
        plats = platforms or _default_platforms(client_id)
        refs = account_refs or {}
        if not plats:
            # Kuch bhi target nahi — na koi social account, na WA phone. Non-silent.
            reason = "koi channel connected nahi (na social account, na WhatsApp phone)"
            logger.warning(f"[engine] enqueue_publish client={client_id}: {reason}")
            try:
                from app.platform import team

                team.log_event(
                    "zara",
                    "social_no_channel",
                    f"{client_id}: {reason} — approved post deliver nahi hoga",
                    status="warn",
                )
            except Exception:
                pass
            return []
        ids: list[str] = []
        for p in plats:
            jid = store.enqueue(
                {
                    "client_id": client_id,
                    "platform": p,
                    "account_ref": refs.get(p, ""),
                    "media_type": media_type,
                    "media_path": media_path,
                    "media_url": media_url,
                    "caption": caption,
                }
            )
            if jid:
                ids.append(jid)
        # best-effort immediate Celery drain — FIRE-AND-FORGET (scheduler drains anyway).
        # .delay() CONNECTS to the Redis broker to publish; a down/unreachable broker makes
        # that socket.connect BLOCK (broker_connection_timeout x retries) — a hang the
        # try/except can't catch. So never let it block the caller: dispatch in a daemon
        # thread with retry=False. (A blocking .delay() here hung full pytest -> SIGABRT/
        # exit 134, and would stall a real request if Redis were down.)
        if ids:
            try:
                import threading

                _n = len(ids) + 5

                def _fire_drain() -> None:
                    try:
                        from .tasks import drain_social_queue

                        if drain_social_queue is not None:
                            drain_social_queue.apply_async(args=[_n], retry=False)
                    except Exception:
                        pass

                threading.Thread(target=_fire_drain, name="social-drain", daemon=True).start()
            except Exception:
                pass
        return ids
    except Exception as e:
        logger.warning(f"[engine] enqueue_publish failed: {e}")
        return []


def _dry_run_enabled() -> bool:
    """Loop-social-3 (2026-07-11): safe E2E validation gate. When SOCIAL_DRY_RUN=1
    the engine drains queued jobs but NEVER hits a real provider — it fabricates
    a `PublishResult(ok=True, post_id="dry-<uuid>", raw={"dry_run": True})` so
    the full pipeline (queue → dispatch → ledger → customer timeline → admin
    cockpit) can be verified without a live FB/IG/GBP/LinkedIn publish.

    Semantics: identical to the master `enabled()` gate (env explicit wins,
    then `data/social_engine.json {"dry_run": true}` fallback). Independent of
    `SOCIAL_ENGINE` — you can enable dry_run without turning on the engine, but
    dry_run only fires ONCE the engine drains (which needs `SOCIAL_ENGINE=1`).
    Ban-safe: never sends a message, never calls a paid API, never violates a
    provider ToS. Meant for staging + first-customer canary."""
    v = os.getenv("SOCIAL_DRY_RUN", "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    try:
        import json as _json

        with open(
            os.getenv("SOCIAL_ENGINE_CONFIG", "data/social_engine.json"), encoding="utf-8"
        ) as fh:
            return bool((_json.load(fh) or {}).get("dry_run"))
    except Exception:
        return False


async def _dispatch_one(job: dict[str, Any]) -> PublishResult:
    p = str(job.get("platform") or "")
    prov = registry().get(p)
    if prov is None:
        return PublishResult(ok=False, platform=p, error="unknown platform")
    acct = _resolve_account(str(job.get("client_id") or ""), p, str(job.get("account_ref") or ""))
    if not prov.configured(acct):
        return PublishResult(ok=False, platform=p, error="__inert__")
    # Loop-social-15 (2026-07-11): Phase-6 platform adaptation — transform
    # caption/hashtags shape BEFORE validation so the validator sees the
    # actually-published body. Adaptation is safe (URL strip → "link in bio",
    # thread split for X, hashtag tail placement, ellipsis truncation) and
    # non-lossy where possible. Adapted job feeds provider.publish().
    try:
        from . import adaptation as _adp

        job = _adp.adapt_for_platform(job, p)
    except Exception:
        pass
    # Loop-social-10 (2026-07-11): Phase-6 platform-adaptation validators.
    # Blocking errors (caption > cap, unsupported media, missing disclaimer)
    # fail-fast with a descriptive error — the drain will retry/dead per normal
    # branching. Warns don't block publish. Lazy-import so tests without the
    # module still drain.
    try:
        from . import validators as _vlz

        issues = _vlz.validate_post(p, job, recent_captions=None)
        if _vlz.has_blocking_error(issues):
            first = next((i for i in issues if i.get("severity") == "error"), None)
            msg = first.get("message") if first else "validation_error"
            return PublishResult(
                ok=False,
                platform=p,
                error=f"validation:{first.get('rule', '')}: {msg}"[:150],
                raw={"validation_issues": issues},
            )
    except Exception:
        # Fail-open on validator crash — a bad validator must not block real posts.
        pass
    # Loop-social-3: DRY-RUN short-circuit. Fires AFTER configured() so we still
    # honestly report inert providers as skipped — dry-run just replaces the
    # provider.publish() call itself. Post-id is deterministic-ish (job id +
    # platform) so ledger + timeline reads look stable across drains.
    if _dry_run_enabled():
        jid = str(job.get("id") or "")[:12]
        return PublishResult(
            ok=True,
            platform=p,
            post_id=f"dry-{p}-{jid}",
            url="",
            raw={"dry_run": True, "job_id": jid, "account_ref": str(acct.get("account_ref") or "")},
        )
    req = PublishRequest(
        client_id=str(job.get("client_id") or ""),
        caption=str(job.get("caption") or ""),
        media_path=str(job.get("media_path") or ""),
        media_url=str(job.get("media_url") or ""),
        media_type=str(job.get("media_type") or "video"),
        platform=p,
        account_ref=str(job.get("account_ref") or "") or str(acct.get("account_ref") or ""),
    )
    return await prov.publish(req, acct)


def _log_delivery(client_id: str, event: str, job: dict[str, Any], detail: str = "") -> None:
    """Best-effort delivery_ledger log for an automated publish outcome. Never
    raises; no-op if client_id is blank (job data malformed)."""
    if not client_id:
        return
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.log_event(
            client_id, event, detail=detail or str(job.get("caption") or "")[:200]
        )
    except Exception as e:
        logger.debug(f"[engine] delivery ledger log skip: {e}")


async def process_queue(limit: int = 20) -> dict[str, Any]:
    """Queued jobs drain karo. Scheduler/worker se. Flag off = inert."""
    if not enabled():
        return {"ran": False, "reason": "SOCIAL_ENGINE off"}
    published = retried = dead = skipped = 0
    # A dry-run drain marks jobs `published` on purpose (canary: verify
    # queue→ledger→timeline→cockpit without a live post). The failure mode is
    # that it is INDISTINGUISHABLE from real publishing: the 2026-07-11 canary
    # gate sat on for 3 days, the cockpit showed 6 self-brand posts "published",
    # and NOTHING ever reached social. Nobody noticed because nothing said so.
    # Same fix as ADR-097: make the silent state LOUD, every drain. The returned
    # dict also carries `dry_run` so callers/UI can badge it instead of guessing.
    dry = _dry_run_enabled()
    if dry:
        logger.warning(
            "🧪 SOCIAL DRY-RUN ACTIVE — jobs will be marked `published` but NOTHING "
            "is posted to any provider. Turn off with SOCIAL_DRY_RUN=0 or "
            'data/social_engine.json {"dry_run": false}.'
        )
    try:
        # Recover jobs stuck in `processing` after worker crash (was admin-only).
        try:
            from . import scheduling as _sched_recover

            _sched_recover.recover_stale_processing(store, older_than_min=15)
        except Exception as _rec_e:
            logger.debug(f"[engine] stale-processing recover skip: {_rec_e}")
        jobs = store.claim_pending(limit)
        # Loop-social-8 (2026-07-11): Phase 8 pause + emergency-stop gates —
        # lazy-import so tests without the module don't crash the drain.
        try:
            from . import pause as _pause
        except Exception:
            _pause = None  # type: ignore
        # Loop-social-14 (2026-07-11): Phase 8 backoff + provider-aware QPM.
        try:
            from . import scheduling as _sched
        except Exception:
            _sched = None  # type: ignore
        for job in jobs:
            jid = str(job.get("id") or "")
            cid_pre = str(job.get("client_id") or "")
            # Pause gate BEFORE publish-started emit — a paused job never
            # entered the "publishing" transition, so ledger stays honest.
            if _pause is not None:
                paused, reason = _pause.should_pause_job(job)
                if paused:
                    store.mark(jid, "skipped", last_error=f"paused:{reason}")
                    skipped += 1
                    _log_delivery(
                        cid_pre, "customer_action_required", job, detail=f"paused: {reason}"
                    )
                    continue
            # Loop-social-14: exponential backoff — a retry-status row still
            # inside its backoff window is put back to 'retry' (no publish).
            if _sched is not None and not _sched.is_ready_for_retry(job):
                store.mark(jid, "retry", last_error="backoff_wait")
                retried += 1
                continue
            # Loop-social-14: per-platform QPM guard. Over-cap = defer (mark
            # retry with a bounded delay). Prevents provider-side 429 storms.
            if _sched is not None:
                plat = str(job.get("platform") or "").strip().lower()
                allowed, used, cap = _sched.check_platform_qpm(plat)
                if not allowed:
                    store.mark(jid, "retry", last_error=f"rate_limit:{plat}:{used}/{cap}")
                    retried += 1
                    _log_delivery(
                        cid_pre,
                        "post_retry_scheduled",
                        job,
                        detail=f"platform QPM guard: {used}/{cap}/min",
                    )
                    continue
            # Loop-social-6 (2026-07-11): emit publish-lifecycle event so the
            # customer timeline + admin cockpit reflect the "publish is running"
            # transition (previously invisible — customer only saw the terminal
            # published/failed state). Never-raise (helper is guarded).
            _log_delivery(cid_pre, "post_publish_started", job)
            try:
                res = await _dispatch_one(job)
            except Exception as e:
                res = PublishResult(
                    ok=False, platform=str(job.get("platform") or ""), error=str(e)[:150]
                )
            cid = str(job.get("client_id") or "")
            if res.ok:
                store.mark(jid, "published", post_id=res.post_id, post_url=res.url)
                published += 1
                _log_delivery(cid, "post_published", job)
            elif res.error == "__inert__":
                store.mark(jid, "skipped", last_error="provider not configured")
                skipped += 1
                # Loop-social-6: an unconfigured provider is customer_action —
                # they need to reconnect the account. Emit the canonical event so
                # the admin cockpit + customer setup checklist highlight it.
                _log_delivery(
                    cid,
                    "customer_action_required",
                    job,
                    detail=f"{job.get('platform', '')} account not connected",
                )
            else:
                attempts = int(job.get("attempts") or 0) + 1
                if attempts >= store.max_attempts():
                    store.mark(jid, "dead", attempts=attempts, last_error=res.error)
                    dead += 1
                    _log_delivery(cid, "post_failed", job, detail=str(res.error or "")[:200])
                else:
                    store.mark(jid, "retry", attempts=attempts, last_error=res.error)
                    retried += 1
                    # Loop-social-6: emit canonical retry event (ops-visible only —
                    # customer_visible=False in ledger LABELS, avoids timeline noise).
                    _log_delivery(
                        cid,
                        "post_retry_scheduled",
                        job,
                        detail=f"attempt {attempts}/{store.max_attempts()} — {str(res.error or '')[:120]}",
                    )
        if jobs:
            # Staff-visibility (2026-07-01): social posting ran completely invisibly on
            # /app/team today — attribute to "zara" (Social Media Manager).
            try:
                from app.platform import team

                team.log_event(
                    "zara",
                    "social_published" if published else "social_run",
                    f"{published} published, {retried} retry, {dead} dead, {skipped} skipped",
                    status="ok" if not dead else "warn",
                )
            except Exception:
                pass
        return {
            "ran": True,
            "claimed": len(jobs),
            "published": published,
            "retried": retried,
            "dead": dead,
            "skipped": skipped,
            # `published` above counts FABRICATED results when dry_run is on.
            # Surface it so no caller/dashboard can read this as real posting.
            "dry_run": dry,
        }
    except Exception as e:
        logger.warning(f"[engine] process_queue failed: {e}")
        return {"ran": False, "reason": str(e)[:150]}
