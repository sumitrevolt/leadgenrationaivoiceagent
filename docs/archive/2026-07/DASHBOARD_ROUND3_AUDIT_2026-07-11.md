# Dashboard Round-3 Audit — 2026-07-11 (post Loop 27 + Loop 28)

**Files audited (post-Loop-28):**
- `frontend/customer_dashboard.html` — 3327 lines
- `frontend/admin_dashboard.html` — 4427 lines

**Excluded (already SHIPPED in Loops 27/28):** Setup Wizard logged-out gate, Reports view content, `<details open>` on Social Advanced, `openConnectDialog` inline modal, dead `#billManageBtn` removal, `#sec-upi-selfserve` hoisted out of Ops collapse, `#platformDialBanner`, `agentAsk` structured errors, `c360ResetPassword` inline modal + strength meter, `disconnectSocialAccount` opaque `account_id`, admin `toast` alias, mobile More sheet (Delivery/Reports/Support), admin `data-active-view` dead switcher (call removed), `fmtMoney` locale-aware, UPI approve/reject/activate → `adminToast`, "jiya makeover" placeholder, `applyDateRange` de-duplication.

Backend cross-check (`app/api/customer_dashboard.py:1583–1798`) confirms `GET /social/accounts` returns opaque `account_id` (16-char sha1 of `client|plat|ref`) and `DELETE /social/accounts/{plat}` accepts BOTH `account_id` (preferred) and legacy `account_ref` — Loop 27 contract is intact. `POST /api/upi/submit` in `upi_payments.py:39–84` derives `client_id` from JWT and IGNORES `body.client_id` — cross-tenant submission blocked at server. Billing endpoints (`billing.py:63–92`) use `_authed_client_id` which overrides query `client_id` for customer role.

---

## P0 — Security / compliance / data-loss / prod outage

### R3-1. Setup Wizard "Review → Mera 7-din ka plan banao" is a silent no-op (dead handler resurfaced)
- **File:** `frontend/customer_dashboard.html:2823` (Review-step button) → handler at `2949` `generateFirstWeek()`.
- **Observed:** Review-step markup renders `<button class="btn primary marketing-only" onclick="generateFirstWeek()">Mera 7-din ka plan banao</button>` with NO `id="swSeedBtn"`. `generateFirstWeek()` line 2950 does `const btn=document.getElementById("swSeedBtn"); if(!btn) return;` — the Review click silently returns without ever POSTing. Customer thinks a plan was queued; nothing happens; no toast, no error.
- **Expected:** Button should either share the `swSeedBtn` id or the function should look up a per-caller id/pass `this`.
- **Impact:** Customer completes the 4-step wizard, hits the last "generate my week" CTA, sees nothing — they conclude the AI is broken. This is the primary activation moment; a silent fail here is a **P0 for GTM 0→1**.
- **Fix:** Give the Review button `id="swSeedBtnReview"` and let `generateFirstWeek()` accept `btnId` OR resolve `btn = document.getElementById("swSeedBtn") || document.getElementById("swSeedBtnReview") || document.querySelector('[data-seed-first-week]')`. Same disabled/label logic.
- **Risk:** LOW — additive, no server change.
- **Test:** Manual UAT — Login → Setup → complete steps 1-3 → Review → click plan button → toast + network POST fired.

