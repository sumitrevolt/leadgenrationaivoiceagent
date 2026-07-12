# Prospector empty-result fallback

## Goal

Keep Rohan's active prospecting agent productive when a configured Google Maps
key is denied, quota-limited, or returns no businesses.

## Root cause

`run_prospecting()` selected Google Maps whenever a non-placeholder key existed.
An empty Google response did not trigger the existing free OSM path, so the
agent recorded successful-but-empty queries and produced no new prospects.
The OSM helper also used synchronous urllib directly inside the async job.

## Contract

- Google results remain primary when present.
- Empty Google results fall back per query to legal, free OSM Overpass data.
- OSM network work runs off the event loop.
- No ToS-blocked scraper or automatic outreach is added.
- Summary identifies `google_maps_api+osm_fallback` when fallback produces rows.

## Verification

Add a regression test for empty Google results -> OSM rows and run the active
agent/scheduler suites plus `prod_check.py` and `check_secrets.py`.
