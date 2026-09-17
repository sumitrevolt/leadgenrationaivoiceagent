"""Revenue Tracking Dashboard with Real-Time Metrics.

Provides real-time revenue metrics, KPI tracking, and dashboard data
for the LeadGen AI platform.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


_IST = timezone(timedelta(hours=5, minutes=30))


class RevenueMetric(BaseModel):
    """Revenue metric for tracking."""
    metric_name: str
    value: float
    currency: str = "INR"
    period: str = "daily"  # hourly, daily, weekly, monthly
    verified: bool = False
    evidence: str = ""
    source: str = ""
    tags: dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(_IST).isoformat())
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "currency": self.currency,
            "period": self.period,
            "verified": self.verified,
            "evidence": self.evidence,
            "source": self.source,
            "tags": self.tags,
            "timestamp": self.timestamp,
        }


class InvoiceRecord(BaseModel):
    """Invoice record for revenue tracking."""
    invoice_number: str
    client_id: str
    client_name: str
    plan: str
    amount_inr: float
    gst_amount: float
    total_inr: float
    status: str  # paid, pending, voided
    payment_ref: Optional[str] = None
    payment_date: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(_IST).isoformat())
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "invoice_number": self.invoice_number,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "plan": self.plan,
            "amount_inr": self.amount_inr,
            "gst_amount": self.gst_amount,
            "total_inr": self.total_inr,
            "status": self.status,
            "payment_ref": self.payment_ref,
            "payment_date": self.payment_date,
            "created_at": self.created_at,
        }


class RevenueDashboard:
    """Revenue tracking dashboard with real-time metrics."""
    
    def __init__(
        self,
        metrics_path: str = "data/revenue_metrics.jsonl",
        invoices_path: str = "data/invoices.jsonl",
    ):
        self.metrics_path = metrics_path
        self.invoices_path = invoices_path
        self.metrics: list[RevenueMetric] = []
        self.invoices: list[InvoiceRecord] = []
        self._load_data()
    
    def _load_data(self):
        """Load metrics and invoices from disk."""
        # Load metrics
        if os.path.exists(self.metrics_path):
            try:
                with open(self.metrics_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                self.metrics.append(RevenueMetric(**data))
                            except Exception:
                                pass
            except Exception as e:
                print(f"[revenue_dashboard] Failed to load metrics: {e}")
        
        # Load invoices
        if os.path.exists(self.invoices_path):
            try:
                with open(self.invoices_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                self.invoices.append(InvoiceRecord(**data))
                            except Exception:
                                pass
            except Exception as e:
                print(f"[revenue_dashboard] Failed to load invoices: {e}")
    
    def _save_metrics(self):
        """Save metrics to disk (append-only)."""
        try:
            os.makedirs(os.path.dirname(self.metrics_path), exist_ok=True)
            with open(self.metrics_path, "a") as f:
                for metric in self.metrics[-100:]:  # Save last 100
                    f.write(json.dumps(metric.to_dict()) + "\n")
        except Exception as e:
            print(f"[revenue_dashboard] Failed to save metrics: {e}")
    
    def _save_invoices(self):
        """Save invoices to disk."""
        try:
            os.makedirs(os.path.dirname(self.invoices_path), exist_ok=True)
            with open(self.invoices_path, "w") as f:
                for invoice in self.invoices:
                    f.write(json.dumps(invoice.to_dict()) + "\n")
        except Exception as e:
            print(f"[revenue_dashboard] Failed to save invoices: {e}")
    
    def record_metric(
        self,
        metric_name: str,
        value: float,
        currency: str = "INR",
        period: str = "daily",
        verified: bool = False,
        evidence: str = "",
        source: str = "",
        tags: Optional[dict[str, str]] = None,
    ) -> RevenueMetric:
        """Record a revenue metric."""
        metric = RevenueMetric(
            metric_name=metric_name,
            value=value,
            currency=currency,
            period=period,
            verified=verified,
            evidence=evidence,
            source=source,
            tags=tags or {},
        )
        self.metrics.append(metric)
        self._save_metrics()
        return metric
    
    def record_invoice(
        self,
        invoice_number: str,
        client_id: str,
        client_name: str,
        plan: str,
        amount_inr: float,
        gst_amount: float = 0.0,
        status: str = "pending",
        payment_ref: Optional[str] = None,
    ) -> InvoiceRecord:
        """Record an invoice."""
        total_inr = amount_inr + gst_amount
        
        invoice = InvoiceRecord(
            invoice_number=invoice_number,
            client_id=client_id,
            client_name=client_name,
            plan=plan,
            amount_inr=amount_inr,
            gst_amount=gst_amount,
            total_inr=total_inr,
            status=status,
            payment_ref=payment_ref,
        )
        self.invoices.append(invoice)
        self._save_invoices()
        
        # Also record revenue metric
        self.record_metric(
            metric_name=f"invoice_{invoice_number}",
            value=total_inr,
            currency="INR",
            period="one_time",
            verified=status == "paid",
            evidence=f"Invoice {invoice_number}",
            source="billing",
            tags={"client_id": client_id, "plan": plan},
        )
        
        return invoice
    
    def update_invoice_payment(
        self,
        invoice_number: str,
        payment_ref: str,
    ) -> dict[str, Any]:
        """Update invoice to paid status."""
        for invoice in self.invoices:
            if invoice.invoice_number == invoice_number:
                invoice.status = "paid"
                invoice.payment_ref = payment_ref
                invoice.payment_date = datetime.now(_IST).isoformat()
                self._save_invoices()
                
                # Update metric
                self.record_metric(
                    metric_name=f"payment_{invoice_number}",
                    value=invoice.total_inr,
                    currency="INR",
                    period="one_time",
                    verified=True,
                    evidence=f"Payment confirmed: {payment_ref}",
                    source="billing",
                    tags={"client_id": invoice.client_id},
                )
                
                return {"success": True, "invoice": invoice.to_dict()}
        
        return {"error": f"Invoice {invoice_number} not found"}
    
    def get_revenue_summary(self) -> dict[str, Any]:
        """Get revenue summary metrics."""
        today = datetime.now(_IST).date()
        this_month = today.replace(day=1)
        this_fy = f"{today.year}-{str(today.year + 1)[2:]}"
        
        # Calculate metrics
        today_revenue = sum(
            i.total_inr for i in self.invoices
            if i.status == "paid"
            and datetime.fromisoformat(i.payment_date or i.created_at).date() == today
        )
        
        month_revenue = sum(
            i.total_inr for i in self.invoices
            if i.status == "paid"
            and datetime.fromisoformat(i.payment_date or i.created_at).date() >= this_month
        )
        
        fy_revenue = sum(
            i.total_inr for i in self.invoices
            if i.status == "paid"
            and i.created_at.startswith(this_fy)
        )
        
        pending_revenue = sum(
            i.total_inr for i in self.invoices
            if i.status == "pending"
        )
        
        total_revenue = sum(
            i.total_inr for i in self.invoices
            if i.status == "paid"
        )
        
        # Count active clients
        paid_clients = set(
            i.client_id for i in self.invoices
            if i.status == "paid"
        )
        
        return {
            "today_revenue_inr": today_revenue,
            "month_revenue_inr": month_revenue,
            "fy_revenue_inr": fy_revenue,
            "pending_revenue_inr": pending_revenue,
            "total_revenue_inr": total_revenue,
            "active_clients": len(paid_clients),
            "total_invoices": len(self.invoices),
            "paid_invoices": len([i for i in self.invoices if i.status == "paid"]),
            "pending_invoices": len([i for i in self.invoices if i.status == "pending"]),
            "fy": this_fy,
        }
    
    def get_revenue_trend(self, days: int = 30) -> list[dict[str, Any]]:
        """Get revenue trend over past N days."""
        today = datetime.now(_IST).date()
        trend = []
        
        for i in range(days):
            date = today - timedelta(days=i)
            day_revenue = sum(
                i.total_inr for i in self.invoices
                if i.status == "paid"
                and datetime.fromisoformat(i.payment_date or i.created_at).date() == date
            )
            trend.append({
                "date": date.isoformat(),
                "revenue_inr": day_revenue,
            })
        
        # Reverse to show oldest first
        trend.reverse()
        return trend
    
    def get_invoice_list(
        self,
        limit: int = 50,
        status: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get invoice list with optional filters."""
        result = []
        for invoice in reversed(self.invoices):
            if status and invoice.status != status:
                continue
            if client_id and invoice.client_id != client_id:
                continue
            result.append(invoice.to_dict())
            if len(result) >= limit:
                break
        return result
    
    def get_client_revenue(self, client_id: str) -> dict[str, Any]:
        """Get revenue summary for a specific client."""
        client_invoices = [
            i for i in self.invoices
            if i.client_id == client_id
        ]
        
        total_paid = sum(
            i.total_inr for i in client_invoices
            if i.status == "paid"
        )
        total_pending = sum(
            i.total_inr for i in client_invoices
            if i.status == "pending"
        )
        
        return {
            "client_id": client_id,
            "total_invoices": len(client_invoices),
            "paid_invoices": len([i for i in client_invoices if i.status == "paid"]),
            "pending_invoices": len([i for i in client_invoices if i.status == "pending"]),
            "total_paid_inr": total_paid,
            "total_pending_inr": total_pending,
            "invoices": [i.to_dict() for i in client_invoices[-10:]],
        }
    
    def get_dashboard_metrics(self) -> dict[str, Any]:
        """Get comprehensive dashboard metrics."""
        summary = self.get_revenue_summary()
        trend = self.get_revenue_trend(7)
        
        # Get recent metrics
        recent_metrics = self.metrics[-20:] if self.metrics else []
        
        # Calculate MRR (Monthly Recurring Revenue)
        mrr = sum(
            i.total_inr for i in self.invoices
            if i.status == "paid"
            and i.plan in ["starter", "marketing", "combo", "advanced"]
        )
        
        return {
            "summary": summary,
            "trend_7d": trend,
            "recent_metrics": [m.to_dict() for m in recent_metrics],
            "mrr_inr": mrr,
            "last_updated": datetime.now(_IST).isoformat(),
        }


