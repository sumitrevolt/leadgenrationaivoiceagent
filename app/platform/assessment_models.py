from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class FeatureStatus(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BROKEN = "broken"


class FeatureCategory(Enum):
    VISUALIZATION = "visualization"
    DATA_TABLE = "data_table"
    ACTION = "action"
    NAVIGATION = "navigation"
    REAL_TIME = "real_time"
    BILLING = "billing"
    ANALYTICS = "analytics"


class Impact(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Effort(Enum):
    HIGH = "high"    # 5+ days
    MEDIUM = "medium"  # 2-4 days
    LOW = "low"    # <2 days


class MoSCoW(Enum):
    MUST_HAVE = "must_have"
    SHOULD_HAVE = "should_have"
    COULD_HAVE = "could_have"
    WONT_HAVE = "wont_have"


class Severity(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class Evidence:
    line_numbers: List[int] = field(default_factory=list)
    code_snippets: List[str] = field(default_factory=list)


@dataclass
class Feature:
    id: str
    name: str
    dashboard: str  # "customer" | "admin"
    category: FeatureCategory
    status: FeatureStatus
    description: str
    ui_elements: List[str] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)
    evidence: Evidence = field(default_factory=Evidence)
    requirement_mapping: List[str] = field(default_factory=list)


@dataclass
class Gap:
    id: str
    name: str
    dashboard: str
    competitive_reference: List[str] = field(default_factory=list)
    prevalence: int = 1
    impact: Impact = Impact.MEDIUM
    effort: Effort = Effort.MEDIUM
    moscow: MoSCoW = MoSCoW.SHOULD_HAVE
    category: str = ""
    description: str = ""
    backend_dependency: bool = False
    proposed_endpoint: Optional[str] = None


@dataclass
class UXIssue:
    id: str
    name: str
    dashboard: str
    dimension: str
    severity: Severity
    wcag_violation: bool = False
    wcag_criterion: Optional[str] = None
    user_impact: str = ""
    evidence: Evidence = field(default_factory=Evidence)
    remediation: str = ""


@dataclass
class BacklogItem:
    item: str
    dashboard: str
    category: str
    moscow: MoSCoW
    impact_score: int = 5
    effort_score: int = 5
    priority_rank: float = 0.0
    estimated_days: int = 3


@dataclass
class AssessmentData:
    assessment_id: str
    generated_at: str
    scores: Dict[str, float] = field(default_factory=dict)
    features: List[Feature] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)
    issues: List[UXIssue] = field(default_factory=list)
    backlog: List[BacklogItem] = field(default_factory=list)
    backend_dependencies: List[Dict] = field(default_factory=list)


@dataclass
class RegressionReport:
    comparison_id: str
    baseline_id: str
    current_id: str
    comparison_date: str
    regressions: List[Dict] = field(default_factory=list)
    improvements: List[Dict] = field(default_factory=list)
    score_deltas: Dict[str, float] = field(default_factory=dict)
