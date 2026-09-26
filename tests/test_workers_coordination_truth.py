from __future__ import annotations


def test_owner_eight_are_hmac_known_tools() -> None:
    from app.platform.coordination_hub_auth import _KNOWN_TOOLS

    expected = {
        "agnes",
        "minimax",
        "hermes",
        "openclaw",
        "freebuff",
        "cline",
        "opencode",
        "workbuddy",
    }
    assert expected <= set(_KNOWN_TOOLS)


def test_workers_command_reconciles_6_9_31_8() -> None:
    from app.integrations.telegram_owner_commands import cmd_workers

    result = cmd_workers()
    assert result.data["cli_worker_count"] == 6
    assert result.data["supervisory_count"] == 9
    assert result.data["agent_count"] == 31
    assert result.data["desktop_total"] == 8
    assert {d["id"] for d in result.data["desktop_apps"]} == {
        "agnes",
        "minimax",
        "hermes",
        "openclaw",
        "freebuff",
        "cline",
        "opencode",
        "workbuddy",
    }


def test_workers_command_uses_fresh_presence(monkeypatch) -> None:
    import app.integrations.telegram_owner_commands as commands
    import app.platform.coordination_hub_auth as auth
    import app.platform.coordination_hub_events as events

    now = 1_800_000_000
    monkeypatch.setattr(commands.time, "time", lambda: now)
    monkeypatch.setattr(
        events,
        "list_presence",
        lambda: {
            "tools": {
                "opencode": {"tool_id": "opencode", "status": "online", "last_seen": now - 12},
                "hermes": {"tool_id": "hermes", "status": "online", "last_seen": now - 900},
            },
            "updated_at": now - 12,
        },
    )
    monkeypatch.setattr(
        auth,
        "tool_auth_status",
        lambda: {"tools_configured": {"opencode": True, "hermes": True}},
    )

    result = commands.cmd_workers()
    by_id = {d["id"]: d for d in result.data["desktop_apps"]}
    assert by_id["opencode"]["runtime_status"] == "VERIFIED_WORKING"
    assert by_id["opencode"]["last_seen_age_s"] == 12
    assert by_id["hermes"]["runtime_status"] == "STALE"
    assert by_id["agnes"]["runtime_status"] == "REGISTERED_NOT_ENROLLED"
