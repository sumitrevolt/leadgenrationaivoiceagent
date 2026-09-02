# Customer Mobile Setup UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make customer onboarding discoverable and reliable on mobile through a visible Setup destination, bounded loading/error states, and a four-step guided wizard.

**Architecture:** Reuse the existing authenticated profile/social endpoints and consolidated `customer_dashboard.html`. Keep one client-side setup state object that merges both responses, renders step-scoped forms, and computes progress. Do not add storage, routes, publishing activation, or backend behavior unless live/local investigation proves a response defect.

**Tech Stack:** Server-rendered HTML, vanilla JavaScript/CSS, FastAPI existing APIs, pytest static frontend contract tests.

## Global Constraints

- Existing billing, auth, tenant isolation, publishing safety, and compliance gates remain unchanged.
- `SOCIAL_ENGINE` and provider gates remain unchanged and saving setup never publishes.
- Mobile target viewport is 380px; tap targets are at least 44px.
- Customer copy is plain Hinglish; raw API/server errors are not displayed.
- No `.env`, database, migration, pricing, telephony, or outbound changes.
- No commit, push, or deploy without explicit user authorization.

---

### Task 1: Prove live/local dashboard mismatch

**Files:**
- Inspect: `frontend/customer_dashboard.html`
- Inspect: live `/app/customer/marketing` response headers/body markers
- Test: `tests/test_customer_mobile_setup_ux.py`

**Interfaces:**
- Consumes: live unauthenticated HTML and local asset markers.
- Produces: documented root cause and stable marker assertions for the current asset.

- [ ] **Step 1: Capture local markers and live response headers/body**

Run a live GET and compare the `mobile-app-nav`, `setupWizardCard`, `data-active-view`, and current commit markers without sending credentials.

- [ ] **Step 2: Write the failing view-isolation contract**

Add assertions that Setup cards use `data-view="setup"`, Home is the initial active view, and mobile navigation invokes `showView()` directly.

- [ ] **Step 3: Run the focused test and record the exact failure**

Run: `.venv\Scripts\python.exe -m pytest tests\test_customer_mobile_setup_ux.py -q`

Expected: fail because the current mobile bar lacks Setup/direct view navigation.

---

### Task 2: Mobile navigation and setup-first home action

**Files:**
- Modify: `frontend/customer_dashboard.html`
- Test: `tests/test_customer_mobile_setup_ux.py`

**Interfaces:**
- Consumes: existing `showView(name)`, `setMeta(data)`, and dashboard sample-data flag.
- Produces: `openSetupWizard()` and a five-item mobile navigation using direct view actions.

- [ ] **Step 1: Add failing tests**

Assert the mobile labels/order are Home, Setup, Posts, Leads, Plan; Setup calls `openSetupWizard()`; no mobile FAB is rendered; and active state can be synchronized from `showView()`.

- [ ] **Step 2: Verify RED**

Run the focused test and confirm the missing Setup/FAB assertions fail.

- [ ] **Step 3: Implement minimal navigation**

Replace the four-item scroll navigation with five direct actions. Add `openSetupWizard()` to call `showView("setup")`, focus the wizard heading, and scroll to top. Update `showView()` to synchronize bottom-nav active state. Hide/remove the mobile FAB while keeping the desktop owner action.

- [ ] **Step 4: Make demo visibility explicit**

Ensure `setMeta(data)` sets `demoBadge.style.display` only when `data.is_sample_data === true`; default markup starts hidden.

- [ ] **Step 5: Verify GREEN**

Run the focused test and HTML/JS validation.

---

### Task 3: Bounded loading and retryable partial state

**Files:**
- Modify: `frontend/customer_dashboard.html`
- Test: `tests/test_customer_mobile_setup_ux.py`

