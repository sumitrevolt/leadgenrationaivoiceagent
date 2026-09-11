---
name: fde-deploy
description: Use the Forward Deployed Engineer (FDE) agents to "deploy" marketing + website + automation for a client in one shot from a brief. Use when the user says "client ke liye setup karo", "FDE deploy", "marketing+website launch karo", names Isha/Veer/Aarav/Neo, "done-for-you client", or wants an agent to assemble a client's growth stack.
---

# FDE Deploy (Forward Deployed Engineer agents)

`app/agents/fde.py` — 4 personas + 11 skills. free-LLM **planner** brief se relevant skill-subset chunता hai, phir deploy karta. Sab skills EXISTING capabilities ko wrap karte hain (REBUILD NAHI). Ban-safe (drafts/setup; auto-publish/send nahi). Handler kabhi raise nahi karta.

## Personas
- **Isha** — Marketing (posts, hashtags, GBP, festivals, reviews).
- **Veer** — Website/mini-site + embed widget + booking.
- **Aarav** — Automation (drip journeys, content schedule, lead capture).
- **Neo** — Full-stack (planner sab domains se chunता) — **default**.

## The 11 skills (wrap existing modules)
marketing_pack (`niche_pack`) · social_posts (`post_generator`) · hashtags · gbp_content (`gbp_text`) · festival_posts (`festivals`) · review_kit (`review_engine`) · competitor · minisite (`/b/<slug>`) · embed_widget · drip_journey (`journeys`) · content_schedule.

## Use it (admin)
- List: `GET /api/growth/fde/agents` (personas + skills).
- Deploy: `POST /api/growth/fde/deploy`:
  ```json
  {"business_name":"Sharma Solar","niche":"solar_residential","city":"Pune",
   "slug":"sharma-solar","client_id":"<optional>","agent":"neo",
   "brief":"3 mahine me leads 2x, festival posts + website"}
  ```
  Planner brief se skills choose karke deploy karta → per-skill output/draft response me.

## Gotchas
- `agent` na do to Neo (full-stack planner) default. Brief jitna specific, planner utna sahi skills chunता.
- `client_id` do to deploy us client se link (dashboard me dikhता).
- Real auto-publish (Meta/GBP) app-review/DLT pe blocked — FDE **drafts/setup** deta, human 1-click post.
- Sab free-stack + import-safe. Rebuild mat karo — pehle se bana hai (commit 647096c).

## Verify
`/api/growth/fde/deploy` response me chosen skills + per-skill output. Mini-site live: `/b/<slug>` → 200. Widget: `GET /api/marketing/embed-snippet?slug=<slug>`. Live demo proven: Neo ne Sharma Solar ke liye 4/4 skills deploy kiye.

## Enterprise gate

Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (full loop `fable-operating-manual`).

**Change-risk tier:** FDE deploy run karna (admin) = **Standard** (drafts/setup, koi auto-publish nahi). FDE handler/skill **code** edit = **High-risk** (client-facing output + ban-safety) — additive only, `fde.py` ka 11-skill wrap-pattern (REBUILD NAHI, commit 647096c) preserve karo.

- **Safety / ban-safe (fail-CLOSED):** FDE drafts/setup hi deta — Meta/GBP auto-publish app-review/DLT pe **blocked**, human 1-click post. Yeh boundary KABHI mat todo (auto-broadcast = number ban). Naya skill bhi import-safe + free-stack + handler kabhi raise nahi (defensive).
- **Idempotency:** dobara deploy pe duplicate mini-site/widget na bane — same `slug`/`client_id` pe re-run safe (existing wrap). `client_id` do to deploy us client se link (dashboard).
- **Tenant boundary:** deploy hamesha sahi `client_id` se scoped; ek client ka content doosre ke namespace/dashboard me leak na ho.
- **Observability/Rollback (NAMED):** deploy response me chosen skills + per-skill output = audit trail. Galat/junk draft → wo ek draft delete (publish nahi hua = blast-radius zero); FDE skill code regression → git-revert + recreate.

**Evidence (done):** `/api/growth/fde/deploy` response me per-skill output + `/b/<slug>` → 200 + `GET /api/marketing/embed-snippet?slug=<slug>` valid snippet. FDE code chhua to `.venv\Scripts\python.exe scripts\prod_check.py` + touched-area test green. Bina mini-site 200 done mat bolo.
