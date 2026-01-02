"""
Feedback Loop for Auto-Learning
Tracks call outcomes and learns which responses work best

Features:
- Track which responses led to successful outcomes
- Weight future responses based on historical success
- Identify winning patterns per industry/niche
- Auto-improve objection handling
- A/B test response variations
"""
import json
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import defaultdict

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class CallOutcome(Enum):
    """Call outcome classification for learning"""
    SUCCESS = "success"  # Appointment or strong interest
    PARTIAL = "partial"  # Callback or mild interest
    FAILURE = "failure"  # Rejection or not interested
    NEUTRAL = "neutral"  # No clear outcome


@dataclass
class ResponsePattern:
    """
    A pattern of response that can be learned from
    """
    pattern_id: str
    
    # Context when this response was used
    intent_before: str  # What intent triggered this response
    industry: str
    language: str
    
    # The actual response
    response_text: str
    response_type: str  # greeting, objection_handler, closing, etc.
    
    # Performance metrics
    times_used: int = 0
    success_count: int = 0
    partial_count: int = 0
    failure_count: int = 0
    
    # Calculated scores
    success_rate: float = 0.0
    confidence: float = 0.0  # Higher with more usage data
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime = field(default_factory=datetime.now)
    
    def update_metrics(self, outcome: CallOutcome):
        """Update pattern metrics based on outcome"""
        self.times_used += 1
        self.last_used_at = datetime.now()
        
        if outcome == CallOutcome.SUCCESS:
            self.success_count += 1
        elif outcome == CallOutcome.PARTIAL:
            self.partial_count += 1
        elif outcome == CallOutcome.FAILURE:
            self.failure_count += 1
        
        # Calculate success rate (success + partial*0.5)
        if self.times_used > 0:
            self.success_rate = (
                self.success_count + self.partial_count * 0.5
            ) / self.times_used
        
        # Confidence increases with more data (asymptotic to 1.0)
        self.confidence = 1 - (1 / (1 + self.times_used * 0.1))
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat()
        }


@dataclass
class ObjectionHandler:
    """Tracks effectiveness of objection responses"""
    objection_type: str  # not_interested, busy, expensive, etc.
    response_variants: List[ResponsePattern] = field(default_factory=list)
    
    # Best performing response for this objection
    best_response: Optional[str] = None
    best_success_rate: float = 0.0
    
    def add_response(self, pattern: ResponsePattern):
        """Add or update a response variant"""
        existing = next(
            (p for p in self.response_variants if p.response_text == pattern.response_text),
            None
        )
        if existing:
            existing.update_metrics(CallOutcome.NEUTRAL)  # Just tracking usage
        else:
            self.response_variants.append(pattern)
        
        self._update_best()
    
    def _update_best(self):
        """Update best performing response"""
        if not self.response_variants:
            return
        
        # Only consider patterns with enough data
        valid_patterns = [p for p in self.response_variants if p.times_used >= 5]
        
        if valid_patterns:
            best = max(valid_patterns, key=lambda p: p.success_rate * p.confidence)
            self.best_response = best.response_text
            self.best_success_rate = best.success_rate


@dataclass
class IndustryInsights:
    """Learned insights for a specific industry"""
    industry: str
    
    # Best performing elements
    best_greeting: Optional[str] = None
    best_value_prop: Optional[str] = None
    best_closing: Optional[str] = None
    
    # Timing insights
    best_call_hour: int = 11  # Default 11 AM
    best_call_day: int = 2  # Default Tuesday (0=Monday)
    
    # Objection patterns
    common_objections: Dict[str, int] = field(default_factory=dict)
    objection_handlers: Dict[str, ObjectionHandler] = field(default_factory=dict)
    
    # Performance metrics
    total_calls: int = 0
    successful_calls: int = 0
    avg_call_duration: float = 0.0
    conversion_rate: float = 0.0