### R3-2. `resolveClientId()` falls back to `?client_id=…` from URL when JWT is missing/invalid
- **File:** `frontend/customer_dashboard.html:2076` — `return localStorage.getItem("lgai_cid") || qparam("client_id") || "demo";`
- **Observed:** If a customer opens `/app/customer/marketing?client_id=other_tenant` and their JWT is expired, `BILL.cid = "other_tenant"`. Every subsequent public/read call that echoes this into query — `/api/billing/subscription?client_id=…`, `/api/billing/usage?client_id=…`, `/api/billing/invoices?client_id=…` (lines 3367-3371), `/api/billing/portal?client_id=…` (3494), `/api/billing/subscription/pause|resume|cancel?client_id=…` (3505-3509) — sends `other_tenant`. Server-side `_authed_client_id` (billing.py:63) refuses unauthenticated calls (401), so no cross-tenant leak actually occurs. **However**: (a) `/api/upi/submit` body still ships `client_id: BILL.cid` (3483); backend ignores it, but a stale `.jsonl` audit log or CSAT dashboard that trusts request body could leak. (b) `localStorage lgai_cid` is set anywhere Loop 8 impersonate flow ran; leftover impersonation cache could persist across a real customer login on the same browser.
- **Expected:** After JWT invalid/expired, `resolveClientId()` should refuse the URL-param fallback and force `/app/login?next=`.
- **Impact:** UI shows a stranger's "Client:" label on the sidebar + tries to load their billing (blocked at 401). Low-blast in practice but a real cross-tenant UX confusion vector; combined with a future admin/dev endpoint that trusts body-`client_id`, it becomes a real leak.
- **Fix:** Delete the `qparam("client_id")` fallback; only allow token→me lookup OR redirect to login. Keep `lgai_cid` for pre-auth marketing-page continuity but scope it to unauthenticated public endpoints only.
- **Risk:** MED — could break existing impersonation deep-links; grep for `?client_id=` in server logs first.
- **Test:** Integration — assert that a logged-out session with `?client_id=X` in URL renders login gate, not a billing card with someone else's cid.

### R3-3. `/api/customer/webhooks/_meta` fetched WITHOUT auth header + no `r.ok` check
- **File:** `frontend/customer_dashboard.html:2389`
- **Observed:** `const meta = await fetch("/api/customer/webhooks/_meta").then(r=>r.json());` — no `billAuthHdr()`, no ok check. If the endpoint is admin/customer-gated and returns 401, `meta = {detail:"..."}`; then `pill` reads "OFF" wrongly and `evtBox.innerHTML = (meta.supported_events||[]).map(...)` = `""`. Empty event list → `whRegister` (line 2431) bails with "Select at least one event" → customer cannot register any webhook. Silent auth failure that breaks the whole webhook config UI.
- **Expected:** Send `billAuthHdr()`, check `r.ok`, render an inline error if not ok.
- **Impact:** Any customer whose token expires while the Billing view is open cannot register/edit webhooks — the pill lies about the flag state too. If the endpoint is meant to be public, add the missing 401 fallback anyway.
- **Fix:** `await fetch("/api/customer/webhooks/_meta", {headers: billAuthHdr()})` + `if(!r.ok){ pill.textContent="?"; list.innerHTML='<div class="sm">Login required</div>'; return; }`.
- **Risk:** LOW.
- **Test:** Manual UAT — expire token in devtools, open Billing → Webhooks; expect visible auth prompt, not stuck-empty.

---

## HIGH — core workflow unusable / silent operator failure / auth-silent

### R3-4. Modals lack focus trap (Loop 27/28 shipped without it — reflag)
- **Files & IDs:** `customer_dashboard.html` — `#connectModalOverlay` (line 3078) + `#mobileMoreSheet` (1296); `admin_dashboard.html` — `#c360PwdModalOverlay` (2878).
- **Observed:** All three set `role="dialog"` + `aria-modal="true"` and handle Esc + backdrop click, but Tab escapes to the underlying page (Home CTAs, sidebar links). Keyboard-only users can Tab past the dialog and click the wrong control. Screen-readers still announce background content.
- **Expected:** Trap Tab/Shift-Tab within modal children; on close, restore focus to the invoking element.
- **Impact:** Fails WCAG 2.4.3 focus order + 2.4.7 focus visible; keyboard user can lose typed credential progress by tabbing "out" of the connect modal.
- **Fix:** Shared helper `_trapFocus(overlay)` that grabs focusable descendants, wraps Tab cursor, records `previousFocus = document.activeElement`, and restores it on close. Apply in `openConnectDialog`, `openMoreSheet`, `c360ResetPassword`.
- **Risk:** LOW — additive, well-known pattern.
- **Test:** Manual UAT — open each modal, press Tab repeatedly, confirm cycle stays inside; close, confirm focus returns to opener.

