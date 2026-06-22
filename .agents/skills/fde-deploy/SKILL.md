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
