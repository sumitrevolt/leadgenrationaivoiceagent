"""Cheap static-HTML guard (mirrors tests/test_office_map_frontend.py's style):
confirms the ledger timeline section exists and stays inside the Account view,
not competing with Home's one-job-above-the-fold rule."""


def test_combo_dashboard_has_timeline_section_in_account_view():
    html = open("frontend/customer_dashboard.html", encoding="utf-8").read()
    assert 'id="deliveryTimelineCard"' in html
    # Must live inside an account-view section (verified real attribute:
    # data-view="account", e.g. line 795's #billingCard), placed after
    # #billingCard (line 795) — not inside the home hero area (line 508+).
    billing_pos = html.index('id="billingCard"')
    timeline_pos = html.index('id="deliveryTimelineCard"')
    home_hero_pos = html.index('data-view="home" class="owner-hero"')
    assert timeline_pos > billing_pos
    assert not (home_hero_pos < timeline_pos < home_hero_pos + 2000), (
        "timeline card must not be crammed into the Home hero area"
    )


# customer_marketing.html/customer_voice.html (separate per-product fork checks
# used to live here) were confirmed unreachable duplicates of this single file
# and deleted 2026-07-07 — see tests/test_customer_dashboard_product_routing.py.
