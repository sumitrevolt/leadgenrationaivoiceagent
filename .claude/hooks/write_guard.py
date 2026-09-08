#!/usr/bin/env python3
"""PreToolUse(Edit|Write) content safety guard.

Companion to guard.py (which only sees Bash|PowerShell commands). This closes
two auto-enforcement gaps the command-guard is blind to — both tied to CLAUDE.md
invariants that were previously SOFT (model-discipline only):

  1. .env overwrite  (§5/§8 "never .env values touch/overwrite"). The command
     guard catches shell redirects, but an Edit/Write aimed straight at .env
     sailed through untouched. -> ASK (force explicit human confirm). Reference
     files (.env.example/.sample/.template/.dist) are allowed silently.
  2. hardcoded secret written into ANY file (§5 "secrets kabhi committed
     file/CLAUDE.md/scripts me nahi"). High-confidence live-key signatures only,
     so placeholders ("sk-xxxx", "your-key-here") do NOT trip it. -> ASK.

Decision model mirrors guard.py: DENY / ASK / else silent-exit-0 (never
auto-allow). Fail-OPEN: any parse/internal error -> exit 0 silently. A guard
must never break editing; worst case it simply does not fire.
"""
import sys
import json
import os
import re


# Reference env files that are legitimately edited (NOT the real secret .env).
_ENV_SAFE_SUFFIX = (".example", ".sample", ".template", ".dist", ".local.example")

# High-confidence live-secret signatures. Length/charset requirements keep
# false-positives low — placeholders and env-var NAMES won't match.
_SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"),
     "a private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access-key id"),
    (re.compile(r"\bsk-[A-Za-z0-9]{24,}\b"), "an OpenAI-style secret key (sk-…)"),
    (re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b"), "a Stripe live secret key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "a GitHub personal access token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "a Slack token"),
    (re.compile(r"\bAQ\.[A-Za-z0-9_-]{22,}\b"), "a Google/Stitch-style API key (AQ.…)"),
]


def _is_real_env(path: str) -> bool:
    base = os.path.basename(path.replace("\\", "/")).lower()
    if base == ".env":
        return True
    if base.startswith(".env.") and not base.endswith(_ENV_SAFE_SUFFIX):
        return True
    return False


def _scan_secret(text: str):
    for pat, label in _SECRET_PATTERNS:
        if pat.search(text):
            return label
    return None


def _decide(path: str, content: str):
    if path and _is_real_env(path):
        return "ask", (
            "Writing to `.env` (real secret file) — CLAUDE.md forbids touching "
            ".env values without an explicit user confirm. Confirm this is "
            "intended; reference edits belong in `.env.example` (`careful` skill)."
        )
    label = _scan_secret(content)
    if label:
        return "ask", (
            f"This edit looks like it hardcodes {label} into a file — CLAUDE.md "
            "§5: secrets live ONLY in .env, never in committed/source files. "
            "Confirm, or move the value to .env and read it via os.getenv."
        )
    return None, None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    if not isinstance(path, str):
        path = ""
    # Write -> `content`; Edit -> `new_string` (the text being introduced).
    content = ""
    for k in ("content", "new_string"):
        v = ti.get(k)
        if isinstance(v, str):
            content += "\n" + v

    decision, reason = _decide(path, content)
    if not decision:
        return 0  # normal flow — never auto-allow

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "🛡️ write-guard: " + reason,
        }
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
