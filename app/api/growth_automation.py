"""Agent automation-ops endpoints — self-improve loop, skill library/pack, code
upgrader, social drafts, lead harvester, approval cockpit, self-improve gates.

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/...).
Also (transitively) mounts the /process/* sub-router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(tags=["Growth"])


# ------------- Self-improve continuous loop + skill library + naye channels ------------- #
@router.get("/selfimprove/status")
async def selfimprove_status(_user=Depends(require_admin)):
    """Continuous loop ka live status: heartbeat, runs, queue, skill summary."""
    from app.agents import self_improve

    return self_improve.status()


@router.post("/selfimprove/run")
async def selfimprove_run(_user=Depends(require_admin)):
    """Loop tick ABHI enqueue karo (Celery worker me chalega — web process block
    nahi hota). Flag OFF ho to bhi one-shot enqueue ho jata (tick khud gate check
    karta, requeue sirf flag ON pe). Celery down ho to in-process fallback."""
    try:
        from app.tasks.staff_jobs import self_improve_tick

        r = self_improve_tick.delay()
        return {"ok": True, "queued": True, "task_id": str(getattr(r, "id", ""))}
    except Exception:
        try:
            from app.agents import self_improve

            res = await self_improve.run_once()
            return {"ok": True, "queued": False, "fallback": "in_process", "result": res}
        except Exception as e2:
            return {
                "ok": False,
                "queued": False,
                "error": str(e2)[:200],
                "hint": "celery worker chal raha hai?",
            }


class SelfImproveTaskIn(BaseModel):
    task: str
    action: str = ""


@router.post("/selfimprove/task")
async def selfimprove_add_task(body: SelfImproveTaskIn, _user=Depends(require_admin)):
    """Manual task queue me daalo — loop agle tick pe ise pehle uthayega.
    Valid actions: self_improve.ACTIONS keys (khali = auto-pick)."""
    from app.agents import self_improve

    return self_improve.add_task(body.task, body.action, source="manual")


@router.get("/selfimprove/actions")
async def selfimprove_actions(_user=Depends(require_admin)):
    """Available loop actions + descriptions."""
    from app.agents import self_improve

    return {
        "actions": [
            {"key": k, "llm_heavy": v[0], "desc": v[1]} for k, v in self_improve.ACTIONS.items()
        ]
    }


@router.get("/skills/library")
async def skills_library(_user=Depends(require_admin)):
    """Auto-learn skill library: per-tactic success-rates + recent lessons."""
    from app.platform import skill_library

    return skill_library.summary()


class LessonIn(BaseModel):
    topic: str = "general"
    lesson: str


@router.post("/skills/lesson")
async def skills_add_lesson(body: LessonIn, _user=Depends(require_admin)):
    """Manual lesson add (human coaching → agents agle runs me use karte)."""
    from app.platform import skill_library

    return skill_library.record_lesson(body.topic, body.lesson, source="manual", agent="sumit")


# ------------- Skill pack (Claude project skills → VPS agents) + code upgrader ------------- #
@router.get("/skills/pack")
async def skills_pack_list(q: str = "", _user=Depends(require_admin)):
    """35+ project skills (+agent-authored extras) — list ya keyword search."""
    from app.platform import skill_pack

    if q:
        return {"query": q, "matches": skill_pack.find(q, k=5)}
    return {"enabled": skill_pack.enabled(), "skills": skill_pack.list_skills()}


@router.get("/skills/pack/{name}")
async def skills_pack_get(name: str, _user=Depends(require_admin)):
    from app.platform import skill_pack

    s = skill_pack.load(name)
    if not s:
        raise HTTPException(status_code=404, detail="skill not found")
    return s


@router.post("/skills/pack/ingest")
async def skills_pack_ingest(_user=Depends(require_admin)):
    """Saari skills KB namespace 'skills' me (Qdrant semantic recall)."""
    from app.platform import skill_pack

    return skill_pack.ingest_to_kb()


class SkillAuthorIn(BaseModel):
    name: str
    text: str


@router.post("/skills/pack/author")
async def skills_pack_author(body: SkillAuthorIn, _user=Depends(require_admin)):
    """Tier-1 SAFE write — naya/updated skill data/skills_extra/ me (runtime-live)."""
    from app.platform import skill_pack

    return skill_pack.author(body.name, body.text)


@router.post("/upgrader/scan")
async def upgrader_scan(_user=Depends(require_admin)):
    """Vikram: observability signals → code-upgrade proposals (flag-independent manual run)."""
    from app.agents import code_upgrader

    return await code_upgrader.scan_and_propose()


@router.get("/upgrader/patches")
async def upgrader_patches(
    status: str | None = None, limit: int = 50, _user=Depends(require_admin)
):
    from app.agents import code_upgrader

    return {"patches": code_upgrader.list_patches(status, limit)}


class PatchStatusIn(BaseModel):
    status: str  # approved | rejected | applied
    note: str = ""


@router.post("/upgrader/patches/{patch_id}/status")
async def upgrader_patch_status(
    patch_id: str, body: PatchStatusIn, _user=Depends(require_super_admin)
):
    """Hybrid gate: core-code patch approve/reject — SUPER_ADMIN only (RBAC design)."""
    from app.agents import code_upgrader

    result = code_upgrader.set_status(patch_id, body.status, body.note)
    try:  # office HQ Approvals-panel cache — see decide() sibling above
        from app.platform import office_hq

        await office_hq.invalidate_snapshot_cache()
    except Exception:
        pass
    return result


@router.get("/upgrader/code-search")
async def upgrader_code_search(q: str, k: int = 6, _user=Depends(require_admin)):
    """Semantic codebase search (Kilo-Code "codebase_search" parity) — engineering
    agents (Vikram) isi se relevant code dhoondte hain. Index daily training job se
    banta; khaali / deps missing → []. Read-only, flag-independent (admin-gated)."""
    from app.agents import code_search

    hits = await code_search.search(q, k=k)
    return {
        "ok": True,
        "query": q,
        "grounding_enabled": code_search.enabled(),
        "count": len(hits),
        "hits": hits,
    }


class CodeDiagnosticsIn(BaseModel):
    code: str
    paths: list[str] = []  # optional: cited file paths to existence-check
    lint: bool = True


@router.post("/upgrader/diagnostics")
async def upgrader_diagnostics(body: CodeDiagnosticsIn, _user=Depends(require_admin)):
    """Static code diagnostics (OpenCode LSP-diagnostics parity) — admin patch-code
    ko approve karne se PEHLE validate kare: ast syntax (+ ruff lint if available) +
    referenced-path existence. Read-only, never-raise."""
    from app.agents import code_diagnostics

    diags = code_diagnostics.check_code(body.code, run_lint=body.lint)
    if body.paths:
        diags = list(diags) + code_diagnostics.check_references(body.paths)
    return {
        "ok": not any(d.get("level") == "error" for d in diags),
        "count": len(diags),
        "summary": code_diagnostics.summary(diags),
        "diagnostics": diags,
    }


@router.get("/social/channels")
async def social_channels_list(_user=Depends(require_admin)):
    """Naye customer-approach channels (sab ban-safe drafts)."""
    from app.marketing import social_channels

    return {"channels": social_channels.list_channels()}


class SocialDraftIn(BaseModel):
    channel: str
    niche: str = "general"
    city: str = ""
    business_name: str = ""


@router.post("/social/draft")
async def social_draft(body: SocialDraftIn, _user=Depends(require_admin)):
    """Ek naye channel ka ready-to-post Hinglish draft (manual 1-click post)."""
    from app.marketing import social_channels

    return await social_channels.draft(body.channel, body.niche, body.city, body.business_name)


class SocialBatchIn(BaseModel):
    niche: str = "general"
    city: str = ""
    business_name: str = ""
    channels: list[str] | None = None
    limit: int = 4


@router.post("/social/batch")
async def social_batch(body: SocialBatchIn, _user=Depends(require_admin)):
    """Multiple naye channels ka draft pack."""
    from app.marketing import social_channels

    return await social_channels.draft_batch(
        body.niche, body.city, body.business_name, body.channels, body.limit
    )


# ------------- Postiz auto-posting config (no-restart, vault-backed) ------------- #
class PostizConfigIn(BaseModel):
    api_key: str = ""  # Postiz Settings -> API se; khali = existing key rakho
    api_url: str = ""  # self-host = https://postiz.<domain>/api; khali = cloud default
    integrations: str = ""  # channel ids csv (Postiz UI se); khali = existing rakho
    enable_engine: bool | None = None  # true/false = data/social_engine.json toggle


@router.post("/social/postiz/configure")
async def social_postiz_configure(body: PostizConfigIn, _user=Depends(require_admin)):
    """Postiz key/url/channel-ids RUNTIME pe set karo (encrypted vault, client
    '_global') — container recreate ki zaroorat nahi (upi_config pattern). Key
    response me kabhi wapas nahi aati."""
    from app.social_engine import vault

    existing = vault.get("_global", "postiz") or {}
    existing_meta = existing.get("meta") or {}
    token = (body.api_key or "").strip() or str(existing.get("token") or "")
    meta = {
        "api_url": (body.api_url or "").strip() or str(existing_meta.get("api_url") or ""),
        "integrations": (body.integrations or "").strip()
        or str(existing_meta.get("integrations") or ""),
    }
    saved = False
    if token or meta["api_url"] or meta["integrations"]:
        saved = bool(vault.put("_global", "postiz", token, meta=meta))

    engine_result: bool | None = None
    if body.enable_engine is not None:
        try:
            import json as _json
            import os as _os

            path = _os.getenv("SOCIAL_ENGINE_CONFIG", "data/social_engine.json")
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"enabled": bool(body.enable_engine)}, fh)
            engine_result = bool(body.enable_engine)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"engine toggle write failed: {e}")

    from app.marketing import postiz_publish
    from app.social_engine import engine as social_engine

    return {
        "ok": True,
        "saved": saved,
        "postiz_configured": postiz_publish.enabled(),
        "api_url": meta["api_url"] or "https://api.postiz.com",
        "integrations_count": len([x for x in meta["integrations"].split(",") if x.strip()]),
        "social_engine_enabled": (
            social_engine.enabled() if engine_result is None else engine_result
        ),
    }


@router.get("/social/postiz/status")
async def social_postiz_status(_user=Depends(require_admin)):
    """Postiz + social-engine readiness (key kabhi expose nahi hoti)."""
    from app.marketing import postiz_publish
    from app.social_engine import engine as social_engine
    from app.social_engine import store, vault

    rec = vault.get("_global", "postiz") or {}
    meta = rec.get("meta") or {}
    vault_integrations = str(meta.get("integrations") or "")

    # 2026-07-14 (ADR-099): report the EFFECTIVE resolved config, not just the
    # vault field. `_integration_ids()` resolves client → env → vault, so env
    # silently wins; counting only vault made this endpoint say
    # `integrations_count: 0` while all 4 channels were wired via
    # POSTIZ_INTEGRATIONS and publishing was fully functional. A status surface
    # that under-reports readiness is the same failure class as ADR-095/096/098
    # (fake state on a real status surface) — it sent an operator chasing a
    # non-existent misconfiguration. `vault_integrations_count` is kept so the
    # configure endpoint's own write is still observable.
    effective_ids = postiz_publish.effective_integration_ids()
    dry_run = bool(social_engine._dry_run_enabled())
    proof = store.publish_proof()
    counts = store.queue_counts()
    live = await postiz_publish.live_integrations_summary()
    youtube_refresh = bool(live.get("youtube_refresh_needed"))
    return {
        "postiz_configured": postiz_publish.enabled(),
        "api_url_set": bool(postiz_publish.api_url()),
        "api_url": postiz_publish.api_url(),
        "integrations_count": len(effective_ids),
        "integrations_source": postiz_publish.integrations_source(),
        "vault_integrations_count": len([x for x in vault_integrations.split(",") if x.strip()]),
        "social_engine_enabled": social_engine.enabled(),
        # ADR-098 class: omit dry_run = status can claim "ready" while publishes are fake.
        "dry_run": dry_run,
        # Launch evidence: real provider post_id from drained jobs (not dry-* fabrications).
        "publish_proven": bool(proof.get("publish_proven")),
        "last_real_post_id": proof.get("last_real_post_id") or "",
        "last_real_post_at": proof.get("last_real_post_at") or "",
        "queue_counts": counts,
        "live_integrations_ok": bool(live.get("ok")),
        "live_channels": live.get("channels") or [],
        "youtube_refresh_needed": youtube_refresh,
        "youtube_oauth_action": (
            "Google Cloud Console → OAuth consent screen → Publish app (testing mode = refresh token ~7d death)"
            if youtube_refresh or not live.get("ok")
            else ""
        ),
    }


# --------------------------------------------------------------------------- #
# Admin Social-Delivery COCKPIT (2026-07-11)                                  #
#                                                                             #
# Read-only triage surface over `social_engine.store.list_jobs()` — customer  #
# social publish queue ka health/DLQ/retry view. `POST /jobs/{id}/retry` re-  #
# marks a dead/failed row queued so the next drain picks it up (idempotent    #
# under the store's latest-wins invariant). No creds ever leaked.             #
# --------------------------------------------------------------------------- #
_SOCIAL_JOB_STATUSES = ("queued", "retry", "processing", "published", "dead", "skipped", "failed")


@router.get("/social/jobs")
async def admin_social_jobs(
    client_id: str = "",
    platform: str = "",
    status: str = "",
    limit: int = 100,
    _user=Depends(require_admin),
):
    """List social-engine publish jobs for admin triage. Filters (all optional):
    `client_id` / `platform` / `status`. Never-500; empty on error."""
    try:
        from app.social_engine import store

        st = (status or "").strip().lower()
        if st and st not in _SOCIAL_JOB_STATUSES:
            st = ""
        rows = store.list_jobs(
            client_id=(client_id or "").strip(),
            status=st,
            limit=max(1, min(int(limit or 100), 500)),
        )
        # Platform filter is post-fetch (store doesn't take it) — keeps store API stable.
        plat = (platform or "").strip().lower()
        if plat:
            rows = [r for r in rows if str(r.get("platform") or "").lower() == plat]

        # Rollup counts (per-status) for the cockpit header.
        counts = dict.fromkeys(_SOCIAL_JOB_STATUSES, 0)
        for r in rows:
            s = str(r.get("status") or "").lower()
            if s in counts:
                counts[s] += 1

        return {
            "ok": True,
            "count": len(rows),
            "counts": counts,
            "jobs": rows,
            "filters": {"client_id": client_id, "platform": plat, "status": st},
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)[:200],
            "count": 0,
            "jobs": [],
            "counts": dict.fromkeys(_SOCIAL_JOB_STATUSES, 0),
        }


class SocialPauseIn(BaseModel):
    """Loop-social-8 (2026-07-11): pause + emergency-stop admin toggle."""

    emergency_stop: bool | None = None
    paused_platforms: list[str] | None = None
    paused_clients: list[str] | None = None


@router.get("/social/pause")
async def admin_social_pause_status(_user=Depends(require_admin)):
    """Read current pause state — env + config-file merged, corruption-safe."""
    from app.social_engine import pause as _pause

    return {
        "ok": True,
        "emergency_stop": _pause.emergency_stop_active(),
        "paused_platforms": sorted(_pause.paused_platforms()),
        "paused_clients": sorted(_pause.paused_clients()),
    }


@router.post("/social/pause")
async def admin_social_pause_set(body: SocialPauseIn, _user=Depends(require_admin)):
    """Runtime pause toggle — writes `data/social_engine.json`. Env vars still
    take precedence (env explicit wins per pause module contract). Any field
    left None preserves the current value."""
    from app.social_engine import pause as _pause

    partial: dict = {}
    if body.emergency_stop is not None:
        partial["emergency_stop"] = bool(body.emergency_stop)
    if body.paused_platforms is not None:
        partial["paused_platforms"] = [
            str(x).strip().lower() for x in body.paused_platforms if str(x).strip()
        ]
    if body.paused_clients is not None:
        partial["paused_clients"] = [str(x).strip() for x in body.paused_clients if str(x).strip()]
    cfg = _pause.set_config(**partial)
    return {
        "ok": True,
        "written": partial,
        "current": {
            "emergency_stop": _pause.emergency_stop_active(),
            "paused_platforms": sorted(_pause.paused_platforms()),
            "paused_clients": sorted(_pause.paused_clients()),
        },
        "config_snapshot": {k: v for k, v in cfg.items() if not k.startswith("_")},
    }


@router.post("/social/jobs/{job_id}/run-now")
async def admin_social_job_run_now(job_id: str, _user=Depends(require_admin)):
    """Loop-social-14 (2026-07-11): admin run-now control (Phase 8). Marks any
    non-terminal job as queued so the next drain picks it up immediately.
    Bypasses backoff (last_error cleared). Idempotent — already-queued = no-op."""
    try:
        from app.social_engine import store

        jid = str(job_id or "").strip()
        cur = store.get(jid)
        if cur is None:
            return {"ok": False, "error": "not_found", "job_id": jid}
        prev = str(cur.get("status") or "").lower()
        if prev == "published":
            return {
                "ok": False,
                "error": "terminal",
                "job_id": jid,
                "message": "Published — cannot re-run (use cancel + new post)",
            }
        store.mark(
            jid,
            "queued",
            last_error="",
            admin_run_now_at=__import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        )
        return {"ok": True, "job_id": jid, "previous": prev, "status": "queued"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/social/token-health")
async def admin_social_token_health(days: int = 7, _user=Depends(require_admin)):
    """Loop-social-21 (2026-07-11): admin cockpit expiring-tokens surface.
    Uses vault.check_token_expiries(). Ledger events already emitted per row."""
    try:
        from app.social_engine import vault

        out = vault.check_token_expiries(days=max(1, min(int(days or 7), 60)))
        # Redact tokens/refs before returning to admin UI.
        for bucket in ("expired", "warning"):
            for row in out.get(bucket, []):
                row.pop("tok", None)
                row["account_ref"] = str(row.get("account_ref") or "")[-6:]
        return {"ok": True, **out}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/social/latest-events")
async def admin_social_latest_events(limit: int = 50, _user=Depends(require_admin)):
    """Loop-social-21: recent social delivery-ledger events across ALL clients
    for admin cockpit 'latest delivery events' feed."""
    try:
        from app.marketing import delivery_ledger

        social_evs = {
            "post_scheduled",
            "post_publish_started",
            "post_published",
            "post_failed",
            "post_partially_published",
            "post_retry_scheduled",
            "post_cancelled",
            "customer_action_required",
            "social_account_connected",
            "social_account_disconnected",
            "social_account_connection_failed",
            "token_expired",
            "token_refreshed",
        }
        # Ledger is per-client JSONL — walk the ledger dir.
        import os as _os

        rows: list[dict] = []
        try:
            ledger_dir = getattr(delivery_ledger, "_LEDGER_DIR", "data/delivery_ledger")
            if _os.path.isdir(ledger_dir):
                for fn in _os.listdir(ledger_dir):
                    if not fn.endswith(".jsonl"):
                        continue
                    cid = fn[:-6]
                    try:
                        for ev in delivery_ledger.timeline(cid, limit=200, customer_only=False):
                            if ev.get("event") in social_evs:
                                ev["client_id"] = cid
                                rows.append(ev)
                    except Exception:
                        continue
        except Exception:
            pass
        rows.sort(key=lambda r: str(r.get("ts") or r.get("timestamp") or ""), reverse=True)
        return {"ok": True, "events": rows[: max(1, min(int(limit or 50), 200))]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "events": []}


@router.post("/social/jobs/{job_id}/cancel")
async def admin_social_job_cancel(job_id: str, _user=Depends(require_admin)):
    """Loop-social-21: cancel a queued/retry/processing job. Idempotent.
    Terminal states (published/dead/skipped) are refused."""
    try:
        from app.social_engine import store

        jid = str(job_id or "").strip()
        cur = store.get(jid)
        if cur is None:
            return {"ok": False, "error": "not_found", "job_id": jid}
        prev = str(cur.get("status") or "").lower()
        if prev in ("published", "dead", "skipped"):
            return {"ok": False, "error": "terminal", "status": prev}
        store.mark(jid, "skipped", last_error="admin_cancelled")
        # Emit ledger cancel.
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                str(cur.get("client_id") or ""),
                "post_cancelled",
                detail=f"admin cancel from {prev}",
                key=f"admin_cancel:{jid}",
            )
        except Exception:
            pass
        return {"ok": True, "job_id": jid, "previous": prev, "status": "skipped"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/social/recover-stale")
async def admin_social_recover_stale(older_than_min: int = 15, _user=Depends(require_admin)):
    """Loop-social-14: Phase 8 stale-job recovery. Any 'processing' row older
    than N minutes → reset to queued (worker crash mid-publish assumed)."""
    try:
        from app.social_engine import scheduling, store

        return {"ok": True, **scheduling.recover_stale_processing(store, older_than_min)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/social/jobs/{job_id}/retry")
async def admin_social_job_retry(job_id: str, _user=Depends(require_admin)):
    """Re-queue a dead/failed social job. Idempotent: append-latest-wins guarantees
    the drain claims the same row again with `attempts` preserved (so max_attempts
    still bounds runaway retries). No-op if job doesn't exist or is already queued."""
    try:
        from app.social_engine import store

        jid = str(job_id or "").strip()
        if not jid:
            raise HTTPException(status_code=400, detail="job_id required")
        cur = store.get(jid)
        if cur is None:
            return {"ok": False, "error": "not_found", "job_id": jid}
        already = str(cur.get("status") or "").lower()
        if already in ("queued", "retry", "processing"):
            return {"ok": True, "job_id": jid, "status": already, "no_change": True}
        # Reset last_error so admin sees a clean state next drain.
        store.mark(
            jid,
            "queued",
            last_error="",
            admin_retry_at=__import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        )
        return {"ok": True, "job_id": jid, "status": "queued", "previous": already}
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "job_id": job_id}


