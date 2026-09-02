"""
Logger Utility
Production-ready centralized logging configuration
Supports structured JSON logging for cloud environments
Integrates with Google Cloud Logging in production
"""

import json
import logging
import os
import sys
from datetime import datetime

from app.config import settings

# =============================================================================
# CLOUD LOGGING SETUP (Production)
# =============================================================================

_cloud_logging_initialized = False


def setup_cloud_logging():
    """
    Initialize Google Cloud Logging for production
    Automatically sends logs to Cloud Logging with proper severity levels
    """
    global _cloud_logging_initialized

    if _cloud_logging_initialized:
        return

    if settings.app_env != "production":
        return

    # Mark as attempted up-front: a FAILED attempt must not be retried by
    # every setup_logger() call — google-cloud's internal retries can block
    # app startup for minutes (seen on VPS deploys without GCP credentials).
    _cloud_logging_initialized = True

    # Only attempt when credentials are plausibly available: explicit
    # service-account file, or running on GCP (Cloud Run/GCE metadata).
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and not os.environ.get("K_SERVICE"):
        return

    try:
        import google.cloud.logging as cloud_logging
        from google.cloud.logging_v2.handlers import CloudLoggingHandler

        # Initialize Cloud Logging client
        client = cloud_logging.Client()

        # Create handler that writes to Cloud Logging
        handler = CloudLoggingHandler(client, name="leadgen-ai")

        # Attach to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        print("Google Cloud Logging initialized")

    except ImportError:
        # google-cloud-logging not installed, use standard logging
        pass
    except Exception as e:
        print(f"?? Could not initialize Cloud Logging: {e}")


# =============================================================================
# CREDENTIAL REDACTION (2026-07-11 P0 loop-flagged: INFO HTTP logs were
# suspected of exposing query-string credentials — Meta OAuth `code=`, Postiz
# `api_key=`, webhook `signature=`, etc.). This module-level redactor runs on
# EVERY emitted log message via the formatter classes below. Fail-safe: any
# regex error returns the original message unchanged (safer than breaking
# logs). Env opt-out `LOG_REDACT_MESSAGES=0` for debug windows only — never
# leave OFF permanently in production.
# =============================================================================

import re as _re

# Case-insensitive credential-like key names, ordered longest-first so
# `client_secret` is not partially matched by `secret`. Covers OAuth
# (code/access_token/refresh_token/id_token/client_secret), webhooks
# (signature/verify_token/webhook_secret), transport auth (authorization/
# bearer/jwt), and generic API keys (api_key/api-key/apikey/token/secret/
# password). Hyphen/underscore variants collapsed via regex.
_SENSITIVE_KEY_NAMES = (
    "client_secret",
    "webhook_secret",
    "refresh_token",
    "access_token",
    "verify_token",
    "auth_token",
    "oauth_token",
    "private_token",
    "private_key",
    "id_token",
    "session_id",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "signature",
    "token",
    "secret",
    "bearer",
    "jwt",
    "code",
)


def _sensitive_name_re_alternation() -> str:
    """Build a name alternation regex that tolerates `-` or `_` between
    words (e.g. `api-key` == `api_key`)."""
    return "|".join(n.replace("-", "[-_]?").replace("_", "[-_]?") for n in _SENSITIVE_KEY_NAMES)


_MESSAGE_KV_REDACT_RE = _re.compile(
    r"\b("
    + _sensitive_name_re_alternation()
    + r')\s*[=:]\s*("[^"]{1,4096}"|\'[^\']{1,4096}\'|[^\s&,;\)\]\}"]{1,4096})',
    _re.IGNORECASE,
)

_MESSAGE_JSON_REDACT_RE = _re.compile(
    r"(['\"])(" + _sensitive_name_re_alternation() + r")\1\s*:\s*(['\"])([^'\"]{1,4096})\3",
    _re.IGNORECASE,
)

# `Bearer <token>`, `Basic <base64>`, `Token <hex>` — auth-header conventions.
_MESSAGE_BEARER_RE = _re.compile(
    r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._\-~+/=]{6,}",
    _re.IGNORECASE,
)

