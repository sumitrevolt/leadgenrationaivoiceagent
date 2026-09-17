"""Celery Tasks for Revenue Tracking.

Background tasks for revenue operations:
- Daily revenue summary
- Invoice processing
- Metric aggregation
- Financial reporting
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.worker import celery_app


_IST = timezone(__import__('datetime').timedelta(hours=5, minutes=30))


@celery_app.task(bind=True, max_retries=3, name="app.tasks.revenue.daily_revenue_summary")
def daily_revenue_summary(self) -> dict[str, Any]:
    """Generate daily revenue summary."""
    try:
        from app.revenue.dashboard import get_dashboard
        
        dashboard = get_dashboard()
        summary = dashboard.get_revenue_summary()
        
        # Record daily summary metric
        dashboard.record_metric(
            metric_name="daily_revenue_summary",
            value=summary["today_revenue_inr"],
            currency="INR",
            period="daily",
            verified=True,
            evidence="Daily summary calculation",
            source="celery_task",
        )
        
        return {
            "success": True,
            "summary": summary,
            "generated_at": datetime.now(_IST).isoformat(),
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.revenue.process_pending_invoices")
def process_pending_invoices(self) -> dict[str, Any]:
    """Process pending invoices (check for payments)."""
    try:
        from app.revenue.dashboard import get_dashboard
        
        dashboard = get_dashboard()
        invoices = dashboard.get_invoice_list(limit=100, status="pending")
        
        processed = 0
        for invoice in invoices:
            # In real impl, check payment gateway/UPI status
            # For now, just return count
            processed += 1
        
        return {
            "pending_count": len(invoices),
            "processed": processed,
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.revenue.generate_financial_report")
def generate_financial_report(self, period: str = "monthly") -> dict[str, Any]:
    """Generate financial report for specified period."""
    try:
        from app.revenue.dashboard import get_dashboard
        
        dashboard = get_dashboard()
        metrics = dashboard.get_dashboard_metrics()
        
        return {
            "period": period,
            "metrics": metrics,
            "generated_at": datetime.now(_IST).isoformat(),
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.revenue.sync_with_gst")
def sync_with_gst(self) -> dict[str, Any]:
    """Sync revenue data with GST invoice system."""
    try:
        from app.revenue.dashboard import get_dashboard
        
        dashboard = get_dashboard()
        invoices = dashboard.get_invoice_list(limit=500)
        
        # In real impl, validate against GST system
        valid_count = len([i for i in invoices if i.get("status") == "paid"])
        
        return {
            "total_invoices": len(invoices),
            "valid_count": valid_count,
            "synced_at": datetime.now(_IST).isoformat(),
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.revenue.aggregate_metrics")
def aggregate_metrics(self) -> dict[str, Any]:
    """Aggregate revenue metrics from various sources."""
    try:
        from app.revenue.dashboard import get_dashboard
        from app.api.growth_revenue import revenue_invoices
        
        dashboard = get_dashboard()
        
        # Get invoices from billing system
        # In real impl, this would call actual billing API
        invoices = dashboard.get_invoice_list(limit=1000)
        
        # Calculate aggregates
        total_revenue = sum(i["total_inr"] for i in invoices if i["status"] == "paid")
        pending_revenue = sum(i["total_inr"] for i in invoices if i["status"] == "pending")
        
        # Record aggregate metrics
        dashboard.record_metric(
            metric_name="total_revenue_aggregated",
            value=total_revenue,
            currency="INR",
            period="all_time",
            verified=True,
            evidence=f"Aggregated from {len(invoices)} invoices",
            source="celery_task",
        )
        
        dashboard.record_metric(
            metric_name="pending_revenue",
            value=pending_revenue,
            currency="INR",
            period="all_time",
            verified=False,
            evidence="Pending payments awaiting confirmation",
            source="celery_task",
        )
        
        return {
            "total_revenue": total_revenue,
            "pending_revenue": pending_revenue,
            "invoices_processed": len(invoices),
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.revenue.cleanup_old_metrics")
def cleanup_old_metrics(self, max_age_days: int = 365) -> dict[str, Any]:
    """Cleanup old revenue metrics."""
    try:
        from app.revenue.dashboard import get_dashboard
        
        dashboard = get_dashboard()
        original_count = len(dashboard.metrics)
        
        # Keep only recent metrics
        cutoff = datetime.now(_IST).timestamp() - (max_age_days * 86400)
        dashboard.metrics = [
            m for m in dashboard.metrics
            if datetime.fromisoformat(m.timestamp).timestamp() > cutoff
        ]
        
        dashboard._save_metrics()
        
        return {
            "original_count": original_count,
            "new_count": len(dashboard.metrics),
            "removed": original_count - len(dashboard.metrics),
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)
