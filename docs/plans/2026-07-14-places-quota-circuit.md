# Places quota circuit-breaker plan — 2026-07-14

## Goal

Stop Google Places `429` quota exhaustion from cascading into legacy geocoding
and browser-scraping fallbacks across the prospecting scheduler.

## Confirmed production evidence

The worker logged repeated `Places(New) HTTP 429` responses, then ran legacy
geocoding for the same prospecting batch. `_search_with_places_new()` returned
an indistinguishable empty list for quota exhaustion, so its caller retried a
different Google endpoint and could continue to scraping.

## Safe change

Add a Redis-backed, best-effort `places` cooldown (24 hours by default). A
429 records the integration failure, starts the cooldown, and terminates that
search without any fallback. A normal empty Places response keeps its existing
OSM/legacy fallback behaviour. Redis failure does not crash prospecting.

## Contract tests

1. A quota-exhausted result never invokes the legacy or browser fallback.
2. A normal empty result still invokes the legacy fallback.
3. A 429 records the failure and sets the shared cooldown.
4. The cooldown helpers never raise when Redis is unavailable.

## Rollback

Revert only the targeted Google Maps scraper and integration-health files;
there is no schema, customer-data, compliance, or feature-flag change.
