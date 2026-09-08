"""
Reporting Tasks
Background tasks for report generation
"""

import asyncio
import csv
import json
import os
from datetime import datetime, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import Integer, func

from app.config import settings
from app.integrations.email_sender import EmailSender
from app.integrations.whatsapp import get_whatsapp_sender
from app.models.base import get_db_session
from app.models.call_log import CallLog, CallOutcome
from app.models.campaign import Campaign
from app.models.client import Client, ClientStatus
from app.models.lead import Lead
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _get_daily_stats(db, date: datetime.date) -> dict[str, Any]:
    """Get daily statistics from database"""
    start_of_day = datetime.combine(date, datetime.min.time())
    end_of_day = datetime.combine(date, datetime.max.time())

    # Call statistics
    total_calls = (
        db.query(func.count(CallLog.id))
        .filter(CallLog.initiated_at.between(start_of_day, end_of_day))
        .scalar()
        or 0
    )

    connected_calls = (
        db.query(func.count(CallLog.id))
        .filter(
            CallLog.initiated_at.between(start_of_day, end_of_day),
            CallLog.outcome.notin_([CallOutcome.NO_ANSWER, CallOutcome.FAILED, CallOutcome.BUSY]),
        )
        .scalar()
        or 0
    )

    appointments = (
        db.query(func.count(CallLog.id))
        .filter(
            CallLog.initiated_at.between(start_of_day, end_of_day),
            CallLog.outcome == CallOutcome.APPOINTMENT,
        )
        .scalar()
        or 0
    )

    hot_leads = (
        db.query(func.count(CallLog.id))
        .filter(CallLog.initiated_at.between(start_of_day, end_of_day), CallLog.is_hot_lead)
        .scalar()
        or 0
    )

    # Lead statistics
    leads_scraped = (
        db.query(func.count(Lead.id))
        .filter(Lead.created_at.between(start_of_day, end_of_day))
        .scalar()
        or 0
    )

    # Calculate conversion rate
    connection_rate = (connected_calls / total_calls * 100) if total_calls > 0 else 0
    appointment_rate = (appointments / connected_calls * 100) if connected_calls > 0 else 0

    return {
        "date": date.isoformat(),
        "total_calls": total_calls,
        "connected_calls": connected_calls,
        "appointments_booked": appointments,
        "hot_leads": hot_leads,
        "leads_scraped": leads_scraped,
        "connection_rate": round(connection_rate, 2),
        "appointment_rate": round(appointment_rate, 2),
    }


def _get_notification_recipients(db) -> dict[str, list[str]]:
    """Get notification recipients from active clients"""
    recipients = {"whatsapp": [], "email": []}

    # Get active clients (status is an Enum column → compare to the member, not the
    # lowercase string; native PG enum stores the member name, so "active" matched 0 rows
    # / raised InvalidTextRepresentation. Contact fields are contact_phone/contact_email.)
    active_clients = db.query(Client).filter(Client.status == ClientStatus.ACTIVE).all()

    for client in active_clients:
        if client.contact_phone:
            recipients["whatsapp"].append(client.contact_phone)
        if client.contact_email:
            recipients["email"].append(client.contact_email)

    # Add platform admin contacts
    if settings.smtp_user:
        recipients["email"].append(settings.smtp_user)

    return recipients


