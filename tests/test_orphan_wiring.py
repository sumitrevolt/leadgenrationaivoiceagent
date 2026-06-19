"""Orphan modules now wired (docs/Automation_Marketing_Repos.md gaps closed).

seo_tools → ads_copy.campaign_plan ('keyword_matrix' field, advertools-backed,
defensive [] without the dep). to_markdown → onboarding fallback (defensive).
"""


def test_campaign_plan_exposes_keyword_matrix():
    from app.marketing.ads_copy import campaign_plan

    plan = campaign_plan("Acme Solar", "Solar", offer="10% off", city="Pune", niche="solar")
    # new additive field — list always (populated when advertools installed, else [])
    assert "keyword_matrix" in plan
    assert isinstance(plan["keyword_matrix"], list)
    # existing contract intact
    assert isinstance(plan.get("keywords"), list) and plan["keywords"]
    assert isinstance(plan.get("negative_keywords"), list)


def test_seo_tools_defensive_without_dep():
    from app.marketing import seo_tools

    # advertools optional — never raises, returns safe types either way
    kws = seo_tools.generate_keywords(["solar panels"], ["price", "near me"])
    assert isinstance(kws, list)
    slots = seo_tools.split_ad("Best solar panels in Pune with free site visit", (30, 30, 90))
    assert isinstance(slots, list)


def test_to_markdown_defensive_without_dep():
    from app.lead_scraper.to_markdown import to_markdown

    # markitdown optional — empty source + missing dep => "" (never raises)
    assert to_markdown("") == ""
    assert isinstance(to_markdown("https://example.com/x.pdf"), str)
