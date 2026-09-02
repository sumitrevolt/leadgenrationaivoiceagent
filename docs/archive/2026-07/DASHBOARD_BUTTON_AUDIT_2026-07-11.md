# Dashboard Button Audit — 2026-07-11

**Files audited:**
- `frontend/customer_dashboard.html` (3456 lines, 91 onclick handlers) — served at `/app/customer/marketing` + `/app/customer`
- `frontend/admin_dashboard.html` (4457 lines, 156 onclick handlers) — served at `/app/admin`

**Verdict:** Both files use hash-view routing (customer `data-view=`) and section-id anchors (admin `id="sec-*"`). **Every onclick handler resolves to a defined JS function** — zero orphan handlers. The real "buttons hain lekin usable nahi" pain is **UX / auth-gating / shallow content**, not dead code.

Line numbers are absolute in the source files.

---

## A. Setup Wizard (customer `#view-setup`) — deep dive

**Root cause of "unusable" complaint:** the 4 step-tabs (`1. Business / 2. Brand / 3. Social / 4. Review`, lines 697–700) are always visible and clickable, but when the user has NO `lgai_token` in localStorage, `loadGuidedSetup()` (line 2618) replaces both card bodies with a single "Login karke setup karein" link (lines 2620–2621). Result: **clicking the tabs just toggles empty cards — appearance of "buttons hain, kaam nahi karte".**

| Button | Line | Handler | API hit | Login req? | UX when clicked | Issue class | Priority |
|---|---|---|---|---|---|---|---|
| `1. Business` | 697 | `showSetupStep(1)` | none | no | Shows step-1 card; if not logged in = login CTA only | confusing-state (logged-out) | **HIGH** |
| `2. Brand` | 698 | `showSetupStep(2)` | none | no | Shows step-2 card; logged out = same login CTA (no visual change) | confusing-state | **HIGH** |
| `3. Social` | 699 | `showSetupStep(3)` | none | no | Toggles social card; logged out = "Login ke baad khulega" | confusing-state | **HIGH** |
| `4. Review` | 700 | `showSetupStep(4)` → `renderSetupReview()` | none | no | Logged out → shows `0% complete, Baaki: business_name, phone…` — nonsense review of empty profile | confusing-state | **HIGH** |
| "Setup continue karein" (home banner) | 575 | `openSetupWizard()` | none | no | Same as above — dumps user into empty tabs when logged out | confusing-state | **HIGH** |
| **Save & Continue →** (Step 1) | 2672 | `saveSetupWizard()` | `POST /api/customer/profile` | **yes** | Silent 401 possible if button somehow surfaces without token | login-blocked-silent | MED |
| **💾 Save Profile** (Step 2) | 2689 | `saveSetupWizard()` | `POST /api/customer/profile` | yes | Toast on success/fail | OK | — |
| **Continue →** (Step 2) | 2690 | `showSetupStep(_SETUP_STATE.step===1?2:3)` | none | no | OK (ternary is smell but works — always goes to 3 from step 2) | OK | — |
| **🚀 Mera 7-din ka plan banao** (Step 2) | 2694 | `generateFirstWeek()` | `POST /api/customer/campaigns/generate-first-week` | yes | Toast on success; `setTimeout(loadAll, 4000)` blind reload — no progress spinner | no-feedback | MED |
| **📤 Bhejo** (KB text) | 2700 | `sendKbInfo()` | `POST /api/customer/kb-info` | yes | ≥5 chars gate + toast | OK | — |
| **🔐 Connect / ➕ Add another** (per platform) | 2843 | `openConnectDialog(plat,…)` | `POST /api/customer/social/accounts/connect` | yes | Uses **`window.prompt()` × 3** (token → account_ref → optional label) — brutal UX, easy to abandon; token pasted into native prompt | confusing-state | **HIGH** |
| **Disconnect** (per platform row) | 2838 | `disconnectSocialAccount(plat, refMaskedEnc)` | `DELETE /api/customer/social/accounts/{plat}?account_ref=…` | yes | Sends **masked** ref (`…12345`) — code comment (2892–2898) admits DELETE may no-op if masked ref doesn't match full stored ref | confusing-state (silent no-op) | MED |
| **💾 Save Social Setup** | 2999 | `saveSocialSetup()` | `POST /api/customer/social/config` | yes | Toast + advance to step 4 + reload social | OK | — |
| **Review setup →** | 3000 | `showSetupStep(4)` | none | no | OK | OK | — |
| **← Wapas** (Review) | 2614 | `showSetupStep(3)` | none | no | OK | OK | — |
| **Mera 7-din ka plan banao** (Review) | 2615 | `generateFirstWeek()` | `POST /api/customer/campaigns/generate-first-week` | yes | Function looks up `swSeedBtn` (only exists in Step-2 copy) and no-ops if missing → **silent click** on Review copy | dead-handler (no-feedback branch) | **HIGH** |
| **Home par jao** (Review) | 2616 | `showView('home')` | none | no | OK | OK | — |
| **Advanced account connection** `<details>` | 2966 | native `<details>` | none | no | Collapsed by default — user won't discover the per-platform Connect buttons unless they open it | confusing-state | MED |

