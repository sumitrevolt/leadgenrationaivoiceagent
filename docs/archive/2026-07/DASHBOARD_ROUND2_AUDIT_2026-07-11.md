# Dashboard Round-2 Audit — 2026-07-11 (post-Loop 27)

**Files audited:** `customer_dashboard.html` (~3540 lines), `admin_dashboard.html` (~4590 lines) — after Loop 27's top-10 UX ship.

## HIGH-IMPACT (fix first)

1. **Admin `toast()` is UNDEFINED** in 10 social-cockpit call sites (A-1473, 1474, 1477, 1479, 1492, 1493, 1494, 1609, 1610, 1611) — every retry-job / cancel-job / emergency-stop / pause-platform / pause-clients throws `ReferenceError`, swallowed by outer try/catch → OPERATOR SEES NO FEEDBACK. Fix (1 line): alias `const toast = (t,m) => adminToast(t + (m?' — '+m:''));` at top of admin script.
2. **Mobile bottom nav missing 3 tabs.** (C-1252-1268) Only 5 tabs: home/setup/calendar/leads/billing. **Missing: Reports, Delivery, Support.** Loop 27 just added Reports content — mobile users can't reach it. Delivery + Support similarly unreachable on phone.
3. **Admin dash renders ~20 top-level cards on landing.** `showAdminView` sets `data-active-view` on body but no matching CSS rule hides non-active views (customer file has this at C-149; admin file doesn't). The view-switcher only updates `<h1>` — all 20 sections stay visible. Either add the CSS or delete the dead switcher.

## MED-IMPACT

4. **`fmtMoney(n,cur)` / `abMoney` always use `en-IN` locale grouping** for USD/EUR (C-2525, A-3441) — a $1,000,000 renders as `$10,00,000`. Wrong for international invoices.
5. **UPI approve/reject/activate use raw `alert()`** (A-4008-4088) on the highest-revenue admin flow. Inconsistent with `adminToast` used elsewhere.
6. **Agent-ask placeholder hardcodes "jiya makeover"** (C-343) — every customer sees a single-tenant name.
7. **401/403 responses render as "undefined" / blank / stuck at "Loading…"** in several loaders: `loadApprovals` C-2632 (no ok-check), billing fetches A-3499-3501 (only status!==404 caught), `openClientTimeline` A-2273 leaves "Loading…" forever on non-ok.
8. **Loop 27 modals lack focus-trap + programmatic `aria-modal`** — Tab escapes modal to background. Fix: on open, `overlay.setAttribute("aria-modal","true")` + trap Tab within modal children.
9. **21× webhook + 2FA operations use `alert()`/`confirm()`** (C-2382-2520) — should use `toast()` for consistency.
10. **`showView` sticky-state doesn't persist across page reload.** `history.replaceState` only updates URL; user landing on `/app/customer/marketing` without a hash always sees Home even if they last used Leads.

## LOW-IMPACT (polish)

11. **Filters reset on reload** — date-range (C-499-501), lead filters (C-884-891), call filters (C-955), campaign selector (C-505). Should mirror admin's `admin_advTechOpen` localStorage pattern.
12. **Support view has two nearly-identical WhatsApp cards** (C-1218 + C-1234). One is enough.
13. **Dead functions / vars:** `setText` (C-1503), `toggleDetails` (C-1530), `openAdvancedSettings` (C-1635), `_origRenderLeadsOld` (C-3522), `expandSystemGroup` (A-3170), `showAdminView` (A-2628 — see #3).
14. **`_ondsm2faCode` TOTP input has no `inputmode="numeric"` + no `pattern`** (C-1099) — mobile shows QWERTY keyboard.
15. **Form validation gaps:** `onbPhone` (A-450) no `pattern=[6-9]\d{9}`, `upiRefInp` (C-1023) no `required`, `whUrl` (C-1067) no https-only `pattern`, `sec2faDisCode` (C-1108) zero validation.
16. **Skeleton loading rows** lack `aria-hidden="true"` and parent tables lack `aria-busy` — screen readers narrate placeholder content.
17. **Calendar grid is 7-col × 80px min-height** on ≤560px (C-796) — overflows viewport.
18. **`.badge-demo` hidden on <560px** (C-414) — user may not realize they're viewing demo data on phone.
19. **`applyDateRange` defined twice** (C-1791, C-3576) — one is a shadow.
20. **Two nearly-duplicate "Support" cards** (delivery view + support view) render the same content — DRY up.

## VESTIGIAL admin sections (candidate for collapse-by-default)
`sec-ops2026` (Deliverability), `sec-audit` (Activity log), `sec-api` (API infra), `sec-sync` (sync health), `sec-recordings`, `sec-webcalls`, `sec-delivery-queue`, `sec-diff` (approvals — often empty).

## Backend method-mismatch spot-checks (needs manual verify)
- `DELETE /api/data/niches/pending/{id}` (A-3483)
- `PATCH /api/growth/selfimprove/approval/{id}/{action}` (A-3712)
- `DELETE /api/customer/social/accounts/{plat}?account_id=...` (Loop 27) — cross-check backend accepts BOTH `account_ref` and `account_id`.