### R3-5. `platform_dial` banner is static — never reflects the actual runtime flag
- **File:** `admin_dashboard.html:817` (`#platformDialBanner`).
- **Observed:** Banner is hard-coded in HTML — always shown. If ops flip `PLATFORM_DIAL_DAILY=1` + `data/platform_dial.json enabled:true`, banner still screams "HARD OFF" while backend actually accepts. Also the Fire Campaign button remains enabled — clicking still POSTs and receives an ambiguous response.
- **Expected:** On `loadGodMode()` / `loadCampaignStatus()`, read `sys.platform_dial` (or a boolean surfaced by `/api/admin/system/summary`); toggle banner + disable `#campFireBtn` when disabled; hide banner when enabled.
- **Impact:** Once user re-enables (per USER-MANDATE contingency), banner becomes false noise; conversely today the button is enabled while the flag is OFF, and there's no server-side "flag OFF" 400 to prove it.
- **Fix:** Add `renderPlatformDialBanner(sys)` called from the same fetch as `renderCampaignPrereq(sys)` at line 4034. Read `sys.platform_dial?.enabled` (or expose it if not already). Disable Fire button when OFF; hide banner when ON.
- **Risk:** LOW.
- **Test:** Integration — mock `/api/admin/system/summary` returning `{platform_dial:{enabled:true}}` → banner hidden + button enabled; `{enabled:false}` → banner visible + button `disabled`.

### R3-6. `bulkDelete` fires N sequential DELETE calls with zero aggregate progress + swallows all errors
- **File:** `admin_dashboard.html:2534-2546`.
- **Observed:** Loop over selected clients: `await fetch(…delete…)` inside `try/catch(e){}`. No progress indicator ("3/10 deleted…"), no `r.ok` check (only `d.deleted`). If backend returns 500 for one client, all remaining still fire; if 25 clients selected it looks hung. On 401 the whole loop silently succeeds with `0 deleted`.
- **Expected:** Show per-item progress (`Deleting 3/10…`), collect failures, surface them in the final toast (`✓ 8/10 deleted · 2 failed — check console`).
- **Impact:** Admin can't tell partial-failure from total-success. If someone triggers a 25-client delete during a DB blip, they think everything succeeded when nothing did.
- **Fix:** Track `ok`, `failed` counters; report both; if `>50%` failed, keep the selection instead of `clearBulkSelect()` so they can retry.
- **Risk:** LOW.
- **Test:** Manual UAT — select 3 clients, take one offline (fake 500), confirm toast shows `2 ok · 1 failed` and 1 stays selected.

### R3-7. `whShowDeliveries` renders "No deliveries yet." on 401 — misleading
- **File:** `customer_dashboard.html:2472-2483`.
- **Observed:** `const d = await r.json()` with no `r.ok` guard. On 401 `d.deliveries` is `undefined`, so the `if(!d.deliveries || !d.deliveries.length)` branch renders "No deliveries yet." — customer thinks the webhook is dead. Same pattern in `whTest` (2461-2463 — shows "✗ Test failed: status=n/a error=unknown") and `whRetry` (2487-2493).
- **Expected:** Detect 401/403 and render "Session expired — login karo".
- **Impact:** Customer files support ticket about "webhook not delivering" when in reality their JWT expired 5 minutes ago.
- **Fix:** Add `if(r.status===401||r.status===403){ box.innerHTML="Session expired — dobara login karo"; return; }` before the JSON parse in all three.
- **Risk:** LOW.
- **Test:** Devtools — set expired token, click "Deliveries" → expect the session-expired notice.

### R3-8. `openBillingPortal` button is dead + `openBillingPortal` still POSTs a 404 for UPI-only tenants
- **File:** `customer_dashboard.html:3492-3501` (function) — button was DOM-removed in Loop 27 but the function + backend endpoint remain callable via console/deep-link.
- **Observed:** `POST /api/billing/portal` returns "portal not available" for the ~100% UPI-only Indian customer base (Stripe removed 2026-07-10). Fallback toast says "Pause/Band Karo button use karein" — but that button lives in a different card, no scroll/link.
- **Expected:** Delete `openBillingPortal()` entirely (button gone in Loop 27) OR make the fallback toast an actionable link that scrolls to `#billingCard` Pause/Cancel.
- **Impact:** LOW-HIGH — someone with old bookmarks/impersonation cache hits console, calls it, gets confusing toast. Dead code = maintenance rot.
- **Fix:** Remove `openBillingPortal()` from `customer_dashboard.html` (also unused in admin `openStripePortal` at admin:3625).
- **Risk:** LOW — Loop 27 already removed the button DOM.
- **Test:** Unit — search codebase for other callers; grep `openBillingPortal` clean before deleting.

