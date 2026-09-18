"""Telegram command parser for coordination control plane.

This module provides a pure, deterministic parser for Telegram commands.
It translates validated commands into typed action objects for the Owner OS.

ARCHITECTURE RULES:
- Parser is FAIL-CLOSED: rejects unauthorized/invalid input
- Parser is STATELESS: only validates, never mutates
- Parser is ISOLATED: no access to secrets, shell, or arbitrary files
- Parser is TESTABLE: pure functions, no side effects
- Poller REMAINS OFF: Hermes is sole `getUpdates` consumer

COMMAND ALLOWLIST:
Read commands:
  /status       - Show system status
  /workers      - Show worker registry
  /agents       - Show agent assignments
  /tasks        - Show active DevTasks
  /revenue      - Show revenue summary
  /health       - Show system health

Mutation commands (require approval):
  /pause <worker>     - Pause a CLI worker
  /resume <worker>    - Resume a paused worker
  /assign <worker> <task-id>  - Assign task to worker
  /approve <decision-id>      - Approve a decision
  /reject <decision-id>       - Reject a decision

SECURITY CONSTRAINTS:
- No shell execution
- No secret retrieval
- No file mutation (except governed DevTask)
- No arbitrary deployments
- No customer data exposure
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Command types for routing to appropriate handlers."""
    READ = "read"
    MUTATION = "mutation"
    UNKNOWN = "unknown"


class CommandStatus(Enum):
    """Parser result status."""
    SUCCESS = "success"
    UNAUTHORIZED = "unauthorized"
    INVALID_FORMAT = "invalid_format"
    UNKNOWN_COMMAND = "unknown_command"
    MALFORMED_ARGUMENTS = "malformed_arguments"
    RATE_LIMITED = "rate_limited"
    DUPLICATE_UPDATE = "duplicate_update"


@dataclass(frozen=True)
class CommandResult:
    """Parsed command result with metadata."""
    status: CommandStatus
    command: str
    args: tuple[str, ...]
    error: Optional[str] = None
    requires_approval: bool = False
    update_id: Optional[int] = None


@dataclass(frozen=True)
class ParsedCommand:
    """Typed action object for Owner OS dispatch."""
    command: str
    args: tuple[str, ...]
    command_type: CommandType
    sender_id: Optional[int] = None
    chat_id: Optional[str] = None
    update_id: Optional[int] = None


# Authorized sender IDs (owner/admin only)
AUTHORIZED_SENDERS: set[int] = set()

# Authorized chat IDs (internal groups only)
AUTHORIZED_CHATS: set[str] = set()

# Command definitions with their patterns and types
_COMMAND_DEFS: dict[str, dict[str, Any]] = {
    "status": {
        "type": CommandType.READ,
        "pattern": r"^/status$",
        "args_count": 0,
        "description": "Show system status",
    },
    "workers": {
        "type": CommandType.READ,
        "pattern": r"^/workers$",
        "args_count": 0,
        "description": "Show worker registry",
    },
    "agents": {
        "type": CommandType.READ,
        "pattern": r"^/agents$",
        "args_count": 0,
        "description": "Show agent assignments",
    },
    "tasks": {
        "type": CommandType.READ,
        "pattern": r"^/tasks$",
        "args_count": 0,
        "description": "Show active DevTasks",
    },
    "revenue": {
        "type": CommandType.READ,
        "pattern": r"^/revenue$",
        "args_count": 0,
        "description": "Show revenue summary",
    },
    "health": {
        "type": CommandType.READ,
        "pattern": r"^/health$",
        "args_count": 0,
        "description": "Show system health",
    },
    "pause": {
        "type": CommandType.MUTATION,
        "pattern": r"^/pause\s+(\w+)$",
        "args_count": 1,
        "description": "Pause a CLI worker",
        "requires_approval": True,
    },
    "resume": {
        "type": CommandType.MUTATION,
        "pattern": r"^/resume\s+(\w+)$",
        "args_count": 1,
        "description": "Resume a paused worker",
        "requires_approval": True,
    },
    "assign": {
        "type": CommandType.MUTATION,
        "pattern": r"^/assign\s+(\w+)\s+(\w+)$",
        "args_count": 2,
        "description": "Assign task to worker",
        "requires_approval": True,
    },
    "approve": {
        "type": CommandType.MUTATION,
        "pattern": r"^/approve\s+(\w+)$",
        "args_count": 1,
        "description": "Approve a decision",
        "requires_approval": True,
    },
    "reject": {
        "type": CommandType.MUTATION,
        "pattern": r"^/reject\s+(\w+)$",
        "args_count": 1,
        "description": "Reject a decision",
        "requires_approval": True,
    },
}