# Env-var-style secret names where the sensitive word is a PREFIX/mid-token (not a
# standalone word), so the word-boundary KV/JSON passes above miss them — e.g.
# `SMTP_PASS=`, `GROQ_API_KEY=`, `SECRET_KEY=`, `VOBIZ_SIP_PASS=`,
# `TURNSTILE_SECRET_KEY=`, `VAPID_PRIVATE_KEY=`, `WAHA_API_KEY=`. Matches an
# UPPERCASE env-style token that ENDS in a sensitive suffix (uppercase-only → never
# touches lowercase words like `pass=42` / `result: pass=`). Optional trailing
# quote handles the `"SECRET_KEY":"v"` JSON form too. 2026-07-12 gap-fix
# (empirically confirmed: env-var names leaked past the word-boundary KV pass).
_MESSAGE_ENVVAR_REDACT_RE = _re.compile(
    r"\b([A-Z0-9]+(?:_[A-Z0-9]+)*_(?:PASS|PASSWORD|PWD|SECRET|TOKEN|KEY|APIKEY|CREDENTIAL|CREDENTIALS))"
    r"""["']?\s*[=:]\s*"""
    r"""("[^"]{1,4096}"|'[^']{1,4096}'|[^\s&,;\)\]\}"]{1,4096})""",
)


def redact_message(message: str) -> str:
    """Redact credential-like key=value / "key":"value" / `Bearer xxx`
    fragments from an arbitrary log message string. Fail-safe: on any regex
    error the original message is returned unchanged (safer than breaking
    logs).

    Pass order matters: `Authorization=Bearer <jwt>` must run the Bearer pass
    FIRST — otherwise the KV pass consumes only the word "Bearer" (space-
    terminated value) and leaves the JWT trailing after the [REDACTED] marker.
    Order: JSON (highest-confidence structured) → Bearer (auth-header +
    free-form `Bearer XXX` catch-all) → KV (remaining `key=value` /
    `key: value`)."""
    if not message:
        return message
    try:
        s = str(message)
        s = _MESSAGE_JSON_REDACT_RE.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(1)}: {m.group(3)}[REDACTED]{m.group(3)}",
            s,
        )
        s = _MESSAGE_BEARER_RE.sub(lambda m: f"{m.group(1)} [REDACTED]", s)
        s = _MESSAGE_KV_REDACT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", s)
        s = _MESSAGE_ENVVAR_REDACT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", s)
        return s
    except Exception:
        return message


def redact_url(url: str) -> str:
    """Redact sensitive query-string params + userinfo from a URL / path.

    Used by request-logging middleware — an INFO log like
    ``GET /callback?token=abc123&user=x`` MUST NOT leak the token. Also
    handles ``https://user:pass@host/`` userinfo form.

    Fail-safe: on any parse/regex error the original url is returned unchanged
    (never break request logging).
    """
    if not url:
        return url
    try:
        s = str(url)
        # 1) userinfo (scheme://user:pass@host) — redact both user and pass.
        s = _re.sub(
            r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<userinfo>[^/@\s]+)@",
            lambda m: f"{m.group('scheme')}[REDACTED]@",
            s,
        )
        # 2) query-string sensitive kv (?token=... or &api_key=...) — case-insensitive.
        if "?" in s or "&" in s:
            qs_re = _re.compile(
                r"([?&])(" + _sensitive_name_re_alternation() + r")(=)([^&#\s]{0,4096})",
                _re.IGNORECASE,
            )
            s = qs_re.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]", s)
        return s
    except Exception:
        return url


