"""Tests for Telegram command parser.

Run: pytest tests/test_telegram_ingress_parser.py -v
"""

import pytest

from app.platform.telegram_ingress_parser import (
    CommandResult,
    CommandStatus,
    CommandType,
    parse_command,
    set_authorized_senders,
    set_authorized_chats,
    validate_command,
    get_command_help,
)


class TestParseCommand:
    """Test command parsing."""

    def test_status_command(self):
        """Test /status parsing."""
        result = parse_command("/status", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "status"
        assert result.args == ()
        assert result.requires_approval == False

    def test_workers_command(self):
        """Test /workers parsing."""
        result = parse_command("/workers", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "workers"
        assert result.args == ()

    def test_pause_command(self):
        """Test /pause command parsing."""
        result = parse_command("/pause operations", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "pause"
        assert result.args == ("operations",)
        assert result.requires_approval == True

    def test_resume_command(self):
        """Test /resume command parsing."""
        result = parse_command("/resume engineering", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "resume"
        assert result.args == ("engineering",)

    def test_assign_command(self):
        """Test /assign command parsing."""
        result = parse_command("/assign operations task_123", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "assign"
        assert result.args == ("operations", "task_123")

    def test_approve_command(self):
        """Test /approve command parsing."""
        result = parse_command("/approve decision_456", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "approve"
        assert result.args == ("decision_456",)

    def test_reject_command(self):
        """Test /reject command parsing."""
        result = parse_command("/reject decision_456", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "reject"
        assert result.args == ("decision_456",)

    def test_unknown_command(self):
        """Test unknown command rejection."""
        result = parse_command("/unknown", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.UNKNOWN_COMMAND
        assert result.error is not None

    def test_empty_command(self):
        """Test empty command rejection."""
        result = parse_command("", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.INVALID_FORMAT
        assert result.error == "Empty command"

    def test_malformed_pause(self):
        """Test malformed /pause command."""
        result = parse_command("/pause", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.UNKNOWN_COMMAND

    def test_malformed_assign(self):
        """Test malformed /assign command."""
        result = parse_command("/assign operations", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.UNKNOWN_COMMAND


class TestAuthorization:
    """Test authorization checks."""

    def test_authorized_sender(self):
        """Test authorized sender passes."""
        set_authorized_senders({123, 456})
        result = parse_command("/status", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS

    def test_unauthorized_sender(self):
        """Test unauthorized sender rejected."""
        set_authorized_senders({123, 456})
        result = parse_command("/status", sender_id=999, chat_id="internal")
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "not authorized" in result.error.lower()

    def test_authorized_chat(self):
        """Test authorized chat passes."""
        set_authorized_chats({"-1001", "-1002"})
        result = parse_command("/status", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS

    def test_unauthorized_chat(self):
        """Test unauthorized chat rejected."""
        set_authorized_chats({"-1001", "-1002"})
        result = parse_command("/status", sender_id=123, chat_id="-1003")
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "not authorized" in result.error.lower()

    def test_no_authorization_configured(self):
        """Test all commands pass when no authorization configured (testing mode)."""
        set_authorized_senders(set())
        set_authorized_chats(set())
        result = parse_command("/status", sender_id=999, chat_id="-999")
        assert result.status == CommandStatus.SUCCESS


class TestValidation:
    """Test command validation for safety."""

    def test_valid_command(self):
        """Test valid command passes validation."""
        from app.platform.telegram_ingress_parser import ParsedCommand
        
        parsed = ParsedCommand(
            command="pause",
            args=("operations",),
            command_type=CommandType.MUTATION,
        )
        assert validate_command(parsed) == True

    def test_suspicious_shell_expansion(self):
        """Test shell variable expansion rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand
        
        parsed = ParsedCommand(
            command="pause",
            args=("$HOME",),
            command_type=CommandType.MUTATION,
        )
        assert validate_command(parsed) == False

    def test_suspicious_command_substitution(self):
        """Test command substitution rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand
        
        parsed = ParsedCommand(
            command="pause",
            args=("$(whoami)",),
            command_type=CommandType.MUTATION,
        )
        assert validate_command(parsed) == False

    def test_suspicious_pipe(self):
        """Test pipe injection rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand
        
        parsed = ParsedCommand(
            command="pause",
            args=("operations|cat /etc/passwd",),
            command_type=CommandType.MUTATION,
        )
        assert validate_command(parsed) == False

    def test_suspicious_delete(self):
        """Test rm command rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand
        
        parsed = ParsedCommand(
            command="pause",
            args=("rm -rf /",),
            command_type=CommandType.MUTATION,
        )
        assert validate_command(parsed) == False


class TestHelp:
    """Test help text generation."""

    def test_help_contains_commands(self):
        """Test help text lists all commands."""
        help_text = get_command_help()
        assert "/status" in help_text
        assert "/workers" in help_text
        assert "/pause" in help_text
        assert "/approve" in help_text

    def test_help_mentions_approval(self):
        """Test help text mentions approval requirement."""
        help_text = get_command_help()
        assert "MUTATION commands require approval" in help_text


class TestUpdateId:
    """Test update ID tracking for deduplication."""

    def test_update_id_stored(self):
        """Test update_id is stored in result."""
        result = parse_command("/status", sender_id=123, chat_id="internal", update_id=42)
        assert result.update_id == 42

    def test_update_id_none_when_not_provided(self):
        """Test update_id is None when not provided."""
        result = parse_command("/status", sender_id=123, chat_id="internal")
        assert result.update_id is None


class TestCaseSensitivity:
    """Test case insensitivity."""

    def test_uppercase_command(self):
        """Test uppercase command is accepted."""
        result = parse_command("/STATUS", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS

    def test_mixed_case_command(self):
        """Test mixed case command is accepted."""
        result = parse_command("/Pause operations", sender_id=123, chat_id="internal")
        assert result.status == CommandStatus.SUCCESS
