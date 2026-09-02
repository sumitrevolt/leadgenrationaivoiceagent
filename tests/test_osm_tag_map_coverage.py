"""OSM tag-map coverage for the default prospect targets (2026-08-23).

The free OSM Overpass path is the no-key fallback for `prospector.run_prospecting`.
`_DEFAULT_TARGETS` exercises "solar installer" and "coaching institute" FIRST, but
those keywords were missing from `_OSM_TAG_MAP`, so `_osm_filters` fell to the
`name~` fallback and returned ~0 on Indian OSM — starving the free path.

These tests are deterministic (no Overpass network) and assert that every default
target keyword resolves to a tag filter (not the name~ fallback), so the map cannot
silently drift back to a gap. They do NOT assert that Overpass returns rows for the
tags — that is a runtime/coverage fact, not a unit contract.
"""

from __future__ import annotations

from app.platform import prospector


def test_default_targets_are_all_mapped_not_name_fallback():
    """Every _DEFAULT_TARGETS query must resolve to a real tag filter."""
    for t in prospector._DEFAULT_TARGETS:
        query = (t.get("query") or "").lower()
        filters = prospector._osm_filters(query)
        assert filters, f"default target {query!r} produced no filters"
        # The name~ fallback is a tell-tale of an UNMAPPED keyword; default targets
        # should never rely on it (it returns ~0 on Indian OSM).
        assert not any(f.startswith("name~") for f in filters), (
            f"default target {query!r} fell back to name~ search — add it to _OSM_TAG_MAP"
        )
        assert any(("=" in f) or ("~" in f) for f in filters), (
            f"default target {query!r} filters malformed: {filters}"
        )


def test_solar_installer_maps_to_craft_or_shop():
    filters = prospector._osm_filters("solar installer")
    assert filters
    # Must NOT be the name~ fallback.
    assert not any(f.startswith("name~") for f in filters)
    assert any(("solar_installer" in f) or ('shop="solar"' in f) for f in filters)


def test_coaching_institute_maps_to_an_amenity_or_office():
    filters = prospector._osm_filters("coaching institute")
    assert filters
    assert not any(f.startswith("name~") for f in filters)
    assert any(
        ("prep_school" in f) or ("educational_institution" in f) or ("language_school" in f)
        for f in filters
    )


def test_unchanged_mapped_keywords_still_work():
    """Existing mapped keywords keep their filters (no regression)."""
    assert any("estate_agent" in f for f in prospector._osm_filters("real estate agency"))
    assert any("restaurant" in f for f in prospector._osm_filters("restaurant"))
    assert any("dentist" in f for f in prospector._osm_filters("dental clinic"))


def test_query_without_city_returns_early():
    """_osm_search must return [] (never raise) when city is missing."""
    out = prospector._osm_search("restaurant", "", 5)
    assert out == []
