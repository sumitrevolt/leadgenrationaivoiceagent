"""Tests for Revenue Tracking Dashboard."""

import pytest
from app.revenue.dashboard import (
    RevenueDashboard,
    RevenueMetric,
    InvoiceRecord,
)


class TestRevenueDashboard:
    """Test revenue tracking dashboard."""
    
    def test_initialization(self):
        """Test dashboard initialization."""
        dashboard = RevenueDashboard()
        assert dashboard is not None
    
    def test_record_metric(self):
        """Test recording a metric."""
        dashboard = RevenueDashboard()
        metric = dashboard.record_metric(
            metric_name="test_metric",
            value=1000.0,
            currency="INR",
            verified=True,
        )
        assert metric.metric_name == "test_metric"
        assert metric.value == 1000.0
        assert metric.verified is True
    
    def test_record_invoice(self):
        """Test creating an invoice."""
        dashboard = RevenueDashboard()
        invoice = dashboard.record_invoice(
            invoice_number="INV/2026-27/0001",
            client_id="client1",
            client_name="Test Business",
            plan="starter",
            amount_inr=1999.0,
            gst_amount=360.0,
            status="pending",
        )
        assert invoice.invoice_number == "INV/2026-27/0001"
        assert invoice.total_inr == 2359.0  # 1999 + 360
    
    def test_update_invoice_payment(self):
        """Test marking invoice as paid."""
        dashboard = RevenueDashboard()
        dashboard.record_invoice(
            invoice_number="INV/2026-27/0002",
            client_id="client2",
            client_name="Test Business 2",
            plan="marketing",
            amount_inr=5999.0,
            status="pending",
        )
        
        result = dashboard.update_invoice_payment(
            "INV/2026-27/0002",
            "UPI123456"
        )
        assert result["success"] is True
        assert result["invoice"]["status"] == "paid"
        assert result["invoice"]["payment_ref"] == "UPI123456"
    
    def test_get_revenue_summary(self):
        """Test revenue summary."""
        dashboard = RevenueDashboard()
        summary = dashboard.get_revenue_summary()
        
        assert "today_revenue_inr" in summary
        assert "month_revenue_inr" in summary
        assert "fy_revenue_inr" in summary
        assert "active_clients" in summary
    
    def test_get_revenue_trend(self):
        """Test revenue trend."""
        dashboard = RevenueDashboard()
        trend = dashboard.get_revenue_trend(days=7)
        assert len(trend) == 7
        assert "date" in trend[0]
        assert "revenue_inr" in trend[0]
    
    def test_get_invoice_list(self):
        """Test invoice list with filters."""
        dashboard = RevenueDashboard()
        dashboard.record_invoice(
            invoice_number="INV/001",
            client_id="client1",
            client_name="Client 1",
            plan="starter",
            amount_inr=1999.0,
            status="paid",
        )
        dashboard.record_invoice(
            invoice_number="INV/002",
            client_id="client1",
            client_name="Client 1",
            plan="marketing",
            amount_inr=5999.0,
            status="pending",
        )
        
        # Get all invoices
        invoices = dashboard.get_invoice_list()
        assert len(invoices) == 2
        
        # Filter by status
        paid = dashboard.get_invoice_list(status="paid")
        assert len(paid) == 1
        assert paid[0]["status"] == "paid"
        
        # Filter by client
        client_invoices = dashboard.get_invoice_list(client_id="client1")
        assert len(client_invoices) == 2
    
    def test_get_client_revenue(self):
        """Test client revenue summary."""
        dashboard = RevenueDashboard()
        dashboard.record_invoice(
            invoice_number="INV/C1",
            client_id="client1",
            client_name="Client 1",
            plan="starter",
            amount_inr=1999.0,
            status="paid",
        )
        
        result = dashboard.get_client_revenue("client1")
        assert result["client_id"] == "client1"
        assert result["total_paid_inr"] == 1999.0
    
    def test_get_dashboard_metrics(self):
        """Test comprehensive dashboard metrics."""
        dashboard = RevenueDashboard()
        metrics = dashboard.get_dashboard_metrics()
        
        assert "summary" in metrics
        assert "trend_7d" in metrics
        assert "mrr_inr" in metrics
        assert "last_updated" in metrics


class TestRevenueMetric:
    """Test RevenueMetric model."""
    
    def test_metric_creation(self):
        """Test creating a revenue metric."""
        metric = RevenueMetric(
            metric_name="daily_revenue",
            value=5000.0,
            currency="INR",
            period="daily",
            verified=True,
        )
        assert metric.metric_name == "daily_revenue"
        assert metric.value == 5000.0
    
    def test_metric_to_dict(self):
        """Test converting metric to dict."""
        metric = RevenueMetric(
            metric_name="test",
            value=100.0,
        )
        data = metric.to_dict()
        assert data["metric_name"] == "test"
        assert data["value"] == 100.0


class TestInvoiceRecord:
    """Test InvoiceRecord model."""
    
    def test_invoice_creation(self):
        """Test creating an invoice."""
        invoice = InvoiceRecord(
            invoice_number="INV/TEST/001",
            client_id="client1",
            client_name="Test Client",
            plan="starter",
            amount_inr=1999.0,
            gst_amount=360.0,
            status="pending",
        )
        assert invoice.total_inr == 2359.0
        assert invoice.status == "pending"
    
    def test_invoice_to_dict(self):
        """Test converting invoice to dict."""
        invoice = InvoiceRecord(
            invoice_number="INV/TEST/002",
            client_id="client2",
            client_name="Test Client 2",
            plan="marketing",
            amount_inr=5999.0,
            status="paid",
        )
        data = invoice.to_dict()
        assert data["invoice_number"] == "INV/TEST/002"
        assert data["status"] == "paid"