**Interfaces:**
- Produces: `fetchSetupJson(url, timeoutMs)`, `loadGuidedSetup()`, and `renderSetupLoadError(targetId, retryFn)`.
- Consumes: `billToken()`, `billAuthHdr()`, `/api/customer/profile`, `/api/customer/social/config`, `/api/customer/social/accounts`.

- [ ] **Step 1: Add failing timeout/error tests**

Assert an AbortController-backed timeout exists, both setup loaders render `Dobara try karein`, and boot calls the unified loader.

- [ ] **Step 2: Verify RED**

Run focused tests and confirm timeout/retry assertions fail.

- [ ] **Step 3: Implement bounded fetch**

Use an 8-second AbortController timeout. Return a normalized `{ok,data,error}` result and clear the timer in `finally`.

- [ ] **Step 4: Implement partial rendering**

Load profile and social config in parallel. Render available steps when one endpoint succeeds; show a customer-safe inline retry for the failed section. Login absence renders a login CTA immediately.

- [ ] **Step 5: Verify GREEN**

Run focused tests and HTML/JS validation.

---

### Task 4: Four-step guided setup and completion progress

**Files:**
- Modify: `frontend/customer_dashboard.html`
- Test: `tests/test_customer_mobile_setup_ux.py`
- Test: `tests/test_customer_setup_wizard_frontend.py`
- Test: `tests/test_social_setup_wizard.py`

**Interfaces:**
- Produces: `_SETUP_STATE`, `setupCompletion()`, `showSetupStep(step)`, `renderGuidedSetup()`, and step-scoped save/continue controls.
- Consumes: existing profile/social save payloads and first-week campaign endpoint.

- [ ] **Step 1: Add failing structure tests**

Assert four step labels, progress meter, Back/Continue controls, review summary, and collapsed advanced connection section exist.

- [ ] **Step 2: Verify RED**

Run focused tests and confirm guided-step assertions fail.

- [ ] **Step 3: Implement state and progress**

Track profile/social response data in `_SETUP_STATE`. Required completion fields are business name, city, phone/WhatsApp, services/products, at least one social channel for Marketing, and approval preference. Compute completed/total percentage without changing backend requirements.

- [ ] **Step 4: Render four steps**

Reuse the existing input IDs/payload builders but group fields into Business, Brand, Social, and Review panels. Keep marketing-only fields product-aware. Advanced access-token cards live in a closed `<details>` element.

- [ ] **Step 5: Save and advance**

Business/Brand saves use `/api/customer/profile`; Social saves use `/api/customer/social/config`. Successful saves update state and advance one step. Review offers first-week generation and a return-home action.

- [ ] **Step 6: Add home completion card**

Render `Aapka setup X% complete`, missing-items summary, `Setup continue karein`, and `2 minute` on incomplete setup. Hide it when complete.

- [ ] **Step 7: Verify GREEN**

Run all setup/social frontend and API contract tests.

---

### Task 5: Visual and production gates

**Files:**
- Modify: `progress.md`
- Verify: `frontend/customer_dashboard.html`

**Interfaces:**
- Consumes: completed frontend behavior.
- Produces: evidence-backed local readiness and an authorized-deploy handoff.

- [ ] **Step 1: Run validation suite**

Run HTML/JS validation, targeted customer dashboard/setup/social tests, `prod_check.py`, explorer sync, secrets scan, and `git diff --check`.

- [ ] **Step 2: Inspect at 380px and desktop**

Confirm no horizontal overflow, bottom nav has five 44px targets, Setup is reachable, loading resolves, retry is actionable, and dark-mode text remains readable.

- [ ] **Step 3: Self-review diff**

Check auth headers, tenant identity, demo honesty, product gates, and that advanced tokens remain collapsed and never logged.

- [ ] **Step 4: Record loop evidence**

Append the canonical nine-field loop entry to `progress.md` with exact pass counts and any live-only limitation.

- [ ] **Step 5: Stop before deploy**

Report changed files and evidence. Deploy only after explicit user authorization; live validation then requires hard refresh plus authenticated setup save/reload.