def _log_redact_enabled() -> bool:
    """Default ON. `LOG_REDACT_MESSAGES=0` (or false/no/off) disables for a
    debug window — never leave OFF permanently in production."""
    v = os.environ.get("LOG_REDACT_MESSAGES", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


# =============================================================================
# FORMATTERS
# =============================================================================


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # Add color to level name
        record.levelname = f"{color}{record.levelname}{reset}"

        formatted = super().format(record)
        # Credential redaction on final formatted output (2026-07-11 P0 hardening).
        # Post-format run catches everything the format string interpolated:
        # message body, extra fields, and any KV/JSON/Bearer credential pair.
        if _log_redact_enabled():
            formatted = redact_message(formatted)
        return formatted


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging in production
    Compatible with Cloud Logging, ELK, etc.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Credential redaction on the fully-interpolated message (2026-07-11
        # P0 hardening). Runs BEFORE serialization so both the structured
        # `message` field and any downstream JSON-log ingestor (Loki/Cloud
        # Logging/Sentry breadcrumbs) see the sanitized text.
        _raw_msg = record.getMessage()
        _msg = redact_message(_raw_msg) if _log_redact_enabled() else _raw_msg
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": _msg,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        if hasattr(record, "tenant_id"):
            log_data["tenant_id"] = record.tenant_id

        if hasattr(record, "call_id"):
            log_data["call_id"] = record.call_id

        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms

        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any other extra fields
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "request_id",
                "tenant_id",
                "call_id",
                "duration_ms",
                "status_code",
            ]:
                if not key.startswith("_"):
                    log_data[key] = value

        return json.dumps(log_data, default=str)


# =============================================================================
# LOGGER SETUP
# =============================================================================


def setup_logger(
    name: str, level: int | None = None, log_file: str | None = None
) -> logging.Logger:
    """
    Setup and return a logger

    Args:
        name: Logger name (usually __name__)
        level: Logging level (defaults to config)
        log_file: Optional file path for file logging

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Determine log level from settings
    if level is None:
        level_name = getattr(settings, "log_level", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

    logger.setLevel(level)

    # Initialize Cloud Logging in production
    if settings.app_env == "production":
        setup_cloud_logging()

    # Determine if we should use JSON logging (production)
    use_json = settings.app_env == "production"

    # Console handler
    # On Windows the console is often cp1252 — emoji in log messages would
    # raise UnicodeEncodeError and crash logging. Force UTF-8 with replacement.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # non-reconfigurable stream (e.g. pytest capture) — fine
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if use_json:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            ColoredFormatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
        )

    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)

        # Always use JSON for file logs
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

    return logger


def get_call_logger(call_id: str) -> logging.Logger:
    """
    Get a logger specific to a call

    Args:
        call_id: Unique call identifier

    Returns:
        Logger for the specific call
    """
    logger = logging.getLogger(f"call.{call_id}")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Create logs directory
    log_dir = "logs/calls"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Date-based subdirectory
    date_str = datetime.now().strftime("%Y-%m-%d")
    date_dir = os.path.join(log_dir, date_str)
    if not os.path.exists(date_dir):
        os.makedirs(date_dir)

    # File handler for this call
    log_file = os.path.join(date_dir, f"{call_id}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S.%f"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


class CallLogger:
    """
    Structured logger for call events
    """

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.logger = get_call_logger(call_id)
        self.events = []

    def log_event(self, event_type: str, data: dict):
        """Log a structured event"""
        event = {"timestamp": datetime.now().isoformat(), "type": event_type, "data": data}
        self.events.append(event)
        self.logger.info(f"{event_type}: {data}")

    def log_speech(self, speaker: str, text: str):
        """Log speech (user or agent)"""
        self.log_event("speech", {"speaker": speaker, "text": text})

    def log_intent(self, intent: str, confidence: float):
        """Log detected intent"""
        self.log_event("intent", {"intent": intent, "confidence": confidence})

    def log_action(self, action: str, result: str):
        """Log action taken"""
        self.log_event("action", {"action": action, "result": result})

    def log_error(self, error: str, details: dict | None = None):
        """Log error"""
        self.logger.error(f"ERROR: {error}")
        self.log_event("error", {"error": error, "details": details or {}})

    def get_transcript(self) -> str:
        """Get call transcript from logged events"""
        transcript = []
        for event in self.events:
            if event["type"] == "speech":
                speaker = event["data"]["speaker"]
                text = event["data"]["text"]
                transcript.append(f"{speaker}: {text}")
        return "\n".join(transcript)

    def get_summary(self) -> dict:
        """Get call summary"""
        return {
            "call_id": self.call_id,
            "total_events": len(self.events),
            "speech_events": len([e for e in self.events if e["type"] == "speech"]),
            "intents_detected": [e["data"]["intent"] for e in self.events if e["type"] == "intent"],
            "errors": [e for e in self.events if e["type"] == "error"],
        }
