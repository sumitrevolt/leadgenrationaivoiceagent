"""daily_video.py — DAILY per-client AI video producer (Product-1 marketing).

WHY a dedicated producer instead of another engine on the `content` chain
--------------------------------------------------------------------------
`content` fans ~15 engines through ``team_scheduler._run_content_engine`` under
a single ``CONTENT_TIME_BUDGET_S`` (default 420s) wall-clock budget, and
``auto_content.run_daily_content()`` runs FIRST. When that eats the budget every
later engine — ``video_ad_cycle`` included — is skipped *silently*
(``_run_content_engine`` closes the coro and returns False; no exception, no
log line that names the video engine).

Prod evidence that this starvation really happens (2026-08-09, live `job_runs`):
the `content` job exceeded its 420s budget on **15 consecutive daily runs**,
2026-07-18 → 2026-08-01 (452–530s each), dropping every engine behind the
overrun with nothing recording which ones.

NOT the same thing as the 15-day video gap (2026-07-22 → 2026-08-06): that gap
was a DEAD GATE — commit `1664811e` (2026-08-05) taught `video_ad_cycle.enabled()`
to honour the `VIDEO_DAILY_SCHEDULER_ENABLED` alias, prod having had the cell flag
ON while `VIDEO_AD_CYCLE` was OFF, so `run_cycle` was fully inert. The prod
`delivery_ledger` holds exactly 6 `video_*` events, all dated 2026-08-06, i.e. no
render was even attempted during the window. Two separate problems; see ADR-166.

So this module:
  * gets its OWN beat entry (`staff-daily-video-daily`), never rides the content chain
  * stays LIGHT — it only ENQUEUES; ffmpeg/HyperFrames never run in this process
  * generates at most once per client per DAY (state file + Celery idempotency)
  * applies REVIEW BACKPRESSURE — the same prod snapshot showed 32/39 records
    stuck at `pending` customer review. Daily generation without a pending cap
    just grows that pile faster.

Fail-closed posture
-------------------
  * ``DAILY_VIDEO_ENABLED`` default OFF → whole module inert.
  * ``DAILY_VIDEO_CLIENTS`` empty = NO tenant. An unset allowlist meaning
    "everyone" is exactly how a canary becomes a fleet-wide daily render storm
    (same rule as ``hyperframes_provider.tenant_allowed``). ``*`` = all eligible.
  * Never raises — every public entry returns a dict.

Engine selection
----------------
``DAILY_VIDEO_ENGINE`` ∈ {auto, advanced, classic} (default ``auto``):
  * ``advanced`` — Creative Automation OS + HyperFrames (``enqueue_generate``).
    Needs CREATIVE_OS_ENABLED=1, CREATIVE_PROVIDER_HYPERFRAMES_ENABLED=1 and the
    tenant in CREATIVE_HYPERFRAMES_CANARY_TENANTS. NOTE: ``hyperframes`` is in
    ``providers.NO_SILENT_FALLBACK`` — a render failure does NOT silently drop to
    the deterministic provider, it fails the creative. That is deliberate
    (quality gate), but it means a missing render toolchain = zero videos.
  * ``classic`` — the proven deterministic ffmpeg path via
    ``video_ad_cycle.generate_for_client`` (approval + publish gate already wired).
  * ``auto`` — advanced when the gate allows AND the tenant's recent advanced
    attempts are not all failing; otherwise classic. This is the safety net for
    the real prod gap: the HyperFrames toolchain lives in the opt-in
    ``Dockerfile.video`` image (`deploy/compose/docker-compose.video.yml`) which
    `docker-compose.vps.yml` does not apply, so `worker-video` currently runs the
    plain `Dockerfile.lock` image with no Node/Chrome. Under ``auto`` the customer
    keeps getting a daily video instead of a silent drought.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# Both stores resolve through runtime_data_authority at CALL time rather than
# being frozen to `data/...` at import. A brand-new store must not be born as
# legacy debt: live automation state already lives under the runtime root, and a
# hardcoded `data/` path is how `data/job_heartbeats.json` ended up a stale
# leftover that briefly fooled the 2026-08-09 audit. The repo's runtime-data
# ratchet enforces exactly this and caught the first draft of this module.
_STATE_STORE: dict[str, Any] = {
    "store_id": "marketing.daily_video",
    "legacy_path": Path("data") / ".daily_video.json",
    "target_segments": ("marketing", "daily_video.json"),
}
_BLOCKS_STORE: dict[str, Any] = {
    "store_id": "marketing.daily_video",
    "legacy_path": Path("data") / ".daily_video_advanced_block.json",
    "target_segments": ("marketing", "daily_video_advanced_block.json"),
}


def _STATE() -> str:
    """Per-client 'generated on this date' map."""
    from app.platform import runtime_data_authority as _auth

    return str(_auth.resolve_store_path(**_STATE_STORE))


def _STATE_TMP() -> str:
    """Atomic-write companion, resolved beside the ACTIVE state target.

    `os.replace` is only atomic within one filesystem, so the temp file must
    never be resolved against a different root than its destination.
    """
    from app.platform import runtime_data_authority as _auth

    return str(_auth.resolve_temp_path(**_STATE_STORE))


def _BLOCKS() -> str:
    """Tenants parked off the advanced engine by a permanent brief refusal."""
    from app.platform import runtime_data_authority as _auth

    return str(_auth.resolve_store_path(**_BLOCKS_STORE))


def _BLOCKS_TMP() -> str:
    from app.platform import runtime_data_authority as _auth

    return str(_auth.resolve_temp_path(**_BLOCKS_STORE))


# Creative OS statuses that still occupy the customer's review attention.
_OPEN_CREATIVE_STATUSES = frozenset({"queued", "generating", "approval_pending", "qa_failed"})

ENGINE_ADVANCED = "advanced"
ENGINE_CLASSIC = "classic"

# Creative OS refusals that will NOT fix themselves on the next tick. Retrying
# these daily is not harmless: ``enqueue_generate`` calls ``record_attempt``
# BEFORE dispatch, so a permanently-refused tenant burns
# CREATIVE_TENANT_DAILY_BUDGET on records that never render, and the operator
# just sees "engine: advanced" with no video and no explanation.
# ``tenant_budget_exceeded`` and ``enqueue_failed`` are deliberately absent —
# those DO clear on their own.
_PERMANENT_ADVANCED_OUTCOMES = frozenset({"needs_customer_input", "blocked"})
_PERMANENT_ADVANCED_ERRORS = ("brief_blocked", "spec_invalid", "needs_customer_input")


# --------------------------------- flags ----------------------------------- #
def _on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def enabled() -> bool:
    """Master gate. OFF = whole producer inert (no state write, no enqueue)."""
    return _on("DAILY_VIDEO_ENABLED")


def engine_preference() -> str:
    raw = os.getenv("DAILY_VIDEO_ENGINE", "auto").strip().lower()
    return raw if raw in ("auto", ENGINE_ADVANCED, ENGINE_CLASSIC) else "auto"


def max_pending() -> int:
    """Per-client cap on OPEN customer reviews before we stop generating."""
    try:
        return max(1, min(50, int(os.getenv("DAILY_VIDEO_MAX_PENDING", "2"))))
    except Exception:
        return 2


def max_per_run() -> int:
    try:
        return max(1, min(200, int(os.getenv("DAILY_VIDEO_MAX_PER_RUN", "10"))))
    except Exception:
        return 10


def advanced_block_days() -> int:
    """How long a permanent advanced refusal parks a tenant before auto-retry.

    Auto-expiry matters: the usual cause is a missing offer / unverified brand
    fact, which the owner fixes in the dashboard. Without expiry that tenant
    would stay on classic forever even after the brief is complete.
    """
    try:
        return max(1, min(90, int(os.getenv("DAILY_VIDEO_ADVANCED_BLOCK_DAYS", "7"))))
    except Exception:
        return 7


def advanced_fail_window() -> int:
    """Consecutive failed advanced attempts before ``auto`` downgrades to classic."""
    try:
        return max(1, min(20, int(os.getenv("DAILY_VIDEO_ADVANCED_FAIL_WINDOW", "2"))))
    except Exception:
        return 2


def _allowlist() -> frozenset[str]:
    raw = os.getenv("DAILY_VIDEO_CLIENTS", "")
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def client_allowed(client_id: str) -> bool:
    """Empty allowlist = NO client (fail-closed). ``*`` = every eligible client."""
    allow = _allowlist()
    if not allow:
        return False
    cid = str(client_id or "").strip().lower()
    return bool(cid) and ("*" in allow or cid in allow)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


# --------------------------------- state ----------------------------------- #
def _load_state() -> dict[str, str]:
    try:
        with open(_STATE(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(state: dict[str, str]) -> None:
    """Atomic replace — a torn state file would re-generate for every client."""
    try:
        # Re-resolve at each I/O site — binding to a local would defeat the
        # authority resolver, and os.replace is only atomic within one filesystem
        # so the temp file must share the destination's root.
        # Re-resolve at each I/O site — binding to a local would defeat the
        # authority resolver.
        os.makedirs(os.path.dirname(_STATE()) or ".", exist_ok=True)
        with open(_STATE_TMP(), "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(_STATE_TMP(), _STATE())
    except Exception as e:
        logger.warning(f"[daily_video] state save failed: {e}")


# -------------------------- advanced-block registry ------------------------- #
def _load_blocks() -> dict[str, dict[str, Any]]:
    try:
        with open(_BLOCKS(), encoding="utf-8") as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_blocks(blocks: dict[str, dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_BLOCKS()) or ".", exist_ok=True)
        with open(_BLOCKS_TMP(), "w", encoding="utf-8") as f:
            json.dump(blocks, f)
        os.replace(_BLOCKS_TMP(), _BLOCKS())
    except Exception as e:
        logger.warning(f"[daily_video] block save failed: {e}")


def _days_since(day: str) -> int:
    try:
        then = time.mktime(time.strptime(day, "%Y-%m-%d"))
        return max(0, int((time.time() - then) // 86400))
    except Exception:
        return 0


def advanced_block(client_id: str) -> dict[str, Any] | None:
    """Active permanent-refusal block for this tenant, or None (auto-expiring)."""
    rec = (_load_blocks() or {}).get(str(client_id or "").strip())
    if not isinstance(rec, dict):
        return None
    age = _days_since(str(rec.get("at") or ""))
    if age >= advanced_block_days():
        return None
    return {**rec, "age_days": age}


def _record_advanced_block(client_id: str, reason: str) -> None:
    blocks = _load_blocks()
    blocks[str(client_id or "").strip()] = {
        "reason": str(reason or "")[:200],
        "at": _today(),
    }
    _save_blocks(blocks)


def clear_advanced_block(client_id: str) -> dict[str, Any]:
    """Operator escape hatch once the customer brief has been completed."""
    cid = str(client_id or "").strip()
    blocks = _load_blocks()
    existed = cid in blocks
    if existed:
        blocks.pop(cid, None)
        _save_blocks(blocks)
    return {"ok": True, "client_id": cid, "cleared": existed}


def _is_permanent_advanced_refusal(res: dict[str, Any]) -> str:
    """Return a reason string when the refusal will NOT clear by itself, else ''."""
    try:
        outcome = str(res.get("outcome") or "").strip().lower()
        if outcome in _PERMANENT_ADVANCED_OUTCOMES:
            missing = ", ".join(str(m) for m in (res.get("missing") or []))
            base = f"{outcome}: {res.get('error') or res.get('reason') or 'brief incomplete'}"
            return f"{base} (missing: {missing})" if missing else base
        err = str(res.get("error") or "").strip().lower()
        for marker in _PERMANENT_ADVANCED_ERRORS:
            if marker in err:
                return str(res.get("error"))[:200]
    except Exception:
        pass
    return ""


# ------------------------------ backpressure -------------------------------- #
def open_review_count(client_id: str) -> int:
    """Open customer reviews across BOTH pipelines for one client.

    Counted together on purpose: the customer sees one review inbox, not two.
    Never raises — an unreadable store must not block the whole run, so it
    contributes 0 rather than an exception.
    """
    total = 0
    try:
        from app.marketing import video_ad_cycle

        for r in video_ad_cycle.list_for_client(client_id, limit=200):
            if str(r.get("status") or "").strip().lower() == "pending":
                total += 1
    except Exception as e:
        logger.debug(f"[daily_video] classic pending count skip: {e}")
    try:
        from app.marketing.creative_os.store import list_records

        out = list_records(client_id, limit=200) or {}
        for r in out.get("items") or []:
            if str(r.get("status") or "").strip().lower() in _OPEN_CREATIVE_STATUSES:
                total += 1
    except Exception as e:
        logger.debug(f"[daily_video] creative pending count skip: {e}")
    return total


def _recent_advanced_failures(client_id: str) -> int:
    """Consecutive most-recent failed Creative OS attempts for this tenant.

    Used only by ``auto`` to stop hammering a broken advanced toolchain forever.
    """
    try:
        from app.marketing.creative_os.store import list_records

        out = list_records(client_id, limit=50) or {}
        items = list(out.get("items") or [])
        # list_records has no guaranteed ordering contract; sort newest-first on
        # whatever timestamp field the record carries, falling back to insertion.
        items.sort(
            key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True
        )
        streak = 0
        for r in items:
            st = str(r.get("status") or "").strip().lower()
            if st == "failed":
                streak += 1
                continue
            break
        return streak
    except Exception as e:
        logger.debug(f"[daily_video] advanced failure streak skip: {e}")
        return 0


# ------------------------------ engine choice ------------------------------- #
def advanced_gate(client_id: str) -> tuple[bool, str]:
    """Can the Creative OS / HyperFrames path serve this tenant right now?

    Only flags + tenant allowlist are checked here. The Node/Chrome toolchain
    deliberately is NOT probed: this code runs in the beat/worker container
    (``Dockerfile.lock``), while the render happens in ``worker-video`` — which
    only has the toolchain when the ``docker-compose.video.yml`` overlay is
    applied. Probing the wrong container would produce a confident false answer.
    """
    try:
        from app.marketing.creative_os import flags as cflags
        from app.marketing.creative_os import hyperframes_provider as hp
    except Exception as e:
        return False, f"creative_os import failed: {str(e)[:80]}"
    if not cflags.os_enabled():
        return False, "CREATIVE_OS_ENABLED off"
    if not hp.provider_enabled():
        return False, "CREATIVE_PROVIDER_HYPERFRAMES_ENABLED off"
    if not hp.tenant_allowed(client_id):
        return False, "tenant not in CREATIVE_HYPERFRAMES_CANARY_TENANTS"
    blocked = advanced_block(client_id)
    if blocked:
        # Stops the daily retry loop AND makes the cause visible in status():
        # without this the operator sees engine="advanced" and simply no video.
        return (
            False,
            f"advanced blocked ({blocked.get('reason')}) — fix brief, then daily-clear-block",
        )
    return True, "ok"


def choose_engine(client_id: str) -> tuple[str, str]:
    """Return ``(engine, reason)``. Never raises."""
    pref = engine_preference()
    if pref == ENGINE_CLASSIC:
        return ENGINE_CLASSIC, "DAILY_VIDEO_ENGINE=classic"
    ok, why = advanced_gate(client_id)
    if pref == ENGINE_ADVANCED:
        # Explicit advanced: honour the operator's choice, but do not pretend the
        # gate passed — the caller records the refusal instead of enqueuing.
        return (ENGINE_ADVANCED, "DAILY_VIDEO_ENGINE=advanced") if ok else ("", why)
    # auto
    if not ok:
        return ENGINE_CLASSIC, f"advanced unavailable ({why})"
    streak = _recent_advanced_failures(client_id)
    if streak >= advanced_fail_window():
        return ENGINE_CLASSIC, f"advanced failing ({streak} consecutive) — auto downgrade"
    return ENGINE_ADVANCED, "advanced ready"


# --------------------------------- enqueue ---------------------------------- #
def _enqueue_classic(client_id: str, day: str) -> dict[str, Any]:
    """Hand the heavy deterministic render to the video Celery queue."""
    try:
        from app.tasks.video_jobs import daily_video_client_task

        res = daily_video_client_task.apply_async(
            kwargs={"client_id": client_id},
            task_id=f"daily_video:{client_id}:{day}",
        )
        return {"ok": True, "engine": ENGINE_CLASSIC, "job_id": str(res.id)}
    except Exception as e:
        logger.warning(f"[daily_video] classic enqueue failed for {client_id}: {e}")
        return {"ok": False, "engine": ENGINE_CLASSIC, "error": f"enqueue_failed:{str(e)[:120]}"}


def _enqueue_advanced(client: dict[str, Any]) -> dict[str, Any]:
    """Creative OS already persists a spec and dispatches to the video queue."""
    cid = str(client.get("id") or "")
    try:
        from app.marketing.creative_os.service import enqueue_generate

        out = enqueue_generate(
            tenant_id=cid,
            business_name=str(client.get("business_name") or "").strip(),
            recipe=os.getenv("DAILY_VIDEO_RECIPE", "offer_announcement").strip()
            or "offer_announcement",
            offer=str(client.get("offer") or "").strip(),
            niche=str(client.get("niche") or "general").strip(),
            language=str(client.get("language") or "hinglish").strip(),
            platform="instagram",
            aspect_ratio="9:16",
            provider="hyperframes",
        )
        out = dict(out or {})
        out["engine"] = ENGINE_ADVANCED
        return out
    except Exception as e:
        logger.warning(f"[daily_video] advanced enqueue failed for {cid}: {e}")
        return {"ok": False, "engine": ENGINE_ADVANCED, "error": str(e)[:160]}


# ---------------------------------- run ------------------------------------- #
async def run_daily() -> dict[str, Any]:
    """Scheduler entrypoint. LIGHT — enqueues only, never renders. Never raises."""
    if not enabled():
        return {"ran": False, "reason": "DAILY_VIDEO_ENABLED off"}
    day = _today()
    out: dict[str, Any] = {
        "ran": True,
        "date": day,
        "engine_preference": engine_preference(),
        "enqueued": 0,
        "skipped": [],
        "results": [],
    }
    try:
        from app.marketing import video_ad_cycle

        clients = video_ad_cycle._eligible_clients()
    except Exception as e:
        logger.warning(f"[daily_video] eligible clients failed: {e}")
        return {"ran": False, "reason": f"eligible_failed:{str(e)[:120]}"}

    if not _allowlist():
        out["ran"] = False
        out["reason"] = "DAILY_VIDEO_CLIENTS empty (fail-closed allowlist)"
        out["eligible"] = len(clients)
        return out

    state = _load_state()
    cap = max_per_run()
    pending_cap = max_pending()
    dirty = False

    for c in clients:
        if out["enqueued"] >= cap:
            out["skipped"].append({"client_id": "*", "reason": f"per_run_cap:{cap}"})
            break
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        if not client_allowed(cid):
            out["skipped"].append({"client_id": cid, "reason": "not_in_DAILY_VIDEO_CLIENTS"})
            continue
        if state.get(cid) == day:
            out["skipped"].append({"client_id": cid, "reason": "already_generated_today"})
            continue
        open_reviews = open_review_count(cid)
        if open_reviews >= pending_cap:
            out["skipped"].append(
                {
                    "client_id": cid,
                    "reason": "pending_review_backlog",
                    "open_reviews": open_reviews,
                    "cap": pending_cap,
                }
            )
            continue

        engine, why = choose_engine(cid)
        if not engine:
            out["skipped"].append({"client_id": cid, "reason": f"engine_unavailable:{why}"})
            continue

        res = _enqueue_advanced(c) if engine == ENGINE_ADVANCED else _enqueue_classic(cid, day)
        res = dict(res or {})
        if engine == ENGINE_ADVANCED and not res.get("ok"):
            permanent = _is_permanent_advanced_refusal(res)
            if permanent:
                # Park the tenant so tomorrow's tick does not burn another
                # CREATIVE_TENANT_DAILY_BUDGET attempt on the same broken brief,
                # then still ship TODAY's video via the classic path (auto only —
                # explicit `advanced` means the operator wants advanced or nothing).
                _record_advanced_block(cid, permanent)
                res["advanced_blocked"] = permanent
                if engine_preference() == "auto":
                    fallback = dict(_enqueue_classic(cid, day) or {})
                    fallback["advanced_blocked"] = permanent
                    fallback["fell_back_from"] = ENGINE_ADVANCED
                    res = fallback
        res["client_id"] = cid
        res["engine_reason"] = why
        out["results"].append(res)
        if res.get("ok"):
            out["enqueued"] += 1
            # Mark the day ONLY on a confirmed enqueue — a failed dispatch must
            # stay retryable on the next tick instead of burning the client's day.
            state[cid] = day
            dirty = True

    if dirty:
        _save_state(state)

    try:
        from app.platform import team

        team.log_event(
            "isha",
            "daily_video",
            f"{out['enqueued']} daily video enqueue ({out['engine_preference']})",
            meta={"date": day, "skipped": len(out["skipped"])},
        )
    except Exception:
        pass
    return out


# --------------------------------- status ----------------------------------- #
def status() -> dict[str, Any]:
    """Operator answer to 'daily video kyun nahi chal raha'. Never raises."""
    day = _today()
    state = _load_state()
    info: dict[str, Any] = {
        "ok": True,
        "date": day,
        "enabled": enabled(),
        "engine_preference": engine_preference(),
        "allowlist": sorted(_allowlist()),
        "allowlist_configured": bool(_allowlist()),
        "max_pending": max_pending(),
        "max_per_run": max_per_run(),
        "advanced_fail_window": advanced_fail_window(),
        "advanced_block_days": advanced_block_days(),
        "clients": [],
    }
    try:
        from app.marketing import video_ad_cycle

        clients = video_ad_cycle._eligible_clients()
    except Exception as e:
        info["eligible_error"] = str(e)[:160]
        clients = []
    for c in clients:
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        engine, why = choose_engine(cid)
        gate_ok, gate_why = advanced_gate(cid)
        info["clients"].append(
            {
                "client_id": cid,
                "business_name": c.get("business_name"),
                "allowed": client_allowed(cid),
                "generated_today": state.get(cid) == day,
                "last_generated": state.get(cid),
                "open_reviews": open_review_count(cid),
                "engine": engine or "none",
                "engine_reason": why,
                "advanced_gate_ok": gate_ok,
                "advanced_gate_reason": gate_why,
                # Distinguishes a PERMANENT brief refusal (owner must complete the
                # customer's offer/brand facts) from a transient advanced failure.
                "advanced_block": advanced_block(cid),
            }
        )
    return info


__all__ = [
    "advanced_block",
    "advanced_block_days",
    "advanced_gate",
    "choose_engine",
    "clear_advanced_block",
    "client_allowed",
    "enabled",
    "engine_preference",
    "max_pending",
    "max_per_run",
    "open_review_count",
    "run_daily",
    "status",
]