# ------------- Lead harvester (multi-source, legal-only, automated loop) ------------- #
class HarvestIn(BaseModel):
    niche: str = ""
    city: str = ""
    limit: int = 10
    sources: list[str] | None = None


@router.post("/harvest/run")
async def harvest_run(body: HarvestIn, _user=Depends(require_admin)):
    """Multi-source lead harvest abhi chalao (manual = flag-independent).
    Sources: prospector (Places/OSM), websearch (BRAVE_API_KEY), opendata
    (DATA_GOV_IN_API_KEY) + email-enrich. Directory/social scraping NAHI (ToS)."""
    from app.platform import lead_harvester

    return await lead_harvester.run_harvest(body.niche, body.city, body.limit, body.sources)


@router.get("/harvest/runs")
async def harvest_runs(limit: int = 15, _user=Depends(require_admin)):
    """Recent harvest runs (per-source stats)."""
    from app.platform import lead_harvester

    return {"runs": lead_harvester.recent_runs(limit)}


@router.get("/harvest/sources")
async def harvest_sources(_user=Depends(require_admin)):
    """Source readiness (kaunse keys armed) + blocked-domains policy."""
    from app.platform import lead_harvester

    return lead_harvester.source_status()


@router.post("/harvest/enrich")
async def harvest_enrich(limit: int = 100, sync: bool = False, _user=Depends(require_admin)):
    """Email-less prospects pe enrich waterfall — DEFAULT: Celery pe enqueue.

    Pehle yeh `await enrich_missing_emails(limit)` INLINE karta tha. Har row ek
    live site fetch (2 × 10s timeout) + MX lookups + politeness sleep hai, to
    bada limit ek web worker ko ghanton block karta — CLAUDE.md §5 ka seedha
    violation ("Web process KABHI heavy job na chalaye — Celery only"). Ab ye
    `scraping` queue pe task enqueue karke task_id lautata hai.

    `sync=true` = chhota INLINE smoke-test path (limit ≤25, 60s hard deadline),
    manual-admin only — `harvest/run` ke "manual = flag-independent" precedent
    jaisa. Bulk drain hamesha queued rehta hai.
    """
    from app.platform import lead_harvester

    if sync:
        capped = max(1, min(int(limit or 10), 25))
        res = await lead_harvester.enrich_missing_emails(capped, deadline_s=60)
        return {"mode": "sync", "limit": capped, **res}

    from app.tasks.scraping import _sweep_enabled, email_enrichment_sweep

    max_rows = max(1, min(int(limit or 100), 1000))
    async_res = email_enrichment_sweep.apply_async(kwargs={"max_rows": max_rows})
    return {
        "mode": "queued",
        "task_id": async_res.id,
        "queue": "scraping",
        "max_rows": max_rows,
        # Flag OFF = task chalega par turant no-op karega. Admin ko yeh saaf
        # dikhna chahiye warna "queued" dekh ke drain ka intezaar karta rahega.
        "flag_enabled": _sweep_enabled(),
        "flag": "EMAIL_ENRICH_SWEEP",
    }