@shared_task
def generate_daily_report():
    """
    Generate and send daily report.

    # idempotency: read-only DB aggregation (no mutations); duplicate runs produce
    # the same report for the same date — safe to re-run. Notification dedup is
    # at recipient level (email/WA already-sent check in EmailSender/WhatsApp).
    """
    logger.info("Generating daily report")

    today = datetime.now().date()

    try:
        with get_db_session() as db:
            # Get daily stats from database
            report_data = _get_daily_stats(db, today)

            # Get notification recipients
            recipients = _get_notification_recipients(db)

            # Format report message
            report_message = f"""📊 Daily Report - {report_data["date"]}

📞 Calls: {report_data["total_calls"]}
✅ Connected: {report_data["connected_calls"]} ({report_data["connection_rate"]}%)
📅 Appointments: {report_data["appointments_booked"]} ({report_data["appointment_rate"]}%)
🔥 Hot Leads: {report_data["hot_leads"]}
🔍 New Leads: {report_data["leads_scraped"]}

Keep crushing it! 🚀"""

            # Send WhatsApp reports
            if recipients["whatsapp"]:
                whatsapp = get_whatsapp_sender()  # dual-engine: self-host or Cloud API
                for number in recipients["whatsapp"]:
                    try:
                        whatsapp.send_message(number, report_message)
                    except Exception as e:
                        logger.warning(f"Failed to send WhatsApp to {number}: {e}")

            # Send email reports
            if recipients["email"]:
                email_sender = EmailSender()
                for email in recipients["email"]:
                    try:
                        email_sender.send_email(
                            to=email,
                            subject=f"Daily Report - {report_data['date']}",
                            body=report_message,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send email to {email}: {e}")

    except Exception as e:
        logger.error(f"Error generating daily report: {e}")
        return {"status": "failed", "error": str(e)}

    return {"status": "completed", "report_date": report_data["date"], "stats": report_data}


@shared_task
def generate_weekly_report():
    """
    Generate and send weekly report.

    # idempotency: read-only DB aggregation — no side-effecting mutations;
    # duplicate runs produce identical stats for the same week window, safe to retry.
    """
    logger.info("Generating weekly report")

    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())

    try:
        with get_db_session() as db:
            start_datetime = datetime.combine(week_start, datetime.min.time())
            end_datetime = datetime.combine(today, datetime.max.time())

            # Aggregate weekly statistics
            total_calls = (
                db.query(func.count(CallLog.id))
                .filter(CallLog.initiated_at.between(start_datetime, end_datetime))
                .scalar()
                or 0
            )

            connected_calls = (
                db.query(func.count(CallLog.id))
                .filter(
                    CallLog.initiated_at.between(start_datetime, end_datetime),
                    CallLog.outcome.notin_(
                        [CallOutcome.NO_ANSWER, CallOutcome.FAILED, CallOutcome.BUSY]
                    ),
                )
                .scalar()
                or 0
            )

            appointments = (
                db.query(func.count(CallLog.id))
                .filter(
                    CallLog.initiated_at.between(start_datetime, end_datetime),
                    CallLog.outcome == CallOutcome.APPOINTMENT,
                )
                .scalar()
                or 0
            )

            # Get top campaigns
            top_campaigns = (
                db.query(
                    Campaign.name,
                    func.count(CallLog.id).label("call_count"),
                    func.sum(func.cast(CallLog.appointment_scheduled, Integer)).label(
                        "appointments"
                    ),
                )
                .join(CallLog, Campaign.id == CallLog.campaign_id)
                .filter(CallLog.initiated_at.between(start_datetime, end_datetime))
                .group_by(Campaign.id)
                .order_by(func.count(CallLog.id).desc())
                .limit(5)
                .all()
            )

            conversion_rate = (appointments / total_calls * 100) if total_calls > 0 else 0

            report_data = {
                "week_start": week_start.isoformat(),
                "week_end": today.isoformat(),
                "total_calls": total_calls,
                "connected_calls": connected_calls,
                "appointments": appointments,
                "conversion_rate": round(conversion_rate, 2),
                "top_campaigns": [
                    {"name": c[0], "calls": c[1], "appointments": c[2] or 0} for c in top_campaigns
                ],
            }

    except Exception as e:
        logger.error(f"Error generating weekly report: {e}")
        return {"status": "failed", "error": str(e)}

    return {"status": "completed", "week": f"{week_start} to {today}", "stats": report_data}


