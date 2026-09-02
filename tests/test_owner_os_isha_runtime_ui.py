"""Contract: Owner OS Runtime panel exposes Isha tenant draft controls."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "owner_os.html").read_text(encoding="utf-8")


def test_runtime_panel_has_isha_tenant_controls():
    assert 'id="rtTenant"' in HTML
    assert 'id="rtTopic"' in HTML
    assert "runtimeIsha()" in HTML
    assert "Run Isha draft brief" in HTML
    assert "tenant_id required" in HTML
    assert "published=false" in HTML or "published=false" in HTML