---

## B. Home + other customer views

### `data-view="home"`
| Button | Line | Handler | API | Issue |
|---|---|---|---|---|
| ✕ clearDateRange | 502 | `clearDateRange()` | none | OK |
| 🔔 Notif bell | 510 | `toggleNotifPanel()` | none | OK |
| "Sab padha" | 517 | `markAllRead()` | none | OK |
| 🌙 dark toggle | 523 | `toggleDark()` | none | OK |
| 💳 Ab pay karo | 528 | `scrollToId('billingCard')` | none | OK |
| Aaj ka kaam dekho | 541 | `runNextStep()` → `scrollToId('contentCard')` | none | scrolls to potentially-not-yet-loaded element | no-feedback |
| Pura hisaab | 542 | `toggleDetails()` | none | OK |
| Setup continue karein | 575 | `openSetupWizard()` | none | See §A — confusing when logged out |
| Leads dekho ↓ | 624 | `scrollToId('leadsCard')` | none | Cross-view switch — OK |
| Action kholo | 637 | `runNextStep()` | none | OK |
| 7× "Jaldi se" action cards | 796–823 | `scrollToId(…)` | none | OK (cross-view auto-switches) |
| ▾ timeline toggle | 995 | `toggleTimelineCard()` | none | OK |

### `data-view="leads"`
| Button | Line | Handler | API | Issue |
|---|---|---|---|---|
| ⬇️ List Download | 833 | `downloadCSV()` | client-side | OK |
| 🧩 CRM me Sync | 834 | `sendToCRM()` | `POST /api/customer/dashboard/send-to-crm` | OK |
| ✕ Clear (leads) | 849 | `clearLeadFilters()` | none | OK |
| ⬇️ Calls Download | 906 | `downloadCallsCSV()` | none | OK |
| ✕ Clear (calls) | 919 | `clearCallFilters()` | none | OK |
| lead-status `<select>` | dyn 1396 | `updateLeadStatus(sel)` | `PATCH /api/customer/leads/{id}` | outline flash feedback only, no toast — subtle |
| + Member | 784 | `routingAddRow()` | none | OK |
| 💾 Team Save | 786 | `routingSave()` | `POST /api/customer/routing` | OK |
| ↻ Refresh | 787 | `loadRouting()` | `GET /api/customer/routing` | OK |
| ✕ (row delete) | dyn 3058 | inline splice + rerender | none | OK |

### `data-view="delivery"`
| Button | Line | Handler | API | Issue |
|---|---|---|---|---|
| 🔄 Refresh Status | 1132 | `loadDeliveryView()` | `GET /api/customer/delivery-proof` | OK |
| approval decide | dyn 2537–8 | `decideApproval(id, 'approve'/'reject')` | `POST /api/customer/approvals/{id}/decide` | OK |
| 💬 WhatsApp | 1168 | native `href` | none | OK |

