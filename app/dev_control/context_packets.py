"""Token-saving context packets for engineering workers (pure, stdlib-first).

A worker must never re-read the whole repository or receive the full project
document set. It gets ONE reproducible packet: goal, acceptance criteria, the
relevant code excerpts, prior failed attempts, and hard do-not-change rules --
capped by size class. Packets are cache-keyed by (task_id, commit_sha,
relevant file hashes, contract_version) so they invalidate exactly when their
inputs change and never otherwise.

Redaction: reuses the existing ``app.voice_agent.guardrails`` PII redactor
(no duplicate PII library) and layers secret-shaped token masking on top.
Everything degrades gracefully -- redaction failure returns masked-by-regex
text, never crashes packet generation.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any

# Approximate tokens as chars/4 -- same convention the gateway already uses.
PACKET_TOKEN_LIMITS = {"simple": 6000, "standard": 12000, "complex": 24000}

_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("[REDACTED_KEY]", re.compile(r"\b(?:sk|rk|pk)[-_](?:live|test|proj)?[-_]?[A-Za-z0-9]{16,}\b")),
    ("[REDACTED_BEARER]", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.~+/]{16,}=*")),
    ("[REDACTED_AWS]", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("[REDACTED_JWT]", re.compile(r"\beyJ[A-Za-z0-9\-_]{8,}\.[A-Za-z0-9\-_]{8,}\.[A-Za-z0-9\-_]{8,}\b")),
    ("[REDACTED_GSTIN]", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z0-9][A-Z0-9]\b")),
    ("\\1=[REDACTED_ENV]", re.compile(r"(?im)^([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|VPA))\s*=\s*\S+")),
]


def estimate_tokens(text: str) -> int:
    return max(0, len(text or "") // 4)


def redact_packet_text(text: str) -> str:
    """PII (guardrails, reused) + secret-shaped tokens. Never raises."""
    out = text or ""
    try:
        from app.voice_agent.guardrails import get_guardrails

        out = get_guardrails().redact_pii(out)
    except Exception:
        pass  # guardrails unavailable in a hermetic context -- regex layer still runs
    for repl, pat in _SECRET_PATTERNS:
        try:
            out = pat.sub(repl, out)
        except Exception:
            continue
    return out


def file_hashes(files: dict[str, str]) -> dict[str, str]:
    """{path: content} -> {path: sha256}. Order-independent."""
    return {p: hashlib.sha256((c or "").encode("utf-8", "replace")).hexdigest() for p, c in files.items()}


def cache_key(*, task_id: str, commit_sha: str, relevant_file_hashes: dict[str, str], contract_version: str) -> str:
    payload = json.dumps(
        {
            "task_id": task_id,
            "commit_sha": commit_sha,
            "hashes": dict(sorted(relevant_file_hashes.items())),
            "contract_version": contract_version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_SECTIONS = (
    ("task_goal", "TASK GOAL"),
    ("business_impact", "BUSINESS IMPACT"),
    ("acceptance_criteria", "ACCEPTANCE CRITERIA"),
    ("relevant_decisions", "RELEVANT ARCHITECTURE DECISIONS"),
    ("relevant_files", "RELEVANT FILES"),
    ("code_excerpts", "RELEVANT CODE EXCERPTS"),
    ("related_tests", "RELATED TESTS"),
    ("known_failures", "KNOWN FAILURES"),
    ("do_not_change", "DO-NOT-CHANGE LIST"),
    ("security_rules", "SECURITY AND PRIVACY RULES"),
    ("output_format", "OUTPUT FORMAT"),
    ("token_budget", "TOKEN BUDGET"),
)


def _as_lines(value: Any) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, str):
        return value.strip() or "(none)"
    if isinstance(value, dict):
        return "\n".join(f"- {k}: {v}" for k, v in value.items()) or "(none)"
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {v}" for v in value) or "(none)"
    return str(value)


def build_context_packet(
    *,
    task_id: str,
    commit_sha: str,
    contract_version: str = "v1",
    size_class: str = "standard",
    task_goal: str,
    business_impact: str = "",
    acceptance_criteria: list[str] | None = None,
    relevant_decisions: list[str] | None = None,
    relevant_files: list[str] | None = None,
    code_excerpts: list[dict[str, Any]] | None = None,
    related_tests: list[str] | None = None,
    known_failures: list[str] | None = None,
    prior_failed_attempts: list[dict[str, Any]] | None = None,
    do_not_change: list[str] | None = None,
    security_rules: list[str] | None = None,
    output_format: str = "unified diff proposal + rationale",
    token_budget: int | None = None,
    oversize_justification: str = "",
) -> dict[str, Any]:
    """Build one reproducible, size-capped, redacted context packet.

    Returns ``{"ok": True, "packet": ..., "text": ..., "tokens": ..., "cache_key": ...}``
    or ``{"ok": False, "reason": "packet_over_budget", ...}`` when the packet
    exceeds its size class and no explicit justification is given.
    """
    if size_class not in PACKET_TOKEN_LIMITS:
        return {"ok": False, "reason": "unknown_size_class", "size_class": size_class}

    excerpts_text = "\n\n".join(
        f"### {e.get('path')} (lines {e.get('start', '?')}-{e.get('end', '?')})\n```\n{e.get('text', '')}\n```"
        for e in (code_excerpts or [])
    ) or "(none)"
    failures = list(known_failures or [])
    for att in prior_failed_attempts or []:
        failures.append(
            f"prior attempt #{att.get('attempt_no', '?')} via {att.get('provider', '?')}: "
            f"{att.get('error') or att.get('outcome') or 'failed'}"
        )

    fields: dict[str, Any] = {
        "task_goal": task_goal,
        "business_impact": business_impact,
        "acceptance_criteria": acceptance_criteria or [],
        "relevant_decisions": relevant_decisions or [],
        "relevant_files": relevant_files or [],
        "code_excerpts": excerpts_text,
        "related_tests": related_tests or [],
        "known_failures": failures,
        "do_not_change": do_not_change or [],
        "security_rules": security_rules or [],
        "output_format": output_format,
        "token_budget": token_budget or PACKET_TOKEN_LIMITS[size_class],
    }
    body = "\n\n".join(f"## {title}\n{_as_lines(fields[key])}" for key, title in _SECTIONS)
    header = f"# CONTEXT PACKET task={task_id} commit={commit_sha} contract={contract_version} class={size_class}\n\n"
    text = redact_packet_text(header + body)

    tokens = estimate_tokens(text)
    limit = PACKET_TOKEN_LIMITS[size_class]
    if tokens > limit and not oversize_justification.strip():
        return {"ok": False, "reason": "packet_over_budget", "tokens": tokens, "limit": limit, "size_class": size_class}

    hashes = file_hashes({e.get("path", f"excerpt-{i}"): e.get("text", "") for i, e in enumerate(code_excerpts or [])})
    key = cache_key(task_id=task_id, commit_sha=commit_sha, relevant_file_hashes=hashes, contract_version=contract_version)
    return {
        "ok": True,
        "cache_key": key,
        "tokens": tokens,
        "limit": limit,
        "size_class": size_class,
        "oversize_justification": oversize_justification.strip() or None,
        "text": text,
        "packet": {**fields, "task_id": task_id, "commit_sha": commit_sha, "contract_version": contract_version},
    }


class PacketCache:
    """In-memory packet cache. The key already encodes every relevant input,
    so invalidation is automatic: changed file/commit/contract => new key."""

    def __init__(self, max_entries: int = 256) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._mutex = threading.Lock()
        self._max = max(1, max_entries)
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict[str, Any] | None:
        with self._mutex:
            found = self._store.get(key)
            if found is not None:
                self.hits += 1
                return dict(found)
            self.misses += 1
            return None

    def put(self, key: str, packet_result: dict[str, Any]) -> None:
        with self._mutex:
            if len(self._store) >= self._max and key not in self._store:
                self._store.pop(next(iter(self._store)))
            self._store[key] = dict(packet_result)


_DEFAULT_CACHE = PacketCache()


def default_cache() -> PacketCache:
    return _DEFAULT_CACHE