### R3-9. Setup → Step 2 "Continue →" button has wrong ternary — always goes to step 3 whether user is on 1 or 2
- **File:** `customer_dashboard.html:2898` — `onclick="showSetupStep(_SETUP_STATE.step===1?2:3)"`.
- **Observed:** Handler ternary `step===1?2:3` — but this button lives inside `data-profile-step="2"` markup (only visible on step 2). It ALWAYS resolves to `3`, so the `===1?2` branch is dead code. Confusing to maintain and hides the intent.
- **Expected:** Simplify to `showSetupStep(3)` — or fold into `showSetupStep(_SETUP_STATE.step+1)` with a Math.min guard.
- **Impact:** LOW functional impact (right answer today) but a code-reader is misled about wizard branching. `saveSetupWizard()` at line 2942 has an identical dead ternary.
- **Fix:** Replace both ternaries with `showSetupStep((_SETUP_STATE.step||1)+1)`.
- **Risk:** LOW.
- **Test:** Unit — advance from Step 1 Save, from Step 2 Save, from Step 2 Continue — assert `_SETUP_STATE.step` is 2, 3, 3 respectively.

### R3-10. Admin "Turnstile / Sentry / PostHog / UPI VPA / seed templates" saves still use raw `alert()`
- **File:** `admin_dashboard.html:4280-4344` — `saveTurnstile`, `saveSentry`, `savePosthog`, `seedFlowTemplates`, `saveUpiVpa`. Also older ops at 1619-1629 (celery-trim, DLQ sweep), 3540-3555 (niche approve/reject), 3630-3648 (billing portal admin), 3770-3789 (auto-si tasks).
- **Observed:** Every God-Mode save shows a native `alert()` on success/error while the same file uses `adminToast()` everywhere else post-Loop-27. Inconsistent muscle memory for the admin.
- **Expected:** Replace `alert("✅ …")` → `adminToast("✅ …","success")`; `alert("Fail: …")` → `adminToast("Fail — …","error")`.
- **Impact:** Admin blocks on modal, loses scroll position, cannot copy-paste error text out. Bulk config sessions become friction.
- **Fix:** Sweep replace, keep native `confirm()` on destructive branches only.
- **Risk:** LOW.
- **Test:** Manual UAT — click each God-Mode save, confirm no modal dialog appears; toast slot fills.

---

## MED — friction / misleading state / weak recovery

### R3-11. `loadUpiSelfServe` renders no auth prompt on 401
- **File:** `admin_dashboard.html:4043-4073`.
- **Observed:** `const r=await fetch('/api/upi/pending')` — no r.ok check. On 401 `d.pending = undefined`, hits `if(!rows.length)` and shows "Koi pending self-serve submission nahi" — admin thinks queue is empty when it's actually auth-locked.
- **Fix:** `if(r.status===401||r.status===403){ el.innerHTML='<div>Login expired — refresh + admin login</div>'; return; }`.
- **Risk:** LOW.
- **Test:** Manual UAT — expire admin token, refresh UPI Self-Serve card → session-expired notice.

### R3-12. `loadSyncHealth`, `renderMcpStatus`, `loadHourlyActivity`, `loadLlmHealth` all render on 401 as if data was legitimate
- **Files:** `admin_dashboard.html:2464-2487` (`loadSyncHealth` throws but the retry link swallows the error), `4135-4144` (`loadMcpStatus`), `1317` (`loadHourlyActivity`), `1339` (`loadLlmHealth`).
- **Observed:** No 401 branch — `d.spf_ok` etc becomes undefined → "✗" everywhere → admin thinks SPF is broken.
- **Fix:** Shared helper `_adminFetch(path)` returning `{ok, data, authFailed}`; every widget renders "Session expired — refresh" on `authFailed`.
- **Risk:** MED — sweeping change; do behind a feature flag or in a single loop.
- **Test:** Manual UAT — expire admin token, `loadDashboard()` → every widget shows the same auth prompt, not fake-red errors.

