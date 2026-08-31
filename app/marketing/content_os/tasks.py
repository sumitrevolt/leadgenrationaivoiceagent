"""
content_os.tasks — Celery task wrappers.

Two periodic tasks:
  * content_os.daily_video_run  — every day 09:00 IST (idempotent within day)
  * content_os.scan_inbox       — every 60s (picks up rendered drops)
  * content_os.notify_owner     — every 15 min — flush pending-approval list
                                  to Telegram / ntfy so owner can act from phone.

All tasks are idempotent and never raise.
"""
from __future__ import annotations

import logging
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="content_os.daily_video_run", bind=True, max_retries=3, default_retry_delay=60)
def daily_video_run_task(self):
    try:
        from app.marketing.content_os.engine import daily_video_run
        return daily_video_run()
    except Exception as e:
        logger.exception("[content_os.daily_video_run] %s", e)
        # Don't retry forever — log and move on.
        return {"ok": False, "error": str(e)[:200]}


@celery_app.task(name="content_os.scan_inbox", bind=True, max_retries=5, default_retry_delay=10)
def scan_inbox_task(self):
    try:
        from app.marketing.content_os.inbox_watcher import scan_inbox
        return scan_inbox()
    except Exception as e:
        logger.exception("[content_os.scan_inbox] %s", e)
        return {"ok": False, "error": str(e)[:200]}


@celery_app.task(name="content_os.notify_owner", bind=True, max_retries=2, default_retry_delay=30)
def notify_owner_task(self):
    try:
        from app.marketing.content_os.inbox_watcher import list_pending
        pending = list_pending(limit=10)
        if not pending:
            return {"ok": True, "pending": 0}
        # Single ntfy push summarizing the queue; Telegram bot polls
        # /internal/media/list every minute and pushes inline keyboards
        # one-per-asset when there are <= 3 pending items.
        from app.integrations.ntfy import push
        msg = "[content_os] {} pending approvals.\n".format(len(pending)) + "\n".join(
            "• {} — {}".format(p["title"][:40], p["id"]) for p in pending[:5]
        )
        push(topic="leadgen-owner", message=msg, priority="high")
        return {"ok": True, "pending": len(pending)}
    except Exception as e:
        logger.warning("[content_os.notify_owner] %s", e)
        return {"ok": False, "error": str(e)[:200]}