@router.get("/harvest/gtm-coverage")
async def harvest_gtm_coverage(_user=Depends(require_admin)):
    """GTM City x Niche coverage matrix status — total/covered pairs, %, leads harvested,
    top uncovered (next up). Gated GTM_TARGETING (else enabled:false)."""
    from app.platform import gtm_targeting

    return gtm_targeting.coverage_summary()


@router.post("/harvest/udyam-run")
async def harvest_udyam_run(
    city: str = "", niche: str = "general", limit: int = 20, _user=Depends(require_admin)
):
    """Run the Udyam-PRIMARY pipeline now: data.gov.in Udyam seeds -> Google-Maps +
    website enrich -> dedup -> persist. Gated UDYAM_PIPELINE (+ DATA_GOV_IN_API_KEY)."""
    from app.platform import udyam_pipeline

    return await udyam_pipeline.run(limit=max(1, min(int(limit or 20), 50)), city=city, niche=niche)


@router.post("/harvest/indiamart-run")
async def harvest_indiamart_run(
    days: int = 1, niche: str = "general", _user=Depends(require_admin)
):
    """Pull the seller's own IndiaMART buyer-leads (official Lead Manager API) + persist.
    Gated INDIAMART_CRM_KEY (seller account). Legal — NOT directory scraping."""
    from app.integrations import indiamart_leads

    return await indiamart_leads.fetch_and_persist(days=max(1, min(int(days or 1), 7)), niche=niche)


