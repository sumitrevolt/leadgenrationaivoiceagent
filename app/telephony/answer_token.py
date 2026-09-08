"""HMAC-signed answer-URL token (stateless, no store).

PROBLEM: the public Vobiz answer_url (`/api/webhooks/vobiz/answer`) honoured a
press-9 opt-out using the request's `From` field, which is fully attacker-
controllable — so anyone could POST `{digits:'9', From:<victim>}` and add an
arbitrary number to the do-not-call suppression list (lead-pipeline DoS).

FIX: call_manager signs the number it is dialling into the answer_url with
`settings.secret_key`; the webhook verifies the signature and suppresses the
SIGNED number, never the request `From`. An attacker can't forge a valid
signature, and a legitimate Vobiz answer-callback always carries the query we
handed it. Stateless (HMAC) so it works across the worker (mint) and web
(verify) processes without Redis. Never raises.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from app.config import settings

_TTL_S = 3600  # answer-url valid 1h — calls connect within minutes


def _secret() -> bytes:
    return (getattr(settings, "secret_key", "") or "leadgen-fallback-secret").encode()


def sign(to: str, exp: int | None = None) -> tuple[str, int]:
    """Return (sig, exp) for a dialled number. exp = unix seconds it stops being valid."""
    exp = int(exp or (int(time.time()) + _TTL_S))
    sig = hmac.new(_secret(), f"{to}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return sig, exp


def verify(to: str, exp: str | int, sig: str) -> bool:
    """True iff sig matches `to.exp` and exp is not in the past. Never raises."""
    try:
        if not to or not sig:
            return False
        exp_i = int(exp)
        if exp_i < int(time.time()):
            return False
        good, _ = sign(to, exp_i)
        return hmac.compare_digest(good, str(sig or ""))
    except Exception:
        return False
