"""TypeSafe consumer inventory guard.

WHY THIS EXISTS (finding `talent_pool_typesafe_cost`, 2026-09-18)
-----------------------------------------------------------------
The app's only TypeSafe consumer was `app/platform/agent_talent_pool.py`, and it
was decorative in the worst way: 31 agents x 32 specializations = **992 paid
HTTP calls** at build time, whose returned answer was then looked up in a
hardcoded snake_case map, so a human-readable answer ("Cold call expert") fell
through to `"general"`. Zero modules consumed the pool at all.

A TypeSafe call that no workflow consumes is decoration, and decoration that
costs 992 round trips is a liability. It was removed
(`git checkout d4243e7a -- app/platform/agent_talent_pool.py` restores it).

This guard makes consumers an *explicit, deliberate* list: adding one is fine,
but it must be a judgment whose result actually changes downstream behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Modules allowed to reference app.platform.typesafe_integration.
# `automation_health` only reads credential_state() (config-only, no network).
ALLOWED_CONSUMERS = {
    "app/platform/automation_health.py",
    "app/agents/workers.py",
    "app/platform/key_manager.py",
    "app/platform/typesafe_executor.py",
    "app/platform/typesafe_services.py",
    # One bounded judgment routes each governed orchestrator task/session.
    "app/platform/typesafe_session_policy.py",
    # These four judgments directly rank an owner queue or drive public API
    # route results; they are runtime consumers, not synthetic pool builders.
    "app/platform/hot_queue_owner_pack.py",
    "app/platform/typesafe_middleware.py",
    "app/platform/typesafe_scraper.py",
    "app/platform/typesafe_telephony.py",
    "app/api/typesafe_routes.py",
    "app/integrations/telegram_bot.py",
    "app/integrations/telegram_typesafe.py",
    # Config-only / future placeholder — no real judgment API call.
    # intake_gate delegates to typesafe_session_policy.judge_task;
    # the typesafe_integration import is a future key-state read placeholder.
    "app/platform/typesafe_intake_gate.py",
    # smartflo_acceptance calls _ts.credential_state() (config-only, no network).
    "app/voice/smartflo_acceptance.py",
}

# A real code reference: importing the module, or using it as an object.
# Two shapes matter, both of which appear in this repo:
#   from app.platform.typesafe_integration import X        (single line)
#   from app.platform import typesafe_integration as _ts    (inside a parenthesised
#                                                         multi-line import block)
# so the leading `^` anchor cannot be used. A bare quoted PATH such as
# "app/platform/typesafe_integration.py" in a data table is excluded by the
# lookbehind: naming the module that OWNS a store is not a call into it.
_CODE_RE = re.compile(
    r"""(?x)
    \bfrom\s+[\w.]*typesafe_integration\b        # from ... import / from ... as
    |^\s*import\s+[\w.]*typesafe_integration\b    # plain import (own line)
    |(?<!["'\w./-])typesafe_integration\s*\.\s*[A-Za-z_]   # attribute access
    """
)
# `from app.platform import typesafe_integration as _ts` is the one form the
# pattern above cannot see, because here it is the IMPORTED NAME rather than part
# of the dotted path. Matched separately so the guarded set stays complete.
_IMPORT_NAME_RE = re.compile(
    r"""(?x)
    \bfrom\s+[\w.]+\s+import\s+(?:[\w,\s(]*\s)?typesafe_integration\b
    """
)

# The definition module itself never counts as a consumer.
_SELF = "app/platform/typesafe_integration.py"


def _reference_sites() -> set[str]:
    """Modules that actually import/use the integration, not merely name it.

    A plain substring scan used to do this, which also matched a PATH quoted in a
    data table. `app/platform/runtime_data_allowlist_entries.py` carries
    `"file": "app/platform/typesafe_integration.py"` to name the module that OWNS
    the `platform.typesafe_intake_trace` store, and that made this guard report a
    phantom consumer. Naming a module is not calling it, so scan for real
    references: an import of the module, or an attribute access on it.
    """
    sites: set[str] = set()
    for path in (ROOT / "app").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel == _SELF:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if _CODE_RE.search(source) or _IMPORT_NAME_RE.search(source):
            sites.add(rel)
    return sites


def test_guard_scans_real_files():
    """A guard that scans nothing is false safety."""
    assert len(list((ROOT / "app").rglob("*.py"))) > 100
    assert (ROOT / _SELF).exists()


def test_only_allowlisted_modules_reference_typesafe():
    unexpected = _reference_sites() - ALLOWED_CONSUMERS
    assert not unexpected, (
        "New TypeSafe consumer(s) detected: "
        f"{sorted(unexpected)}. If the judgment changes downstream behaviour, add "
        "the module to ALLOWED_CONSUMERS in this test with the consumer it drives. "
        "If it is decorative (or calls TypeSafe in a loop over synthetic items), "
        "do not merge it."
    )


def test_allowlist_has_no_stale_entries():
    """A stale allowlist entry hides a deleted consumer."""
    stale = ALLOWED_CONSUMERS - _reference_sites()
    assert not stale, f"ALLOWED_CONSUMERS lists modules that no longer consume: {sorted(stale)}"


def test_decorative_talent_pool_is_gone():
    """The 992-call orphan must not silently return."""
    assert not (ROOT / "app/platform/agent_talent_pool.py").exists(), (
        "agent_talent_pool.py is back — see this test's docstring before restoring it"
    )
    with pytest.raises(ImportError):
        __import__("app.platform.agent_talent_pool")


def test_admin_triage_tool_is_a_real_consumer():
    """The admin triage tool must actually call TypeSafe and persist a trace."""
    script = ROOT / "scripts/typesafe_admin_triage.py"
    src = script.read_text(encoding="utf-8")
    assert "system_one" in src, "triage tool no longer calls the System One endpoint"
    assert "typesafe_decisions.jsonl" in src, "triage tool no longer writes a trace"
    assert "downstream_action" in src, "trace must record the downstream action"
