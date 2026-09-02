"""P0 security regression: credentials must NEVER appear in emitted log
messages.

2026-07-11 loop-flagged: INFO-level HTTP-URL logs were suspected of exposing
query-string credentials (Meta OAuth `code=`, Postiz `api_key=`, webhook
`signature=`, etc.). This test suite locks in the centralized `redact_message`
utility in `app/utils/logger.py` and proves both formatters (ColoredFormatter
for dev/console, JSONFormatter for production) surface the sanitized message,
not the raw one.

Each test constructs a real `logging.LogRecord`, runs it through the
formatter, and asserts:
  1. The sensitive value NEVER appears in the emitted text.
  2. The `[REDACTED]` sentinel DOES appear (proving the redactor fired, not
     just that the input happened to be missing).
  3. The surrounding non-sensitive context IS preserved (so debugging still
     works).
"""

from __future__ import annotations

import json
import logging

import pytest

from app.utils import logger as log_mod


# --------------------------------------------------------------------------- #
# Pure `redact_message` unit tests
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,forbidden,expected_marker",
    [
        # OAuth code + client_secret in URL query
        (
            "callback https://leadsgenai.in/oauth/meta?code=AQD-Xh__SECRET_CODE_9876&client_secret=fbShh_TOP_SECRET_KEY",
            ("AQD-Xh__SECRET_CODE_9876", "fbShh_TOP_SECRET_KEY"),
            "[REDACTED]",
        ),
        # Postiz api_key in outgoing request log
        (
            "POST https://api.postiz.io/v1/posts?api_key=pk_live_ABCDEF1234567890XYZ&user=42",
            ("pk_live_ABCDEF1234567890XYZ",),
            "[REDACTED]",
        ),
        # Webhook signature in body log
        (
            "webhook body: signature=sha256_e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855&event=post_published",
            ("sha256_e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",),
            "[REDACTED]",
        ),
        # JSON blob with password
        (
            'admin login: {"username":"sumit","password":"S3cretP@ss!"}',
            ("S3cretP@ss!",),
            "[REDACTED]",
        ),
        # Bearer token in Authorization header string
        (
            "outgoing headers: Authorization=Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqaXlhIn0.SIG",  # nosecret — synthetic JWT for redaction test
            ("eyJhbGciOiJIUzI1NiJ9",),  # nosecret
            "[REDACTED]",
        ),
        # Meta verify_token in webhook subscription
        (
            "GET /webhooks/meta?hub.verify_token=meta_verify_ULTRA_secret_9x&hub.mode=subscribe",
            ("meta_verify_ULTRA_secret_9x",),
            "[REDACTED]",
        ),
        # OAuth refresh_token
        (
            "token refresh: refresh_token=1//09-refresh_SECRET_LONG_STRING_HERE ok",
            ("09-refresh_SECRET_LONG_STRING_HERE",),
            "[REDACTED]",
        ),
        # Case-insensitive: API-KEY
        (
            "outgoing GET https://x.com/?API-KEY=UPPERCASE_KEY_123ABC",
            ("UPPERCASE_KEY_123ABC",),
            "[REDACTED]",
        ),
    ],
)
def test_redact_message_hides_credential(raw, forbidden, expected_marker):
    out = log_mod.redact_message(raw)
    for f in forbidden:
        assert f not in out, f"credential leaked: {f!r} in {out!r}"
    assert expected_marker in out


def test_redact_message_preserves_non_sensitive_context():
    raw = "POST /api/campaigns?api_key=SECRET_KEY&campaign_id=42&limit=25"
    out = log_mod.redact_message(raw)
    # Non-sensitive fields must survive
    assert "campaign_id=42" in out
    assert "limit=25" in out
    assert "SECRET_KEY" not in out


# --------------------------------------------------------------------------- #
# 2026-07-12 gap-fix: env-var-style secret names (SMTP_PASS / GROQ_API_KEY /
# SECRET_KEY / VOBIZ_SIP_PASS ...) leaked past the word-boundary KV pass because
# the sensitive word is a prefix/mid-token, not a standalone word. Empirically
# found this session; locked here so it can't regress.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,secret",
    [
        ("mailer config SMTP_PASS=SuperSecret123 for admin@leadsgenai.in", "SuperSecret123"),
        ("env dump: GROQ_API_KEY=gsk_live_9f8e7d6c5b4a", "gsk_live_9f8e7d6c5b4a"),
        ("boot SECRET_KEY=flask_session_signing_key_xyz", "flask_session_signing_key_xyz"),
        ("sip creds VOBIZ_SIP_PASS=vs_pass_4455 host=x", "vs_pass_4455"),
        ("REDIS_PASSWORD=rp_secret_00 connecting", "rp_secret_00"),
        ("MISTRAL_API_KEY=ms_key_abc used for llm", "ms_key_abc"),
        ('config {"TURNSTILE_SECRET_KEY":"ts_secret_zz"}', "ts_secret_zz"),
        ("VAPID_PRIVATE_KEY=vapid_priv_9090 push", "vapid_priv_9090"),
    ],
)
def test_redact_message_hides_envvar_style_credential(raw, secret):
    """Env-var-style names (sensitive word inside the identifier) must redact —
    2026-07-12 gap: these leaked past the word-boundary KV/JSON passes."""
    out = log_mod.redact_message(raw)
    assert secret not in out, f"env-var credential leaked: {secret!r} in {out!r}"
    assert "[REDACTED]" in out