# Module-level singleton
_dashboard: Optional[RevenueDashboard] = None


def get_dashboard() -> RevenueDashboard:
    """Get or create singleton RevenueDashboard."""
    global _dashboard
    if _dashboard is None:
        _dashboard = RevenueDashboard()
    return _dashboard


def record_metric(
    metric_name: str,
    value: float,
    currency: str = "INR",
    period: str = "daily",
    verified: bool = False,
    evidence: str = "",
    source: str = "",
    tags: Optional[dict[str, str]] = None,
) -> RevenueMetric:
    """Convenience function to record a metric."""
    return get_dashboard().record_metric(
        metric_name, value, currency, period, verified, evidence, source, tags
    )


def record_invoice(
    invoice_number: str,
    client_id: str,
    client_name: str,
    plan: str,
    amount_inr: float,
    gst_amount: float = 0.0,
    status: str = "pending",
    payment_ref: Optional[str] = None,
) -> InvoiceRecord:
    """Convenience function to record an invoice."""
    return get_dashboard().record_invoice(
        invoice_number, client_id, client_name, plan, amount_inr, gst_amount, status, payment_ref
    )


def get_revenue_summary() -> dict[str, Any]:
    """Convenience function to get revenue summary."""
    return get_dashboard().get_revenue_summary()


def get_dashboard_metrics() -> dict[str, Any]:
    """Convenience function to get dashboard metrics."""
    return get_dashboard().get_dashboard_metrics()


def get_invoice_list(
    limit: int = 50,
    status: Optional[str] = None,
    client_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Convenience function to get invoice list."""
    return get_dashboard().get_invoice_list(limit, status, client_id)
