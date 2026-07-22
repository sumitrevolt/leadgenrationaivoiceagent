"""
Context Governance & Sanitizer (M4) — Context Compaction & PII Redaction.
========================================================================

WHY (2026-07-22, Agent Harness Engineering Standard M4):
Provides context window management, sliding-window compaction with verbatim
retention of pinned system/tenant prompts, and automated secret/PII redaction
prior to sending data to LLM providers.

Import-safe; zero side-effects on import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Patterns for secret / credential redaction (M4 Governance)
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"gsk_[a-zA-Z0-9_-]{20,}", re.IGNORECASE), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"AIzaSy[a-zA-Z0-9_-]{30,40}", re.IGNORECASE), "[REDACTED_GEMINI_KEY]"),
    (re.compile(r"bearer\s+[a-zA-Z0-9\._-]{20,}", re.IGNORECASE), "Bearer [REDACTED_JWT]"),
    (re.compile(r"(?:password|passwd|secret|token)\s*=\s*['\"]?[^\s'\"]{4,}", re.IGNORECASE), "[REDACTED_CREDENTIAL]"),
]


def sanitize_prompt_text(text: str) -> str:
    """Sanitize prompt text by stripping recognized secrets, tokens, or sensitive API keys."""
    if not text:
        return ""
    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def estimate_tokens(text: str) -> int:
    """Rough token estimation (approx 4 chars per token for English/Hinglish)."""
    return max(1, len(text) // 4)


@dataclass
class ContextWindow:
    system_prompt: str
    tenant_id: str
    pinned_context: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, str]] = field(default_factory=list)
    max_tokens: int = 4000

    def get_total_tokens(self) -> int:
        sys_tokens = estimate_tokens(self.system_prompt)
        pinned_tokens = estimate_tokens(str(self.pinned_context))
        msg_tokens = sum(estimate_tokens(m.get("content", "")) for m in self.messages)
        return sys_tokens + pinned_tokens + msg_tokens

    def compact(self) -> list[dict[str, str]]:
        """Compact message history if total tokens exceed max_tokens.

        Retains system prompt & pinned context verbatim, compacts oldest turns.
        """
        if self.get_total_tokens() <= self.max_tokens or len(self.messages) <= 2:
            return [
                {"role": m["role"], "content": sanitize_prompt_text(m["content"])}
                for m in self.messages
            ]

        # Preserve the latest 2 messages verbatim, condense/truncate earlier messages
        kept_messages = self.messages[-2:]
        summary_msg = {
            "role": "system",
            "content": f"[Context Compacted: Previous {len(self.messages) - 2} turns omitted for context limit]",
        }
        compacted = [summary_msg] + kept_messages
        return [
            {"role": m["role"], "content": sanitize_prompt_text(m["content"])}
            for m in compacted
        ]
