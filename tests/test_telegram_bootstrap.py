"""Hermetic bootstrap retry and unknown-state safety tests."""
import json

import pytest

from scripts import telegram_setup as setup


@pytest.fixture
def harness(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "STATE_PATH", tmp_path / "state.json")
    calls = []

    def api(token, method, params):
        calls.append(method)
        return {
            "createForumTopic": {"message_thread_id": 10},
            "sendMessage": {"message_id": 20},
            "getChat": {"invite_link": "https://t.me/+existing"},
        }.get(method, True)

    monkeypatch.setattr(setup, "_api_call", api)
    group = {"name": "Test", "kind": "supergroup", "access": "private", "chat_id": -1001,
             "forum_topics": ["Health"], "intro": "Welcome"}
    return {"cross_product": [group]}, calls, api


def test_unknown_existing_chat_is_not_modified(harness):
    spec, calls, _ = harness
    assert setup.apply(spec, "test") == 1
    assert calls == []


def test_repeat_run_does_not_duplicate_or_rotate(harness):
    spec, calls, _ = harness
    spec["cross_product"][0]["bootstrap_empty_verified"] = True
    assert setup.apply(spec, "test") == 0
    assert setup.apply(spec, "test") == 0
    assert calls.count("createForumTopic") == 1
    assert calls.count("sendMessage") == 1
    assert "exportChatInviteLink" not in calls


def test_reconciled_existing_chat_never_creates(harness):
    spec, calls, _ = harness
    spec["cross_product"][0].update(topic_ids={"Health": 10}, intro_message_id=20)
    assert setup.apply(spec, "test") == 0
    assert "createForumTopic" not in calls
    assert "sendMessage" not in calls


def test_unknown_remote_outcome_blocks_retry(harness, monkeypatch):
    spec, calls, api = harness
    spec["cross_product"][0]["bootstrap_empty_verified"] = True

    def broken(token, method, params):
        if method == "createForumTopic":
            calls.append(method)
            raise RuntimeError("timeout after request")
        return api(token, method, params)

    monkeypatch.setattr(setup, "_api_call", broken)
    assert setup.apply(spec, "test") == 1
    assert setup.apply(spec, "test") == 1
    assert calls.count("createForumTopic") == 1
    assert json.loads(setup.STATE_PATH.read_text())["-1001"]["pending"]


def test_pin_failure_does_not_repeat_intro(harness, monkeypatch):
    spec, calls, api = harness
    spec["cross_product"][0]["bootstrap_empty_verified"] = True

    def broken(token, method, params):
        if method == "pinChatMessage":
            raise RuntimeError("no pin rights")
        return api(token, method, params)

    monkeypatch.setattr(setup, "_api_call", broken)
    assert setup.apply(spec, "test") == 1
    monkeypatch.setattr(setup, "_api_call", api)
    assert setup.apply(spec, "test") == 0
    assert calls.count("sendMessage") == 1


def test_missing_chat_is_partial_failure(harness):
    spec, calls, _ = harness
    spec["cross_product"][0]["chat_id"] = None
    assert setup.apply(spec, "test") == 1
    assert calls == []


def test_concurrent_or_interrupted_run_refuses(harness):
    spec, calls, _ = harness
    setup.STATE_PATH.with_suffix(".lock").write_text("")
    assert setup.apply(spec, "test") == 1
    assert calls == []


def test_description_respects_telegram_limit():
    assert len(setup._description({"purpose": "a" * 300})) == 255


def test_reconciliation_fills_saved_missing_ids(harness):
    spec, calls, _ = harness
    setup.STATE_PATH.write_text(json.dumps({"-1001": {"topic_ids": {}}}))
    spec["cross_product"][0].update(topic_ids={"Health": 10}, intro_message_id=20)
    assert setup.apply(spec, "test") == 0
    assert "createForumTopic" not in calls
    assert "sendMessage" not in calls


@pytest.mark.parametrize("value", [True, 0, -1, "10", 11])
def test_invalid_or_conflicting_reconciliation_is_refused(harness, value):
    spec, calls, _ = harness
    setup.STATE_PATH.write_text(json.dumps({"-1001": {"topic_ids": {"Health": 10}}}))
    spec["cross_product"][0].update(topic_ids={"Health": value}, intro_message_id=20)
    assert setup.apply(spec, "test") == 1
    assert calls == []
