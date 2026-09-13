"""Single authority for "are we running in production?".

OPS-019 (2026-09-07, cycle 10). This predicate decides whether a fail-OPEN
escape hatch (``DND_FAIL_OPEN``, ``WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN``) is
honoured or refused. Before this module existed there were **four** independent
implementations — ``app/telephony/compliance.py::_is_production`` (settings
first, then env), ``app/platform/runtime_data.py::is_production`` (env only,
accepts ``prod``), ``app/integrations/openclaw/policies.py::is_production_env``
(env only, set membership) and ``app/config.py`` (a settings method). Four
answers to one question is how a safety flag ends up honoured in production:
the gate that refuses it and the gate that checks it must agree.

This module is the strongest of the four (settings first, env fallback) and
never raises: a probe that can crash must never be able to turn a refusal into
an approval.

Not yet unified: ``runtime_data.is_production`` and
``openclaw.policies.is_production_env`` still answer the same question their own
way. Folding them in is a behaviour change in two unrelated domains, so it is
recorded as a follow-up rather than done unattended.
"""

from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, "") or "").strip() or default


def is_production() -> bool:
    """True when this process is running in production. Never raises.

    Order matters: ``settings.is_production`` first (it is the configured
    answer), then ``ENVIRONMENT`` / ``APP_ENV`` as a fallback for the
    cached-settings mismatch case (a settings object imported before the env was
    applied). An unset environment resolves to **False** — callers that care
    must treat "unknown" as the safe side, never as "production is fine".
    """
    try:
        from app.config import settings

        if bool(getattr(settings, "is_production", False)):
            return True
    except Exception:  # noqa: BLE001 - a probe must never crash the gate
        pass
    return (_env("ENVIRONMENT") or _env("APP_ENV")).lower() == "production"


def fail_open_refused(flag: str, consequence: str) -> bool:
    """True when a fail-OPEN flag is set AND production must refuse it.

    Helper for the shared pattern: an ops escape hatch that is legitimate in
    dev/staging but must never reach production. Returns ``True`` only when the
    caller should IGNORE the flag (i.e. stay fail-closed).

    Args:
        flag: the environment variable name, for the log line.
        consequence: what staying fail-closed actually means, for the log line.
    """
    if _env(flag, "0").lower() not in ("1", "true", "yes", "on"):
        return False
    return is_production()


def refusal_message(flag: str, consequence: str) -> str:
    """The one-time CRITICAL line to log when a fail-OPEN flag is refused."""
    return (
        f"🚨 {flag}=1 IGNORED in production — {consequence}. "
        f"There is NO legitimate prod use; unset {flag}."
    )
