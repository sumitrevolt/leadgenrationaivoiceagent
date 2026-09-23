"""Inline test runner for the dispatcher (avoiding pytest collection hang)."""
from __future__ import annotations

import importlib
import sys
import time
import traceback
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKTREE))

import tests.test_telegram_owner_command_dispatcher as t  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
ERROR = "ERROR"

results: list[tuple[str, str, str]] = []


def run_one(name, fn) -> None:
    started = time.time()
    try:
        fn()
        results.append((name, PASS, ""))
    except AssertionError as e:
        results.append((name, FAIL, f"AssertionError: {e}"))
    except Exception as e:  # noqa: BLE001
        results.append(
            (name, ERROR, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=2)}")
        )


def main() -> int:
    tests = [
        n for n, _ in [
            (n, getattr(t, n))
            for n in dir(t)
            if n.startswith("test_") and callable(getattr(t, n))
        ]
    ]
    tests.sort()

    # Each test that uses fixtures expects pytest to inject them. We invoke
    # them manually: signature-driven by fixture name.
    import inspect
    import os

    # Build a fake pytest fixture substitution
    def _build_env_for_test(name, fn):
        sig = inspect.signature(fn)
        kwargs = {}
        for fname, param in sig.parameters.items():
            if fname == "owner_chat_id":
                os.environ["TELEGRAM_OWNER_CHAT_IDS"] = "1621120182"
                kwargs[fname] = 1621120182
            elif fname == "ready_task":
                kwargs[fname] = t._FakeTask(task_id="task_79406871", status="READY", assigned_agent="hermes")
            elif fname == "env":
                rt = kwargs.get("ready_task") or t._FakeTask(task_id="task_79406871", status="READY", assigned_agent="hermes")
                store = t._FakeStore(tasks={rt.id: rt})
                orch = t._FakeOrchestrator(store)
                bot = t._FakeBot(ok=True, message_id=424242)
                import types
                kwargs[fname] = types.SimpleNamespace(store=store, orch=orch, bot=bot, task=rt)
            elif fname == "monkeypatch":
                # Build a minimal monkeypatch stand-in (only setattr used here)
                class _MiniMonkey:
                    def __init__(self):
                        self._saved = {}
                    def setattr(self, target, name, value=None):
                        # signature: monkeypatch.setattr(target, name, value)
                        # Sometimes 2-arg form: monkeypatch.setattr(target_string, value)
                        # The dispatcher tests use the 3-arg form.
                        pass
                    def setenv(self, key, value):
                        self._saved.setdefault(("env", key), os.environ.get(key))
                        os.environ[key] = value
                    def delenv(self, key, raising=True):
                        self._saved.setdefault(("env", key), os.environ.get(key))
                        os.environ.pop(key, None)
                    def undo(self):
                        for (kind, key), old in self._saved.items():
                            if kind == "env":
                                if old is None:
                                    os.environ.pop(key, None)
                                else:
                                    os.environ[key] = old
                kwargs[fname] = _MiniMonkey()
        return kwargs

    for name in tests:
        fn = getattr(t, name)
        # Reuse the inline dispatcher's manual signature fixture resolver
        # to keep tests honest.
        try:
            kwargs = _build_env_for_test(name, fn)
        except Exception as e:
            results.append((name, ERROR, f"fixture_build:{type(e).__name__}:{e}"))
            continue
        # Tests use both `monkeypatch.setattr(target, name, value)` and
        # `monkeypatch.setattr("target_string", value)` forms. Our minimal
        # monkey above only exposes setattr for 3-arg form. We monkey-patch
        # the function to dispatch correctly.
        if "monkeypatch" in kwargs:
            mp = kwargs["monkeypatch"]
            def _setattr(target, name_or_value, value=None):
                if value is None:
                    # 2-arg form: setattr(target_string, value) — module-level
                    parts = target.rsplit(".", 1)
                    if len(parts) == 2:
                        mod_name, attr = parts
                        import importlib
                        mod = importlib.import_module(mod_name)
                        old = getattr(mod, attr, None)
                        setattr(mod, attr, name_or_value)
                        # queue restore
                        if not hasattr(mp, "_attrs"):
                            mp._attrs = []
                        mp._attrs.append((mod, attr, old))
                    else:
                        raise ValueError("2-arg setattr form not supported here")
                else:
                    # 3-arg form: setattr(target, name, value) — instance attribute
                    old = getattr(target, name_or_value, None)
                    setattr(target, name_or_value, value)
                    if not hasattr(mp, "_attrs"):
                        mp._attrs = []
                    mp._attrs.append((target, name_or_value, old))
            mp.setattr = _setattr
            # Patch undo to also restore attribute changes
            orig_undo = mp.undo
            def _undo_with_attrs():
                orig_undo()
                if hasattr(mp, "_attrs"):
                    for target, name, old in reversed(mp._attrs):
                        if old is None:
                            try:
                                delattr(target, name)
                            except AttributeError:
                                pass
                        else:
                            setattr(target, name, old)
                    mp._attrs = []
            mp.undo = _undo_with_attrs
        try:
            fn(**kwargs)
            results.append((name, PASS, ""))
        except AssertionError as e:
            results.append((name, FAIL, f"AssertionError: {e}"))
        except Exception as e:
            results.append(
                (name, ERROR, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=2)}")
            )
        # restore env
        if "monkeypatch" in kwargs:
            try:
                kwargs["monkeypatch"].undo()
            except Exception:
                pass

    # Print results
    n_pass = sum(1 for _, s, _ in results if s == PASS)
    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    n_err = sum(1 for _, s, _ in results if s == ERROR)
    print(f"\n=== {len(results)} tests: {n_pass} pass / {n_fail} fail / {n_err} error ===")
    for name, status, msg in results:
        line = f"  [{status}] {name}"
        if msg:
            line += f"\n      {msg[:300]}"
        print(line)

    return 0 if (n_fail == 0 and n_err == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
