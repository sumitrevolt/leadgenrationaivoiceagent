#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell) deterministic safety guard.

Why: CLAUDE.md + the `careful` / parallel-cursor / stale-mount lessons are SOFT
(model must remember them). This hook makes the catastrophic ones HARD — the
model cannot rationalize past a deterministic gate. Directly reduces the
high-cost, hallucination/drift-driven mistakes on this repo.

Decision model (PreToolUse):
  - DENY  -> block the command, tell the model the safe alternative.
  - ASK   -> force a human confirm (implements `careful` skill automatically).
  - else  -> print NOTHING + exit 0 (normal permission flow, never auto-allow).

Fail-OPEN: any parse/internal error -> exit 0 silently. A guard must never
break the session; worst case it simply does not fire.
"""
import sys
import json
import re


# Command-boundary anchor: a dangerous command must START the line or follow a
# shell separator (newline, ;, |, &, &&, ||). This stops false-positives on the
# SAME strings appearing inside commit messages / echo / grep text — e.g. a
# commit message that merely mentions "git add -A" as documentation.
_B = r"(?:^|[\n;|&])[ \t]*"

# --- DENY: catastrophic / repo-known footguns (block outright) ---------------
DENY = [
    (_B + r"git\s+add\s+(-A\b|--all\b|\.(\s|$))",
     "`git add -A/./--all` is blocked (parallel-Cursor truncation hazard — "
     "shared files get clobbered). Stage explicit paths: `git add <path1> <path2>`."),
    (_B + r"git\s+push\b[^\n]*?(--force(?!-with-lease)|\s-f\b|\s\+[\w/])",
     "Force-push is blocked (history-rewrite risk on shared main) — incl the "
     "`git push origin +main` plus-refspec form. Use `--force-with-lease` if you "
     "truly must, after confirming with the user (`careful` skill)."),
    (_B + r"(sudo\s+)?rm\s+-[a-z]*[rf][a-z]*\s+(/|~|\$HOME|/\*)(\s|$|/)",
     "Recursive delete of `/`, `~`, or `$HOME` is blocked (catastrophic). "
     "Narrow the path to the exact target dir (`careful` skill)."),
    (r">>?\s*[\"']?\S*(CLAUDE\.md|AGENTS\.md|SESSION_LOG)",
     "Shell redirect into CLAUDE.md/AGENTS.md/SESSION_LOG is blocked "
     "(stale-mount mid-file corruption — happened before). Use the Edit tool instead."),
]

# --- ASK: risky-but-sometimes-needed (force an explicit human confirm) --------
ASK = [
    (_B + r"git\s+reset\s+--hard\b",
     "`git reset --hard` discards work and can clobber the VPS uncommitted hotfix. "
     "Confirm intent + prefer surgical `git checkout <ref> -- <paths>` (`careful` skill)."),
    (_B + r"git\s+(checkout\s+--\s|clean\s+-[a-z]*f)",
     "`git checkout -- <path>` / `git clean -f` discards uncommitted changes. Confirm first (`careful`)."),
    (_B + r"git\s+(commit|push)\b[^\n]*--no-verify\b",
     "`--no-verify` skips the pre-commit/pre-push hooks (secrets scan, lint). "
     "CLAUDE.md §8: never skip hooks unless the user explicitly asked. Confirm intent."),
    (_B + r"docker\s+(system\s+)?\w*prune\b",
     "`docker prune` can delete the ollama/observability/data volumes & images. "
     "Confirm scope; never `prune -a --volumes` on the live VPS (`careful` skill)."),
    (r"\b(DROP\s+(TABLE|DATABASE)|TRUNCATE\s+TABLE?)\b",
     "Destructive DDL (DROP/TRUNCATE) — confirm against prod DB + have a rollback/backup (`careful` skill)."),
    (r"\bDELETE\s+FROM\s+\w+\s*(;|$)(?![^;]*\bWHERE\b)",
     "`DELETE FROM <table>` with no WHERE wipes the table. Add a WHERE or confirm (`careful` skill)."),
    (_B + r"docker\s+(compose\b[^\n]*\bdown\b|stop\s+leadgen_|rm\s+leadgen_)",
     "Stopping/removing a live `leadgen_*` container takes prod down. Confirm + know the recreate path (`prod-incident-triage`)."),
]


def _decide(cmd: str):
    for pat, reason in DENY:
        if re.search(pat, cmd, re.IGNORECASE):
            return "deny", reason
    for pat, reason in ASK:
        if re.search(pat, cmd, re.IGNORECASE):
            return "ask", reason
    return None, None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = ((data.get("tool_input") or {}).get("command") or "")
    if not isinstance(cmd, str) or not cmd.strip():
        return 0

    decision, reason = _decide(cmd)
    if not decision:
        return 0  # normal flow — never auto-allow

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "🛡️ guard: " + reason,
        }
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
