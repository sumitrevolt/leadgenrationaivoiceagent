#!/usr/bin/env python3
"""PreToolUse(Edit|Write) skill-reminder hook.

Reason: skill-firing audit (2026-06-27) showed project-specific skills
(security-review/api-design/marketing-feature/...) fire ~1x despite excellent
trigger descriptions. Root cause = discipline-gap (agent skips invoking), NOT
an SDO/description gap. writing-skills says: mechanical constraint -> automate.

This injects a concise, path-targeted reminder into the model context BEFORE a
code/frontend edit. It NEVER blocks (always allows the edit) and stays silent
for docs/markdown/.claude/memory edits so it is low-noise, high-signal.

Output contract: stdout = JSON with hookSpecificOutput.additionalContext.
Empty / no relevant skills -> print nothing, exit 0.
Any internal error -> exit 0 silently (hook must never break editing).
"""
import sys
import json


def relevant_skills(path: str):
    """Map a file path to the skills whose triggers fire for it."""
    p = path.replace("\\", "/").lower()

    # Skip non-code surfaces entirely (docs, memory, the skills/config dir).
    if any(seg in p for seg in ("/.claude/", "/docs/", "/memory/", "/.git/")):
        return []
    if not p.rsplit(".", 1)[-1] in ("py", "html", "css", "js", "ts", "jsx", "tsx"):
        return []

    skills = []

    def add(*names):
        for n in names:
            if n not in skills:
                skills.append(n)

    # Tests get the contract-first discipline, nothing else.
    if "/tests/" in p or p.startswith("tests/"):
        add("tdd-contract-first")
        return skills

    # All code edits: read touch-points first.
    add("context-first")

    # API / routing surfaces.
    if "app/api/" in p or p.endswith("/main.py") or p.endswith("app/main.py"):
        add("api-design", "duplicate-route-guard")

    # Security-sensitive surfaces.
    if any(k in p for k in (
        "auth", "billing", "payment", "webhook", "public_site",
        "login", "rbac", "consent", "subscription", "packages",
    )):
        add("security-review")

    # Telephony / phone voice path.
    if any(k in p for k in (
        "app/telephony/", "vobiz", "phone_stream", "call_manager", "carrier_router",
    )):
        add("telephony-engineering")

    # Voice agent brain / web-call path.
    if any(k in p for k in ("voice_agent", "web_call", "telecaller", "free_ai")):
        add("voice-humanization")

    # Marketing feature surfaces.
    if "app/marketing/" in p or "api/marketing" in p:
        add("marketing-feature")

    # Frontend visual surfaces.
    if p.endswith(".html") or p.endswith(".css") or "frontend/" in p:
        add("design-review")

    return skills


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not path:
        return 0

    skills = relevant_skills(path)
    if not skills:
        return 0

    msg = (
        "🧭 Skill check for this edit — invoke the ones that apply (reading a "
        "skill's name is not invoking it): "
        + ", ".join(skills)
        + ". Before declaring done: self-code-review -> /verify. "
        "(Hook is a reminder, not a gate — skip a skill only if it truly does not apply.)"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg,
        },
        "suppressOutput": True,
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
