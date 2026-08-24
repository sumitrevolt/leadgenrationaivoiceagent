"""Security test — lifecycle_hooks SSRF guard (audit HIGH finding fix).

Uses IP LITERALS / internal hostnames so the checks resolve offline (no real DNS).
"""

from app.agents import lifecycle_hooks


def test_rejects_loopback_and_linklocal():
    assert lifecycle_hooks._is_safe_target("http://127.0.0.1/x")[0] is False
    assert lifecycle_hooks._is_safe_target("http://169.254.169.254/latest/meta-data")[0] is False


def test_rejects_internal_hostnames():
    for h in (
        "http://localhost/x",
        "http://qdrant:6333",
        "http://pgbouncer:6432",
        "http://redis/x",
    ):
        assert lifecycle_hooks._is_safe_target(h)[0] is False


def test_rejects_non_http_scheme():
    assert lifecycle_hooks._is_safe_target("ftp://example.com")[0] is False
    assert lifecycle_hooks._is_safe_target("file:///etc/passwd")[0] is False
    assert lifecycle_hooks._is_safe_target("")[0] is False


def test_allows_public_ip_literal():
    ok, why = lifecycle_hooks._is_safe_target("https://8.8.8.8/hook")
    assert ok is True, why


def test_register_blocks_unsafe_target(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle_hooks, "_DATA_FILE", str(tmp_path / "hooks.json"))
    res = lifecycle_hooks.register("pre_task", "evil", "webhook", "http://169.254.169.254/")
    assert res["ok"] is False
    assert "unsafe" in res["error"].lower()


def test_register_allows_safe_target(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle_hooks, "_DATA_FILE", str(tmp_path / "hooks.json"))
    res = lifecycle_hooks.register("post_task", "ok", "webhook", "https://8.8.8.8/hook")
    assert res["ok"] is True
