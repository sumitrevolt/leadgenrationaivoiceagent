import json
from datetime import datetime, timedelta, timezone

from app.platform import automation_log_service as svc


def test_log_event_returns_id_when_db_fails_but_jsonl_fallback_writes(monkeypatch, tmp_path):
    path = tmp_path / "automation_logs.jsonl"
    monkeypatch.setattr(svc, "_JSONL_PATH", str(path))

    import app.models.base as base_mod

    def broken_session():
        raise RuntimeError("db down")

    monkeypatch.setattr(base_mod, "get_db_session", broken_session)

    log_id = svc.log_event(client_id="c1", job_type="daily_content", status="success")

    assert log_id
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["id"] == log_id
    assert rows[0]["client_id"] == "c1"
    assert rows[0]["job_type"] == "daily_content"


def test_jsonl_read_filters_days_and_has_run_today(monkeypatch, tmp_path):
    path = tmp_path / "automation_logs.jsonl"
    monkeypatch.setattr(svc, "_JSONL_PATH", str(path))
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=9)
    rows = [
        {
            "id": "old",
            "client_id": "c1",
            "job_type": "daily_content",
            "status": "success",
            "created_at": old.isoformat(timespec="seconds"),
        },
        {
            "id": "new",
            "client_id": "c1",
            "job_type": "daily_content",
            "status": "success",
            "created_at": now.isoformat(timespec="seconds"),
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    import app.models.base as base_mod

    def broken_session():
        raise RuntimeError("db down")

    monkeypatch.setattr(base_mod, "get_db_session", broken_session)

    recent = svc.get_logs(client_id="c1", job_type="daily_content", days=7)

    assert [r["id"] for r in recent] == ["new"]
    assert svc.has_run_today("c1", "daily_content") is True
