# Customer Mobile Setup and Dashboard UX Design

Date: 2026-07-11
Status: Approved design; implementation pending

## Goal

Customer ko mobile dashboard par turant samajh aaye ki setup kahan se aur kaise complete karna hai. Permanent loading states, hidden setup navigation, technical social-token controls, aur vague actions remove karne hain without changing billing, auth, tenant isolation, publishing safety, or compliance gates.

## Success Criteria

- Mobile bottom navigation me visible `Setup` action ho.
- Incomplete customer setup login ke baad guided setup ko primary action banaye.
- Setup flow four clear steps me ho: Business, Brand, Social, Review.
- Customer setup progress, completed fields, aur next action plain Hinglish me dekhe.
- Profile/social API failure ya timeout permanent loader na chhode; retry action show ho.
- Advanced token connection normal customer flow ko clutter na kare.
- Actual demo response ke bina `Demo Data` badge show na ho.
- Home, setup, posts, leads, and plan navigation 380px viewport par usable ho.

## Recommended Experience

### Mobile Navigation

Bottom bar order:

1. Home
2. Setup
3. Posts
4. Leads
5. Plan

Each action changes the dashboard view directly. `Setup` opens the setup view, not a scroll target on Home. Active state follows the current view. The floating `Action kholo` button is removed on mobile; the relevant screen owns its primary CTA.

### Home Screen

Home remains a short operational summary. If setup is incomplete, the first visible card becomes:

- `Aapka setup X% complete`
- one plain-language missing-item summary
- primary `Setup continue karein` button
- estimated effort such as `2 minute`

Completed customers see the normal daily-work action instead.

### Guided Setup

The existing profile and social APIs remain the source of truth. The UI presents them as one four-step wizard:

1. Business: name, city, phone, services, target area, WhatsApp.
2. Brand: tagline, logo text, tone, colours, website, audience, language.
3. Social: social links, selected content channels, cadence, posting days/times, approval preference.
4. Review: completion summary, missing required fields, saved status, and optional first-week plan generation.

Save is step-scoped. A successful save advances to the next step. Existing values pre-fill. Optional fields are clearly marked.

### Social Connections

Simple social links and channel selection appear first. Direct provider access-token connection is placed inside a collapsed `Advanced account connection` section with an honest explanation that provider approval may still be pending. Saving preferences never enables publishing; existing `SOCIAL_ENGINE` and provider gates remain unchanged.

### Loading and Error States

Both profile and social requests get a bounded client timeout. Each panel moves from loading to one of:

- loaded form;
- login-required message;
- retryable `Setup load nahi hua` state with `Dobara try karein`;
- partial state when one API succeeds and the other fails.

No fetch failure can leave `Load ho raha hai…` indefinitely. Errors remain customer-safe and do not expose raw server details.

### Demo and Product Awareness

`Demo Data` appears only when the dashboard payload explicitly reports sample/demo data. Marketing-only setup fields stay hidden on the Voice product. Combo retains both relevant surfaces. Auth and tenant identity continue to come only from the existing customer token.

## Technical Boundaries

- Primary file: `frontend/customer_dashboard.html`.
- Existing APIs reused: `GET/POST /api/customer/profile`, `GET/POST /api/customer/social/config`, social accounts, and first-week campaign endpoint.
- Backend changes only if investigation proves a response-contract defect.
- No new database or store.
- No pricing, billing, telephony, outbound, or compliance changes.
- No auto-post activation and no `.env` changes.

## Failure Investigation Before UI Edit

The screenshot conflicts with current view CSS because Setup cards appear while Home is active. Implementation begins by comparing the live-served dashboard asset with the local file and checking browser/runtime errors. The fix must address the proven source: stale deployed asset/cache, incorrect response headers, or runtime view-state failure. UI redesign must not hide that defect.

## Testing

- Add/extend frontend contract tests for Setup bottom-nav, four steps, retry states, demo badge behavior, and mobile primary CTA.
- Preserve profile and social API tests and customer isolation checks.
- Run HTML/JS validation.
- Run targeted customer dashboard/setup/social tests.
- Run `prod_check.py`, explorer check, secrets scan, and duplicate-route check if backend changes.
- Verify at 380px and desktop with an authenticated customer session.
- After an authorized deploy, hard-refresh and confirm the live asset plus setup save/reload flow.

## Rollback

Frontend-only rollback is the prior `customer_dashboard.html`. Existing API contracts remain unchanged, so rollback requires no data migration. If a backend contract fix is required, it must be additive and independently reversible.

## Out of Scope

- Provider app approvals.
- Enabling real social publishing.
- Voice outbound activation.
- Billing or pricing changes.
- A full visual redesign of every dashboard screen.
