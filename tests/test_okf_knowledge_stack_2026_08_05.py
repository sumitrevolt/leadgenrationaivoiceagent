"""OKF knowledge-stack polish — ADR-119 Phase-1 (bundle + ingest gate + public path)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.platform import okf_bundle, okf_ingest


@pytest.fixture()
def tiny_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "knowledge"
    (root / "product").mkdir(parents=True)
    (root / "index.md").write_text(
        '---\nokf_version: "0.1"\ntitle: Index\n---\n\n# Index\n\nHello.\n',
        encoding="utf-8",
    )
    (root / "product" / "pricing-rules.md").write_text(
        "---\ntype: Policy\ntitle: Pricing rules\ntags: [billing]\n---\n\n"
        "# Pricing\n\npackages.py is the single source.\n",
        encoding="utf-8",
    )
    (root / "product" / "leaky.md").write_text(
        "---\ntitle: Bad\n---\n\napi_key: sk-abcdefghijklmnopqrstuvwxyz123456\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(root))
    monkeypatch.delenv("OKF_INGEST_ENABLED", raising=False)
    return root


def test_list_and_block_secrets(tiny_bundle: Path):
    docs = okf_bundle.list_docs(root=tiny_bundle)
    assert len(docs) == 3
    by = {d.relpath: d for d in docs}
    assert by["product/pricing-rules.md"].ok
    assert by["product/pricing-rules.md"].title == "Pricing rules"
    assert by["product/leaky.md"].blocked_reason == "secret_pattern"
    snap = okf_bundle.snapshot(root=tiny_bundle)
    assert snap["blocked_count"] == 1
    assert snap["ingest_enabled"] is False


def test_resolve_public_path_traversal(tiny_bundle: Path):
    assert okf_bundle.resolve_public_path("../etc/passwd", root=tiny_bundle) is None
    assert okf_bundle.resolve_public_path("..\\windows", root=tiny_bundle) is None
    p = okf_bundle.resolve_public_path("product/pricing-rules", root=tiny_bundle)
    assert p is not None
    assert p.name == "pricing-rules.md"
    assert okf_bundle.resolve_public_path("index.md", root=tiny_bundle) is not None


def test_route_knowledge_source_hints():
    assert okf_bundle.route_knowledge_source("kitne invoices paid hain?") == "postgres"
    assert okf_bundle.route_knowledge_source("pricing rule for starter") == "okf"
    assert okf_bundle.route_knowledge_source("blast radius of deploy_vps") == "graphify"
    assert okf_bundle.route_knowledge_source("salon festival caption ideas") == "qdrant"


def test_dry_run_skips_blocked(tiny_bundle: Path):
    out = okf_ingest.dry_run(root=tiny_bundle)
    assert out["dry_run"] is True
    assert out["ready_count"] == 2
    assert out["skipped_count"] == 1
    assert any(s["reason"] == "secret_pattern" for s in out["skipped"])
    assert "okf:product/pricing-rules.md" in out["sources"]


def test_ingest_fail_closed_when_flag_off(tiny_bundle: Path):
    out = okf_ingest.ingest(root=tiny_bundle, force=False)
    assert out["ok"] is False
    assert out["reason"] == "okf_ingest_disabled"


def test_ingest_with_fake_kb(tiny_bundle: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OKF_INGEST_ENABLED", "1")
    added: list[tuple] = []

    class _FakeKB:
        def add_documents(self, docs, source=None, namespace="default", replace_source=False):
            added.append((docs, source, namespace, replace_source))
            return 1

        def backend(self, namespace="default"):
            return "keyword"

    monkeypatch.setattr("app.voice_agent.knowledge_base.get_knowledge_base", lambda: _FakeKB())
    out = okf_ingest.ingest(root=tiny_bundle, force=False)
    assert out["ok"] is True
    assert out["chunks"] == 2
    assert out["namespace"] == "okf"
    assert all(t[2] == "okf" and t[3] is True for t in added)
    assert all(str(t[1]).startswith("okf:") for t in added)


def test_public_routes_and_admin_mount():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    # Public index should 200 when default public ON and real knowledge/ exists
    r = client.get("/okf/")
    assert r.status_code == 200
    assert "okf_version" in r.text or "LeadGen" in r.text or "OKF" in r.text
    # Traversal refuse
    assert client.get("/okf/../../CLAUDE.md").status_code == 404
    # Admin status mounted (TestClient may bypass cookie auth in this suite)
    st = client.get("/api/admin/okf/status")
    assert st.status_code != 404
    if st.status_code == 200:
        body = st.json()
        assert body.get("okf_version") == "0.1"
        assert body.get("namespace") == "okf"
        assert isinstance(body.get("paths"), list)
        assert body.get("ingest_enabled") is False