@shared_task
def generate_monthly_report(year: int = None, month: int = None):
    """
    Generate monthly report.

    # idempotency: read-only DB aggregation keyed on (year, month) — no mutations;
    # duplicate runs for the same month produce identical output, safe to retry.
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    logger.info(f"Generating monthly report for {year}-{month}")

    try:
        with get_db_session() as db:
            # Calculate month boundaries
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

            # Monthly aggregates
            total_calls = (
                db.query(func.count(CallLog.id))
                .filter(CallLog.initiated_at.between(start_date, end_date))
                .scalar()
                or 0
            )

            appointments = (
                db.query(func.count(CallLog.id))
                .filter(
                    CallLog.initiated_at.between(start_date, end_date),
                    CallLog.outcome == CallOutcome.APPOINTMENT,
                )
                .scalar()
                or 0
            )

            leads_generated = (
                db.query(func.count(Lead.id))
                .filter(Lead.created_at.between(start_date, end_date))
                .scalar()
                or 0
            )

            # Cost calculations
            total_cost = (
                db.query(func.sum(CallLog.call_cost))
                .filter(CallLog.initiated_at.between(start_date, end_date))
                .scalar()
                or 0
            )

            cost_per_call = (total_cost / total_calls) if total_calls > 0 else 0
            cost_per_appointment = (total_cost / appointments) if appointments > 0 else 0

            report_data = {
                "year": year,
                "month": month,
                "total_calls": total_calls,
                "appointments": appointments,
                "leads_generated": leads_generated,
                "total_cost_paise": total_cost,
                "total_cost_inr": total_cost / 100,
                "cost_per_call_paise": round(cost_per_call, 2),
                "cost_per_appointment_paise": round(cost_per_appointment, 2),
            }

    except Exception as e:
        logger.error(f"Error generating monthly report: {e}")
        return {"status": "failed", "error": str(e)}

    return {"status": "completed", "month": f"{year}-{month:02d}", "stats": report_data}


@shared_task
def clean_old_logs(days: int = 30):
    """
    Clean log files older than specified days.

    # idempotency: already-deleted folders are skipped (os.path.exists guard);
    # duplicate runs are safe — absent files produce no error, cutoff window is stable.
    """
    logger.info(f"Cleaning logs older than {days} days")

    log_dir = "logs/calls"
    cutoff = datetime.now() - timedelta(days=days)
    deleted_count = 0

    if os.path.exists(log_dir):
        for date_folder in os.listdir(log_dir):
            folder_path = os.path.join(log_dir, date_folder)

            if os.path.isdir(folder_path):
                try:
                    folder_date = datetime.strptime(date_folder, "%Y-%m-%d")
                    if folder_date < cutoff:
                        # Delete old folder
                        for file in os.listdir(folder_path):
                            os.remove(os.path.join(folder_path, file))
                            deleted_count += 1
                        os.rmdir(folder_path)
                        logger.info(f"Deleted log folder: {date_folder}")
                except ValueError:
                    pass  # Skip folders that don't match date pattern

    return {"status": "completed", "deleted_files": deleted_count}


@shared_task
def export_campaign_report(campaign_id: str, format: str = "csv"):
    """
    Export campaign data to file.

    # idempotency: read-only query on campaign_id; output file uses timestamp suffix
    # to avoid collision. Duplicate task runs produce separate timestamped files
    # (idempotent from a data-mutation standpoint — no DB writes).
    """
    logger.info(f"Exporting campaign {campaign_id} to {format}")

    try:
        with get_db_session() as db:
            # Get campaign details
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                return {"status": "failed", "error": "Campaign not found"}

            # Get all leads and calls for this campaign
            leads = db.query(Lead).filter(Lead.campaign_id == campaign_id).all()
            calls = db.query(CallLog).filter(CallLog.campaign_id == campaign_id).all()

            # Prepare export data
            export_data = {
                "campaign": {
                    "id": campaign.id,
                    "name": campaign.name,
                    "status": campaign.status.value if campaign.status else None,
                    "niche": campaign.niche,
                    "leads_scraped": campaign.leads_scraped,
                    "leads_called": campaign.leads_called,
                    "appointments_booked": campaign.appointments_booked,
                },
                "leads": [
                    {
                        "id": lead.id,
                        "company_name": lead.company_name,
                        "contact_name": lead.contact_name,
                        "phone": lead.phone,
                        "email": lead.email,
                        "city": lead.city,
                        "status": lead.status.value if lead.status else None,
                        "lead_score": lead.lead_score,
                        "call_attempts": lead.call_attempts,
                    }
                    for lead in leads
                ],
                "calls": [
                    {
                        "id": call.id,
                        "lead_id": call.lead_id,
                        "outcome": call.outcome.value if call.outcome else None,
                        "duration_seconds": call.duration_seconds,
                        "initiated_at": (
                            call.initiated_at.isoformat() if call.initiated_at else None
                        ),
                        "appointment_scheduled": call.appointment_scheduled,
                    }
                    for call in calls
                ],
            }

            # Generate file based on format
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = "data/exports"
            os.makedirs(export_dir, exist_ok=True)

            if format == "csv":
                # Export leads to CSV
                filename = f"{export_dir}/campaign_{campaign_id}_{timestamp}.csv"
                with open(filename, "w", newline="", encoding="utf-8") as f:
                    if export_data["leads"]:
                        writer = csv.DictWriter(f, fieldnames=export_data["leads"][0].keys())
                        writer.writeheader()
                        writer.writerows(export_data["leads"])
            else:
                # Export as JSON
                filename = f"{export_dir}/campaign_{campaign_id}_{timestamp}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, default=str)

            return {
                "status": "completed",
                "campaign_id": campaign_id,
                "format": format,
                "filename": filename,
                "leads_count": len(leads),
                "calls_count": len(calls),
            }

    except Exception as e:
        logger.error(f"Error exporting campaign report: {e}")
        return {"status": "failed", "error": str(e)}


# =============================================================================
# Social auto-poster (Track 3) — publish content_schedule 'ready' items via Meta
# =============================================================================
async def run_social_autopost(limit: int = 20) -> dict[str, Any]:
    """Publish scheduled 'ready' posts to clients' connected Meta (FB Page / Instagram).

    For each ``content_schedule`` item with status='ready' (up to ``limit``): resolve the
    client's Meta connection and publish via the Graph API. Real publishing only when
    ``SOCIAL_AUTOPOST=1`` AND a token exists — otherwise the publisher returns a MOCK
    result and the item STAYS 'ready' (a later real run can still post it). On a real post
    the item is marked 'posted' (idempotent — never re-posted). NEVER raises.

    Returns a counters dict: ``{"ready", "posted", "mock", "failed"}``.
    """
    res = {"ready": 0, "posted": 0, "mock": 0, "failed": 0}
    try:
        from app.integrations import meta_graph
        from app.marketing import content_schedule

        ready = content_schedule.list_scheduled(status="ready", limit=max(1, limit))
        res["ready"] = len(ready)
        for item in ready:
            try:
                # Graph calls are blocking httpx -> run off the event loop.
                out = await asyncio.to_thread(meta_graph.publish_post, item)
            except Exception as e:
                logger.info("autopost item err: %s", e)
                res["failed"] += 1
                continue
            status = (out or {}).get("status")
            if status == "posted":
                res["posted"] += 1
                try:
                    content_schedule.mark(item.get("id", ""), "posted")
                except Exception:
                    pass
            elif status == "mock":
                res["mock"] += 1
            else:
                res["failed"] += 1
        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "social_autopost",
                f"{res['posted']} posted, {res['mock']} mock (of {res['ready']} ready)",
            )
        except Exception:
            pass
    except Exception as e:
        logger.info("run_social_autopost err: %s", e)
    return res


@shared_task
def social_autopost_task(limit: int = 20):
    """Celery entrypoint for the social auto-poster (wraps the async core).

    # idempotency: run_social_autopost marks posted items 'posted' before returning;
    # duplicate runs skip already-posted items (status != 'ready') — safe to retry.
    """
    from app.platform.celery_async import run as run_async

    return run_async(run_social_autopost(limit))
