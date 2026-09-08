"""Tests — agent-scale power features (batch harness + code_exec + browser_tools).

Hermetic, pure-python: koi real subprocess of arbitrary code, koi network, koi real
browser NAHI. Power-features (code_exec/browser) ka GATED-OFF path test hota (disabled
return), aur batch harness ek trivial async callable + checkpoint/resume pe.
asyncio.run pattern (sync tests), tmp stores monkeypatch.
"""

from __future__ import annotations

import asyncio

import pytest


# ----------------------------- batch harness ----------------------------- #
def _patch_batch_dir(monkeypatch, tmp_path):
    from app.agents import batch_harness as bh

    monkeypatch.setattr(bh, "_DIR", str(tmp_path / "batch_runs"))
    return bh


def test_batch_runs_trivial_async_callable(tmp_path, monkeypatch):
    bh = _patch_batch_dir(monkeypatch, tmp_path)

    async def fn(item):
        return {"ok": True, "summary": f"got:{item}"}

    res = asyncio.run(bh.run_batch(fn, [1, 2, 3, 4, 5], concurrency=2, ckpt_id="t1"))
    assert res["ok"] is True
    assert res["total"] == 5
    assert res["done"] == 5
    assert res["failed"] == 0
    assert res["ckpt_id"] == "t1"


def test_batch_one_failure_does_not_kill_batch(tmp_path, monkeypatch):
    bh = _patch_batch_dir(monkeypatch, tmp_path)

    async def fn(item):
        if item == 3:
            raise ValueError("boom")  # ek item fail
        return {"ok": True}

    res = asyncio.run(bh.run_batch(fn, [1, 2, 3, 4], concurrency=4, ckpt_id="t2"))
    assert res["total"] == 4
    assert res["done"] == 3
    assert res["failed"] == 1
    assert res["ok"] is False  # failed>0


def test_batch_resume_skips_done_indices(tmp_path, monkeypatch):
    bh = _patch_batch_dir(monkeypatch, tmp_path)
    calls = {"n": 0}

    async def fn(item):
        calls["n"] += 1
        return {"ok": True}

    # first run completes all
    res1 = asyncio.run(bh.run_batch(fn, [1, 2, 3], concurrency=2, ckpt_id="resume1"))
    assert res1["done"] == 3
    first_calls = calls["n"]

    # second run, SAME ckpt_id → all skipped, fn not re-invoked
    res2 = asyncio.run(bh.run_batch(fn, [1, 2, 3], concurrency=2, ckpt_id="resume1"))
    assert res2["skipped"] == 3
    assert res2["done"] == 0
    assert calls["n"] == first_calls  # fn not called again


def test_batch_concurrency_clamped(tmp_path, monkeypatch):
    bh = _patch_batch_dir(monkeypatch, tmp_path)

    async def fn(item):
        return {"ok": True}

    # huge + tiny both must complete fine (internal clamp [1,16])
    res_hi = asyncio.run(bh.run_batch(fn, [1, 2], concurrency=9999, ckpt_id="c_hi"))
    res_lo = asyncio.run(bh.run_batch(fn, [1, 2], concurrency=0, ckpt_id="c_lo"))
    assert res_hi["done"] == 2
    assert res_lo["done"] == 2


def test_batch_list_batches(tmp_path, monkeypatch):
    bh = _patch_batch_dir(monkeypatch, tmp_path)

    async def fn(item):
        return {"ok": True}

    asyncio.run(bh.run_batch(fn, [1, 2], ckpt_id="listme"))
    runs = bh.list_batches()
    assert any(r["ckpt_id"] == "listme" for r in runs)


def test_batch_enabled_default_off(monkeypatch):
    from app.agents import batch_harness as bh

    monkeypatch.delenv("BATCH_HARNESS", raising=False)
    assert bh.enabled() is False


# ----------------------------- code_exec (GATED OFF) ----------------------------- #
def test_code_exec_disabled_by_default_runs_nothing(monkeypatch):
    from app.agents import code_exec

    monkeypatch.delenv("CODE_EXEC", raising=False)
    assert code_exec.enabled() is False
    # Even a script that WOULD have side-effects must NOT run — disabled returns early.
    res = asyncio.run(code_exec.execute("import os; os.system('echo hi')"))
    assert res["ok"] is False
    assert res["error"] == "disabled"
    assert res["hint"] == "set CODE_EXEC=1"


def test_code_exec_enabled_flag_parsing(monkeypatch):
    from app.agents import code_exec

    monkeypatch.setenv("CODE_EXEC", "1")
    assert code_exec.enabled() is True
    monkeypatch.setenv("CODE_EXEC", "no")
    assert code_exec.enabled() is False


# ----------------------------- browser_tools (GATED OFF) ----------------------------- #
def test_browser_disabled_by_default(monkeypatch):
    from app.agents import browser_tools

    monkeypatch.delenv("BROWSER_TOOLS", raising=False)
    assert browser_tools.enabled() is False
    res = asyncio.run(browser_tools.fetch_rendered("https://example.com"))
    assert res["ok"] is False
    assert res["error"] == "disabled"

    res2 = asyncio.run(browser_tools.extract("https://example.com", "h1"))
    assert res2["ok"] is False
    assert res2["error"] == "disabled"


def test_browser_enabled_but_no_playwright_is_graceful(monkeypatch):
    """Flag ON par bhi playwright import fail → graceful, NO real browser launch."""
    import builtins

    from app.agents import browser_tools

    monkeypatch.setenv("BROWSER_TOOLS", "1")
    # SSRF guard offline DNS-fail pe fail-closed block karta — is test ka target
    # playwright-missing path hai; guard ka apna suite hai (test_browser_tools_ssrf).
    monkeypatch.setattr(browser_tools, "_url_is_safe", lambda url: True)
    real_import = builtins.__import__

    def _no_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("simulated: playwright not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_playwright)
    res = asyncio.run(browser_tools.fetch_rendered("https://example.com"))
    assert res["ok"] is False
    assert res["error"] == "playwright_not_installed"


# ----------------------------- router import sanity ----------------------------- #
def test_router_imports_and_has_routes():
    from app.api import agent_scale

    paths = {r.path for r in agent_scale.router.routes}
    # prefix-less here; mount adds /api/agents-ext
    assert "/batch" in paths
    assert "/exec" in paths
    assert "/browser/fetch" in paths
    assert "/status" in paths


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
