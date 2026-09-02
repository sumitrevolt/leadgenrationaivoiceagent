"""
Network Guard for pytest — blocks real external network calls so the full
test suite completes offline without hanging.

HOW IT WORKS
------------
We monkey-patch the three lowest-level socket entry-points:
  • socket.socket.connect / connect_ex
  • socket.create_connection
  • socket.getaddrinfo  (catches DNS resolution before connect)

WHAT IS ALLOWED
---------------
  • localhost / 127.0.0.1 / ::1  (local DB, in-process TestClient, etc.)
  • UNIX-domain sockets           (path-based, e.g. /var/run/…)
  • Any call that passes through ASGITransport — TestClient never opens a
    real socket at all, so it is completely unaffected.

WHAT IS BLOCKED
---------------
Everything else: LLM providers (Cerebras, Groq, Gemini, OpenRouter),
Exotel, HuggingFace model downloads, Google Maps, SMTP, Redis on VPS, etc.
They raise RuntimeError immediately → app's try/except catches it → fast
fallback / skip, NO hang.

Usage (called from conftest.py at import time)::

    from tests._netguard import enable
    enable()
"""

from __future__ import annotations

import builtins
import socket as _socket_module

# ── helpers ──────────────────────────────────────────────────────────────────

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", ""})

# These AF_* constants are always present on every platform
_AF_INET = _socket_module.AF_INET
_AF_INET6 = _socket_module.AF_INET6
try:
    _AF_UNIX = _socket_module.AF_UNIX  # not on Windows, but safe guard
except AttributeError:
    _AF_UNIX = None


def _addr_is_local(address) -> bool:
    """Return True if the target address is local (allow) or a UNIX socket."""
    if address is None:
        return True  # can't block what we can't inspect

    # UNIX domain socket: address is a string path or bytes
    if isinstance(address, (str, bytes)):
        # A path-based UNIX socket — always local
        return True

    # TCP/UDP: address is (host, port) or (host, port, flowinfo, scope_id)
    if isinstance(address, tuple) and len(address) >= 2:
        host = address[0]
        if isinstance(host, str):
            host_lower = host.lower().strip()
            return host_lower in _LOCAL_HOSTS
        if isinstance(host, bytes):
            return host in (b"", b"127.0.0.1", b"::1", b"localhost")

    return False  # unknown shape → block to be safe


def _block(address):
    raise RuntimeError(
        f"[netguard] Blocked external network call in tests: {address!r}. "
        "Use a mock/monkeypatch to stub this dependency."
    )


# ── original references (stored once, restored on disable()) ──────────────

_orig_connect = None
_orig_connect_ex = None
_orig_create_connection = None
_orig_getaddrinfo = None

_enabled = False


# ── patched implementations ───────────────────────────────────────────────


def _patched_connect(self, address):
    if not _addr_is_local(address):
        _block(address)
    return _orig_connect(self, address)


def _patched_connect_ex(self, address):
    if not _addr_is_local(address):
        _block(address)
    return _orig_connect_ex(self, address)


def _patched_create_connection(
    address,
    timeout=_socket_module._GLOBAL_DEFAULT_TIMEOUT,
    source_address=None,
    *,
    all_errors=False,
):
    if not _addr_is_local(address):
        _block(address)
    # Forward to original — signature varies across Python 3.10/3.11/3.12
    try:
        return _orig_create_connection(address, timeout, source_address, all_errors=all_errors)
    except TypeError:
        return _orig_create_connection(address, timeout, source_address)


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    # Allow local / numeric addresses through; block named external hosts
    host_str = host if isinstance(host, str) else (host.decode() if host else "")
    host_lower = host_str.lower().strip()
    if host_lower and host_lower not in _LOCAL_HOSTS:
        # Check if it looks like an IP (do NOT block numeric IPs — they go
        # straight to connect which we also guard, but let getaddrinfo pass
        # so we get a clean socket error rather than a dns-level one for
        # numeric addresses like "127.0.0.1").
        is_numeric = False
        try:
            _socket_module.inet_aton(host_str)  # IPv4 numeric
            is_numeric = True
        except Exception:
            pass
        if not is_numeric:
            try:
                _socket_module.inet_pton(_AF_INET6, host_str)  # IPv6 numeric
                is_numeric = True
            except Exception:
                pass
        if not is_numeric:
            _block(f"DNS lookup for {host!r}:{port}")
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


# ── public API ────────────────────────────────────────────────────────────


def enable() -> None:
    """Install the network guard. Safe to call multiple times (idempotent)."""
    global _enabled, _orig_connect, _orig_connect_ex
    global _orig_create_connection, _orig_getaddrinfo

    if _enabled:
        return

    try:
        _orig_connect = _socket_module.socket.connect
        _orig_connect_ex = _socket_module.socket.connect_ex
        _orig_create_connection = _socket_module.create_connection
        _orig_getaddrinfo = _socket_module.getaddrinfo

        _socket_module.socket.connect = _patched_connect
        _socket_module.socket.connect_ex = _patched_connect_ex
        _socket_module.create_connection = _patched_create_connection
        _socket_module.getaddrinfo = _patched_getaddrinfo

        _enabled = True
    except Exception as exc:
        # NEVER break pytest collection — silently log and give up
        import warnings

        warnings.warn(
            f"[netguard] Could not install network guard: {exc!r}. "
            "Tests may hang on real network calls.",
            RuntimeWarning,
            stacklevel=2,
        )


def disable() -> None:
    """Remove the network guard and restore originals."""
    global _enabled

    if not _enabled:
        return

    try:
        if _orig_connect is not None:
            _socket_module.socket.connect = _orig_connect
        if _orig_connect_ex is not None:
            _socket_module.socket.connect_ex = _orig_connect_ex
        if _orig_create_connection is not None:
            _socket_module.create_connection = _orig_create_connection
        if _orig_getaddrinfo is not None:
            _socket_module.getaddrinfo = _orig_getaddrinfo
        _enabled = False
    except Exception as exc:
        import warnings

        warnings.warn(f"[netguard] Could not restore originals: {exc!r}", RuntimeWarning)
