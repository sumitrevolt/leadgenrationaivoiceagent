"""Phase-3 tests: minute metering/enforcement (billing.usage) + tenant white-label.

Free-stack. No DB rows required — tests cover the math + fail-open + host parsing.
"""

from app.billing import usage
from app.middleware import tenant


def test_plan_minutes():
    assert usage.plan_minutes("advanced") == 500
    assert usage.plan_minutes("starter") == 0
    assert usage.plan_minutes("growth") == 0
    assert usage.plan_minutes(None) == 0
    assert usage.plan_minutes("unknown") == 0


def test_has_minutes_fail_open_for_noncalling_plans():
    # cap<=0 (starter/growth/unknown) -> fail-OPEN (do not block calls here).
    assert usage.has_minutes("no-such-client", plan="starter") is True
    assert usage.has_minutes("no-such-client", plan="growth") is True
    # advanced + a client with no usage rows -> within cap -> allowed.
    assert usage.has_minutes("no-such-client", plan="advanced") is True


def test_record_and_used_are_safe_without_data():
    assert usage.record_call_usage("", 120) is False  # no client -> no-op
    assert usage.record_call_usage("x", 0) is False  # zero duration -> no-op
    assert usage.minutes_used_this_period("") == 0
    assert usage.minutes_remaining("no-such-client", plan="advanced") == 500


def test_own_brand_call_usage_resolves_sql_platform_client(monkeypatch):
    class _Query:
        def __init__(self, model):
            self.model = model
            self._mode = ""

        def filter(self, expr):
            text = str(expr)
            if "clients.id" in text:
                self._mode = "id"
            else:
                self._mode = "name"
            return self

        def first(self):
            if self._mode == "id":
                return type("ClientRow", (), {"id": "platform"})()
            return None

    class _DB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, model):
            return _Query(model)

    monkeypatch.setattr("app.models.base.get_db_session", lambda: _DB())
    assert usage.resolve_client_id("LeadGen AI") == "platform"


def test_subdomain_parsing():
    assert tenant._subdomain("agency.leadsgenai.in") == "agency"
    assert tenant._subdomain("leadsgenai.in") == ""
    assert tenant._subdomain("www.leadsgenai.in") == ""
    assert tenant._subdomain("foo.bar.leadsgenai.in") == "foo"
    assert tenant._subdomain("") == ""


def test_resolve_branding_apex_reserved_and_unknown():
    assert tenant.resolve_branding("leadsgenai.in") is None
    assert tenant.resolve_branding("www.leadsgenai.in") is None
    assert tenant.resolve_branding("app.leadsgenai.in") is None  # reserved
    assert tenant.resolve_branding("no-such-agency.leadsgenai.in") is None  # no client


def test_call_request_has_client_id_default():
    from app.telephony.call_manager import CallRequest

    r = CallRequest(
        lead_id="l",
        phone_number="p",
        campaign_id="c",
        niche="n",
        client_name="cn",
        client_service="cs",
        script_name="s",
        lead_data={},
    )
    assert r.client_id == ""


def test_imports_clean_no_circular():
    from app.main import app

    assert len(app.routes) > 100