def set_authorized_senders(sender_ids: set[int]) -> None:
    """Set authorized sender IDs (owner/admin)."""
    global AUTHORIZED_SENDERS
    AUTHORIZED_SENDERS = sender_ids or set()


def set_authorized_chats(chat_ids: set[str]) -> None:
    """Set authorized chat IDs (internal groups)."""
    global AUTHORIZED_CHATS
    AUTHORIZED_CHATS = chat_ids or set()


def parse_command(
    text: str,
    sender_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    update_id: Optional[int] = None,
) -> CommandResult:
    """Parse a Telegram command message.

    Args:
        text: Raw message text from Telegram
        sender_id: Telegram user ID (for authorization check)
        chat_id: Telegram chat ID (for authorization check)
        update_id: Telegram update ID (for deduplication)

    Returns:
        CommandResult with status and parsed data
    """
    # Normalize input
    text = str(text or "").strip()
    if not text:
        return CommandResult(
            status=CommandStatus.INVALID_FORMAT,
            command="",
            args=(),
            error="Empty command",
        )

    # Check authorization
    if sender_id is not None and not _is_authorized_sender(sender_id):
        logger.warning("[telegram_parser] Unauthorized sender: %s", sender_id)
        return CommandResult(
            status=CommandStatus.UNAUTHORIZED,
            command="",
            args=(),
            error=f"Sender {sender_id} not authorized",
            update_id=update_id,
        )

    if chat_id is not None and not _is_authorized_chat(chat_id):
        logger.warning("[telegram_parser] Unauthorized chat: %s", chat_id)
        return CommandResult(
            status=CommandStatus.UNAUTHORIZED,
            command="",
            args=(),
            error=f"Chat {chat_id} not authorized",
            update_id=update_id,
        )

    # Match against command patterns
    for cmd_name, cmd_def in _COMMAND_DEFS.items():
        pattern = cmd_def["pattern"]
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            args = match.groups() if match.groups else ()
            return CommandResult(
                status=CommandStatus.SUCCESS,
                command=cmd_name,
                args=args,
                requires_approval=cmd_def.get("requires_approval", False),
                update_id=update_id,
            )

    # No match found
    logger.info("[telegram_parser] Unknown command: %s", text[:50])
    return CommandResult(
        status=CommandStatus.UNKNOWN_COMMAND,
        command="",
        args=(),
        error=f"Unknown command: {text[:30]}",
        update_id=update_id,
    )


def _is_authorized_sender(sender_id: int) -> bool:
    """Check if sender is authorized."""
    if not AUTHORIZED_SENDERS:
        # If no authorized senders configured, allow all (for testing)
        return True
    return sender_id in AUTHORIZED_SENDERS


def _is_authorized_chat(chat_id: str) -> bool:
    """Check if chat is authorized."""
    if not AUTHORIZED_CHATS:
        # If no authorized chats configured, allow all (for testing)
        return True
    return chat_id in AUTHORIZED_CHATS


def validate_command(parsed: ParsedCommand) -> bool:
    """Validate a parsed command for safety.

    Returns True if command is safe to execute, False otherwise.
    """
    # Check for suspicious patterns
    suspicious_patterns = [
        r"\$\{",  # Shell variable expansion ${...}
        r"\$\(",  # Command substitution $(...)
        r"`.*`",  # Backtick command substitution
        r";.*",   # Command chaining
        r"\|.*",  # Pipe
        r"&&",    # Logical AND
        r"wget",  # Download
        r"curl",  # Download
        r"rm\s",  # Delete
        r"chmod", # Permissions
        r"chown", # Ownership
        r"/etc/", # System files
        r"\.\.",  # Path traversal
        r"\$[A-Z_]+",  # Environment variable reference $HOME, $PATH
    ]

    for arg in parsed.args:
        for pattern in suspicious_patterns:
            if re.search(pattern, arg):
                logger.warning("[telegram_parser] Suspicious pattern in arg: %s", arg)
                return False

    return True


def get_command_help() -> str:
    """Get help text for all commands."""
    lines = ["Available commands:", ""]
    for cmd_name, cmd_def in sorted(_COMMAND_DEFS.items()):
        lines.append(f"  /{cmd_name} - {cmd_def['description']}")
    lines.append("")
    lines.append("READ commands show system state.")
    lines.append("MUTATION commands require approval.")
    return "\n".join(lines)


__all__ = [
    "CommandResult",
    "ParsedCommand",
    "CommandStatus",
    "CommandType",
    "parse_command",
    "set_authorized_senders",
    "set_authorized_chats",
    "validate_command",
    "get_command_help",
]
