"""
TypeSafe Lead Scraper Integration
===================================
Integrates TypeSafe Jev decisions into the lead scraping pipeline:
- Lead source quality scoring
- Scraping strategy selection
- Data validation decisions
- Deduplication intelligence
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScraperDecision:
    """Decision result from TypeSafe lead scraper integration."""
    decision_id: str
    source: str
    decision_type: str  # "quality", "strategy", "validate", "dedupe"
    result: dict[str, Any]
    confidence: float
    latency_ms: float
    timestamp: str
    source: str  # "typesafe" or "heuristic"


class TypeSafeScraper:
    """
    TypeSafe-powered lead scraper integration.
    
    Provides intelligent lead source evaluation, scraping strategy
    selection, data validation, and deduplication decisions.
    """
    
    def __init__(self):
        self.decision_log = Path("data/scraper_decisions.jsonl")
        self.decision_log.parent.mkdir(parents=True, exist_ok=True)
    
    def evaluate_source_quality(self, source_config: dict[str, Any]) -> ScraperDecision:
        """
        Evaluate lead source quality using TypeSafe.
        
        Args:
            source_config: Source configuration including name, reliability, cost
        
        Returns:
            ScraperDecision with quality assessment
        """
        start_time = time.time()
        decision_id = f"quality_{source_config.get('name', 'unknown')}_{int(time.time())}"
        
        state = {
            "source_name": source_config.get("name", ""),
            "source_type": source_config.get("type", "unknown"),
            "reliability_score": source_config.get("reliability_score", 50),
            "cost_per_lead": source_config.get("cost_per_lead", 0),
            "average_lead_quality": source_config.get("average_lead_quality", 50),
            "success_rate": source_config.get("success_rate", 0.5),
            "data_freshness": source_config.get("data_freshness", "unknown"),
            "geographic_coverage": source_config.get("geographic_coverage", "global"),
        }
        
        questions = {
            "quality_rating": {
                "type": "choice",
                "instructions": "Rate overall lead source quality.",
                "criteria": ["excellent", "good", "average", "poor", "unreliable"]
            },
            "should_use": {
                "type": "choice",
                "instructions": "Should this source be used for lead generation?",
                "criteria": ["yes_primary", "yes_secondary", "yes_occasional", "no"]
            },
            "cost_effectiveness": {
                "type": "score",
                "instructions": "Rate cost effectiveness from 0 to 100.",
                "min": 0,
                "max": 100
            }
        }
        
        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()
            
            if not client.enabled:
                logger.warning("TypeSafe not enabled, using heuristic source evaluation")
                return self._heuristic_quality(source_config, decision_id, start_time)
            
            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )
            
            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000
            
            decision = ScraperDecision(
                decision_id=decision_id,
                source=source_config.get("name", "unknown"),
                decision_type="quality",
                result={
                    "quality_rating": answers.get("quality_rating", {}).get("choice", "average"),
                    "should_use": answers.get("should_use", {}).get("choice", "yes_secondary"),
                    "cost_effectiveness": answers.get("cost_effectiveness", {}).get("score", 50),
                },
                confidence=answers.get("cost_effectiveness", {}).get("confidence", 0.5),
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            
            self._log_decision(decision)
            return decision
            
        except Exception as e:
            logger.error(f"TypeSafe source evaluation failed: {e}")
            return self._heuristic_quality(source_config, decision_id, start_time)
    
    def select_scraping_strategy(self, niche: str, target_count: int, budget: float) -> ScraperDecision:
        """
        Select optimal scraping strategy using TypeSafe.
        
        Args:
            niche: Business niche to scrape
            target_count: Number of leads target
            budget: Available budget
        
        Returns:
            ScraperDecision with strategy recommendation
        """
        start_time = time.time()
        decision_id = f"strategy_{niche}_{int(time.time())}"
        
        state = {
            "niche": niche,
            "target_count": target_count,
            "budget": budget,
            "urgency": "high" if target_count > 100 else "medium",
            "quality_requirement": "high" if budget > 1000 else "medium",
            "geographic_focus": "india" if niche in ["real_estate", "solar"] else "global",
        }
        
        questions = {
            "primary_source": {
                "type": "choice",
                "instructions": "Select primary lead source for this niche.",
                "criteria": ["google_maps", "indiamart", "justdial", "linkedin", "web_search", "social_media"]
            },
            "secondary_source": {
                "type": "choice",
                "instructions": "Select secondary source for redundancy.",
                "criteria": ["google_maps", "indiamart", "justdial", "linkedin", "web_search", "social_media"]
            },
            "scraping_frequency": {
                "type": "choice",
                "instructions": "How frequently should scraping occur?",
                "criteria": ["real_time", "hourly", "daily", "weekly"]
            },
            "quality_threshold": {
                "type": "score",
                "instructions": "Set minimum lead quality threshold (0-100).",
                "min": 0,
                "max": 100
            }
        }
        
        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()
            
            if not client.enabled:
                return self._heuristic_strategy(niche, target_count, budget, decision_id, start_time)
            
            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )
            
            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000
            
            decision = ScraperDecision(
                decision_id=decision_id,
                source=niche,
                decision_type="strategy",
                result={
                    "primary_source": answers.get("primary_source", {}).get("choice", "google_maps"),
                    "secondary_source": answers.get("secondary_source", {}).get("choice", "indiamart"),
                    "scraping_frequency": answers.get("scraping_frequency", {}).get("choice", "daily"),
                    "quality_threshold": answers.get("quality_threshold", {}).get("score", 50),
                },
                confidence=0.6,
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            
            self._log_decision(decision)
            return decision
            
        except Exception as e:
            logger.error(f"TypeSafe strategy selection failed: {e}")
            return self._heuristic_strategy(niche, target_count, budget, decision_id, start_time)
    
    def validate_lead_data(self, lead_data: dict[str, Any]) -> ScraperDecision:
        """
        Validate scraped lead data using TypeSafe.
        
        Args:
            lead_data: Raw scraped lead data
        
        Returns:
            ScraperDecision with validation result
        """
        start_time = time.time()
        decision_id = f"validate_{lead_data.get('id', 'unknown')}_{int(time.time())}"
        
        state = {
            "lead_id": lead_data.get("id", ""),
            "company_name": lead_data.get("company_name", ""),
            "phone": lead_data.get("phone", ""),
            "email": lead_data.get("email", ""),
            "address": lead_data.get("address", ""),
            "city": lead_data.get("city", ""),
            "has_phone": bool(lead_data.get("phone")),
            "has_email": bool(lead_data.get("email")),
            "has_address": bool(lead_data.get("address")),
            "source": lead_data.get("source", "unknown"),
        }
        
        questions = {
            "data_quality": {
                "type": "choice",
                "instructions": "Rate the quality of this lead data.",
                "criteria": ["excellent", "good", "acceptable", "poor", "invalid"]
            },
            "can_contact": {
                "type": "choice",
                "instructions": "Can this lead be contacted with provided data?",
                "criteria": ["yes_phone", "yes_email", "yes_either", "no"]
            },
            "needs_enrichment": {
                "type": "choice",
                "instructions": "Does this lead need additional data enrichment?",
                "criteria": ["no", "phone_only", "email_only", "full_enrichment"]
            }
        }
        
        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()
            
            if not client.enabled:
                return self._heuristic_validate(lead_data, decision_id, start_time)
            
            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )
            
            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000
            
            decision = ScraperDecision(
                decision_id=decision_id,
                source=lead_data.get("source", "unknown"),
                decision_type="validate",
                result={
                    "data_quality": answers.get("data_quality", {}).get("choice", "acceptable"),
                    "can_contact": answers.get("can_contact", {}).get("choice", "no"),
                    "needs_enrichment": answers.get("needs_enrichment", {}).get("choice", "no"),
                },
                confidence=0.6,
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            
            self._log_decision(decision)
            return decision
            
        except Exception as e:
            logger.error(f"TypeSafe validation failed: {e}")
            return self._heuristic_validate(lead_data, decision_id, start_time)
    
    def decide_deduplication(self, lead1: dict, lead2: dict) -> ScraperDecision:
        """
        Decide if two leads are duplicates using TypeSafe.
        
        Args:
            lead1: First lead data
            lead2: Second lead data
        
        Returns:
            ScraperDecision with deduplication result
        """
        start_time = time.time()
        decision_id = f"dedupe_{lead1.get('id', 'unknown')}_{lead2.get('id', 'unknown')}_{int(time.time())}"
        
        state = {
            "lead1_id": lead1.get("id", ""),
            "lead1_company": lead1.get("company_name", ""),
            "lead1_phone": lead1.get("phone", ""),
            "lead1_email": lead1.get("email", ""),
            "lead1_city": lead1.get("city", ""),
            "lead2_id": lead2.get("id", ""),
            "lead2_company": lead2.get("company_name", ""),
            "lead2_phone": lead2.get("phone", ""),
            "lead2_email": lead2.get("email", ""),
            "lead2_city": lead2.get("city", ""),
        }
        
        questions = {
            "is_duplicate": {
                "type": "choice",
                "instructions": "Are these two leads likely duplicates of the same business?",
                "criteria": ["yes_duplicate", "probably_duplicate", "maybe_duplicate", "no_duplicate"]
            },
            "confidence": {
                "type": "score",
                "instructions": "Rate confidence in duplicate determination (0-100).",
                "min": 0,
                "max": 100
            },
            "merge_action": {
                "type": "choice",
                "instructions": "What action should be taken if duplicates?",
                "criteria": ["merge_keep_first", "merge_keep_second", "merge_combine", "keep_separate"]
            }
        }
        
        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()
            
            if not client.enabled:
                return self._heuristic_dedup(lead1, lead2, decision_id, start_time)
            
            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )
            
            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000
            
            decision = ScraperDecision(
                decision_id=decision_id,
                source="deduplication",
                decision_type="dedupe",
                result={
                    "is_duplicate": answers.get("is_duplicate", {}).get("choice", "no_duplicate"),
                    "confidence": answers.get("confidence", {}).get("score", 50),
                    "merge_action": answers.get("merge_action", {}).get("choice", "keep_separate"),
                },
                confidence=answers.get("confidence", {}).get("confidence", 0.5),
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            
            self._log_decision(decision)
            return decision
            
        except Exception as e:
            logger.error(f"TypeSafe deduplication failed: {e}")
            return self._heuristic_dedup(lead1, lead2, decision_id, start_time)
    
    def _log_decision(self, decision: ScraperDecision):
        """Log decision to JSONL file."""
        try:
            with open(self.decision_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "decision_id": decision.decision_id,
                    "source": decision.source,
                    "decision_type": decision.decision_type,
                    "result": decision.result,
                    "confidence": decision.confidence,
                    "latency_ms": decision.latency_ms,
                    "timestamp": decision.timestamp,
                    "source_type": decision.source,
                }) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log scraper decision: {e}")
    
    # Heuristic fallbacks
    
    def _heuristic_quality(self, source_config: dict, decision_id: str, start_time: float) -> ScraperDecision:
        """Fallback heuristic for source quality."""
        reliability = source_config.get("reliability_score", 50)
        cost = source_config.get("cost_per_lead", 0)
        
        if reliability >= 80 and cost < 10:
            quality, should_use = "excellent", "yes_primary"
        elif reliability >= 60:
            quality, should_use = "good", "yes_secondary"
        elif reliability >= 40:
            quality, should_use = "average", "yes_occasional"
        else:
            quality, should_use = "poor", "no"
        
        return ScraperDecision(
            decision_id=decision_id,
            source=source_config.get("name", "unknown"),
            decision_type="quality",
            result={
                "quality_rating": quality,
                "should_use": should_use,
                "cost_effectiveness": reliability
            },
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    
    def _heuristic_strategy(self, niche: str, target_count: int, budget: float, decision_id: str, start_time: float) -> ScraperDecision:
        """Fallback heuristic for strategy selection."""
        default_sources = {
            "real_estate": ("google_maps", "indiamart"),
            "solar": ("google_maps", "justdial"),
            "logistics": ("google_maps", "indiamart"),
            "digital_marketing": ("linkedin", "google_maps"),
        }
        
        primary, secondary = default_sources.get(niche, ("google_maps", "indiamart"))
        frequency = "real_time" if target_count > 500 else "daily" if target_count > 100 else "weekly"
        
        return ScraperDecision(
            decision_id=decision_id,
            source=niche,
            decision_type="strategy",
            result={
                "primary_source": primary,
                "secondary_source": secondary,
                "scraping_frequency": frequency,
                "quality_threshold": 50
            },
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    
    def _heuristic_validate(self, lead_data: dict, decision_id: str, start_time: float) -> ScraperDecision:
        """Fallback heuristic for validation."""
        has_phone = bool(lead_data.get("phone"))
        has_email = bool(lead_data.get("email"))
        
        if has_phone and has_email:
            quality, can_contact, needs = "excellent", "yes_either", "no"
        elif has_phone or has_email:
            quality, can_contact, needs = "good", "yes_phone" if has_phone else "yes_email", "phone_only" if not has_phone else "email_only"
        else:
            quality, can_contact, needs = "poor", "no", "full_enrichment"
        
        return ScraperDecision(
            decision_id=decision_id,
            source=lead_data.get("source", "unknown"),
            decision_type="validate",
            result={
                "data_quality": quality,
                "can_contact": can_contact,
                "needs_enrichment": needs
            },
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    
    def _heuristic_dedup(self, lead1: dict, lead2: dict, decision_id: str, start_time: float) -> ScraperDecision:
        """Fallback heuristic for deduplication."""
        company1 = lead1.get("company_name", "").lower().strip()
        company2 = lead2.get("company_name", "").lower().strip()
        phone1 = lead1.get("phone", "").strip()
        phone2 = lead2.get("phone", "").strip()
        
        if company1 == company2 or (phone1 and phone2 and phone1 == phone2):
            is_dup, confidence, action = "yes_duplicate", 90, "merge_combine"
        elif company1 and company2 and (company1 in company2 or company2 in company1):
            is_dup, confidence, action = "probably_duplicate", 70, "merge_keep_first"
        else:
            is_dup, confidence, action = "no_duplicate", 95, "keep_separate"
        
        return ScraperDecision(
            decision_id=decision_id,
            source="deduplication",
            decision_type="dedupe",
            result={
                "is_duplicate": is_dup,
                "confidence": confidence,
                "merge_action": action
            },
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# Singleton instance
_scraper: Optional[TypeSafeScraper] = None


def get_scraper() -> TypeSafeScraper:
    """Get or create singleton TypeSafeScraper."""
    global _scraper
    if _scraper is None:
        _scraper = TypeSafeScraper()
    return _scraper


def evaluate_source(source_config: dict) -> ScraperDecision:
    """Quick function to evaluate source quality."""
    return get_scraper().evaluate_source_quality(source_config)


def select_strategy(niche: str, target_count: int, budget: float) -> ScraperDecision:
    """Quick function to select scraping strategy."""
    return get_scraper().select_scraping_strategy(niche, target_count, budget)


def validate_lead(lead_data: dict) -> ScraperDecision:
    """Quick function to validate lead data."""
    return get_scraper().validate_lead_data(lead_data)


def decide_dedup(lead1: dict, lead2: dict) -> ScraperDecision:
    """Quick function to decide deduplication."""
    return get_scraper().decide_deduplication(lead1, lead2)


__all__ = [
    "TypeSafeScraper",
    "ScraperDecision",
    "get_scraper",
    "evaluate_source",
    "select_strategy",
    "validate_lead",
    "decide_dedup",
]
