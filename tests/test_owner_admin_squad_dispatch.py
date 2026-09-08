"""Regression tests — owner_admin.py + squad module import/dispatch fixes.

2026-09-05 fixes under test:
1. ``owner_admin.py`` used ``from app.platform.squad_X import *`` then called
   ``squad_voice_calling()`` etc. as callables — but the squad modules export
   plain functions (``run_daily_beat``, ``run_hourly_campaign``, ...), so
   ``cmd_squad_task`` would raise NameError at runtime. Star-imports replaced
   with explicit imports and dispatch rewritten to call the real functions.
2. ``squad_voice_calling.py`` imported a non-existent ``STAFF_JOBS_VALID``
   symbol from ``team_scheduler`` — module failed to import.
3. ``squad_knowledge.py`` imported non-existent ``gen_domain_briefs`` /
   ``validate_full_os`` — moved to lazy defensive imports that call the real
   ``run()`` / ``main()`` entrypoints.
"""

import inspect

import pytest


def test_owner_admin_imports_cleanly():
    """Module imports without error (no star-import NameErrors, no broken symbols)."""
    import app.platform.owner_admin as oa

    assert oa.app is not None
    assert len(oa.app.routes) >= 1


def test_owner_admin_has_no_star_imports():
    """Star imports removed — F403/F405 class of lint + undefined-name bugs gone."""
    import app.platform.owner_admin as oa

    src = inspect.getsource(oa)
    assert "import *" not in src


def test_cmd_squad_task_resolves_no_nameerror():
    """Dispatch table calls real squad functions — no `squad_X()` callable stubs."""
    import app.platform.owner_admin as oa

    src = inspect.getsource(oa.cmd_squad_task)
    # The old broken pattern called the module name as a callable.
    for stale in ("squad_voice_calling()", "squad_marketing()", "squad_compliance()"):
        assert stale not in src

    # Dispatch to an unknown squad returns a clean error, not a raise.
    result = oa.cmd_squad_task(99)
    assert "error" in result


def test_squad_voice_calling_imports_and_runs_compliance_check():
    """squad_voice_calling imports without the stale STAFF_JOBS_VALID symbol."""
    from app.platform import squad_voice_calling as svc

    assert svc.squad_name == "Voice Calling"
    # check_compliance is deterministic local logic — must return a bool (fail-open False outside window).
    assert isinstance(svc.check_compliance(), bool)
    # run_daily_beat either runs or skips for compliance — must not raise and never leak a coroutine.
    out = svc.run_daily_beat()
    assert isinstance(out, dict)
    assert not inspect.iscoroutine(out)


def test_squad_knowledge_lazy_imports_ok():
    """squad_knowledge imports cleanly and its daily update never raises."""
    from app.platform import squad_knowledge as sk

    assert sk.squad_name == "Knowledge-OS"
    out = sk.daily_index_update()
    assert isinstance(out, dict)
    assert out.get("status") in ("index_updated",)
    # validation best-effort — must carry a status key either way
    assert "validation" in out


def test_all_squad_modules_import_cleanly():
    """Every squad_* module the owner console consumes imports without error."""
    modules = [
        "squad_billing",
        "squad_cicd",
        "squad_compliance",
        "squad_data",
        "squad_deploy",
        "squad_knowledge",
        "squad_marketing",
        "squad_monitoring",
        "squad_qa",
        "squad_voice_calling",
        "squad_whatsapp",
    ]
    for name in modules:
        __import__(f"app.platform.{name}")