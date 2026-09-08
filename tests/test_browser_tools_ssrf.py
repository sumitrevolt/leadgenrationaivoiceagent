"""Contract for browser_tools SSRF guard (audit 2026-07-06, 2nd-pass sec fix).

`fetch_rendered`/`extract` drive a headless browser to a caller-supplied URL. Even
though the tools are super-admin + BROWSER_TOOLS-gated, a compromised admin could
pivot to internal hosts (127.0.0.1:6333 Qdrant, 169.254.169.254 cloud metadata,
Docker net). `_url_is_safe` blocks nav to any host resolving to a non-public IP.
Offline-safe: literal IPs + localhost resolve without DNS.
"""

import pytest

from app.agents.browser_tools import _url_is_safe


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
        "http://127.0.0.1:6333/collections",  # loopback (Qdrant)
        "http://localhost/admin",  # loopback by name
        "http://10.0.0.5/",  # private
        "http://192.168.1.1/",  # private
        "https://172.16.0.9/",  # private
        "http://0.0.0.0/",  # unspecified
        "ftp://example.com/",  # non-http scheme
        "file:///etc/passwd",  # non-http scheme
        "not-a-url",  # unparseable
        "",  # empty
    ],
)
def test_unsafe_urls_blocked(url):
    assert _url_is_safe(url) is False


def test_public_ip_literal_allowed():
    # 8.8.8.8 is a public IP literal — resolves without DNS, so offline-safe.
    assert _url_is_safe("http://8.8.8.8/") is True


async def test_fetch_rendered_blocks_private_even_when_enabled(monkeypatch):
    # With the flag ON, an internal URL must be refused BEFORE any browser launch.
    monkeypatch.setenv("BROWSER_TOOLS", "1")
    from app.agents import browser_tools

    out = await browser_tools.fetch_rendered("http://127.0.0.1:6333/")
    assert out["ok"] is False
    assert out["error"] == "blocked_unsafe_url"
