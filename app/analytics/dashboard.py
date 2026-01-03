"""
Enhanced Analytics Dashboard
ROI Calculator, Conversion Funnels, Call Analysis

This module provides comprehensive analytics for:
1. Platform owner (you) - track all tenants
2. Tenants (your customers) - track their campaigns
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TimeRange(Enum):
    """Time range for analytics"""
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


@dataclass
class CallMetrics:
    """Metrics for calls"""
    total_calls: int = 0
    connected_calls: int = 0
    answered_calls: int = 0
    voicemail: int = 0
    busy: int = 0
    no_answer: int = 0
    failed: int = 0
    
    total_duration_minutes: float = 0
    avg_duration_seconds: float = 0
    
    connect_rate: float = 0  # answered / total
    
    def calculate_rates(self):
        if self.total_calls > 0:
            self.connect_rate = self.answered_calls / self.total_calls


@dataclass
class LeadMetrics:
    """Metrics for leads"""
    total_leads_called: int = 0
    qualified_leads: int = 0
    unqualified_leads: int = 0
    not_interested: int = 0
    callbacks_scheduled: int = 0
    appointments_booked: int = 0
    
    qualification_rate: float = 0
    appointment_rate: float = 0
    
    def calculate_rates(self):
        if self.total_leads_called > 0:
            self.qualification_rate = self.qualified_leads / self.total_leads_called
            self.appointment_rate = self.appointments_booked / self.total_leads_called


@dataclass
class ROIMetrics:
    """ROI calculation metrics"""
    period_start: datetime
    period_end: datetime
    
    # Costs
    subscription_cost: Decimal = Decimal("0")
    telephony_cost: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    
    # Value generated
    appointments_value: Decimal = Decimal("0")
    qualified_leads_value: Decimal = Decimal("0")
    deals_closed_value: Decimal = Decimal("0")
    total_value: Decimal = Decimal("0")
    
    # ROI
    roi_percentage: float = 0
    cost_per_lead: Decimal = Decimal("0")
    cost_per_appointment: Decimal = Decimal("0")
    cost_per_call: Decimal = Decimal("0")
    
    # Savings vs manual
    manual_calling_cost_estimate: Decimal = Decimal("0")
    savings_vs_manual: Decimal = Decimal("0")


@dataclass
class FunnelStage:
    """Single stage in a funnel"""
    name: str
    count: int
    percentage: float = 0
    conversion_from_previous: float = 0


@dataclass
class ConversionFunnel:
    """Conversion funnel data"""
    name: str
    stages: List[FunnelStage] = field(default_factory=list)
    
    def calculate_percentages(self):
        if not self.stages:
            return
        
        top_count = self.stages[0].count
        for i, stage in enumerate(self.stages):
            if top_count > 0:
                stage.percentage = (stage.count / top_count) * 100
            
            if i > 0 and self.stages[i-1].count > 0:
                stage.conversion_from_previous = (
                    stage.count / self.stages[i-1].count
                ) * 100


@dataclass
class ObjectionAnalysis:
    """Analysis of objections encountered"""
    objection_type: str
    count: int
    success_rate: float  # How often AI overcame it
    common_responses: List[str] = field(default_factory=list)


@dataclass
class IndustryPerformance:
    """Performance metrics by industry"""
    industry: str
    calls_made: int
    connect_rate: float
    qualification_rate: float
    appointment_rate: float
    avg_lead_score: float
    top_objections: List[str]


class AnalyticsDashboard:
    """
    Main analytics dashboard
    Provides comprehensive insights
    """
    
    def __init__(self):
        # In production, these would come from database
        self.call_logs: List[Dict] = []
        self.lead_records: List[Dict] = []
        self.objections: List[Dict] = []
        
        logger.info("📊 Analytics Dashboard initialized")
    
    # =========================================================================
    # DATA INGESTION
    # =========================================================================
    
    def record_call(self, call_data: Dict[str, Any]):
        """Record a completed call"""
        self.call_logs.append({
            **call_data,
            "recorded_at": datetime.now()
        })
    
    def record_lead(self, lead_data: Dict[str, Any]):
        """Record lead qualification result"""
        self.lead_records.append({
            **lead_data,
            "recorded_at": datetime.now()
        })
    
    def record_objection(self, objection_data: Dict[str, Any]):
        """Record objection handling"""
        self.objections.append({
            **objection_data,
            "recorded_at": datetime.now()
        })
    
    # =========================================================================
    # CALL ANALYTICS
    # =========================================================================
    
    def get_call_metrics(
        self,
        tenant_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> CallMetrics:
        """Get call metrics for a period"""
        
        # Filter calls
        filtered = self._filter_by_time(self.call_logs, time_range, start_date, end_date)
        
        if tenant_id:
            filtered = [c for c in filtered if c.get("tenant_id") == tenant_id]
        if campaign_id:
            filtered = [c for c in filtered if c.get("campaign_id") == campaign_id]
        
        metrics = CallMetrics()
        metrics.total_calls = len(filtered)
        
        for call in filtered:
            status = call.get("status", "")
            duration = call.get("duration_seconds", 0)
            
            if status == "answered":
                metrics.answered_calls += 1
                metrics.connected_calls += 1
                metrics.total_duration_minutes += duration / 60
            elif status == "voicemail":
                metrics.voicemail += 1
            elif status == "busy":
                metrics.busy += 1
            elif status == "no_answer":
                metrics.no_answer += 1
            elif status == "failed":
                metrics.failed += 1
        
        if metrics.answered_calls > 0:
            metrics.avg_duration_seconds = (
                metrics.total_duration_minutes * 60 / metrics.answered_calls
            )
        
        metrics.calculate_rates()
        return metrics
    
    # =========================================================================
    # LEAD ANALYTICS
    # =========================================================================
    
    def get_lead_metrics(
        self,
        tenant_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS
    ) -> LeadMetrics:
        """Get lead metrics for a period"""
        
        filtered = self._filter_by_time(self.lead_records, time_range)
        
        if tenant_id:
            filtered = [l for l in filtered if l.get("tenant_id") == tenant_id]
        if campaign_id:
            filtered = [l for l in filtered if l.get("campaign_id") == campaign_id]
        
        metrics = LeadMetrics()
        metrics.total_leads_called = len(filtered)
        
        for lead in filtered:
            qualification = lead.get("qualification_result", "")
            
            if qualification == "qualified":
                metrics.qualified_leads += 1
            elif qualification == "unqualified":
                metrics.unqualified_leads += 1
            elif qualification == "not_interested":
                metrics.not_interested += 1
            
            if lead.get("callback_scheduled"):
                metrics.callbacks_scheduled += 1
            if lead.get("appointment_booked"):
                metrics.appointments_booked += 1
        
        metrics.calculate_rates()
        return metrics
    
    # =========================================================================
    # ROI CALCULATOR
    # =========================================================================
    
    def calculate_roi(
        self,
        tenant_id: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
        avg_deal_value: Decimal = Decimal("10000"),
        appointment_to_deal_rate: float = 0.2,
        qualified_lead_value: Decimal = Decimal("500")
    ) -> ROIMetrics:
        """
        Calculate ROI for a tenant
        
        Args:
            tenant_id: Tenant to calculate for
            time_range: Time period
            avg_deal_value: Average value of a closed deal
            appointment_to_deal_rate: What % of appointments become deals
            qualified_lead_value: Value assigned to a qualified lead
        """
        
        # Get period
        start, end = self._get_date_range(time_range)
        
        # Get metrics
        call_metrics = self.get_call_metrics(tenant_id=tenant_id, time_range=time_range)
        lead_metrics = self.get_lead_metrics(tenant_id=tenant_id, time_range=time_range)
        
        roi = ROIMetrics(period_start=start, period_end=end)
        
        # Calculate costs
        # Assuming ₹2 per call average (telephony)
        roi.telephony_cost = Decimal(str(call_metrics.total_calls)) * Decimal("2")
        roi.subscription_cost = Decimal("15000")  # Base subscription
        roi.total_cost = roi.telephony_cost + roi.subscription_cost
        
        # Calculate value generated
        roi.appointments_value = (
            Decimal(str(lead_metrics.appointments_booked)) * 
            avg_deal_value * 
            Decimal(str(appointment_to_deal_rate))
        )
        
        roi.qualified_leads_value = (
            Decimal(str(lead_metrics.qualified_leads)) * qualified_lead_value
        )
        
        # Estimated deals closed
        estimated_deals = int(lead_metrics.appointments_booked * appointment_to_deal_rate)
        roi.deals_closed_value = Decimal(str(estimated_deals)) * avg_deal_value
        
        roi.total_value = roi.appointments_value + roi.qualified_leads_value
        
        # Calculate ROI
        if roi.total_cost > 0:
            roi.roi_percentage = float(
                ((roi.total_value - roi.total_cost) / roi.total_cost) * 100
            )
        
        # Per-unit costs
        if lead_metrics.qualified_leads > 0:
            roi.cost_per_lead = roi.total_cost / lead_metrics.qualified_leads
        
        if lead_metrics.appointments_booked > 0:
            roi.cost_per_appointment = roi.total_cost / lead_metrics.appointments_booked
        
        if call_metrics.total_calls > 0:
            roi.cost_per_call = roi.total_cost / call_metrics.total_calls
        
        # Compare to manual calling
        # Assume 1 telecaller: ₹20,000/month, can make 100 calls/day
        # AI made X calls in the period
        days_in_period = (end - start).days or 1
        calls_per_day = call_metrics.total_calls / days_in_period
        telecallers_needed = max(1, calls_per_day / 100)
        roi.manual_calling_cost_estimate = Decimal(str(telecallers_needed)) * Decimal("20000")
        roi.savings_vs_manual = roi.manual_calling_cost_estimate - roi.total_cost
        
        return roi
    
    # =========================================================================
    # CONVERSION FUNNELS
    # =========================================================================
    
    def get_conversion_funnel(
        self,
        tenant_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS
    ) -> ConversionFunnel:
        """Get conversion funnel"""
        
        call_metrics = self.get_call_metrics(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            time_range=time_range
        )
        
        lead_metrics = self.get_lead_metrics(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            time_range=time_range
        )
        
        funnel = ConversionFunnel(name="Lead to Appointment Funnel")
        
        funnel.stages = [
            FunnelStage(name="Calls Made", count=call_metrics.total_calls),
            FunnelStage(name="Calls Connected", count=call_metrics.connected_calls),
            FunnelStage(name="Conversations Completed", count=call_metrics.answered_calls),
            FunnelStage(name="Leads Qualified", count=lead_metrics.qualified_leads),
            FunnelStage(name="Appointments Booked", count=lead_metrics.appointments_booked),
        ]
        
        funnel.calculate_percentages()
        return funnel
    
    def get_lead_quality_funnel(
        self,
        tenant_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS
    ) -> ConversionFunnel:
        """Get lead quality breakdown funnel"""
        
        filtered = self._filter_by_time(self.lead_records, time_range)
        if tenant_id:
            filtered = [l for l in filtered if l.get("tenant_id") == tenant_id]
        
        total = len(filtered)
        
        # Count by lead score ranges
        hot = sum(1 for l in filtered if l.get("lead_score", 0) >= 80)
        warm = sum(1 for l in filtered if 50 <= l.get("lead_score", 0) < 80)
        cold = sum(1 for l in filtered if l.get("lead_score", 0) < 50)
        
        funnel = ConversionFunnel(name="Lead Quality Distribution")
        funnel.stages = [
            FunnelStage(name="Total Leads", count=total),
            FunnelStage(name="Hot Leads (80+)", count=hot),
            FunnelStage(name="Warm Leads (50-79)", count=warm),
            FunnelStage(name="Cold Leads (<50)", count=cold),
        ]
        
        funnel.calculate_percentages()
        return funnel
    
    # =========================================================================
    # OBJECTION ANALYSIS
    # =========================================================================
    
    def get_objection_analysis(
        self,
        tenant_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS
    ) -> List[ObjectionAnalysis]:
        """Analyze objections and AI performance"""
        
        filtered = self._filter_by_time(self.objections, time_range)
        if tenant_id:
            filtered = [o for o in filtered if o.get("tenant_id") == tenant_id]
        
        # Group by objection type
        objection_groups: Dict[str, List] = {}
        for obj in filtered:
            obj_type = obj.get("objection_type", "unknown")
            if obj_type not in objection_groups:
                objection_groups[obj_type] = []
            objection_groups[obj_type].append(obj)
        
        analysis = []
        for obj_type, instances in objection_groups.items():
            total = len(instances)
            overcame = sum(1 for o in instances if o.get("overcame", False))
            
            analysis.append(ObjectionAnalysis(
                objection_type=obj_type,
                count=total,
                success_rate=overcame / total if total > 0 else 0,
                common_responses=[
                    o.get("ai_response", "")[:100] 
                    for o in instances[:3]
                ]
            ))
        
        # Sort by count
        analysis.sort(key=lambda x: x.count, reverse=True)
        return analysis
    
    # =========================================================================
    # INDUSTRY PERFORMANCE
    # =========================================================================
    
    def get_industry_performance(
        self,
        tenant_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS
    ) -> List[IndustryPerformance]:
        """Get performance breakdown by industry"""
        
        calls = self._filter_by_time(self.call_logs, time_range)
        leads = self._filter_by_time(self.lead_records, time_range)
        
        if tenant_id:
            calls = [c for c in calls if c.get("tenant_id") == tenant_id]
            leads = [l for l in leads if l.get("tenant_id") == tenant_id]
        
        # Group by industry
        industries: Dict[str, Dict] = {}
        
        for call in calls:
            industry = call.get("industry", "unknown")
            if industry not in industries:
                industries[industry] = {
                    "calls": 0, "connected": 0, "qualified": 0,
                    "appointments": 0, "scores": [], "objections": []
                }
            
            industries[industry]["calls"] += 1
            if call.get("status") == "answered":
                industries[industry]["connected"] += 1
        
        for lead in leads:
            industry = lead.get("industry", "unknown")
            if industry in industries:
                if lead.get("qualification_result") == "qualified":
                    industries[industry]["qualified"] += 1
                if lead.get("appointment_booked"):
                    industries[industry]["appointments"] += 1
                if lead.get("lead_score"):
                    industries[industry]["scores"].append(lead["lead_score"])
        
        performance = []
        for industry, data in industries.items():
            calls = data["calls"]
            performance.append(IndustryPerformance(
                industry=industry,
                calls_made=calls,
                connect_rate=data["connected"] / calls if calls > 0 else 0,
                qualification_rate=data["qualified"] / calls if calls > 0 else 0,
                appointment_rate=data["appointments"] / calls if calls > 0 else 0,
                avg_lead_score=sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0,
                top_objections=[]  # Would aggregate from objections data
            ))
        
        return performance
    
    # =========================================================================
    # DASHBOARD SUMMARY
    # =========================================================================
    
    def get_dashboard_summary(
        self,
        tenant_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS
    ) -> Dict[str, Any]:
        """Get complete dashboard summary"""
        
        call_metrics = self.get_call_metrics(tenant_id=tenant_id, time_range=time_range)
        lead_metrics = self.get_lead_metrics(tenant_id=tenant_id, time_range=time_range)
        
        # Calculate comparison with previous period
        prev_calls = self.get_call_metrics(
            tenant_id=tenant_id, 
            time_range=TimeRange.LAST_30_DAYS
        )
        
        return {
            "overview": {
                "total_calls": call_metrics.total_calls,
                "connect_rate": f"{call_metrics.connect_rate * 100:.1f}%",
                "avg_call_duration": f"{call_metrics.avg_duration_seconds:.0f}s",
                "total_call_time": f"{call_metrics.total_duration_minutes:.0f} min"
            },
            "leads": {
                "total_contacted": lead_metrics.total_leads_called,
                "qualified": lead_metrics.qualified_leads,
                "qualification_rate": f"{lead_metrics.qualification_rate * 100:.1f}%",
                "appointments": lead_metrics.appointments_booked,
                "appointment_rate": f"{lead_metrics.appointment_rate * 100:.1f}%",
                "callbacks_scheduled": lead_metrics.callbacks_scheduled
            },
            "disposition_breakdown": {
                "not_interested": lead_metrics.not_interested,
                "unqualified": lead_metrics.unqualified_leads,
                "voicemail": call_metrics.voicemail,
                "no_answer": call_metrics.no_answer,
                "busy": call_metrics.busy
            },
            "funnel": self._funnel_to_dict(
                self.get_conversion_funnel(tenant_id=tenant_id, time_range=time_range)
            ),
            "top_industries": [
                {
                    "name": p.industry,
                    "appointment_rate": f"{p.appointment_rate * 100:.1f}%"
                }
                for p in self.get_industry_performance(tenant_id=tenant_id)[:5]
            ]
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _filter_by_time(
        self,
        records: List[Dict],
        time_range: TimeRange,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Filter records by time range"""
        
        start, end = self._get_date_range(time_range, start_date, end_date)
        
        return [
            r for r in records
            if start <= r.get("recorded_at", datetime.min) <= end
        ]
    
    def _get_date_range(
        self,
        time_range: TimeRange,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> tuple:
        """Get start and end dates for time range"""
        
        now = datetime.now()
        
        if time_range == TimeRange.CUSTOM:
            return start_date or now, end_date or now
        
        ranges = {
            TimeRange.TODAY: (
                now.replace(hour=0, minute=0, second=0),
                now
            ),
            TimeRange.YESTERDAY: (
                (now - timedelta(days=1)).replace(hour=0, minute=0, second=0),
                (now - timedelta(days=1)).replace(hour=23, minute=59, second=59)
            ),
            TimeRange.LAST_7_DAYS: (
                now - timedelta(days=7),
                now
            ),
            TimeRange.LAST_30_DAYS: (
                now - timedelta(days=30),
                now
            ),
            TimeRange.THIS_MONTH: (
                now.replace(day=1, hour=0, minute=0, second=0),
                now
            ),
            TimeRange.LAST_MONTH: (
                (now.replace(day=1) - timedelta(days=1)).replace(day=1),
                now.replace(day=1) - timedelta(seconds=1)
            )
        }
        
        return ranges.get(time_range, (now - timedelta(days=30), now))
    
    def _funnel_to_dict(self, funnel: ConversionFunnel) -> Dict:
        """Convert funnel to dictionary"""
        return {
            "name": funnel.name,
            "stages": [
                {
                    "name": s.name,
                    "count": s.count,
                    "percentage": f"{s.percentage:.1f}%",
                    "conversion": f"{s.conversion_from_previous:.1f}%"
                }
                for s in funnel.stages
            ]
        }


# Global analytics instance
analytics_dashboard = AnalyticsDashboard()
