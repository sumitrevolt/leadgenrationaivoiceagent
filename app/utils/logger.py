"""
Logger Utility
Production-ready centralized logging configuration
Supports structured JSON logging for cloud environments
Integrates with Google Cloud Logging in production
"""
import logging
import sys
import json
from typing import Optional, Any, Dict
from datetime import datetime
import os

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
        
        _cloud_logging_initialized = True
        print("? Google Cloud Logging initialized")
        
    except ImportError:
        # google-cloud-logging not installed, use standard logging
        pass
    except Exception as e:
        print(f"?? Could not initialize Cloud Logging: {e}")


# =============================================================================
# FORMATTERS
# =============================================================================

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Add color to level name
        record.levelname = f"{color}{record.levelname}{reset}"
        
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging in production
    Compatible with Cloud Logging, ELK, etc.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
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
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "request_id", "tenant_id", "call_id", "duration_ms", "status_code",
            ]:
                if not key.startswith("_"):
                    log_data[key] = value
        
        return json.dumps(log_data, default=str)


# =============================================================================
# LOGGER SETUP
# =============================================================================

def setup_logger(
    name: str,
    level: Optional[int] = None,
    log_file: Optional[str] = None
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
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    if use_json:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
    
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.FileHandler(log_file)
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
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S.%f'
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
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": data
        }
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
    
    def log_error(self, error: str, details: Optional[dict] = None):
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
            "errors": [e for e in self.events if e["type"] == "error"]
        }