### R3-13. `openClientTimeline` shows "band hai — CLIENT_TIMELINE=1" text on ANY non-200 response
- **File:** `admin_dashboard.html:2296-2304`.
- **Observed:** `if(!d.enabled)` runs whether the call actually returned `{enabled:false}` (flag off) or `{detail:"unauthorized"}` (401). Admin thinks flag is off and burns time toggling env.
- **Fix:** `if(!r.ok){ b.innerHTML="<i>Load failed — HTTP "+r.status+"</i>"; return; }` before the `d.enabled` branch.
- **Risk:** LOW.
- **Test:** Unit — mock 401 → error surface says "auth", not "flag off".

### R3-14. `whTest` and `whRetry` announce success/failure via `alert()`, not `toast()` or inline banner
- **File:** `customer_dashboard.html:2459-2497`.
- **Observed:** `alert("✓ Test delivered (200)")` blocks the page. Also the recovered secret in `whRegister` (line 2443) is displayed inline (good), but `whTest` blocks scroll.
- **Fix:** Replace all three `alert()` calls in the webhook section with `toast()` (the Loop-27 alias exists and is safe).
- **Risk:** LOW.
- **Test:** Manual UAT — test a webhook, expect toast top-right, no modal.

### R3-15. Setup Wizard Step-2 Continue "Continue →" (line 2898) violates guaranteed-forward mental model
- **File:** `customer_dashboard.html:2898`.
- **Observed:** From Step 2 the user has two buttons: "💾 Save Profile" (posts profile then advances) and "Continue →" (advances without saving). If user edits fields, clicks Continue, their edits are lost.
- **Expected:** Either single "Save & Continue" button OR the Continue button posts a save-in-flight.
- **Impact:** Data-loss vector — Setup completion metrics look worse than they are because edited-but-unsaved forms show 0%.
- **Fix:** Delete the Continue button OR make its handler call `saveSetupWizard()` and then advance.
- **Risk:** LOW.
- **Test:** Manual UAT — edit tone field on step 2, click Continue, come back — value should persist.

### R3-16. `whUrl` / `upiRefInp` / `sec2faCode` / `onbPhone` still lack HTML-level validation
- **Files:** `customer_dashboard.html:1044` (`#upiRefInp` — no `required` / `minlength`), `1120` (`#sec2faCode` — no `inputmode="numeric"` / `pattern="\d{6}"`), `1129` (`#sec2faDisCode` — same), `2426`/`whUrl` (no `pattern="https://.*"`); `admin_dashboard.html:450` (`onbPhone` — no `pattern="[6-9]\d{9}"`).
- **Observed:** Round-2 audit LOW-14/15 flagged; nothing changed. On mobile these inputs still show QWERTY not numeric keyboard for TOTP.
- **Fix:** Add attributes inline; still let JS validate for backwards compat.
- **Risk:** LOW.
- **Test:** Manual UAT — open TOTP input on Android → numeric pad; type letters → browser rejects.

### R3-17. Customer sidebar "Client:" shows literal string `demo` when unauthenticated
- **File:** `customer_dashboard.html:1756` — `document.getElementById("sideClient").textContent="Client: "+(d.client_id||"demo");` and 3361 same.
- **Observed:** Unauthed visitor lands on `/app/customer/marketing` from a marketing link → sidebar reads "Client: demo" — makes real customers who mis-typed URL believe someone else's account is loaded.
- **Fix:** When unauthed, render "Client: — (login karo)" and hide the pill styling.
- **Risk:** LOW.
- **Test:** Manual UAT — logout, refresh page, sidebar reads "Client: — (login karo)".

### R3-18. `dedupeClients`, `flywheelIdentity` show cryptic `e.message` toast on error
- **File:** `admin_dashboard.html:2512-2532`.
- **Observed:** `adminToast("Dedupe fail: "+e.message,"error")` — `e.message` might be `Failed to fetch` or `NetworkError when attempting to fetch resource.`; not actionable.
- **Fix:** Detect network vs 4xx vs 5xx and give a friendly hint (retry / re-login / open console).
- **Risk:** LOW.
- **Test:** Unit — offline network → "Network error, wifi check karo" toast.