@pytest.mark.parametrize(
    "raw,preserved",
    [
        ("prod_check result: pass=42 fail=0 skip=1", "pass=42"),
        ("tuning LLM_BULK_TOKEN_THRESHOLD=6000 applied", "LLM_BULK_TOKEN_THRESHOLD=6000"),
        ("nav compass=north heading ok", "compass=north"),
    ],
)
def test_redact_message_does_not_over_redact_non_secrets(raw, preserved):
    """Uppercase-only + sensitive-suffix anchoring must NOT eat lowercase words
    (`pass=42`) or non-secret env names ending in a non-sensitive suffix
    (`..._THRESHOLD`)."""
    out = log_mod.redact_message(raw)
    assert preserved in out, f"over-redacted a non-secret: {preserved!r} missing from {out!r}"


def test_redact_message_fail_safe_returns_original_on_error(monkeypatch):
    """Regex error must NOT break logging — return original (safer)."""

    class _EvilStr(str):
        def __str__(self):
            raise RuntimeError("boom")

    # We can't easily force a regex error, so simulate by patching the compiled RE.
    fake = type(
        "FakePat", (), {"sub": lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("regex boom"))}
    )()
    monkeypatch.setattr(log_mod, "_MESSAGE_KV_REDACT_RE", fake)
    r = log_mod.redact_message("hello world")
    assert r == "hello world"


def test_redact_message_no_op_on_empty():
    assert log_mod.redact_message("") == ""
    assert log_mod.redact_message(None) is None or log_mod.redact_message(None) == ""


# --------------------------------------------------------------------------- #
# Formatter-integration tests: sensitive values must not reach emitted logs
# --------------------------------------------------------------------------- #


def _make_record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.log_redaction",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_colored_formatter_redacts(monkeypatch):
    monkeypatch.delenv("LOG_REDACT_MESSAGES", raising=False)
    fmt = log_mod.ColoredFormatter("%(levelname)s | %(message)s")
    r = _make_record("outbound https://api.example.com/?access_token=LEAKED_TOKEN_ABC123&x=1")
    out = fmt.format(r)
    assert "LEAKED_TOKEN_ABC123" not in out
    assert "[REDACTED]" in out
    assert "x=1" in out


def test_json_formatter_redacts_before_serialization(monkeypatch):
    monkeypatch.delenv("LOG_REDACT_MESSAGES", raising=False)
    fmt = log_mod.JSONFormatter()
    r = _make_record('login body: {"username":"jiya","password":"REAL_PASSWORD_XYZ"}')
    out = fmt.format(r)
    # JSON-parse the output and inspect the `message` field
    payload = json.loads(out)
    assert "REAL_PASSWORD_XYZ" not in payload["message"], "raw password leaked into JSON log"
    assert "REAL_PASSWORD_XYZ" not in out, "raw password leaked into JSON blob"
    assert "[REDACTED]" in payload["message"]


def test_env_flag_can_disable_redaction(monkeypatch):
    """LOG_REDACT_MESSAGES=0 = debug-window opt-out (never leave OFF in prod)."""
    monkeypatch.setenv("LOG_REDACT_MESSAGES", "0")
    fmt = log_mod.ColoredFormatter("%(message)s")
    r = _make_record("api_key=DEBUG_KEY_VISIBLE")
    out = fmt.format(r)
    assert "DEBUG_KEY_VISIBLE" in out, "flag=0 must fully disable redaction for debug"


def test_env_flag_defaults_to_on(monkeypatch):
    monkeypatch.delenv("LOG_REDACT_MESSAGES", raising=False)
    assert log_mod._log_redact_enabled() is True


# --------------------------------------------------------------------------- #
# _SENSITIVE_KEY_NAMES coverage lock: the P0 loop-flagged sensitive names must
# ALL be in the redactor's name set — regression-prevention if someone shrinks
# the list.
# --------------------------------------------------------------------------- #

_REQUIRED_NAMES = (
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "client_secret",
    "authorization",
    "password",
    "signature",
    "code",
    "verify_token",
    "webhook_secret",
)


@pytest.mark.parametrize("name", _REQUIRED_NAMES)
def test_required_credential_name_gets_redacted(name):
    """End-to-end guardrail: a message containing `{name}=SENSITIVE_VALUE` must
    end up with the value redacted, no matter which alias form is used."""
    payload = f"outbound https://api.example.com/?{name}=SENSITIVE_VALUE_XYZ&x=1"
    out = log_mod.redact_message(payload)
    assert "SENSITIVE_VALUE_XYZ" not in out, (
        f"credential name {name!r} did not trigger redaction — "
        "reopens the 2026-07-11 P0 log-leak regression"
    )
    assert "[REDACTED]" in out
    assert "x=1" in out  # non-sensitive context preserved
