"""HMAC-signed Vobiz media-stream token (stateless, no store) — INERT by default.

PROBLEM (2026-07-06 security sweep, [M]): the media WebSocket at
`/api/telephony/vobiz/stream/{token}` runs a full STT->LLM->TTS conversation
loop for ANY token — `answer_stream_xml` deliberately serves unknown tokens
(niche=general) because a legit call is already live when Vobiz fetches it. But
that same leniency means an anonymous attacker who reaches the WS and speaks the
wire protocol can burn the free-AI capacity (the #1 bottleneck). Unlike Twilio
webhooks there is no signature.

FIX: OUR outbound `/stream-call` mints a raw uuid token, `sign()`s it, and hands
the signed form to Vobiz. A signed token is STABLE, so it still `verify()`s on a
mid-call WS reconnect AFTER `_pop_pending` removed the pending state — that's the
whole point (survives the pending-pop, unlike pending-only checks). The WS then
treats "pending existed OR verify(token)" as known, and (only when explicitly
gated on) rejects everything else.

INERT DEFAULT: the secret comes from `VOBIZ_STREAM_SECRET` at call-time. If it is
unset, `sign()` returns the raw token unchanged and `verify()` returns True — so
with no env set there is ZERO behavior change. Rejection is a second, separate
opt-in (`VOBIZ_STREAM_REQUIRE_TOKEN`) enforced by the caller. Stdlib-only (no
app imports) so INERT stays self-contained and circular-import-free. Never raises.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

_TTL_S = 3600  # signed token valid 1h — calls connect within minutes; a long
#                live call's reconnect still lands inside this window.
_SIG_LEN = 16  # sig = first 16 hex chars of the HMAC-SHA256 digest.


def _secret() -> str:
    """Signing secret from env, read at call-time (empty = INERT)."""
    return (os.getenv("VOBIZ_STREAM_SECRET") or "").strip()


def _sig(raw: str, exp: int, secret: str) -> str:
    return hmac.new(secret.encode(), f"{raw}.{exp}".encode(), hashlib.sha256).hexdigest()[:_SIG_LEN]


def sign(raw: str, exp: int | None = None) -> str:
    """Return a signed token ``"<raw>.<exp>.<sig>"`` for a raw token string.

    INERT: if `VOBIZ_STREAM_SECRET` is unset, returns `raw` unchanged (the token
    Vobiz receives is then identical to today's uuid — zero behavior change).
    `exp` = unix seconds the signature stops being valid (default now+1h);
    exposed for tests. Never raises — on any error returns `raw` as-is (fail-open
    minting; a call must never be dropped by a signing bug)."""
    try:
        secret = _secret()
        if not secret:
            return raw
        exp_i = int(exp if exp is not None else int(time.time()) + _TTL_S)
        return f"{raw}.{exp_i}.{_sig(raw, exp_i, secret)}"
    except Exception:
        return raw


def verify(token: str) -> bool:
    """True iff `token` carries a valid, unexpired signature for the current
    secret. Constant-time compare (`hmac.compare_digest`).

    INERT: if `VOBIZ_STREAM_SECRET` is unset, returns True (verification is a
    no-op — every token is accepted, today's behavior). Also True for a token
    that simply has no `.<exp>.<sig>` suffix ONLY when inert; when a secret IS
    set, an unsigned/malformed/expired/tampered token returns False. Never raises."""
    try:
        secret = _secret()
        if not secret:
            return True  # inert — accept everything (current behavior)
        parts = (token or "").rsplit(".", 2)
        if len(parts) != 3:
            return False
        raw, exp_s, sig = parts
        exp_i = int(exp_s)
        if exp_i < int(time.time()):
            return False  # expired
        return hmac.compare_digest(_sig(raw, exp_i, secret), sig)
    except Exception:
        return False
