"""
TypeSafe Integration Module
Uses TypeSafe API for AI-powered judgments
"""
import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# TypeSafe API configuration
#
# SECURITY (2026-09-17): a LIVE ~100-char API key was hardcoded here as the
# `os.getenv(...)` FALLBACK DEFAULT (introduced in 7317f990). That is worse than
# a plain literal, because `check_secrets.py` could not see it: its generic
# pattern requires `KEY = "<value>"`, and the getenv form is `KEY = os.getenv(`
# — so all 12 patterns missed it and `--all` reported "[OK] no secrets detected"
# across 4272 files while the key sat in plain sight.
#
# The literal has been REMOVED. Read order:
#   1. env var TYPEsafe_API_KEY   (production: /opt/leadgen/.env)
#   2. "" (empty) -> the integration is INERT, not silently authenticated.
# The exposed key is in git history (7317f990) and MUST be revoked/rotated by
# the owner — deleting the line here does NOT un-expose it.
#
# MODEL (2026-09-18): Canonical model is `jev-latest` (owner-verified via Playground).
# Configurable via TYPESAFE_MODEL env var; defaults to jev-latest.
TYPEsafe_API_KEY = os.getenv("TYPEsafe_API_KEY", "").strip() or ""
TYPEsafe_BASE_URL = "https://api.typesafe.ai/v1"
TYPEsafe_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")

@dataclass
class TypeSafeResponse:
    """Response from TypeSafe API"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    @property
    def value(self):
        """Get the primary value from result"""
        if self.result:
            return self.result.get("value") or self.result.get("choice") or self.result.get("score")
        return None
    
    @property
    def confidence(self):
        """Get confidence score"""
        if self.result:
            return self.result.get("confidence", 0.5)
        return 0.5

class TypeSafeClient:
    """TypeSafe API client for AI judgments"""
    
    def __init__(self, api_key: str = TYPEsafe_API_KEY):
        self.api_key = (api_key or "").strip()
        self.base_url = TYPEsafe_BASE_URL
        self.model = TYPEsafe_MODEL
        self._initialized = False
        # Fail-closed: with no key configured the client stays INERT and never
        # sends an unauthenticated/blank-Authorization request. Callers already
        # treat `success=False` as "judgment unavailable" and fall back, so this
        # degrades quietly instead of silently issuing broken calls.
        self.enabled = bool(self.api_key)
    
    def initialize(self) -> TypeSafeResponse:
        """Initialize and test connection"""
        try:
            # Test connection with simple judgment
            result = self._make_request("POST", "/health")
            self._initialized = True
            logger.info(f"TypeSafe initialized successfully: {result}")
            return TypeSafeResponse(success=True, result=result)
        except Exception as e:
            logger.error(f"TypeSafe initialization failed: {e}")
            return TypeSafeResponse(success=False, error=str(e))
    
    def choice(self, question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
        """
        Make a choice judgment using TypeSafe
        
        Args:
            question: The question to ask
            state: Current state/context
            criteria: Possible choices with descriptions
        
        Returns:
            TypeSafeResponse with selected choice
        """
        try:
            payload = {
                "model": self.model,
                "question": question,
                "state": state,
                "criteria": criteria
            }
            
            result = self._make_request("POST", "/choice", payload)
            return TypeSafeResponse(success=True, result=result)
            
        except Exception as e:
            logger.error(f"TypeSafe choice failed: {e}")
            return TypeSafeResponse(success=False, error=str(e))
    
    def noul(self, question: str, state: Dict[str, Any]) -> TypeSafeResponse:
        """
        Make a binary (yes/no) judgment using TypeSafe
        
        Args:
            question: The question to ask
            state: Current state/context
        
        Returns:
            TypeSafeResponse with probability
        """
        try:
            payload = {
                "model": self.model,
                "question": question,
                "state": state
            }
            
            result = self._make_request("POST", "/noul", payload)
            return TypeSafeResponse(success=True, result=result)
            
        except Exception as e:
            logger.error(f"TypeSafe noul failed: {e}")
            return TypeSafeResponse(success=False, error=str(e))
    
    def score(self, question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
        """
        Make a scoring judgment using TypeSafe
        
        Args:
            question: The question to ask
            state: Current state/context
            criteria: Score levels with descriptions
        
        Returns:
            TypeSafeResponse with score value
        """
        try:
            payload = {
                "model": self.model,
                "question": question,
                "state": state,
                "criteria": criteria
            }
            
            result = self._make_request("POST", "/score", payload)
            return TypeSafeResponse(success=True, result=result)
            
        except Exception as e:
            logger.error(f"TypeSafe score failed: {e}")
            return TypeSafeResponse(success=False, error=str(e))
    
    def _make_request(self, method: str, endpoint: str, payload: Dict = None) -> Dict:
        """Make HTTP request to TypeSafe API"""
        import requests
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.request(method, url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def is_initialized(self) -> bool:
        """Check if client is initialized"""
        return self._initialized

# Global client instance
_typesafe_client = None

def get_typesafe_client() -> TypeSafeClient:
    """Get or create TypeSafe client singleton"""
    global _typesafe_client
    if _typesafe_client is None:
        _typesafe_client = TypeSafeClient()
        _typesafe_client.initialize()
    return _typesafe_client

def typesafe_choice(question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
    """Convenience function for choice judgments"""
    return get_typesafe_client().choice(question, state, criteria)

def typesafe_noul(question: str, state: Dict[str, Any]) -> TypeSafeResponse:
    """Convenience function for binary judgments"""
    return get_typesafe_client().noul(question, state)

def typesafe_score(question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
    """Convenience function for scoring judgments"""
    return get_typesafe_client().score(question, state, criteria)
