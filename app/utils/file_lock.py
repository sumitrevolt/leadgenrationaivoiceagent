"""Cross-process file lock for jsonl/json stores (multi-worker corruption fix).

PROBLEM: app ab 2 uvicorn workers + celery worker(s) — sab `data/*.jsonl`
stores pe likh sakte hain. Single-line APPEND (<4KB) Linux pe O_APPEND se
~atomic hota hai, par READ-MODIFY-WRITE (trim/rewrite/json.dump snapshot)
do process me ek saath chale to file TRUNCATE/corrupt ho sakti hai.

YEH UTILITY: sidecar `<path>.lock` file pe OS-level lock —
  - Linux/mac: fcntl.flock (containers me yahi chalta)
  - Windows: msvcrt.locking (dev machine)
  - dono unavailable (exotic env): graceful no-op (aaj jaisa)

Use:
    from app.utils.file_lock import file_lock
    with file_lock(path):           # default timeout 5s
        ...read-modify-write...

Timeout pe bhi block NAHI karte — lock na mile to bina lock aage badh jaate
(defensive: store-write kabhi automation ko hang nahi karna chahiye; warna
lock-file leak/crash pe sab ruk jata). KABHI raise nahi.
"""

from __future__ import annotations

import contextlib
import os
import time

try:  # Linux/mac
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - windows
    fcntl = None  # type: ignore

try:  # Windows
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover - linux
    msvcrt = None  # type: ignore


@contextlib.contextmanager
def file_lock(path: str, timeout_s: float = 5.0):
    """Sidecar-lock context manager. Lock fail/timeout = no-op passthrough."""
    lock_path = f"{path}.lock"
    fh = None
    locked = False
    try:
        try:
            os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
            fh = open(lock_path, "a+")
            deadline = time.monotonic() + max(0.1, timeout_s)
            while time.monotonic() < deadline:
                try:
                    if fcntl is not None:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                        break
                    elif msvcrt is not None:
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                        locked = True
                        break
                    else:  # no locking primitive — no-op
                        break
                except OSError:
                    time.sleep(0.05)
        except Exception:
            pass
        yield locked
    finally:
        try:
            if fh is not None:
                if locked:
                    try:
                        if fcntl is not None:
                            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                        elif msvcrt is not None:
                            fh.seek(0)
                            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                fh.close()
        except Exception:
            pass


def locked_append(path: str, line: str, timeout_s: float = 5.0) -> bool:
    """Lock ke saath single-line append. KABHI raise nahi. Return: written?"""
    try:
        with file_lock(path, timeout_s):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line.rstrip("\n") + "\n")
        return True
    except Exception:
        return False


def locked_rewrite(path: str, content: str, timeout_s: float = 5.0) -> bool:
    """Lock + ATOMIC rewrite (tmp file + os.replace) — half-written file kabhi
    visible nahi hoti, crash-safe. KABHI raise nahi. Return: written?"""
    try:
        with file_lock(path, timeout_s):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = f"{path}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
        return True
    except Exception:
        try:
            if os.path.exists(tmp):  # type: ignore[possibly-undefined]
                os.remove(tmp)  # type: ignore[possibly-undefined]
        except Exception:
            pass
        return False