@router.get("/enrich/opencorporates")
async def enrich_opencorporates(name: str, _user=Depends(require_admin)):
    """Company-registry lookup (CIN/status/incorporation) for a business name.
    Gated OPENCORPORATES_API_TOKEN (else empty)."""
    from app.integrations import opencorporates

    return await opencorporates.enrich(name)


# Process-engine endpoints extracted to app/api/growth_process.py (2026-06-20);
# included below so /api/growth/process/* paths stay unchanged.
from app.api.growth_process import router as _process_router  # noqa: E402

router.include_router(_process_router)


# --------------------- Agentic-Output Approval Cockpit (sub-project D V1) ----- #
@router.get("/approvals/drafts")
async def approvals_drafts(include_decided: bool = False, _user=Depends(require_admin)):
    """Unified agentic-draft queue (sales/coordinator/fde) — risk-tiered cockpit.

    Bridge-first V1: surfaces the orphan agentic outputs that otherwise rot in
    data/*.jsonl. code_upgrader/process-breakpoint/self_improve keep their own
    endpoints. Read-only; inert if no drafts exist."""
    from app.platform import approvals_bridge

    return approvals_bridge.list_drafts(include_decided=include_decided)


class DraftDecideIn(BaseModel):
    decision: str  # approve | reject


@router.post("/approvals/drafts/{source}/{item_id}/decide")
async def approvals_draft_decide(
    source: str, item_id: str, body: DraftDecideIn, _user=Depends(require_admin)
):
    """Smart 1-click: stamp status + fire the BOUNDED SAFE next-action per source
    (sales=mark-reviewed · coordinator=self_improve task · fde=enable disabled drip).
    Risky real-send stays draft-only by design. Idempotent."""
    from app.platform import approvals_bridge

    result = approvals_bridge.decide(
        source, item_id, body.decision, by=getattr(_user, "email", "admin") or "admin"
    )
    # Office HQ snapshot caches build_approvals() for 18s — without invalidating
    # here, the very next Approvals-panel refresh (fired immediately after this
    # click) re-serves the stale cache and the just-decided item looks stuck,
    # i.e. "click nahi hora". Same fix already applied to every other office_hq
    # mutation (pause/resume/assign/next-action/move) — this decide path used a
    # pre-existing admin API outside office_hq's own router, so it was missed.
    try:
        from app.platform import office_hq

        await office_hq.invalidate_snapshot_cache()
    except Exception:
        pass
    return result


