# LeadsGen AI — Admin Console

A fully responsive admin dashboard for managing **leads and AI voice calls**. Built as a standalone
React 18 + TypeScript + Vite application so it can be developed and shipped independently of the
existing FastAPI service, while keeping a single, clearly marked seam for wiring the real backend.

```bash
npm install
npm run dev        # http://localhost:5173
```

## Demo credentials

| Role     | Email                | Password   |
| -------- | -------------------- | ---------- |
| Owner    | `admin@leadsgenai.in`| `admin123` |
| Operator | `ops@leadsgenai.in`  | `ops123`   |

## What's inside

| Route          | What it does                                                                 |
| -------------- | ---------------------------------------------------------------------------- |
| `/`            | Overview: 6 KPI cards, trend area chart, status donut, niche bars, call-outcome split, funnel, top cities, recent runs, quick-action triggers |
| `/leads`       | Full CRUD table: global search, column sorting, status/niche/temperature filters, pagination, bulk select + delete, CSV export |
| `/calls`       | Voice call log with outcome/intent filters, sorting, pagination and a transcript viewer |
| `/automations` | Automation centre — 9 workflows, each with a manual **Run now** trigger, dry run for destructive jobs, per-run parameters, enable/pause schedule and run history |
| `/settings`    | Theme, session info, failure-injection slider, demo-data reset, backend integration notes |

## Requirement coverage

**1. Authentication** — `src/auth/AuthContext.tsx` issues a session (`token`, `issuedAt`,
`expiresAt`) that is persisted in `localStorage` (remember me) or `sessionStorage`. On boot the
stored session is revalidated against `api.auth.me()`. `ProtectedRoute` guards every dashboard
route and preserves the attempted URL so login resumes it; `PublicOnlyRoute` bounces authenticated
users away from `/login`. Expired sessions are cleared and redirected to `/login`.

**2. Dashboard view** — six KPI cards with period-over-period deltas, a leads-vs-calls area chart,
status donut, horizontal bar for niches, call-outcome donut, conversion funnel, top-city ranking and
a recent-runs feed. Range selector for 7 / 30 / 90 days.

**3. List management** — a generic `DataTable` (`src/components/ui/DataTable.tsx`) provides column
sorting with `aria-sort`, a debounced global search box, faceted dropdown filters, pagination with a
page-size selector, row selection with an indeterminate header checkbox, and responsive column
hiding per breakpoint.

**4. Form editing** — `src/components/leads/LeadForm.tsx` handles create and update in one modal.
Field-level validation runs on blur and after a submit attempt (untouched fields stay quiet). Errors
render inline under each control with `aria-invalid` and `role="alert"`. Submit/cancel live in the
modal footer; destructive deletes require an explicit confirmation dialog.

**5. Responsive layout** — `AppShell` + `Sidebar`. Desktop: 248 px sidebar that collapses to a 68 px
icon rail (state persisted). Tablet: rail by default. Mobile: off-canvas drawer with scrim, closed
automatically on navigation. Data tables hide low-priority columns progressively and scroll
horizontally when needed.

**6. UX feedback** — skeleton shimmer for KPI cards, charts and table rows; spinners inside buttons
and on the login submit; `ErrorState` with a **Try again** action wherever a request can fail; and a
toast system (`src/components/ui/Toast.tsx`) covering every user-triggered and automated action,
including manual automation runs.

**7. Automation with manual controls** — this is the centrepiece. Nine workflows are defined in
`src/api/client.ts`. Every one of them is schedulable *and* manually triggerable:

| Automation            | Category  | Manual control                                        |
| --------------------- | --------- | ----------------------------------------------------- |
| Lead Enrichment       | data      | Run now; quick action on Dashboard; button on Leads    |
| Lead Scoring          | data      | Run now; quick action on Dashboard                     |
| Duplicate Cleanup     | hygiene   | Run now + **Dry run** (destructive)                    |
| AI Auto-Dial Batch    | voice     | Run now; quick action on Dashboard                     |
| No-Answer Retry       | voice     | Run now; button on Call Log                            |
| Follow-up Sequences   | outreach  | Run now                                                |
| Call Transcription    | voice     | Run now; button on Call Log                            |
| Stale Lead Reaper     | hygiene   | Run now + **Dry run** (destructive, disabled by default)|
| Nightly Digest Report | reporting | Run now                                                |

Additional entry points: **Run all enabled** on the Automation page fires every enabled workflow
sequentially; the Dashboard's *Quick actions* card triggers the three most common ones; each run is
logged with trigger source, status, records processed and message.

## Architecture

```
src/
├── api/
│   ├── client.ts      ApiClient interface + mock implementation (the swap seam)
│   └── seed.ts        deterministic 248-lead / 720-call dataset
├── auth/              AuthContext, ProtectedRoute, PublicOnlyRoute
├── components/
│   ├── dashboard/     StatCard
│   ├── layout/        AppShell, Sidebar, Topbar
│   ├── leads/         LeadFormModal + validation
│   └── ui/            primitives, DataTable, Pagination, Modal, Toast
├── hooks/useAsync.ts  loading / error / retry with stale-response protection
├── lib/               utils (formatters, csv), theme
├── pages/             Login, Dashboard, Leads, Calls, Automations, Settings, NotFound
└── types.ts           domain model
```

### Wiring the real backend

Every component talks to the `ApiClient` interface declared in `src/api/client.ts` and imported via
`import { api } from '@/api/client'`. To go live, implement the same interface with `fetch` and
change the final export of that file:

```ts
export const api: ApiClient = createHttpApiClient(); // instead of createMockApiClient()
```

The expected REST contract is documented on the **Settings → Backend integration** panel:
`POST /api/auth/login`, `GET|POST|PATCH|DELETE /api/leads`, `GET /api/calls`,
`GET /api/metrics/overview`, `GET /api/automations`, `POST /api/automations/{id}/run`.

### Data persistence

The mock client stores leads, calls and run history in `localStorage` under `lg_admin_store_v1`, so
edits and automation effects survive a reload. **Settings → Reset demo dataset** regenerates the
seed. Automation *definitions* always come from code; only the enabled flag and last-run pointer
persist.

### Exercising error states

**Settings → Diagnostics** exposes a failure-injection slider. Raise it above 0% and the configured
share of API calls will fail, letting you verify skeletons, error states and retry handlers without
touching code.

## Scripts

| Command             | Purpose                                  |
| ------------------- | ---------------------------------------- |
| `npm run dev`       | Vite dev server on port 5173             |
| `npm run build`     | `tsc --noEmit` then production build     |
| `npm run typecheck` | Type check only                          |
| `npm run preview`   | Serve the production build on port 4173  |

## Accessibility & theming notes

- Semantic landmarks (`header`, `nav`, `main`, `footer`), labelled form controls, `aria-sort` on
  sortable headers, `aria-invalid` on errored fields, `role="status"` toasts, `role="alert"` for
  inline errors, visible focus rings and keyboard-dismissable modals (Esc).
- Dark and light themes are driven by CSS custom properties (`src/index.css`) with a persisted
  toggle; the system preference is respected on first load.

---

Demo dataset only — no live calls are placed and no real prospects are contacted.