### R3-19. `submitUpiRef` sends `client_id: BILL.cid` in body even though backend ignores it
- **File:** `customer_dashboard.html:3483`.
- **Observed:** `body:JSON.stringify({plan:plan,upi_ref:ref,client_id:BILL.cid})` — server derives from JWT. Body field is dead + a small info leak (in server logs) about which local-cache cid the browser was using.
- **Fix:** Drop `client_id` from body; server signature unchanged.
- **Risk:** LOW.
- **Test:** Contract test on `/api/upi/submit` — assert body without `client_id` still succeeds.

### R3-20. Content/calendar view shows "Aaj ka content abhi ban raha hai — subah 7 baje tak" even mid-morning
- **File:** `customer_dashboard.html:2642`.
- **Observed:** Static string always says "subah 7 baje tak" regardless of current time — at 10am the message is stale and worrying.
- **Fix:** Compute delta to next 07:00 IST; if past, show "Team AI content generate kar rahi — thodi der me aa jayega."
- **Risk:** LOW.
- **Test:** Unit — mock `Date` to 08:30 → non-time-specific message.

---

## LOW — polish / dead code / minor a11y / consistency

### R3-21. Support view still has TWO WhatsApp CTAs (round-2 LOW-12 not fixed)
- **File:** `customer_dashboard.html` — one card in `data-view="delivery"` + one in `data-view="support"` render identical "💬 WhatsApp Support" content.
- **Fix:** Delete the duplicate from delivery view; keep support-view canonical.
- **Risk:** LOW.
- **Test:** Manual UAT — grep for `wa.me/91` in the file, expect 1 authoritative CTA.

### R3-22. Dead functions/vars remain (round-2 LOW-13 partially fixed)
- **File:** `customer_dashboard.html` — `setText` (1503), `toggleDetails` (1530), `openAdvancedSettings` (1635), `_origRenderLeadsOld` (3522) still present per grep.
- **File:** `admin_dashboard.html` — `showAdminView` (2652) function retained "for future wiring" per Loop 28 comment; dead until then. `expandSystemGroup` (3170) still there.
- **Fix:** Delete if no callers; re-verify via grep before removing.
- **Risk:** LOW.
- **Test:** grep -c after removal → 0.

### R3-23. Filters do not persist across reload (round-2 LOW-11)
- **File:** `customer_dashboard.html` — `#drFrom`/`#drTo` (498-501), `#leadFilter*` (884-891), `#callFilter*` (955), `#campaign` (505) do not read/write localStorage.
- **Fix:** Mirror admin's `admin_advTechOpen` localStorage pattern.
- **Risk:** LOW.
- **Test:** Manual UAT — set filter, F5, expect same filter.

### R3-24. Calendar grid overflows viewport at ≤560px (round-2 LOW-17)
- **File:** `customer_dashboard.html:796` — 7-column grid × 80px min-height forces horizontal scroll on 375px viewports.
- **Fix:** Media query `@media (max-width:560px){ #calendarGrid { grid-template-columns: repeat(7,1fr); font-size:10px; min-height:48px } }`.
- **Risk:** LOW.
- **Test:** Manual UAT — Chrome iPhone SE emulation → no horiz scroll.

### R3-25. `.badge-demo` hidden on <560px viewport (round-2 LOW-18)
- **File:** `customer_dashboard.html:414`.
- **Observed:** Mobile visitor to a demo tenant doesn't see the DEMO badge — could be misled.
- **Fix:** Show demo pill on mobile; shrink to icon-only if space is tight.
- **Risk:** LOW.

### R3-26. Skeleton rows lack `aria-hidden` + `aria-busy` (round-2 LOW-16)
- **File:** all `.skeleton` usages across both files.
- **Fix:** Wrapping table gets `aria-busy="true"`; skeleton cells get `aria-hidden="true"`.
- **Risk:** LOW.
- **Test:** Manual UAT — NVDA/JAWS narrates "loading", not fake numbers.