# ----------------------------- Self-Improve Approval Gates (Phase 6) -------- #


@router.get("/selfimprove/cost-status")
async def selfimprove_cost(current_user=Depends(require_admin)):
    """Daily cost tracking status (budget cap, spent, remaining)."""
    from app.agents import self_improve

    return self_improve.cost_status()


@router.get("/selfimprove/approvals-pending")
async def selfimprove_approvals(current_user=Depends(require_admin)):
    """List all pending approval tasks (Phase 6 gate)."""
    from app.agents import self_improve

    status = self_improve.approval_status()
    return status


class ApprovalActionIn(BaseModel):
    reason: str = ""


@router.patch("/selfimprove/approval/{task_id}/approve")
async def approve_selfimprove_task(
    task_id: str,
    body: ApprovalActionIn | None = None,
    current_user=Depends(require_admin),
):
    """Admin approves a pending self-improve task."""
    from app.agents import self_improve

    aq = self_improve._get_approval_queue()
    success = aq.approve(task_id)
    if success:
        try:
            from app.platform import team

            team.log_event(
                "admin",
                "selfimprove_approved",
                f"Task {task_id} approved by {getattr(current_user, 'email', 'admin')}",
            )
        except Exception:
            pass
        try:  # office HQ Approvals-panel cache — see decide() sibling above
            from app.platform import office_hq

            await office_hq.invalidate_snapshot_cache()
        except Exception:
            pass
        return {"status": "approved", "task_id": task_id}
    return {"status": "error", "detail": f"task {task_id} not found"}


@router.patch("/selfimprove/approval/{task_id}/reject")
async def reject_selfimprove_task(
    task_id: str,
    body: ApprovalActionIn,
    current_user=Depends(require_admin),
):
    """Admin rejects a pending self-improve task."""
    from app.agents import self_improve

    aq = self_improve._get_approval_queue()
    success = aq.reject(task_id, reason=body.reason or "")
    if success:
        try:
            from app.platform import team

            team.log_event(
                "admin",
                "selfimprove_rejected",
                f"Task {task_id} rejected: {body.reason or 'no reason'} by {getattr(current_user, 'email', 'admin')}",
            )
        except Exception:
            pass
        try:  # office HQ Approvals-panel cache — see decide() sibling above
            from app.platform import office_hq

            await office_hq.invalidate_snapshot_cache()
        except Exception:
            pass
        return {"status": "rejected", "task_id": task_id, "reason": body.reason}
    return {"status": "error", "detail": f"task {task_id} not found"}