class FeedbackLoop:
    """
    Learns from call outcomes to improve future responses
    
    This is the core learning engine that:
    1. Tracks every response and its outcome
    2. Identifies patterns that lead to success
    3. Weights responses based on historical performance
    4. Provides optimized responses for future calls
    """
    
    def __init__(self, data_dir: str = "data/feedback"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Response patterns indexed by type
        self.patterns: Dict[str, List[ResponsePattern]] = defaultdict(list)
        
        # Industry-specific insights
        self.industry_insights: Dict[str, IndustryInsights] = {}
        
        # Objection handlers (global)
        self.objection_handlers: Dict[str, ObjectionHandler] = {}
        
        # Load existing data
        self._load_data()
        
        logger.info("🔄 Feedback loop initialized")
    
    def _load_data(self):
        """Load existing feedback data from disk"""
        patterns_file = self.data_dir / "patterns.json"
        if patterns_file.exists():
            try:
                with open(patterns_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Reconstruct patterns (simplified)
                    logger.info(f"📂 Loaded {len(data.get('patterns', {}))} pattern types")
            except Exception as e:
                logger.warning(f"Failed to load patterns: {e}")
    
    def _save_data(self):
        """Save feedback data to disk"""
        patterns_file = self.data_dir / "patterns.json"
        
        data = {
            "patterns": {k: [p.to_dict() for p in v] for k, v in self.patterns.items()},
            "updated_at": datetime.now().isoformat()
        }
        
        with open(patterns_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def record_outcome(
        self,
        call_id: str,
        tenant_id: str,
        industry: str,
        language: str,
        responses_used: List[Dict],  # List of responses with context
        outcome: CallOutcome,
        outcome_details: Dict = None
    ):
        """
        Record the outcome of a call to learn from it
        
        Args:
            call_id: Unique call identifier
            tenant_id: Tenant who made the call
            industry: Lead's industry
            language: Language used (hindi/english/hinglish)
            responses_used: List of responses with their context
            outcome: The call outcome
            outcome_details: Additional details (appointment time, etc.)
        """
        
        logger.info(f"📊 Recording outcome: {call_id} -> {outcome.value}")
        
        # Update each response pattern
        for response_data in responses_used:
            await self._update_pattern(
                response_text=response_data.get("content", ""),
                response_type=response_data.get("type", "general"),
                intent_before=response_data.get("intent", "unknown"),
                industry=industry,
                language=language,
                outcome=outcome
            )
        
        # Update industry insights
        await self._update_industry_insights(industry, outcome, responses_used)
        
        # Handle objections specifically
        for response_data in responses_used:
            if response_data.get("type") == "objection_handler":
                await self._update_objection_handler(
                    objection_type=response_data.get("objection_type", "unknown"),
                    response_text=response_data.get("content", ""),
                    industry=industry,
                    outcome=outcome
                )
        
        # Persist data periodically
        self._save_data()
    
    async def _update_pattern(
        self,
        response_text: str,
        response_type: str,
        intent_before: str,
        industry: str,
        language: str,
        outcome: CallOutcome
    ):
        """Update or create a response pattern"""
        
        # Create pattern key
        pattern_key = f"{response_type}_{industry}_{language}"
        
        # Find existing pattern or create new
        pattern_id = f"{pattern_key}_{hash(response_text) % 100000}"
        
        existing = next(
            (p for p in self.patterns[pattern_key] if p.response_text == response_text),
            None
        )
        
        if existing:
            existing.update_metrics(outcome)
        else:
            new_pattern = ResponsePattern(
                pattern_id=pattern_id,
                intent_before=intent_before,
                industry=industry,
                language=language,
                response_text=response_text,
                response_type=response_type
            )
            new_pattern.update_metrics(outcome)
            self.patterns[pattern_key].append(new_pattern)
    
    async def _update_industry_insights(
        self,
        industry: str,
        outcome: CallOutcome,
        responses_used: List[Dict]
    ):
        """Update industry-specific insights"""
        
        if industry not in self.industry_insights:
            self.industry_insights[industry] = IndustryInsights(industry=industry)
        
        insights = self.industry_insights[industry]
        insights.total_calls += 1
        
        if outcome == CallOutcome.SUCCESS:
            insights.successful_calls += 1
        
        insights.conversion_rate = insights.successful_calls / insights.total_calls
        
        # Track objections
        for response_data in responses_used:
            intent = response_data.get("intent", "")
            if "objection" in intent.lower() or response_data.get("type") == "objection_handler":
                objection_type = response_data.get("objection_type", intent)
                insights.common_objections[objection_type] = (
                    insights.common_objections.get(objection_type, 0) + 1
                )
    
    async def _update_objection_handler(
        self,
        objection_type: str,
        response_text: str,
        industry: str,
        outcome: CallOutcome
    ):
        """Update objection handler effectiveness"""
        
        if objection_type not in self.objection_handlers:
            self.objection_handlers[objection_type] = ObjectionHandler(
                objection_type=objection_type
            )
        
        handler = self.objection_handlers[objection_type]
        
        # Find or create pattern
        pattern = next(
            (p for p in handler.response_variants if p.response_text == response_text),
            None
        )
        
        if pattern:
            pattern.update_metrics(outcome)
        else:
            pattern = ResponsePattern(
                pattern_id=f"objection_{objection_type}_{len(handler.response_variants)}",
                intent_before=objection_type,
                industry=industry,
                language="hinglish",
                response_text=response_text,
                response_type="objection_handler"
            )
            pattern.update_metrics(outcome)
            handler.response_variants.append(pattern)
        
        handler._update_best()
    
    def get_best_response(
        self,
        response_type: str,
        industry: str,
        language: str = "hinglish",
        fallback: str = None
    ) -> Optional[str]:
        """
        Get the best performing response for a given context
        
        Args:
            response_type: Type of response needed (greeting, closing, etc.)
            industry: Lead's industry
            language: Language preference
            fallback: Default response if no learned response available
        
        Returns:
            Best performing response text or fallback
        """
        
        pattern_key = f"{response_type}_{industry}_{language}"
        patterns = self.patterns.get(pattern_key, [])
        
        if not patterns:
            # Try without language specificity
            for key in self.patterns:
                if key.startswith(f"{response_type}_{industry}"):
                    patterns = self.patterns[key]
                    break
        
        if not patterns:
            return fallback
        
        # Filter patterns with enough data
        valid_patterns = [p for p in patterns if p.times_used >= 3]
        
        if not valid_patterns:
            return fallback
        
        # Select best by weighted score (success_rate * confidence)
        best = max(valid_patterns, key=lambda p: p.success_rate * p.confidence)
        
        # Only use if significantly better than average
        if best.success_rate > 0.3:  # 30% success rate threshold
            return best.response_text
        
        return fallback
    
    def get_best_objection_response(
        self,
        objection_type: str,
        fallback: str = None
    ) -> Optional[str]:
        """Get best response for a specific objection"""
        
        handler = self.objection_handlers.get(objection_type)
        
        if handler and handler.best_response:
            return handler.best_response
        
        return fallback
    
    def get_industry_insights(self, industry: str) -> Optional[IndustryInsights]:
        """Get learned insights for an industry"""
        return self.industry_insights.get(industry)
    
    def get_response_options(
        self,
        response_type: str,
        industry: str,
        top_k: int = 3
    ) -> List[Tuple[str, float]]:
        """
        Get top K response options with their success rates
        Useful for A/B testing selection
        
        Returns:
            List of (response_text, success_rate) tuples
        """
        
        pattern_key = f"{response_type}_{industry}_hinglish"
        patterns = self.patterns.get(pattern_key, [])
        
        valid = [p for p in patterns if p.times_used >= 3]
        sorted_patterns = sorted(
            valid,
            key=lambda p: p.success_rate * p.confidence,
            reverse=True
        )
        
        return [
            (p.response_text, p.success_rate)
            for p in sorted_patterns[:top_k]
        ]
    
    def get_stats(self) -> Dict:
        """Get feedback loop statistics"""
        
        total_patterns = sum(len(v) for v in self.patterns.values())
        
        return {
            "total_patterns": total_patterns,
            "pattern_types": list(self.patterns.keys()),
            "industries_tracked": list(self.industry_insights.keys()),
            "objection_types": list(self.objection_handlers.keys()),
            "data_directory": str(self.data_dir)
        }
    
    async def export_learnings(self, output_file: str):
        """Export all learned patterns and insights"""
        
        export_data = {
            "patterns": {k: [p.to_dict() for p in v] for k, v in self.patterns.items()},
            "industry_insights": {
                k: asdict(v) for k, v in self.industry_insights.items()
            },
            "objection_handlers": {
                k: {
                    "objection_type": v.objection_type,
                    "best_response": v.best_response,
                    "best_success_rate": v.best_success_rate,
                    "variants_count": len(v.response_variants)
                }
                for k, v in self.objection_handlers.items()
            },
            "exported_at": datetime.now().isoformat()
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📤 Exported learnings to {output_file}")


# Singleton instance
feedback_loop = FeedbackLoop()
