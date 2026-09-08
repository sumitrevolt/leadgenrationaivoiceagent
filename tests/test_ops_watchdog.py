"""ops_watchdog — redis-down detection (proactive critical alert).

Redis is the Celery broker + cache + rate-limit + distributed call-state. When it
goes down, automation_health.queue_depth() silently returns -1 (looks like 'no
backlog'), so before this guard the operator got NO alert that Redis itself died.
These tests pin the new sense→alert behavior.
"""

from app.platform import ops_watchdog


def test_redis_down_is_critical():
    issues = ops_watchdog._detect({"redis_ok": False})
    by_key = {i["key"]: i for i in issues}
    assert "redis_down" in by_key
    assert by_key["redis_down"]["sev"] == "critical"
    assert "Redis" in by_key["redis_down"]["msg"]


def test_redis_ok_no_issue():
    assert not any(i["key"] == "redis_down" for i in ops_watchdog._detect({"redis_ok": True}))


def test_redis_unknown_stays_quiet():
    """None = can't assess (dev box, no redis lib/url) -> must NOT alert."""
    assert not any(i["key"] == "redis_down" for i in ops_watchdog._detect({"redis_ok": None}))
    assert not any(i["key"] == "redis_down" for i in ops_watchdog._detect({}))


def test_redis_ok_never_raises():
    """Real probe: returns a tri-state and never raises (covers ImportError/conn-fail)."""
    assert ops_watchdog._redis_ok() in (True, False, None)
