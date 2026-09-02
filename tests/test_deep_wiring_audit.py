"""Regression contracts for the production frontend wiring audit."""

from scripts import deep_wiring_audit as audit


def test_dynamic_route_matcher_is_compiled_and_cached():
    audit._route_to_regex.cache_clear()
    routes = {"/api/customers/{customer_id}/reports/{report_id}"}

    assert audit.route_exists("/api/customers/acme/reports/monthly", routes)
    first = audit._route_to_regex.cache_info()
    assert audit.route_exists("/api/customers/jiya/reports/weekly", routes)
    second = audit._route_to_regex.cache_info()

    assert first.misses == 1
    assert second.hits >= 1