### R3-27. Vestigial admin sections still expanded by default (round-2 §"VESTIGIAL")
- **File:** `admin_dashboard.html` — `sec-ops2026`, `sec-audit`, `sec-api`, `sec-sync`, `sec-recordings`, `sec-webcalls`, `sec-delivery-queue`, `sec-diff` (approvals, often empty).
- **Fix:** Wrap each in the existing `_restoreCollapsibleCards()` pattern; save open-state to localStorage.
- **Risk:** MED — a currently-visible ops surface will be one click deeper; ops teams may complain. Add a "Open all" toggle up top.
- **Test:** Manual UAT — admin lands on dashboard, sees Today's business + Automation + Clients + a UPI Self-Serve card above the fold.

### R3-28. `admin_dashboard.html:3037` — `fetch("/api/admin/office")` result unused
- **File:** `admin_dashboard.html:3037-3040`.
- **Observed:** Fetch is fired on load but `.then(...)` swallows into a no-op; wastes a network call per admin page load.
- **Fix:** Delete the block OR wire it into the office teaser.
- **Risk:** LOW.

### R3-29. Admin `loadAgents` and `loadOfficeTeaser` don't share the same auth-error surface
- **Files:** `admin_dashboard.html:2489-2510`.
- **Observed:** `loadAgents` silently returns on non-ok; `loadOfficeTeaser` writes "Office status abhi load nahi ho paya" — inconsistent.
- **Fix:** One shared "widget failed" pill.
- **Risk:** LOW.

### R3-30. `submitUpiRef` "Pehle plan chuno" / "UPI Transaction ID daalo" errors use ochre color (`#b45309`) but `.showMsg("var(--ok)")` for success — success-color `--ok` might be undefined in `dark` mode
- **File:** `customer_dashboard.html:3477-3485`.
- **Fix:** Use pre-computed color tokens; verify in dark mode.
- **Risk:** LOW.

### R3-31. `saveSocialSetup` reads `document.getElementById("ssSafety").value` but the field isn't rendered in the default form — grep shows it inside a "Prohibited topics" details block that's not universally present
- **File:** `customer_dashboard.html:3296` + originating field around line 3261 area.
- **Observed:** If safety instructions field isn't rendered (feature-gated), we send empty string — harmless. But it means saving from step 3 nukes any server-side default. Server should not overwrite absent fields with "".
- **Fix:** Send only keys with non-empty user input; server accepts partial patch.
- **Risk:** MED — server contract change; requires backend patch too.
- **Test:** Contract test — POST `/api/customer/social/config` with `{}` should NOT overwrite `brand_safety_instructions` if the field is absent from the body.

### R3-32. Sidebar "Client:" pill and "logout" button have no `aria-live` region for state changes
- **Files:** both.
- **Fix:** Wrap in `<div aria-live="polite">…</div>` so screen readers announce login/logout.
- **Risk:** LOW.

### R3-33. `loadCampaignStatus`'s `traiFetch.then(sys=>…)` swallows errors silently (line 4376-4382)
- **File:** `admin_dashboard.html`.
- **Observed:** `.catch(()=>({}))` — if `/api/admin/system/summary` is 401, chip renders "🔴 CLOSED — 10:00-19:00" and pre-req shows "Loading…" forever.
- **Fix:** Detect empty response and render "Session expired".
- **Risk:** LOW.

### R3-34. `admin_dashboard.html` still has ~8 `alert()` calls in `wa*`, `saveTurnstile`, `saveSentry`, `savePosthog`, `seedFlowTemplates`, `saveUpiVpa`, `sec360` (customer-360 flywheel) code paths
- **Files:** admin_dashboard.html:4287-4344, 3630-3648.
- **Fix:** Same as R3-10 — sweep to `adminToast`.

---

## Backend spot-check (no code changes; verification items)

1. `GET /api/customer/webhooks/_meta` — verify whether it's public (no auth) or gated. If gated, R3-3 is the fix; if public, frontend can still add r.ok guard for defense-in-depth.
2. `POST /api/customer/social/config` — verify server treats absent fields as "no change" (not "set to empty"). Relevant to R3-31.
3. `DELETE /api/customer/social/accounts/{plat}?account_id=…` — confirmed accepting `account_id` (customer_dashboard.py:1747). Sanity-check: legacy `account_ref` parameter path still works for admin tools.
4. `POST /api/upi/submit` — confirmed `client_id` derived from JWT (upi_payments.py:44). Frontend body `client_id` is safely ignored; still delete it per R3-19 to avoid log noise.
5. `POST /api/admin/campaign/launch` — verify current implementation returns a distinguishable "platform_dial off" 4xx so R3-5's front-end disable is defense-in-depth, not the only safeguard.

