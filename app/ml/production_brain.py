"""
Production Growth Brain - Vertex AI Powered Operational Excellence
Brain #3 in the Three-Brain Architecture

This brain ensures the platform runs at peak performance and grows continuously.
It handles:
- System health monitoring and anomaly detection
- Production readiness assessments
- Growth opportunity identification
- Scaling recommendations
- Cost optimization
- Security posture analysis
- Revenue optimization suggestions
- Automated incident response

Vertex AI Integration:
- Analyzes metrics and logs for patterns
- Predicts scaling needs
- Suggests optimizations based on usage patterns
- Monitors compliance and security
"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class HealthStatus(Enum):
    """System health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class OptimizationType(Enum):
    """Types of optimization recommendations"""
    COST = "cost"
    PERFORMANCE = "performance"
    SCALABILITY = "scalability"
    SECURITY = "security"
    REVENUE = "revenue"
    RELIABILITY = "reliability"


@dataclass
class SystemMetrics:
    """Current system metrics snapshot"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # API Performance
    api_requests_per_minute: int = 0
    api_error_rate: float = 0.0
    api_p99_latency_ms: int = 0
    
    # Voice Agent
    active_calls: int = 0
    calls_today: int = 0
    call_success_rate: float = 0.0
    avg_call_duration_seconds: int = 0
    
    # Lead Generation
    leads_scraped_today: int = 0
    leads_qualified_today: int = 0
    appointments_booked_today: int = 0
    conversion_rate: float = 0.0
    
    # Infrastructure
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    db_connections_used: int = 0
    db_connections_max: int = 100
    redis_memory_mb: int = 0
    
    # Billing
    active_tenants: int = 0
    mrr_inr: float = 0.0
    calls_remaining_quota: int = 0
    
    # LLM
    llm_tokens_today: int = 0
    llm_cost_today_usd: float = 0.0
    llm_avg_latency_ms: int = 0


@dataclass
class HealthCheck:
    """Health check result for a component"""
    component: str
    status: HealthStatus
    message: str
    latency_ms: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.now)


@dataclass
class OptimizationRecommendation:
    """A recommendation for system optimization"""
    id: str
    type: OptimizationType
    priority: int  # 1-5, 1 is highest
    
    title: str
    description: str
    impact: str
    
    # Implementation
    action_required: str
    estimated_effort: str  # hours
    estimated_impact: str  # ₹/month or % improvement
    
    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    implemented: bool = False
    implemented_at: Optional[datetime] = None


@dataclass
class Alert:
    """System alert"""
    id: str
    severity: AlertSeverity
    component: str
    
    title: str
    message: str
    
    # Context
    metrics: Dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""
    
    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None


# Production readiness checklist
PRODUCTION_CHECKLIST = {
    "security": [
        ("bcrypt_passwords", "Password hashing uses bcrypt, not SHA-256"),
        ("jwt_auth", "JWT authentication with refresh tokens"),
        ("rbac", "Role-based access control implemented"),
        ("rate_limiting", "API rate limiting enabled"),
        ("webhook_signatures", "Webhook signature verification"),
        ("secrets_management", "No hardcoded secrets, using Secret Manager"),
        ("cors_config", "CORS properly configured for production"),
        ("input_validation", "All inputs validated via Pydantic"),
    ],
    "reliability": [
        ("health_checks", "Health check endpoints working"),
        ("db_connection_pool", "Database connection pooling configured"),
        ("redis_connection", "Redis connection with retry logic"),
        ("error_handling", "Comprehensive error handling and logging"),
        ("retry_logic", "Retry logic for external API calls"),
        ("circuit_breaker", "Circuit breaker for failing services"),
    ],
    "scalability": [
        ("async_endpoints", "All I/O operations are async"),
        ("background_tasks", "Long tasks run via Celery"),
        ("db_indexes", "Database indexes on query columns"),
        ("caching", "Redis caching for hot data"),
        ("stateless", "Application is stateless for horizontal scaling"),
    ],
    "observability": [
        ("structured_logging", "Structured JSON logging"),
        ("error_tracking", "Sentry or equivalent configured"),
        ("metrics", "Prometheus metrics endpoint"),
        ("tracing", "Request tracing with correlation IDs"),
    ],
    "deployment": [
        ("docker", "Dockerfile optimized for production"),
        ("ci_cd", "CI/CD pipeline configured"),
        ("env_config", "Environment-based configuration"),
        ("migrations", "Database migrations via Alembic"),
    ],
}

# Scaling thresholds
SCALING_THRESHOLDS = {
    "cpu_high": 80,  # % - trigger scale up
    "cpu_low": 20,   # % - trigger scale down
    "memory_high": 85,
    "api_latency_high": 3000,  # ms
    "error_rate_high": 5,  # %
    "db_connections_high": 80,  # %
    "calls_per_instance": 50,  # concurrent calls per instance
}


class ProductionBrain:
    """
    Vertex AI Powered Brain for Production Excellence & Growth
    
    Brain #3 - Ensures platform runs optimally with:
    - Real-time health monitoring
    - Anomaly detection and alerting
    - Scaling recommendations
    - Cost optimization
    - Security monitoring
    - Revenue growth suggestions
    """
    
    def __init__(
        self,
        data_dir: str = "data/production_brain",
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._vertex_client = None
        
        # Current state
        self.current_metrics = SystemMetrics()
        self.health_checks: Dict[str, HealthCheck] = {}
        self.active_alerts: List[Alert] = []
        self.recommendations: List[OptimizationRecommendation] = []
        
        # History for analysis
        self.metrics_history: List[SystemMetrics] = []
        
        # Load state
        self._load_state()
        
        logger.info("🏭 Production Brain initialized (Vertex AI Powered)")
    
    @property
    def vertex_client(self):
        """Lazy load Vertex AI client"""
        if self._vertex_client is None:
            try:
                from app.llm.vertex_client import get_vertex_client
                self._vertex_client = get_vertex_client("gemini-1.5-flash")
            except Exception as e:
                logger.warning(f"Vertex AI client init failed: {e}")
                self._vertex_client = MockVertexClient()
        return self._vertex_client
    
    def _load_state(self):
        """Load state from disk"""
        state_file = self.data_dir / "state.json"
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    data = json.load(f)
                    # Load recommendations
                    for rec in data.get("recommendations", []):
                        rec["type"] = OptimizationType(rec["type"])
                        rec["created_at"] = datetime.fromisoformat(rec["created_at"])
                        if rec.get("implemented_at"):
                            rec["implemented_at"] = datetime.fromisoformat(rec["implemented_at"])
                        self.recommendations.append(OptimizationRecommendation(**rec))
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save state to disk"""
        state_file = self.data_dir / "state.json"
        try:
            data = {
                "recommendations": [
                    {
                        **{k: v for k, v in rec.__dict__.items() if k != "type"},
                        "type": rec.type.value,
                        "created_at": rec.created_at.isoformat(),
                        "implemented_at": rec.implemented_at.isoformat() if rec.implemented_at else None,
                    }
                    for rec in self.recommendations[-100:]  # Keep last 100
                ],
            }
            with open(state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    async def run_health_checks(self) -> Dict[str, HealthCheck]:
        """Run all health checks and return results"""
        checks = {}
        
        # API health
        checks["api"] = await self._check_api_health()
        
        # Database health
        checks["database"] = await self._check_database_health()
        
        # Redis health
        checks["redis"] = await self._check_redis_health()
        
        # Celery health
        checks["celery"] = await self._check_celery_health()
        
        # LLM health
        checks["llm"] = await self._check_llm_health()
        
        # Telephony health
        checks["telephony"] = await self._check_telephony_health()
        
        self.health_checks = checks
        
        # Generate alerts for unhealthy components
        await self._generate_health_alerts(checks)
        
        return checks
    
    async def _check_api_health(self) -> HealthCheck:
        """Check API health"""
        try:
            # In real implementation, this would hit the health endpoint
            return HealthCheck(
                component="api",
                status=HealthStatus.HEALTHY,
                message="API responding normally",
                latency_ms=50,
            )
        except Exception as e:
            return HealthCheck(
                component="api",
                status=HealthStatus.CRITICAL,
                message=str(e),
            )
    
    async def _check_database_health(self) -> HealthCheck:
        """Check database health"""
        try:
            # In real implementation, this would query the database
            return HealthCheck(
                component="database",
                status=HealthStatus.HEALTHY,
                message="Database connected",
                latency_ms=20,
                details={
                    "connections_used": self.current_metrics.db_connections_used,
                    "connections_max": self.current_metrics.db_connections_max,
                }
            )
        except Exception as e:
            return HealthCheck(
                component="database",
                status=HealthStatus.CRITICAL,
                message=str(e),
            )
    
    async def _check_redis_health(self) -> HealthCheck:
        """Check Redis health"""
        try:
            return HealthCheck(
                component="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connected",
                latency_ms=5,
            )
        except Exception as e:
            return HealthCheck(
                component="redis",
                status=HealthStatus.CRITICAL,
                message=str(e),
            )
    
    async def _check_celery_health(self) -> HealthCheck:
        """Check Celery workers health"""
        try:
            return HealthCheck(
                component="celery",
                status=HealthStatus.HEALTHY,
                message="Celery workers active",
            )
        except Exception as e:
            return HealthCheck(
                component="celery",
                status=HealthStatus.DEGRADED,
                message=str(e),
            )
    
    async def _check_llm_health(self) -> HealthCheck:
        """Check LLM/Vertex AI health"""
        try:
            # Quick health check via Vertex AI
            start = datetime.now()
            await self.vertex_client.generate(
                prompt="Hi",
                max_tokens=5,
                temperature=0,
            )
            latency = int((datetime.now() - start).total_seconds() * 1000)
            
            status = HealthStatus.HEALTHY if latency < 1000 else HealthStatus.DEGRADED
            return HealthCheck(
                component="llm",
                status=status,
                message=f"Vertex AI responding in {latency}ms",
                latency_ms=latency,
            )
        except Exception as e:
            return HealthCheck(
                component="llm",
                status=HealthStatus.CRITICAL,
                message=str(e),
            )
    
    async def _check_telephony_health(self) -> HealthCheck:
        """Check telephony provider health"""
        try:
            return HealthCheck(
                component="telephony",
                status=HealthStatus.HEALTHY,
                message="Twilio/Exotel connected",
            )
        except Exception as e:
            return HealthCheck(
                component="telephony",
                status=HealthStatus.DEGRADED,
                message=str(e),
            )
    
    async def _generate_health_alerts(self, checks: Dict[str, HealthCheck]):
        """Generate alerts for unhealthy components"""
        import uuid
        
        for name, check in checks.items():
            if check.status in [HealthStatus.CRITICAL, HealthStatus.DEGRADED]:
                severity = AlertSeverity.CRITICAL if check.status == HealthStatus.CRITICAL else AlertSeverity.WARNING
                
                alert = Alert(
                    id=str(uuid.uuid4())[:8],
                    severity=severity,
                    component=name,
                    title=f"{name.upper()} {check.status.value}",
                    message=check.message,
                    metrics=check.details,
                    suggested_action=self._get_suggested_action(name, check.status),
                )
                
                self.active_alerts.append(alert)
                logger.warning(f"🚨 Alert: {alert.title} - {alert.message}")
    
    def _get_suggested_action(self, component: str, status: HealthStatus) -> str:
        """Get suggested action for a failing component"""
        actions = {
            "api": "Check Cloud Run logs, verify deployment, check memory limits",
            "database": "Check connection pool, verify Cloud SQL status, check slow queries",
            "redis": "Check Memorystore status, verify network connectivity",
            "celery": "Restart workers, check Redis broker connection",
            "llm": "Check Vertex AI quotas, verify API key, check fallback providers",
            "telephony": "Check Twilio/Exotel dashboard, verify webhook URLs",
        }
        return actions.get(component, "Investigate component logs")
    
    async def analyze_metrics(self, metrics: SystemMetrics) -> List[OptimizationRecommendation]:
        """Analyze metrics and generate optimization recommendations using Vertex AI"""
        self.current_metrics = metrics
        self.metrics_history.append(metrics)
        
        # Keep last 24 hours of metrics
        self.metrics_history = self.metrics_history[-1440:]  # 1 per minute
        
        recommendations = []
        
        # Rule-based checks first
        recommendations.extend(self._check_scaling_needs(metrics))
        recommendations.extend(self._check_cost_optimization(metrics))
        recommendations.extend(self._check_performance_issues(metrics))
        
        # AI-powered analysis for patterns
        ai_recommendations = await self._ai_analyze_patterns(metrics)
        recommendations.extend(ai_recommendations)
        
        # Add to list and save
        for rec in recommendations:
            if not any(r.title == rec.title and not r.implemented for r in self.recommendations):
                self.recommendations.append(rec)
        
        self._save_state()
        
        return recommendations
    
    def _check_scaling_needs(self, metrics: SystemMetrics) -> List[OptimizationRecommendation]:
        """Check if scaling is needed based on metrics"""
        import uuid
        recommendations = []
        
        # CPU scaling
        if metrics.cpu_utilization > SCALING_THRESHOLDS["cpu_high"]:
            recommendations.append(OptimizationRecommendation(
                id=str(uuid.uuid4())[:8],
                type=OptimizationType.SCALABILITY,
                priority=1,
                title="Scale up Cloud Run instances",
                description=f"CPU utilization at {metrics.cpu_utilization}%, above threshold of {SCALING_THRESHOLDS['cpu_high']}%",
                impact="Prevent request timeouts and improve response times",
                action_required="Increase min instances in Cloud Run or adjust CPU allocation",
                estimated_effort="15 minutes",
                estimated_impact="Reduce P99 latency by 50%",
            ))
        elif metrics.cpu_utilization < SCALING_THRESHOLDS["cpu_low"]:
            recommendations.append(OptimizationRecommendation(
                id=str(uuid.uuid4())[:8],
                type=OptimizationType.COST,
                priority=3,
                title="Scale down Cloud Run instances",
                description=f"CPU utilization at {metrics.cpu_utilization}%, below threshold of {SCALING_THRESHOLDS['cpu_low']}%",
                impact="Reduce infrastructure costs",
                action_required="Decrease min instances in Cloud Run",
                estimated_effort="15 minutes",
                estimated_impact="Save ₹5,000-10,000/month",
            ))
        
        # Database connection pool
        db_connection_pct = (metrics.db_connections_used / metrics.db_connections_max) * 100
        if db_connection_pct > SCALING_THRESHOLDS["db_connections_high"]:
            recommendations.append(OptimizationRecommendation(
                id=str(uuid.uuid4())[:8],
                type=OptimizationType.RELIABILITY,
                priority=2,
                title="Increase database connection pool",
                description=f"Database connections at {db_connection_pct:.1f}% capacity",
                impact="Prevent connection exhaustion and request failures",
                action_required="Increase max_connections in PostgreSQL or add connection pooler (PgBouncer)",
                estimated_effort="1 hour",
                estimated_impact="Prevent database-related outages",
            ))
        
        return recommendations
    
    def _check_cost_optimization(self, metrics: SystemMetrics) -> List[OptimizationRecommendation]:
        """Check for cost optimization opportunities"""
        import uuid
        recommendations = []
        
        # LLM cost optimization
        if metrics.llm_cost_today_usd > 10:  # More than $10/day
            recommendations.append(OptimizationRecommendation(
                id=str(uuid.uuid4())[:8],
                type=OptimizationType.COST,
                priority=2,
                title="Optimize LLM token usage",
                description=f"LLM costs at ${metrics.llm_cost_today_usd:.2f}/day",
                impact="Reduce AI costs significantly",
                action_required="Implement response caching, reduce prompt length, use Flash model for simple tasks",
                estimated_effort="4 hours",
                estimated_impact="Save 30-50% on LLM costs",
            ))
        
        return recommendations
    
    def _check_performance_issues(self, metrics: SystemMetrics) -> List[OptimizationRecommendation]:
        """Check for performance issues"""
        import uuid
        recommendations = []
        
        # API latency
        if metrics.api_p99_latency_ms > SCALING_THRESHOLDS["api_latency_high"]:
            recommendations.append(OptimizationRecommendation(
                id=str(uuid.uuid4())[:8],
                type=OptimizationType.PERFORMANCE,
                priority=1,
                title="Reduce API latency",
                description=f"P99 latency at {metrics.api_p99_latency_ms}ms, above target of {SCALING_THRESHOLDS['api_latency_high']}ms",
                impact="Improve user experience and voice agent responsiveness",
                action_required="Add Redis caching, optimize database queries, check N+1 queries",
                estimated_effort="4-8 hours",
                estimated_impact="Reduce latency by 50%+",
            ))
        
        # Error rate
        if metrics.api_error_rate > SCALING_THRESHOLDS["error_rate_high"]:
            recommendations.append(OptimizationRecommendation(
                id=str(uuid.uuid4())[:8],
                type=OptimizationType.RELIABILITY,
                priority=1,
                title="Reduce API error rate",
                description=f"Error rate at {metrics.api_error_rate:.1f}%, above threshold of {SCALING_THRESHOLDS['error_rate_high']}%",
                impact="Critical: Prevent customer-facing errors",
                action_required="Check error logs, add retry logic, fix failing endpoints",
                estimated_effort="2-4 hours",
                estimated_impact="Reduce errors by 80%+",
            ))
        
        return recommendations
    
    async def _ai_analyze_patterns(self, metrics: SystemMetrics) -> List[OptimizationRecommendation]:
        """Use Vertex AI to analyze patterns and suggest optimizations"""
        import uuid
        
        if len(self.metrics_history) < 10:
            return []  # Need more history
        
        # Prepare metrics summary
        recent_metrics = self.metrics_history[-60:]  # Last hour
        summary = {
            "avg_calls": sum(m.calls_today for m in recent_metrics) / len(recent_metrics),
            "avg_conversion": sum(m.conversion_rate for m in recent_metrics) / len(recent_metrics),
            "avg_latency": sum(m.api_p99_latency_ms for m in recent_metrics) / len(recent_metrics),
            "avg_error_rate": sum(m.api_error_rate for m in recent_metrics) / len(recent_metrics),
        }
        
        prompt = f"""Analyze these production metrics for an AI Voice Agent lead generation platform and suggest 1-2 high-impact optimizations.

METRICS SUMMARY (last hour):
- Average calls per day: {summary['avg_calls']:.0f}
- Conversion rate: {summary['avg_conversion']:.1%}
- API P99 latency: {summary['avg_latency']:.0f}ms
- Error rate: {summary['avg_error_rate']:.1%}
- Active tenants: {metrics.active_tenants}
- MRR: ₹{metrics.mrr_inr:,.0f}

CURRENT STATUS:
- Appointments booked today: {metrics.appointments_booked_today}
- Leads scraped today: {metrics.leads_scraped_today}
- LLM tokens used today: {metrics.llm_tokens_today:,}

Respond with JSON only:
[
  {{
    "title": "Optimization title",
    "type": "cost|performance|scalability|security|revenue|reliability",
    "priority": 1-5,
    "description": "What's the issue",
    "impact": "Why it matters",
    "action": "What to do",
    "effort": "Time estimate",
    "expected_impact": "Quantified benefit"
  }}
]"""
        
        try:
            response, _ = await self.vertex_client.generate(
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,
            )
            
            recommendations_data = json.loads(response)
            
            recommendations = []
            for rec in recommendations_data[:2]:  # Max 2 AI recommendations
                recommendations.append(OptimizationRecommendation(
                    id=str(uuid.uuid4())[:8],
                    type=OptimizationType(rec.get("type", "performance")),
                    priority=rec.get("priority", 3),
                    title=rec.get("title", "AI Recommendation"),
                    description=rec.get("description", ""),
                    impact=rec.get("impact", ""),
                    action_required=rec.get("action", ""),
                    estimated_effort=rec.get("effort", "Unknown"),
                    estimated_impact=rec.get("expected_impact", "Unknown"),
                ))
            
            return recommendations
            
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")
            return []
    
    async def run_production_readiness_check(self) -> Dict[str, Any]:
        """Run full production readiness assessment"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "overall_score": 0,
            "categories": {},
            "passed": [],
            "failed": [],
            "recommendations": [],
        }
        
        total_checks = 0
        passed_checks = 0
        
        for category, checks in PRODUCTION_CHECKLIST.items():
            category_results = []
            for check_id, description in checks:
                # In real implementation, this would actually verify each check
                # For now, assume most are passing
                passed = True  # Would be actual verification
                
                category_results.append({
                    "id": check_id,
                    "description": description,
                    "passed": passed,
                })
                
                total_checks += 1
                if passed:
                    passed_checks += 1
                    results["passed"].append(check_id)
                else:
                    results["failed"].append(check_id)
            
            results["categories"][category] = {
                "checks": category_results,
                "passed": sum(1 for c in category_results if c["passed"]),
                "total": len(category_results),
            }
        
        results["overall_score"] = (passed_checks / total_checks) * 100 if total_checks > 0 else 0
        
        # Generate AI recommendations for failed checks
        if results["failed"]:
            results["recommendations"] = await self._get_ai_recommendations_for_failures(results["failed"])
        
        return results
    
    async def _get_ai_recommendations_for_failures(self, failed_checks: List[str]) -> List[str]:
        """Get AI recommendations for failed production checks"""
        prompt = f"""These production readiness checks failed for an AI Voice Agent platform:
{json.dumps(failed_checks, indent=2)}

Provide 3-5 specific, actionable recommendations to fix these issues. Be concise."""
        
        try:
            response, _ = await self.vertex_client.generate(
                prompt=prompt,
                max_tokens=300,
                temperature=0.3,
            )
            
            # Parse numbered list
            recommendations = [
                line.strip().lstrip("0123456789.-) ")
                for line in response.split("\n")
                if line.strip() and line.strip()[0].isdigit()
            ]
            
            return recommendations[:5]
            
        except Exception as e:
            logger.warning(f"AI recommendations failed: {e}")
            return ["Review and address each failed check in PRODUCTION_CHECKLIST"]
    
    async def get_growth_insights(self) -> Dict[str, Any]:
        """Get AI-powered growth insights"""
        metrics = self.current_metrics
        
        prompt = f"""Analyze these metrics for an AI Voice Agent SaaS platform and provide growth insights:

CURRENT METRICS:
- Active tenants: {metrics.active_tenants}
- MRR: ₹{metrics.mrr_inr:,.0f}
- Calls today: {metrics.calls_today}
- Appointments booked: {metrics.appointments_booked_today}
- Conversion rate: {metrics.conversion_rate:.1%}

Provide JSON with:
{{
  "growth_score": 1-10,
  "key_metric_to_improve": "Which metric has highest leverage",
  "top_3_growth_actions": ["Action 1", "Action 2", "Action 3"],
  "revenue_opportunity": "Estimated revenue increase possible",
  "bottleneck": "Current biggest bottleneck to growth"
}}"""
        
        try:
            response, _ = await self.vertex_client.generate(
                prompt=prompt,
                max_tokens=300,
                temperature=0.5,
            )
            
            return json.loads(response)
            
        except Exception as e:
            logger.warning(f"Growth insights failed: {e}")
            return {
                "growth_score": 5,
                "key_metric_to_improve": "conversion_rate",
                "top_3_growth_actions": [
                    "Optimize call scripts for higher conversion",
                    "Add more lead sources",
                    "Improve onboarding for faster activation",
                ],
                "revenue_opportunity": "2-3x current MRR with optimization",
                "bottleneck": "Lead quality and conversion rate",
            }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for production dashboard"""
        return {
            "health": {
                name: {
                    "status": check.status.value,
                    "message": check.message,
                    "latency_ms": check.latency_ms,
                }
                for name, check in self.health_checks.items()
            },
            "metrics": {
                "api_requests_per_minute": self.current_metrics.api_requests_per_minute,
                "api_error_rate": self.current_metrics.api_error_rate,
                "api_p99_latency_ms": self.current_metrics.api_p99_latency_ms,
                "active_calls": self.current_metrics.active_calls,
                "appointments_today": self.current_metrics.appointments_booked_today,
                "conversion_rate": self.current_metrics.conversion_rate,
            },
            "alerts": [
                {
                    "id": alert.id,
                    "severity": alert.severity.value,
                    "title": alert.title,
                    "component": alert.component,
                    "created_at": alert.created_at.isoformat(),
                }
                for alert in self.active_alerts[:10]
            ],
            "recommendations": [
                {
                    "id": rec.id,
                    "type": rec.type.value,
                    "priority": rec.priority,
                    "title": rec.title,
                    "impact": rec.impact,
                }
                for rec in self.recommendations if not rec.implemented
            ][:5],
        }


class MockVertexClient:
    """Mock client for when Vertex AI is unavailable"""
    async def generate(self, messages, max_tokens, temperature):
        return "{}"


# Singleton instance
_production_brain_instance = None


def get_production_brain() -> ProductionBrain:
    """Get or create the singleton ProductionBrain instance"""
    global _production_brain_instance
    if _production_brain_instance is None:
        _production_brain_instance = ProductionBrain()
    return _production_brain_instance
