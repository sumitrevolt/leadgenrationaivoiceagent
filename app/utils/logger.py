"""
Logger Utility
Centralized logging configuration
"""
import logging
import sys
from typing import Optional
from datetime import datetime
import os


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


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Setup and return a logger
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level
        log_file: Optional file path for file logging
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    console_format = ColoredFormatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        
        file_format = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
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