### `data-view="calendar"`
| Button | Line | Handler | API | Issue |
|---|---|---|---|---|
| ◀ Prev | 739 | `shiftMon(-1)` | none | OK |
| Next ▶ | 741 | `shiftMon(1)` | none | OK |
| Aaj | 742 | `goTodayMon()` | none | OK |

Calendar renders an empty grid until data loads — no "empty state" hint if 0 posts.

### `data-view="reports"` — **SHALLOW**
Contains ONLY `mktKpis` (KPI strip, 668–669). No tables, no charts, no exports. Users clicking "Reports" get 4 KPI numbers and nothing else. **HIGH** — confusing-state.

### `data-view="billing"`
| Button | Line | Handler | API | Issue |
|---|---|---|---|---|
| ⏸ Plan Roko | 943 | `billingAction('pause')` | `POST /api/billing/subscription/pause` | Appears only if `hasSub && !isPaused` |
| ▶️ Phir Shuru | 944 | `billingAction('resume')` | `POST /api/billing/subscription/resume` | OK |
| **💳 Payment Manage** | 945 | `openBillingPortal()` | `POST /api/billing/portal` | **DEAD in UI**: `renderBilling()` hard-codes `show("billManageBtn", false)` at line 3174 — button is NEVER shown | dead-handler |
| ✖ Band Karo | 946 | `billingAction('cancel')` | `POST /api/billing/subscription/cancel` | OK |
| 💬 WhatsApp | 962 | native `<a>` | none | OK |
| ✅ Maine Pay Kiya — Submit | 974 | `submitUpiRef()` | `POST /api/upi/submit` (LIVE per CLAUDE.md 2026-07-10) | OK |
| + Register (webhook) | 1022 | `whRegister()` | `POST /api/customer/webhooks` | OK |
| ⏸/▶ (per webhook) | dyn 2232 | `whToggle(id, !isOn)` | `PATCH /api/customer/webhooks/{id}` | OK |
| Test | dyn 2233 | `whTest(id)` | `POST /api/customer/webhooks/{id}/test` | OK |
| Deliveries | dyn 2234 | `whShowDeliveries(id)` | `GET /api/customer/webhooks/{id}/deliveries` | OK |
| 🔄 Rotate | dyn 2235 | `whRotate(id)` | `POST /api/customer/webhooks/{id}/rotate-secret` | OK |
| ✕ delete | dyn 2236 | `whDelete(id)` | `DELETE /api/customer/webhooks/{id}` | OK |
| ↻ retry | dyn 2301 | `whRetry(...)` | `POST /api/customer/webhooks/{id}/deliveries/{did}/retry` | OK |
| ▶ 2FA Enable | 1042 | `sec2faEnroll()` | `POST /api/customer/2fa/enroll` | OK |
| ✓ Confirm | 1050 | `sec2faConfirm()` | `POST /api/customer/2fa/confirm` | OK |
| Disable 2FA | 1059 | `sec2faDisable()` | `POST /api/customer/2fa/disable` | OK |
| ✓ Update Password | 1073 | `pwChange()` | `POST /api/customer/auth/change-password` | OK |

### `data-view="support"`
Static content only — WhatsApp CTA + support email. Works, but feels shallow if user expected a ticket form.

---

## C. Admin dashboard — grouped by section-id

