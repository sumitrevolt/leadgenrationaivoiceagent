"""
Scraping Tasks
Background tasks for lead scraping
"""

import json
import os
import time
import uuid

from celery import shared_task

from app.config import settings
from app.lead_scraper.scraper_manager import LeadScraperManager
from app.models.base import get_db_session
from app.models.campaign import Campaign, CampaignStatus
from app.models.lead import Lead, LeadSource, LeadStatus
from app.platform.celery_async import run as run_async
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@shared_task(bind=True, max_retries=3)
def scrape_leads_task(self, niche: str, cities: list, max_leads: int = 100):
    """
    Background task to scrape leads
    """
    try:
        logger.info(f"Starting scrape task: {niche}, cities={cities}, max={max_leads}")

        scraper = LeadScraperManager()

        # Run async scraping in sync context
        leads = run_async(scraper.scrape_leads(niche, cities, max_leads))

        logger.info(f"Scrape completed: {len(leads)} leads found")

        return {"status": "completed", "leads_found": len(leads), "niche": niche}

    except Exception as e:
        logger.error(f"Scrape task failed: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


@shared_task
def scheduled_scrape():
    """
    Scheduled daily scraping for active campaigns
    """
    logger.info("Running scheduled scraping")

    campaigns_processed = 0

    try:
        with get_db_session() as db:
            # Get active campaigns that need lead scraping
            active_campaigns = (
                db.query(Campaign)
                .filter(
                    Campaign.status == CampaignStatus.RUNNING,
                    Campaign.leads_scraped < Campaign.target_lead_count,
                )
                .all()
            )

            for campaign in active_campaigns:
                # Calculate how many leads we still need
                leads_needed = campaign.target_lead_count - campaign.leads_scraped
                if leads_needed <= 0:
                    continue

                # Parse target cities
                try:
                    target_cities = (
                        json.loads(campaign.target_cities) if campaign.target_cities else []
                    )
                except json.JSONDecodeError:
                    target_cities = (
                        campaign.target_cities.split(",") if campaign.target_cities else []
                    )

                if not target_cities:
                    target_cities = settings.platform_target_cities

                # Limit to 100 leads per scrape run
                max_leads = min(leads_needed, 100)

                # Queue scraping task for this campaign
                scrape_for_campaign.delay(
                    campaign_id=campaign.id,
                    niche=campaign.niche,
                    cities=target_cities,
                    max_leads=max_leads,
                )

                campaigns_processed += 1
                logger.info(
                    f"Queued scraping for campaign {campaign.name}: {max_leads} leads needed"
                )

    except Exception as e:
        logger.error(f"Scheduled scrape error: {e}")
        return {"status": "failed", "error": str(e)}

    return {"status": "completed", "campaigns_processed": campaigns_processed}


@shared_task(bind=True, max_retries=2)
def scrape_for_campaign(self, campaign_id: str, niche: str, cities: list, max_leads: int = 100):
    """
    Scrape leads for a specific campaign and save to database
    """
    logger.info(f"Scraping for campaign {campaign_id}: {niche}, max={max_leads}")

    leads_saved = 0

    try:
        scraper = LeadScraperManager()

        # Run async scraping
        scraped_leads = run_async(scraper.scrape_leads(niche, cities, max_leads))

        # Save leads to database
        with get_db_session() as db:
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                return {"status": "failed", "error": "Campaign not found"}

            for lead_data in scraped_leads:
                # Check for duplicate by phone (format-variant-aware — audit
                # 2026-07-04: exact-string match missed cross-source duplicates
                # where one path stores "+91..." and another "91...").
                from app.models.lead import lead_exists_for_phone

                if lead_exists_for_phone(db, lead_data.get("phone")):
                    continue

                # Create new lead
                import uuid

                new_lead = Lead(
                    id=str(uuid.uuid4()),
                    company_name=lead_data.get("name", lead_data.get("company_name", "Unknown")),
                    contact_name=lead_data.get("contact_name", ""),
                    phone=lead_data.get("phone"),
                    email=lead_data.get("email"),
                    address=lead_data.get("address"),
                    city=lead_data.get("city"),
                    category=lead_data.get("category"),
                    niche=niche,
                    source=LeadSource.GOOGLE_MAPS,  # Default source
                    status=LeadStatus.NEW,
                    campaign_id=campaign_id,
                    assigned_to=campaign.client_id,
                    website=lead_data.get("website"),
                    tags=json.dumps(lead_data.get("tags", [])) if lead_data.get("tags") else None,
                )

                db.add(new_lead)
                leads_saved += 1

            # Update campaign stats
            campaign.leads_scraped = (campaign.leads_scraped or 0) + leads_saved

            db.commit()

        logger.info(f"Saved {leads_saved} leads for campaign {campaign_id}")

        return {
            "status": "completed",
            "campaign_id": campaign_id,
            "leads_scraped": len(scraped_leads),
            "leads_saved": leads_saved,
        }

    except Exception as e:
        logger.error(f"Campaign scraping failed: {e}")
        raise self.retry(exc=e, countdown=600)


@shared_task
def verify_phone_numbers(lead_ids: list[str] = None, limit: int = 100):
    """
    Verify phone numbers for leads
    """
    logger.info("Verifying phone numbers")

    verified_count = 0
    invalid_count = 0

    try:
        import phonenumbers

        with get_db_session() as db:
            # `not Lead.phone_verified` is a Python bool op on a column (raises
            # TypeError at query build). Use .is_(False) for "not yet verified".
            query = db.query(Lead).filter(Lead.phone_verified.is_(False))

            if lead_ids:
                query = query.filter(Lead.id.in_(lead_ids))

            leads = query.limit(limit).all()

            for lead in leads:
                try:
                    # Parse and validate phone number
                    parsed = phonenumbers.parse(lead.phone, "IN")

                    if phonenumbers.is_valid_number(parsed):
                        # Format to E.164
                        lead.phone = phonenumbers.format_number(
                            parsed, phonenumbers.PhoneNumberFormat.E164
                        )
                        lead.phone_verified = True
                        verified_count += 1
                    else:
                        lead.status = LeadStatus.WRONG_NUMBER
                        invalid_count += 1

                except Exception as e:
                    logger.debug(f"Invalid phone for lead {lead.id}: {e}")
                    invalid_count += 1

            db.commit()

    except ImportError:
        logger.warning("phonenumbers library not installed")
        return {"status": "failed", "error": "phonenumbers not installed"}
    except Exception as e:
        logger.error(f"Phone verification error: {e}")
        return {"status": "failed", "error": str(e)}

    return {"status": "completed", "verified": verified_count, "invalid": invalid_count}


@shared_task
def enrich_lead_data(lead_ids: list[str] = None, limit: int = 50):
    """
    Enrich leads (no email, has website) by scraping a contact email off their site.

    All website fetches run concurrently via ``httpx.AsyncClient`` + ``asyncio.gather``
    with a strict 3-second per-request timeout, so one slow site never blocks the
    Celery worker thread (the old code fetched sequentially with a 10s timeout each).
    """
    logger.info("Enriching lead data")

    enriched_count = 0

    try:
        import asyncio
        import re

        import httpx

        email_re = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

        with get_db_session() as db:
            # NOTE: use .is_(None)/.isnot(None) — `Lead.email is None` is a Python
            # identity check that SQLAlchemy turns into a constant-False filter.
            query = db.query(Lead).filter(Lead.email.is_(None), Lead.website.isnot(None))

            if lead_ids:
                query = query.filter(Lead.id.in_(lead_ids))

            leads = query.limit(limit).all()
            targets = [(lead, lead.website) for lead in leads if lead.website]

            if not targets:
                return {"status": "completed", "enriched_count": 0}

            async def _fetch_all() -> list:
                # One shared client; timeout=3.0 applies strictly per request.
                async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:

                    async def _one(url: str):
                        try:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                found = email_re.findall(resp.text)
                                return found[0] if found else None
                        except Exception as e:  # timeout / DNS / TLS — skip this lead
                            logger.debug(f"enrich fetch failed for {url}: {e}")
                        return None

                    return await asyncio.gather(*[_one(u) for _, u in targets])

            results = run_async(_fetch_all())

            for (lead, _url), email in zip(targets, results, strict=False):
                if email:
                    lead.email = email
                    lead.email_verified = False
                    enriched_count += 1

            db.commit()

    except Exception as e:
        logger.error(f"Lead enrichment error: {e}")
        return {"status": "failed", "error": str(e)}

    return {"status": "completed", "enriched_count": enriched_count}


# ---------------------------------------------------------------------------
# PROSPECT email-enrichment sweep (data/prospects.jsonl store — NOT the `leads`
# table that enrich_lead_data above walks; the outreach sender reads the JSONL).
#
# WHY A TASK: POST /api/growth/harvest/enrich used to `await
# enrich_missing_emails(limit)` inline in the HTTP request. Each row does a live
# site fetch (2 x 10s httpx timeout) + MX lookups + a politeness sleep, so a
# meaningful batch pins a web worker for many minutes — exactly what CLAUDE.md
# §5 forbids ("Web process KABHI heavy job na chalaye — Celery only"). The only
# other caller was run_harvest's limit=6, i.e. ~12-18 rows/day against a
# 4,216-row enrichable backlog.
#
# Lands on the `scraping` queue via app/worker.py's static `app.tasks.scraping.*`
# route, which leadgen_worker already consumes (-Q celery,calling,scraping,...).
# No new queue, no new worker, no compose change.
# ---------------------------------------------------------------------------

# Rows per set_prospect_fields_bulk() write. That call rewrites the ENTIRE ~20MB
# JSONL, so per-row writes are out; but a single giant write is equally wrong —
# a hard kill mid-run would discard every attempt marker and re-create the stall
# this whole change exists to fix. 25 caps the loss to one batch.
_SWEEP_BATCH_DEFAULT = 25
# Rows per task run. 100 x ~4s observed-typical = ~7min, matching the deadline.
_SWEEP_MAX_ROWS_DEFAULT = 100
# Wall-clock budget handed to enrich_missing_emails. Deliberately below
# soft_time_limit so OUR deadline fires first and flushes progress, instead of
# Celery's SoftTimeLimitExceeded killing an unflushed batch.
_SWEEP_DEADLINE_S_DEFAULT = 420
_SWEEP_SOFT_TIME_LIMIT = 480
_SWEEP_TIME_LIMIT = 540
# Lease TTL must EXCEED time_limit, else a slow-but-alive run loses its lease and
# a second worker starts rewriting the same file concurrently (lost update).
_SWEEP_LEASE_TTL_S = 900
_SWEEP_LEASE_KEY = "harvest:email_enrich_sweep:lease"


def _sweep_enabled() -> bool:
    """EMAIL_ENRICH_SWEEP — INERT by default (AUTOMATION_FLAGS registry)."""
    return os.environ.get("EMAIL_ENRICH_SWEEP", "0").strip().lower() in ("1", "true", "yes")


def _sweep_arg(override: int, env_name: str, default: int, lo: int, hi: int) -> int:
    """Resolve a bound: explicit caller arg (0/negative = unset) > env > default.
    Both paths are clamped to [lo, hi] so an admin-supplied value can never widen
    the sweep past what the worker's time/memory limits can absorb."""
    try:
        raw = override if override > 0 else int(os.environ.get(env_name, "") or default)
        return max(lo, min(hi, raw))
    except Exception:
        return default


def _sweep_redis():
    try:
        import redis as _redis

        return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
    except Exception:
        return None


def _release_sweep_lease(token: str) -> None:
    if not token:
        return
    r = _sweep_redis()
    if r is None:
        return
    try:
        cur = r.get(_SWEEP_LEASE_KEY)
        if isinstance(cur, bytes):
            cur = cur.decode("utf-8", "ignore")
        if str(cur or "") == token:
            r.delete(_SWEEP_LEASE_KEY)
    except Exception:
        pass


@shared_task(
    bind=True,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=_SWEEP_SOFT_TIME_LIMIT,
    time_limit=_SWEEP_TIME_LIMIT,
)
def email_enrichment_sweep(self, max_rows: int = 0, batch: int = 0, deadline_s: int = 0):
    """Drain the prospect email-enrichment backlog in bounded, checkpointed batches.

    Single-flight via a Redis lease with owner-token compare-and-delete (mirrors
    app/tasks/kb_niche_refresh.py). Fail-CLOSED when Redis is unreachable: with no
    dedupe guarantee, two concurrent runs would each _read_all() then rewrite the
    whole JSONL and one would silently clobber the other's attempt markers.

    Idempotent by construction — enrich_missing_emails stamps
    email_enrich_attempts per row and skips rows at EMAIL_ENRICH_MAX_ATTEMPTS, so
    a re-run resumes rather than repeating. Failures raise (bounded retry, then
    the worker's task_failure signal records to dlq:failed_tasks).
    """
    if not _sweep_enabled():
        return {"status": "skipped", "reason": "flag_off", "flag": "EMAIL_ENRICH_SWEEP"}

    rows_cap = _sweep_arg(max_rows, "EMAIL_ENRICH_SWEEP_MAX_ROWS", _SWEEP_MAX_ROWS_DEFAULT, 1, 1000)
    batch_size = _sweep_arg(batch, "EMAIL_ENRICH_SWEEP_BATCH", _SWEEP_BATCH_DEFAULT, 1, 100)
    budget = _sweep_arg(
        deadline_s,
        "EMAIL_ENRICH_SWEEP_DEADLINE_S",
        _SWEEP_DEADLINE_S_DEFAULT,
        30,
        _SWEEP_SOFT_TIME_LIMIT - 30,
    )

    r = _sweep_redis()
    if r is None:
        logger.warning("[enrich-sweep] no redis — refusing to run without a dedupe lease")
        return {"status": "skipped", "reason": "no_redis"}
    token = uuid.uuid4().hex
    try:
        acquired = r.set(_SWEEP_LEASE_KEY, token, nx=True, ex=_SWEEP_LEASE_TTL_S)
    except Exception as e:
        logger.warning("[enrich-sweep] lease error error_class=%s", type(e).__name__)
        return {"status": "skipped", "reason": "lease_error"}
    if not acquired:
        return {"status": "skipped", "reason": "already_running"}

    from celery.exceptions import SoftTimeLimitExceeded

    from app.platform import lead_harvester

    t0 = time.monotonic()
    tried = found = exhausted = batches = 0
    stopped = "rows_cap"
    try:
        while tried < rows_cap:
            remaining_time = budget - (time.monotonic() - t0)
            if remaining_time <= 1:
                stopped = "deadline"
                break
            # One bulk write per batch; enrich_missing_emails flushes its own
            # attempt markers before returning, so progress survives the loop exit.
            asked = min(batch_size, rows_cap - tried)
            res = run_async(
                lead_harvester.enrich_missing_emails(limit=asked, deadline_s=remaining_time)
            )
            batches += 1
            got = int(res.get("tried") or 0)
            tried += got
            found += int(res.get("found") or 0)
            # Each batch re-scans from the head, so this is a snapshot of rows
            # already at max attempts — take the high-water mark, not a sum.
            exhausted = max(exhausted, int(res.get("skipped_exhausted") or 0))
            if res.get("error"):
                stopped = "error"
                logger.warning("[enrich-sweep] batch error: %s", str(res.get("error"))[:120])
                break
            if res.get("deadline_hit"):
                stopped = "deadline"
                break
            if got < asked:
                # Short batch without a deadline hit = the scan reached EOF, so
                # nothing enrichable is left this pass. Breaking here avoids one
                # wasted full 20MB _read_all() just to confirm it.
                stopped = "backlog_empty"
                break
    except SoftTimeLimitExceeded:
        # Our own deadline should always fire first; if it didn't, exit cleanly
        # (completed batches are already written) rather than dying unflushed.
        stopped = "soft_time_limit"
        logger.warning("[enrich-sweep] soft time limit hit after %s rows", tried)
    finally:
        _release_sweep_lease(token)

    out = {
        "status": "completed",
        "tried": tried,
        "found": found,
        "skipped_exhausted": exhausted,
        "batches": batches,
        "stopped": stopped,
        "duration_s": round(time.monotonic() - t0, 1),
    }
    logger.info("[enrich-sweep] %s", out)
    try:
        lead_harvester._append_run(
            {"ts": lead_harvester._now(), "job": "email_enrich_sweep", **out}
        )
    except Exception:
        pass
    return out
