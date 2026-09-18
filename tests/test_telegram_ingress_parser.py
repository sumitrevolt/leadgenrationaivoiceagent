"""Tests for Telegram command parser.

Run: pytest tests/test_telegram_ingress_parser.py -v
"""

import pytest

from app.platform.telegram_ingress_parser import (
    CANONICAL_CLI_WORKERS,
    CommandResult,
    CommandStatus,
    CommandType,
    get_command_help,
    parse_command,
    set_authorized_chats,
    set_authorized_senders,
    validate_command,
)


class TestParseCommand:
    """Test command parsing."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, monkeypatch):
        """Setup authorized sender/chat for all tests in this class."""
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_SENDERS", {123})
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_CHATS", {"-1001"})

    def test_status_command(self):
        """Test /status parsing."""
        result = parse_command("/status", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "status"
        assert result.args == ()
        assert not result.requires_approval

    def test_workers_command(self):
        """Test /workers parsing."""
        result = parse_command("/workers", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "workers"
        assert result.args == ()

    def test_pause_command(self):
        """Test /pause command parsing."""
        result = parse_command("/pause operations", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "pause"
        assert result.args == ("operations",)
        assert result.requires_approval

    def test_resume_command(self):
        """Test /resume command parsing."""
        result = parse_command("/resume engineering", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "resume"
        assert result.args == ("engineering",)

    def test_assign_command(self):
        """Test /assign command parsing."""
        result = parse_command("/assign operations task_123", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "assign"
        assert result.args == ("operations", "task_123")

    def test_approve_command(self):
        """Test /approve command parsing."""
        result = parse_command("/approve decision_456", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "approve"
        assert result.args == ("decision_456",)

    def test_reject_command(self):
        """Test /reject command parsing."""
        result = parse_command("/reject decision_456", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
        assert result.command == "reject"
        assert result.args == ("decision_456",)

    def test_unknown_command(self):
        """Test unknown command rejection."""
        result = parse_command("/unknown", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.UNKNOWN_COMMAND
        assert result.error is not None

    def test_empty_command(self):
        """Test empty command rejection."""
        result = parse_command("", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.INVALID_FORMAT
        assert result.error == "Empty command"

    def test_malformed_pause(self):
        """Test malformed /pause command."""
        result = parse_command("/pause", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.UNKNOWN_COMMAND

    def test_malformed_assign(self):
        """Test malformed /assign command."""
        result = parse_command("/assign operations", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.UNKNOWN_COMMAND


class TestFailClosedAuthorization:
    """Test fail-closed authorization (production default: DENY ALL)."""

    def test_missing_sender_id_rejected(self):
        """Test missing sender_id is rejected."""
        result = parse_command("/status", chat_id="internal")
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "Missing sender_id" in result.error

    def test_missing_chat_id_rejected(self):
        """Test missing chat_id is rejected."""
        result = parse_command("/status", sender_id=123)
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "Missing chat_id" in result.error

    def test_empty_sender_allowlist_denies_all(self):
        """Test empty sender allowlist denies everyone (fail-closed)."""
        set_authorized_senders(set())
        set_authorized_chats({"-1001"})
        result = parse_command("/status", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "not authorized" in result.error.lower()

    def test_empty_chat_allowlist_denies_all(self):
        """Test empty chat allowlist denies everyone (fail-closed)."""
        set_authorized_senders({123})
        set_authorized_chats(set())
        result = parse_command("/status", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "not authorized" in result.error.lower()

    def test_unauthorized_sender_rejected(self):
        """Test unauthorized sender rejected."""
        set_authorized_senders({123, 456})
        set_authorized_chats({"-1001"})
        result = parse_command("/status", sender_id=999, chat_id="-1001")
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "not authorized" in result.error.lower()

    def test_unauthorized_chat_rejected(self):
        """Test unauthorized chat rejected."""
        set_authorized_senders({123})
        set_authorized_chats({"-1001", "-1002"})
        result = parse_command("/status", sender_id=123, chat_id="-1003")
        assert result.status == CommandStatus.UNAUTHORIZED
        assert "not authorized" in result.error.lower()

    def test_authorized_sender_and_chat_passes(self):
        """Test authorized sender + chat passes."""
        set_authorized_senders({123})
        set_authorized_chats({"-1001"})
        result = parse_command("/status", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS


class TestCanonicalWorkers:
    """Test canonical CLI worker validation."""

    def test_canonical_workers_defined(self):
        """Test canonical workers set is defined."""
        assert len(CANONICAL_CLI_WORKERS) == 6
        assert "operations" in CANONICAL_CLI_WORKERS
        assert "engineering" in CANONICAL_CLI_WORKERS
        assert "platform" in CANONICAL_CLI_WORKERS
        assert "guardian" in CANONICAL_CLI_WORKERS
        assert "sales" in CANONICAL_CLI_WORKERS
        assert "success" in CANONICAL_CLI_WORKERS

    def test_pilot_not_in_canonical_workers(self):
        """Test Pilot is NOT a canonical CLI worker."""
        assert "Pilot" not in CANONICAL_CLI_WORKERS
        assert "pilot" not in CANONICAL_CLI_WORKERS

    def test_board_not_in_canonical_workers(self):
        """Test board is NOT a canonical CLI worker."""
        assert "board" not in CANONICAL_CLI_WORKERS
        assert "Board" not in CANONICAL_CLI_WORKERS

    def test_hunter_not_in_canonical_workers(self):
        """Test hunter is NOT a canonical CLI worker."""
        assert "hunter" not in CANONICAL_CLI_WORKERS
        assert "Hunter" not in CANONICAL_CLI_WORKERS

    def test_invalid_worker_rejected_by_validation(self):
        """Test invalid worker name rejected by validate_command."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="pause",
            args=("Pilot",),
            command_type=CommandType.MUTATION,
        )
        assert not validate_command(parsed)

    def test_valid_worker_accepted_by_validation(self):
        """Test valid worker name accepted by validate_command."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="pause",
            args=("operations",),
            command_type=CommandType.MUTATION,
        )
        assert validate_command(parsed)


class TestDevTaskIDValidation:
    """Test DevTask/decision ID format validation."""

    def test_valid_devtask_id_format(self):
        """Test valid DevTask ID formats."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        valid_ids = ["task_123", "DEC-2024-001", "sprint-42.refinement", "abc"]
        for devtask_id in valid_ids:
            parsed = ParsedCommand(
                command="assign",
                args=("operations", devtask_id),
                command_type=CommandType.MUTATION,
            )
            assert validate_command(parsed), f"Expected {devtask_id} to be valid"

    def test_invalid_devtask_id_too_short(self):
        """Test DevTask ID too short is rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="assign",
            args=("operations", "ab"),
            command_type=CommandType.MUTATION,
        )
        assert not validate_command(parsed)

    def test_invalid_devtask_id_special_chars(self):
        """Test DevTask ID with special chars is rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="assign",
            args=("operations", "task@123"),
            command_type=CommandType.MUTATION,
        )
        assert not validate_command(parsed)


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
        assert validate_command(parsed)

    def test_suspicious_shell_expansion(self):
        """Test shell variable expansion rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="pause",
            args=("$HOME",),
            command_type=CommandType.MUTATION,
        )
        assert not validate_command(parsed)

    def test_suspicious_command_substitution(self):
        """Test command substitution rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="pause",
            args=("$(whoami)",),
            command_type=CommandType.MUTATION,
        )
        assert not validate_command(parsed)

    def test_suspicious_pipe(self):
        """Test pipe injection rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="pause",
            args=("operations|cat /etc/passwd",),
            command_type=CommandType.MUTATION,
        )
        assert not validate_command(parsed)

    def test_suspicious_delete(self):
        """Test rm command rejected."""
        from app.platform.telegram_ingress_parser import ParsedCommand

        parsed = ParsedCommand(
            command="pause",
            args=("rm -rf /",),
            command_type=CommandType.MUTATION,
        )
        assert not validate_command(parsed)


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

    def test_help_mentions_canonical_workers(self):
        """Test help text lists canonical workers."""
        help_text = get_command_help()
        assert "operations" in help_text
        assert "engineering" in help_text


class TestUpdateId:
    """Test update ID tracking (no dedup implementation)."""

    def test_update_id_stored(self, monkeypatch):
        """Test update_id is stored in result."""
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_SENDERS", {123})
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_CHATS", {"-1001"})
        result = parse_command("/status", sender_id=123, chat_id="-1001", update_id=42)
        assert result.update_id == 42

    def test_update_id_none_when_not_provided(self, monkeypatch):
        """Test update_id is None when not provided."""
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_SENDERS", {123})
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_CHATS", {"-1001"})
        result = parse_command("/status", sender_id=123, chat_id="-1001")
        assert result.update_id is None

    def test_duplicate_update_status_exists_but_not_implemented(self, monkeypatch):
        """Test DUPLICATE_UPDATE status exists but parser is stateless."""
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_SENDERS", {123})
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_CHATS", {"-1001"})
        # Parser is stateless - it cannot detect duplicates
        # Deduplication belongs in the single ingress adapter
        result1 = parse_command("/status", sender_id=123, chat_id="-1001", update_id=42)
        result2 = parse_command("/status", sender_id=123, chat_id="-1001", update_id=42)
        # Both return SUCCESS (no dedup in parser)
        assert result1.status == CommandStatus.SUCCESS
        assert result2.status == CommandStatus.SUCCESS


class TestCaseSensitivity:
    """Test case insensitivity."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, monkeypatch):
        """Setup authorized sender/chat for all tests in this class."""
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_SENDERS", {123})
        monkeypatch.setattr("app.platform.telegram_ingress_parser.AUTHORIZED_CHATS", {"-1001"})

    def test_uppercase_command(self):
        """Test uppercase command is accepted."""
        result = parse_command("/STATUS", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS

    def test_mixed_case_command(self):
        """Test mixed case command is accepted."""
        result = parse_command("/Pause operations", sender_id=123, chat_id="-1001")
        assert result.status == CommandStatus.SUCCESS