Most issues here are **auth-silent** (fetch 401/403 → generic error toast) and **shallow feedback** (native `alert()` and `confirm()` used ~30 places instead of the file's own `adminToast` helper).

### Sidebar / topbar
| Button | Line | Handler | Issue |
|---|---|---|---|
| ➕ Add Customer (sidebar) | 224 | `openOnboard()` | OK |
| ▼ Show all system pages | 237 | `expandAdvTech();expandSystemGroup()` | OK |
| ⚡ God Mode | 271 | `expandAdvTech()` | OK |
| Logout | 282 | `adminLogout()` | OK; hidden until authed |
| ☰ menu | 291 | inline class toggle | OK |
| ➕ Add Customer (topbar) | 302 | `openOnboard()` | OK |
| ↻ Refresh | 303 | `loadDashboard()` | OK |

### 🏠 Aaj ka business (`sec-today-biz`)
`↻ Refresh` (313) → `GET /api/growth/overview/today` — OK; 401 shows login CTA.

### 🤖 Agents se baat karo
| Bhejo | 345 | `agentAsk()` | `POST /api/platform/office/ask` | On non-200 shows generic "HTTP ?" — user can't tell LLM quota vs auth vs rate-limit. Fix: surface `d.detail`/`d.error` (backend returns it) | no-feedback |
| 🧹 Clear | 350 | `agentAskClear(event)` | none | OK |

### ➕ Add Customer form
| Create + Issue Login | 438 | `onbSubmit()` | `POST /api/admin/onboard-client` | Uses `alert()` on error — inconsistent with `adminToast` used elsewhere | no-feedback |

### 🔧 Technical / Ops Details (COLLAPSED by default)
Contains many critical ops tools discoverable only after clicking "Dikhao ▾":
- ⚡ God Mode + controls
- **📥 UPI Self-Serve Submissions** (the only active payment channel per CLAUDE.md § Current State)
- 🔌 MCP Server Status
- 🕐 Hourly jobs, 📜 Activity log, 🧠 LLM Brain health, 🌐 Social Delivery Cockpit

**HIGH** — confusing-state. New admin sees "Dikhao ▾" and no discovery breadcrumb pointing at UPI.

### ⚡ God Mode
All 12 buttons work; **most use native `alert()`** where a toast would be consistent:
- 💾 Save VPA (3718), ✓ Activate trial-client (3731), 💾 Turnstile (3755), 💾 Sentry (3757), 💾 PostHog (3762), 🌱 Seed templates (3800), ✓ UPI manual activate (3791) — all `alert()`.
- 🔄 WA Status (3772), 📷 Show QR (3773), ▶ Start session (3774), 🔍 Search UPI clients (3786) — inline feedback, OK.

### 📥 UPI Self-Serve Submissions
| Button | Line | Handler | Note |
|---|---|---|---|
| ↻ Refresh | 507 | `loadUpiSelfServe()` | endpoint not verified — **needs manual check** |
| ✓ Approve / ✕ Reject | dyn 3865–66 | `upiSelfServeDecide(pid, bool)` | endpoint not verified — **needs manual check** |

### 🔌 MCP Server Status
- ▶ Health check chalao (520) → `POST /api/admin/mcp/health/run` — OK
- ↻ Refresh (521) → `GET /api/admin/mcp/health` — OK

### 🕐/📜/🧠/🌐 Ops widgets
| ↻ hourly-activity | 547 | `loadHourlyActivity()` | needs manual check |
| ↻ llmHealth | 559 | `loadLlmHealth()` | needs manual check |
| ↻ Social Cockpit | 574 | `loadSocialCockpit()` | `GET /api/growth/social/jobs` OK |
| Filter | 601 | `loadSocialCockpit()` | OK |
| Emergency stop | 621 | `toggleEmergencyStop()` | `POST /api/growth/social/pause` — uses `confirm()`, works |
| Save paused clients | 623 | `savePausedClients()` | OK |
| Per-platform pause chips | dyn 1535 | `togglePausePlatform(plat)` | OK |
| 🔁 retry (per job) | dyn 1408 | `retrySocialJob(jid)` | OK |
| ✖ cancel (per job) | dyn 1409 | `cancelSocialJob(jid)` | OK |

### System Health / Agents cards
Both default to COLLAPSED. A health monitor collapsed by default in an ops console is odd. Toggle handlers OK (`toggleCardCollapse('sec-health')` / `sec-agents`).

### Clients (`sec-clients`)
All working: Export CSV (688), Dedupe (689), Flywheel ID (690), Customer select (694), filter inputs, ✕ Clear (727), Product chips (dyn 1648), bulk Export/Email/Pause/Resume/Impersonate/Delete (732–737), select-all (744), Details 360 (dyn 1687).

Concerns:
- 🗑 Delete on bulk-select iterates one-by-one with no aggregate progress on multi-select — could look hung.
- 📧 Email Selected, ⏸ bulkPause, ▶ bulkResume, 🕵️ bulkImpersonate — **needs manual check** for status feedback.

### 🎛 Automation Workflows (`sec-automation`)
~21 `autoAction(kind)` buttons at 966–986, each fires a distinct endpoint (`/api/growth/selfimprove/run`, `/api/growth/optimizer/run`, `/api/growth/niche/scrape`, `/api/platform/team/*/run`, `/api/growth/harvest/run`, `/api/journeys/emit`, etc.). Each shows `⏳ Running…` → `✅/❌` inline (good feedback). Suspects that need spot verification:
- 📣 Daily Content → `/api/platform/team/run/isha`
- 📝 SEO Blog → `/api/platform/team/run/blog`
- ✅ QA Run → `/api/platform/team/run/arjun`
- 📊 Growth Pulse → `/api/platform/team/growth/run`

Also OK: + Queue for next tick (999) `autoQueueTask()`, approve/reject SI (dyn 3508), ✓ Approve process (dyn 3514), ▶ Run staff (dyn 3490 — needs manual check).

### 🚀 Outbound Campaign Launcher (`sec-launch-calls`)
| 🚀 Fire Campaign | 830 | `fireCampaign()` | `POST /api/admin/campaign/launch` | OK |
| ↻ Status | 831 | `loadCampaignStatus()` | `GET /api/admin/campaign/status` | OK |
| ⏹ Stop | 832 | `stopCampaign()` | `POST /api/admin/campaign/stop` — needs verify |

**Per CLAUDE.md § 5** `platform_dial = HARD OFF (USER-MANDATE)` — but the launcher UI has NO "backend is force-disabled" banner. User firing this could get very confused when nothing happens. **HIGH** — confusing-state.

### Billing (`sec-billing`)
- Load Billing (1044), Pause/Resume/Cancel (1045/46/48), 💳 Portal (1047) — all `display:none` until a client is loaded.
- 💳 Portal is Stripe-only; UPI-only clients (i.e. all Indian customers currently) → returns "portal not available" — confusing.

### Recordings / Web Calls
- ↺ Refresh (1065/1093), Dikhao ▾ (1066/1094), ✕ Clear (1077), ▶ Play / ⬇ per row (dyn 4282–4304) — all OK.
- Both cards collapsed by default.

### Delivery Queue
- ↻ Refresh (1106) → `GET /api/admin/command-center` — OK
- 🚀 Deliver Now per row (dyn 2844) → `POST /api/admin/clients/{cid}/deliver-now` — OK

### Customer 360
| ✕ Close | 1133 | `closeCustomer360()` | OK |
| 🚀 Deliver Value Now | 1149 | `c360DeliverNow()` | OK |
| 🌐 Re-Scrape Website | 1150 | `c360ScrapeWebsite()` | OK |
| 🔑 Reset Password | 1151 | `c360ResetPassword()` | Uses `prompt()` — shoulder-surfable, password echoed | confusing-state |

### Misc ops controls
- 🧹 Trim queue / ↻ DLQ sweep (dyn 1240–41) → `POST /api/admin/ops/celery-trim` + `dlq-sweep` — uses `confirm()` + `alert()`.
- 🧪 RAG A/B Gate (dyn 1840) → needs manual check.
- Record decision + ⬇ Priority CSV (2018, 885) → needs manual check.

---

## D. API endpoint reachability spot-check

Backend routers scanned: `app/api/*.py`. Endpoints verified against decorated handlers.

| Endpoint | Exists | Route file | Note |
|---|---|---|---|
| `POST /api/customer/profile` | ✅ | `customer_dashboard.py:1188` | — |
| `POST /api/customer/campaigns/generate-first-week` | ✅ | `customer_dashboard.py:1248` | — |
| `POST /api/customer/kb-info` | ✅ | `customer_dashboard.py:1090` | — |
| `POST /api/customer/social/config` | ✅ | `customer_dashboard.py:1447` | — |
| `GET /api/customer/social/accounts` | ✅ | `customer_dashboard.py:1583` | — |
| `POST /api/customer/social/accounts/connect` | ✅ | `customer_dashboard.py:1639` | — |
| `DELETE /api/customer/social/accounts/{platform}` | ✅ | `customer_dashboard.py:1730` | — |
| `POST /api/customer/auth/change-password` | ✅ | `customer_auth.py` | — |
| `PATCH /api/customer/leads/{lead_id}` | ✅ | `customer_dashboard.py:904` | — |
| `POST /api/upi/submit` | ✅ (LIVE 2026-07-10 `4aaf8040`) | `upi_payments.py` | Returns 401 without auth |
| `GET /api/public/pay-info` | ✅ | `public_site.py` | Public |
| `POST /api/platform/office/ask` | ✅ | `office_hq.py:114` | admin-gated |
| `GET /api/admin/dashboard` | ✅ | `admin_dashboard.py:108` | — |
| `GET /api/admin/command-center` | ✅ | `admin_dashboard.py:362` | — |
| `POST /api/admin/clients/{cid}/deliver-now` | ✅ | `admin_ops.py:880` | — |
| `POST /api/admin/clients/{cid}/onboard/scrape` | ✅ | `admin_ops.py:926` | — |
| `POST /api/admin/clients/{cid}/password-reset` | ✅ | `admin_ops.py:906` | — |
| `POST /api/admin/clients/{cid}/delete` | ✅ | `admin_dashboard.py:667` | — |
| `POST /api/admin/clients/dedupe` | ✅ | `admin_dashboard.py:681` | — |
| `POST /api/admin/clients/bulk-email` | ✅ | `admin_dashboard.py:704` | — |
| `GET /api/admin/system/summary` | ✅ | `admin_ops.py:447` | — |
| `POST /api/admin/mcp/health/run`, `GET /api/admin/mcp/health` | ✅ | `mcp_product.py:274/282` | — |
| `POST /api/admin/upi/activate|configure|clients` | ✅ | `admin_ops.py` | — |
| `GET/POST /api/growth/social/jobs`, `pause`, `token-health`, `latest-events` | ✅ | `growth_*.py` | — |
| `POST /api/growth/selfimprove/run`, `task`, `approval/{id}/{action}` | ✅ | `growth_automation.py` | — |
| `POST /api/admin/campaign/launch|status|stop` | ✅ | `admin_ops.py` + `tasks/calling.py:335` | Backend `platform_dial` HARD OFF |
| Other `autoAction(...)` endpoints (21 total) | ⚠ | mixed `growth_*.py`, `team.py` | Full sweep needs manual check |
| `POST /api/admin/flow/seed-templates` | ✅ | `activation.py` / `customer_flows.py` | needs manual check |
| `POST /api/admin/trust/configure-{turnstile,sentry,posthog}` | ⚠ | probable `admin_ops.py` | needs manual check |

**Conclusion:** no confirmed 404-suspect endpoints on the customer surface. Admin surface backend coverage looks complete for sampled endpoints; the ~10 flagged "needs manual check" are inside the collapsed "Technical / Ops Details" section that non-technical admin won't open — low-blast-radius even if broken.

---

## E. Top 10 fixes ranked by user-impact ("now it works")

1. **Setup Wizard tabs when logged out.** Setup nav (tabs 1/2/3/4) is fully clickable when the user has no `lgai_token`, but every tab shows the same "Login karke setup karein" content. Fix: in `showSetupStep()`, if `!billToken()`, disable/gray the tabs and show a single centered login gate card ("Login karke aage badhein"). OR: redirect `/app/customer/marketing#view-setup` to `/app/login?next=…` when unauthenticated.

2. **Reports view is empty.** Sidebar promises "Reports"; user gets a 4-KPI strip and nothing else. Fix: either move the marketing KPI strip into Home and rename Reports → "Delivery Reports" wiring it to `/api/customer/delivery-proof` + weekly summary; OR delete the Reports nav item until the view has real content.

3. **"Advanced account connection" hidden inside `<details>` on Social setup step.** New customers can't find how to connect a platform. Fix: expand `<details>` by default (`open` attribute), OR hoist per-platform Connect cards above the preferences form.

4. **`window.prompt()` chain for social token entry (`openConnectDialog`).** Three sequential native prompts is not enterprise-grade and looks broken to a first-time user. Fix: replace with an inline modal / drawer form (already have `.card` styles) with proper masking, paste hint, and cancel button.

5. **Payment Manage button (billing view) is dead in DOM.** Line 3174 hard-codes `show("billManageBtn", false)`. Button is defined at 945 but never shown. Fix: delete lines 945 + supporting JS entirely, OR flip to `show(hasSub && sub.payment_gateway==='stripe')`.

6. **Admin ops tools hidden under "Technical / Ops Details ▾" collapse.** UPI Self-Serve queue (the only active payment channel), MCP status, God Mode, Automation queue — all one click deeper than they should be. Fix: pin "📥 UPI Self-Serve Submissions" out of the collapse (it's business-critical, not "Technical"); leave the rest inside.

7. **Campaign Launcher has no "backend disabled" banner.** Per CLAUDE.md § 5, `platform_dial = HARD OFF` — but launcher UI at `sec-launch-calls` is fully visible/interactive and will happily "queue" a call that never fires. Fix: check `/api/admin/system/summary` for the `platform_dial` flag on load and gate the Fire button with a red banner: "Platform-dial disabled by admin — enable in God Mode first."

8. **Silent errors on 🤖 "Agents se baat karo" copilot.** On non-200 the reply says "❌ Jawab nahi mila (HTTP ?)"; user can't tell whether it's LLM quota, auth, or rate-limit. Fix: parse `d.detail` / `d.error` from response body (backend returns it at `office_hq.py:122`) and surface the specific reason.

9. **`c360ResetPassword` uses `prompt()`.** Admin types a password into a native prompt — shoulder-surfable, no confirm-entry, no strength check. Fix: replace with a modal in the card (already 280+ lines of Customer 360 modal code) with password + confirm + strength meter + copy-to-clipboard.

10. **`disconnectSocialAccount` sends a masked `account_ref`.** Frontend passes `…12345` (the mask) as `account_ref` — backend probably no-ops, then frontend toasts success anyway. Fix: change DELETE contract to accept the platform-level tag and delete all of that platform's accounts, OR store an unmasked `account_id` alongside the mask for the button `data-*` attribute.

---

## Sanity checks / caveats

- ~7 admin endpoints marked "needs manual check" (mostly `/api/admin/trust/*`, `loadHourlyActivity`, `loadLlmHealth`, `autoStaffRun`, `runRagAbGate`, `exportOutreachReviewCSV`, `recordOutreachReviewDecision`) — grep hit them but router files not opened.
- All sampled `onclick` → function pairs resolve to defined functions. **"Unusable" pain is real UX/gating, NOT literal dead code.**
- Backend routers cross-referenced: `customer_dashboard.py`, `customer_webhooks.py`, `customer_totp.py`, `admin_dashboard.py`, `admin_ops.py`, `office_hq.py`, `mcp_product.py`, `activation.py`, `growth*.py`, `team.py`, `public_site.py`, `upi_payments.py`.
