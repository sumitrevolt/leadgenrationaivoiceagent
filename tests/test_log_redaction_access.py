"""Access-log credential redaction.

Regression lock for a live prod leak found 2026-09-11: uvicorn's access logger
carries its own formatter, so the module-level redaction in `app.utils.logger`
never touched it and a real webhook token landed in `leadgen_app` logs:

    INFO: 172.16.1.3:0 - "POST /api/wa/selfhost/webhook?token=<live token> HTTP/1.1" 200 OK

These tests assert the LogRecord-level filter strips it, and that the filter is
fail-safe (never drops or corrupts a record).
"""

import logging

from app.utils.logger import UvicornAccessRedactionFilter, install_access_log_redaction

# Sentinel values that must never survive the filter. These are deliberately
# fake strings used as redaction targets — not credentials. `nosecret` marker
# keeps scripts/check_secrets.py from flagging them as leaked secrets.
_TOKEN = "supersecretvalue123abc"  # nosecret
_APIKEY = "abcdef123456789"  # nosecret
_SIG = "deadbeefcafebabe"  # nosecret
_ACCESS = "xyz987654321zzz"  # nosecret


def _record(args, msg='%s - "%s %s HTTP/%s" %d'):
    """Build an uvicorn.access-style LogRecord."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_query_string_token_is_redacted():
    rec = _record(
        ("172.16.1.3:0", "POST", f"/api/wa/selfhost/webhook?token={_TOKEN}", "1.1", 200)
    )
    UvicornAccessRedactionFilter().filter(rec)
    out = rec.getMessage()
    assert _TOKEN not in out, out
    assert "[REDACTED]" in out, out
    # The path itself must survive — logs stay useful.
    assert "/api/wa/selfhost/webhook" in out, out
    assert "172.16.1.3:0" in out, out
    assert "200" in out, out


def test_api_key_signature_and_access_token_are_redacted():
    for qs, secret in (
        (f"api_key={_APIKEY}", _APIKEY),
        (f"signature={_SIG}", _SIG),
        (f"access_token={_ACCESS}", _ACCESS),
    ):
        rec = _record(("1.2.3.4:0", "GET", f"/cb?{qs}", "1.1", 200))
        UvicornAccessRedactionFilter().filter(rec)
        assert secret not in rec.getMessage(), rec.getMessage()


def test_clean_path_is_untouched():
    rec = _record(("1.2.3.4:0", "GET", "/health", "1.1", 200))
    before = rec.getMessage()
    UvicornAccessRedactionFilter().filter(rec)
    assert rec.getMessage() == before


def test_filter_always_returns_true():
    """A logging filter must never drop a record."""
    rec = _record(("1.2.3.4:0", "GET", "/x?token=a", "1.1", 200))
    assert UvicornAccessRedactionFilter().filter(rec) is True


def test_exact_output_shape_no_double_redaction():
    """Regression: the args pass and the message pass must not both fire on the
    same line, which produced a malformed ``token=[REDACTED]]``."""
    rec = _record(("172.16.1.3:0", "POST", f"/api/wa/selfhost/webhook?token={_TOKEN}", "1.1", 200))
    UvicornAccessRedactionFilter().filter(rec)
    out = rec.getMessage()
    assert "token=[REDACTED]" in out, out
    assert "[REDACTED]]" not in out, out


def test_install_is_idempotent_and_attaches():
    install_access_log_redaction()
    install_access_log_redaction()  # second call must be a no-op, not a duplicate
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        lg = logging.getLogger(name)
        matches = [f for f in lg.filters if isinstance(f, UvicornAccessRedactionFilter)]
        assert len(matches) == 1, f"{name} has {len(matches)} redaction filters"


def test_malformed_records_do_not_raise():
    """Fail-safe: odd args must not break logging."""
    assert UvicornAccessRedactionFilter().filter(_record(None)) is True
    assert UvicornAccessRedactionFilter().filter(_record((1, 2, 3))) is True
    assert UvicornAccessRedactionFilter().filter(_record(("a", "b"))) is True
