"""FastAPI Endpoints for Revenue Tracking Dashboard.

Provides REST API for:
- Revenue metrics recording
- Invoice management
- Dashboard summaries
- Financial reports
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/revenue", tags=["Revenue"])


# ============================================================================
# METRIC ENDPOINTS
# ============================================================================

class MetricRecordRequest(BaseModel):
    metric_name: str
    value: float
    currency: str = "INR"
    period: str = "daily"
    verified: bool = False
    evidence: str = ""
    source: str = ""
    tags: dict[str, str] | None = None


class MetricRecordResponse(BaseModel):
    success: bool
    metric: dict[str, Any] | None = None
    error: str | None = None


@router.post("/metrics")
async def record_metric(
    request: MetricRecordRequest,
    _user=Depends(require_admin),
) -> MetricRecordResponse:
    """Record a revenue metric."""
    from app.revenue.dashboard import record_metric

    metric = record_metric(
        metric_name=request.metric_name,
        value=request.value,
        currency=request.currency,
        period=request.period,
        verified=request.verified,
        evidence=request.evidence,
        source=request.source,
        tags=request.tags,
    )

    return MetricRecordResponse(success=True, metric=metric.to_dict())


@router.get("/metrics")
async def list_metrics(
    metric_name: str | None = None,
    limit: int = 100,
    _user=Depends(require_admin),
) -> list[dict[str, Any]]:
    """List revenue metrics."""
    from app.revenue.dashboard import get_dashboard

    dashboard = get_dashboard()

    if metric_name:
        return [m.to_dict() for m in dashboard.metrics if m.metric_name == metric_name][-limit:]

    return [m.to_dict() for m in dashboard.metrics][-limit:]


# ============================================================================
# INVOICE ENDPOINTS
# ============================================================================

class InvoiceCreateRequest(BaseModel):
    invoice_number: str
    client_id: str
    client_name: str
    plan: str
    amount_inr: float
    gst_amount: float = 0.0
    status: str = "pending"
    payment_ref: str | None = None


class InvoiceCreateResponse(BaseModel):
    success: bool
    invoice: dict[str, Any] | None = None
    error: str | None = None


class InvoiceListResponse(BaseModel):
    invoices: list[dict[str, Any]]
    total: int


@router.post("/invoices")
async def create_invoice(
    request: InvoiceCreateRequest,
    _user=Depends(require_admin),
) -> InvoiceCreateResponse:
    """Create a new invoice."""
    from app.revenue.dashboard import record_invoice

    invoice = record_invoice(
        invoice_number=request.invoice_number,
        client_id=request.client_id,
        client_name=request.client_name,
        plan=request.plan,
        amount_inr=request.amount_inr,
        gst_amount=request.gst_amount,
        status=request.status,
        payment_ref=request.payment_ref,
    )

    return InvoiceCreateResponse(success=True, invoice=invoice.to_dict())


@router.get("/invoices")
async def list_invoices(
    limit: int = 50,
    status: str | None = None,
    client_id: str | None = None,
    _user=Depends(require_admin),
) -> InvoiceListResponse:
    """List invoices with optional filters."""
    from app.revenue.dashboard import get_invoice_list

    invoices = get_invoice_list(limit, status, client_id)
    return InvoiceListResponse(invoices=invoices, total=len(invoices))


@router.post("/invoices/{invoice_number}/pay")
async def mark_invoice_paid(
    invoice_number: str,
    payment_ref: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Mark invoice as paid."""
    from app.revenue.dashboard import get_dashboard

    dashboard = get_dashboard()
    result = dashboard.update_invoice_payment(invoice_number, payment_ref)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================

class DashboardMetricsResponse(BaseModel):
    summary: dict[str, Any]
    trend_7d: list[dict[str, Any]]
    recent_metrics: list[dict[str, Any]]
    mrr_inr: float
    last_updated: str


@router.get("/dashboard")
async def get_dashboard_metrics(_user=Depends(require_admin)) -> DashboardMetricsResponse:
    """Get comprehensive revenue dashboard metrics."""
    from app.revenue.dashboard import get_dashboard_metrics

    metrics = get_dashboard_metrics()
    return DashboardMetricsResponse(**metrics)


@router.get("/dashboard/summary")
async def get_revenue_summary(_user=Depends(require_admin)) -> dict[str, Any]:
    """Get revenue summary."""
    from app.revenue.dashboard import get_revenue_summary

    return get_revenue_summary()


@router.get("/dashboard/trend")
async def get_revenue_trend(
    days: int = 30,
    _user=Depends(require_admin),
) -> list[dict[str, Any]]:
    """Get revenue trend over past N days."""
    from app.revenue.dashboard import get_dashboard

    dashboard = get_dashboard()
    return dashboard.get_revenue_trend(days)


@router.get("/dashboard/client/{client_id}")
async def get_client_revenue(
    client_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Get revenue summary for a specific client."""
    from app.revenue.dashboard import get_dashboard

    dashboard = get_dashboard()
    result = dashboard.get_client_revenue(client_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


# ============================================================================
# REPORT ENDPOINTS
# ============================================================================

@router.get("/reports/monthly")
async def get_monthly_report(
    year: int = 2026,
    month: int = 9,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Get monthly revenue report."""
    from app.revenue.dashboard import get_dashboard

    dashboard = get_dashboard()
    invoices = dashboard.get_invoice_list(limit=1000)

    # Filter by month
    from datetime import datetime
    month_invoices = [
        i for i in invoices
        if datetime.fromisoformat(i["created_at"]).year == year
        and datetime.fromisoformat(i["created_at"]).month == month
    ]

    total_revenue = sum(i["total_inr"] for i in month_invoices if i["status"] == "paid")
    pending_revenue = sum(i["total_inr"] for i in month_invoices if i["status"] == "pending")

    return {
        "year": year,
        "month": month,
        "total_invoices": len(month_invoices),
        "paid_invoices": len([i for i in month_invoices if i["status"] == "paid"]),
        "pending_invoices": len([i for i in month_invoices if i["status"] == "pending"]),
        "total_revenue_inr": total_revenue,
        "pending_revenue_inr": pending_revenue,
    }


@router.get("/reports/fy")
async def get_fy_report(
    fy: str = "2026-27",
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Get fiscal year revenue report."""
    from app.revenue.dashboard import get_dashboard

    dashboard = get_dashboard()
    summary = dashboard.get_revenue_summary()

    return {
        "fy": fy,
        "summary": summary,
    }
