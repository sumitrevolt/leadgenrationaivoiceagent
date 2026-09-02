import asyncio

from app.automation import flow_http


def test_host_allowed_suffix_logic():
    allow = ["leadsgenai.in"]
    assert flow_http._host_allowed("leadsgenai.in", allow)
    assert flow_http._host_allowed("ntfy.leadsgenai.in", allow)
    assert not flow_http._host_allowed("evil.com", allow)
    assert not flow_http._host_allowed("notleadsgenai.in", allow)  # suffix-boundary safe
    assert not flow_http._host_allowed("leadsgenai.in", [])  # empty allowlist denies all


def test_is_public_blocks_private_and_internal():
    assert not flow_http._is_public("127.0.0.1")
    assert not flow_http._is_public("10.0.0.5")
    assert not flow_http._is_public("localhost")
    assert not flow_http._is_public("foo.internal")
    assert not flow_http._is_public("")


def test_run_rejects_bad_method(monkeypatch):
    monkeypatch.setenv("FLOW_HTTP_ALLOWLIST", "leadsgenai.in")
    r = asyncio.run(flow_http.run({"url": "https://leadsgenai.in/x", "method": "DELETE"}))
    assert r["ok"] is False and "method" in r["detail"].lower()


def test_run_rejects_non_http_scheme(monkeypatch):
    monkeypatch.setenv("FLOW_HTTP_ALLOWLIST", "leadsgenai.in")
    r = asyncio.run(flow_http.run({"url": "ftp://leadsgenai.in/x"}))
    assert r["ok"] is False


def test_run_rejects_host_not_on_allowlist(monkeypatch):
    monkeypatch.setenv("FLOW_HTTP_ALLOWLIST", "leadsgenai.in")
    r = asyncio.run(flow_http.run({"url": "https://evil.com/x"}))
    assert r["ok"] is False and "allowlist" in r["detail"].lower()


def test_run_empty_allowlist_denies_all(monkeypatch):
    monkeypatch.delenv("FLOW_HTTP_ALLOWLIST", raising=False)
    r = asyncio.run(flow_http.run({"url": "https://leadsgenai.in/x"}))
    assert r["ok"] is False


def test_provider_hosts_rejected_with_realistic_allowlist(monkeypatch):
    monkeypatch.setenv("FLOW_HTTP_ALLOWLIST", "leadsgenai.in,ntfy.leadsgenai.in")
    for h in ("api.telegram.org", "graph.facebook.com"):
        r = asyncio.run(flow_http.run({"url": f"https://{h}/send"}))
        assert r["ok"] is False


def test_run_get_success_mocked(monkeypatch):
    monkeypatch.setenv("FLOW_HTTP_ALLOWLIST", "leadsgenai.in")
    monkeypatch.setattr(flow_http, "_is_public", lambda h: True)

    class FakeResp:
        status_code = 200
        text = "x" * 10

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return FakeResp()

        async def post(self, url, headers=None, json=None):
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    r = asyncio.run(flow_http.run({"url": "https://leadsgenai.in/health"}))
    assert r["ok"] is True and "200" in r["detail"]