---

## Summary table (33 items)

| # | Pri | File | Line | One-liner |
|---|---|---|---|---|
| R3-1 | **P0** | customer | 2823 / 2949 | Review → generate week is silent no-op (btn id missing) |
| R3-2 | **P0** | customer | 2076 | `?client_id=` URL fallback in `resolveClientId` |
| R3-3 | **P0** | customer | 2389 | `/webhooks/_meta` fetch no auth + no r.ok — breaks webhook UI on 401 |
| R3-4 | HIGH | both | 3078/1296/2878 | Loop 27/28 modals have no focus trap |
| R3-5 | HIGH | admin | 817 | platform_dial banner is static, ignores real flag |
| R3-6 | HIGH | admin | 2534 | bulkDelete = N sequential ops, no progress, no error surface |
| R3-7 | HIGH | customer | 2472 | whShowDeliveries misreports 401 as "No deliveries" |
| R3-8 | HIGH | customer | 3492 | Dead `openBillingPortal` callable via console |
| R3-9 | HIGH | customer | 2898/2942 | Setup step-2 Continue ternary is dead code |
| R3-10 | HIGH | admin | 4280–4344 | God-Mode saves still use raw `alert()` |
| R3-11 | MED | admin | 4043 | UPI self-serve renders as empty queue on 401 |
| R3-12 | MED | admin | 2464/4135/1317/1339 | 4 ops widgets fake-red on auth failure |
| R3-13 | MED | admin | 2296 | openClientTimeline confuses 401 with flag-off |
| R3-14 | MED | customer | 2461/2487 | whTest/whRetry use blocking `alert()` |
| R3-15 | MED | customer | 2898 | Step-2 "Continue" bypasses save → data loss vector |
| R3-16 | MED | both | 1044/1120/2426/450 | Missing HTML validation (inputmode/pattern/required) |
| R3-17 | MED | customer | 1756 | Sidebar shows literal "Client: demo" unauthed |
| R3-18 | MED | admin | 2519 | Cryptic `e.message` toasts on dedupe/flywheel |
| R3-19 | MED | customer | 3483 | `submitUpiRef` sends dead body-`client_id` |
| R3-20 | MED | customer | 2642 | Empty-content message hardcodes "subah 7 baje" |
| R3-21 | LOW | customer | dup | Duplicate WhatsApp Support cards |
| R3-22 | LOW | both | various | Dead functions/vars (setText, toggleDetails, showAdminView…) |
| R3-23 | LOW | customer | 499/884/955 | Filters don't persist across reload |
| R3-24 | LOW | customer | 796 | Calendar grid overflows on ≤560px |
| R3-25 | LOW | customer | 414 | .badge-demo hidden on mobile |
| R3-26 | LOW | both | .skeleton | Skeletons lack aria-hidden/aria-busy |
| R3-27 | LOW | admin | vestigial | 8 admin sections should collapse by default |
| R3-28 | LOW | admin | 3037 | `/api/admin/office` fetched but unused |
| R3-29 | LOW | admin | 2489/2499 | Widget failure surfaces inconsistent |
| R3-30 | LOW | customer | 3477 | `showMsg("var(--ok)")` may be undefined in dark mode |
| R3-31 | LOW | customer | 3296 | Empty-field send may overwrite server defaults |
| R3-32 | LOW | both | sidebar | No aria-live region for login/logout state |
| R3-33 | LOW | admin | 4376 | Silent `.catch(()=>({}))` on TRAI/summary fetch |
| R3-34 | LOW | admin | 4287–4344 | Duplicate of R3-10 — remaining alert() call sites |

**Recommended loop sequence:** R3-1 → R3-3 → R3-4 → R3-9 (activation + auth + a11y = fastest customer-facing wins) → R3-5 → R3-6 → R3-10 (ops-console polish) → deploy → then MED sweep in a single follow-up loop.
