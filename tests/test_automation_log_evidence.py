"""ADR-068: automation_logs.evidence_url proof column (migration 014).

Covers the model column, the migration chain, the service round-trip (write +
read echo evidence_url), and the client_report + panel wiring.
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _boom():
    raise RuntimeError("no db (test) -> JSONL fallback")


def test_model_has_evidence_url_column():
    from app.models.automation_log import AutomationLog

    assert "evidence_url" in AutomationLog.__table__.columns


def test_migration_014_present_and_chained():
    p = ROOT / "alembic" / "versions" / "014_add_automation_log_evidence.py"
    spec = importlib.util.spec_from_file_location("m014", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "014_add_automation_log_evidence"
    assert m.down_revision == "013_add_automation_logs"


def test_log_event_and_get_logs_roundtrip_evidence_url(monkeypatch, tmp_path):
    import app.models.base as base
    from app.platform import automation_log_service as svc

    # Force the DB path to fail so we exercise the JSONL fallback deterministically.
    monkeypatch.setattr(svc, "_JSONL_PATH", str(tmp_path / "auto.jsonl"))
    monkeypatch.setattr(base, "get_db_session", _boom, raising=False)

    log_id = svc.log_event(
        job_type="client_report",
        client_id="c1",
        status="success",
        evidence_url="data/client_reports/c1.html",
    )
    assert log_id
    rows = svc.get_logs(client_id="c1", days=30)
    assert rows
    assert rows[0].get("evidence_url") == "data/client_reports/c1.html"


def test_client_report_passes_evidence_url():
    src = (ROOT / "app" / "marketing" / "client_report.py").read_text(encoding="utf-8")
    assert "evidence_url=_path" in src


def test_panel_proof_prefers_evidence_url():
    html = (ROOT / "frontend" / "delivery_command_center.html").read_text(encoding="utf-8")
    assert "r.evidence_url" in html
