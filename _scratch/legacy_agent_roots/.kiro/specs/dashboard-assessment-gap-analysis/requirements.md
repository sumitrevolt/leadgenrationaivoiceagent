# Requirements Document

## Introduction

**Feature:** Dashboard Assessment & Gap Analysis

This document provides a **systematic audit and assessment** of the LeadGen AI frontend dashboards (`customer_dashboard.html` and `admin_dashboard.html`). The goal is to catalog what currently exists, identify gaps compared to competitive SaaS dashboards, and define acceptance criteria for a "complete dashboard" experience that meets modern B2B SaaS standards.

**Product Context:** LeadGen AI is an AI Marketing + Voice Agent SaaS for local businesses in India. The platform has two dashboards:
- **Customer Dashboard** — Hinglish, client-facing (shows leads/calls/content/billing)
- **Admin Dashboard** — English, operator console (manages all clients/campaigns/agents/billing)

**Stack:** FastAPI backend + vanilla JavaScript frontend (no framework)

## Glossary

- **Dashboard**: A web-based interface displaying KPI cards, charts, tables, and actions for monitoring business metrics
- **Customer_Dashboard**: The client-facing dashboard accessed at `/app/customer` (Hinglish UI)
- **Admin_Dashboard**: The operator console accessed at `/app/admin` (English UI, manages all clients)
- **KPI_Card**: A visual widget displaying a single key performance indicator (value + label + change indicator)
- **Assessment_System**: THE system that inventories, categorizes, and prioritizes dashboard features and gaps
- **Gap**: A missing feature, incomplete implementation, or UX issue identified through competitive analysis
- **MoSCoW_Priority**: Prioritization framework — Must have / Should have / Could have / Won't have
- **Competitive_SaaS**: Reference dashboards (HubSpot, Mixpanel, Stripe, ChartMogul, Salesforce, Intercom, Segment, PipeDrive)
- **Feature_Completeness_Score**: A 0-100 calculated metric indicating dashboard maturity vs competitive baseline

## Requirements

### Requirement 1: Inventory Existing Dashboard Features

**User Story:** As a product manager, I want a complete inventory of all implemented dashboard features, so that I can understand the current state before planning improvements.

#### Acceptance Criteria

1. THE Assessment_System SHALL catalog ALL visual components in Customer_Dashboard (KPI cards, charts, tables, action buttons, sections)
2. THE Assessment_System SHALL catalog ALL visual components in Admin_Dashboard (KPI cards, charts, tables, forms, action buttons, sections)
3. THE Assessment_System SHALL catalog ALL backend API endpoints used by both dashboards (fetch calls, POST actions)
4. THE Assessment_System SHALL categorize features by type: visualization (charts/KPIs), data_table, action (buttons/forms), navigation, real-time_updates
5. THE Assessment_System SHALL identify which features use live API data vs demo/embedded data
6. FOR ALL features, THE Assessment_System SHALL produce a structured JSON inventory with: {feature_name, dashboard, category, status (complete/partial/broken), api_endpoints[], ui_elements[]}

### Requirement 2: Document Customer Dashboard Completeness

**User Story:** As a product owner, I want to know what features are fully functional in the customer dashboard, so that I can communicate capabilities to clients accurately.

#### Acceptance Criteria

1. THE Assessment_System SHALL list ALL complete features in Customer_Dashboard:
   - ☀️ "Aaj ke liye" section (today's post, new leads hero number)
   - Quick action cards (3 clickable shortcuts: leads/calls/billing)
   - KPI grid (5 metrics: calls/connections/leads/conversion/cost)
   - Leads table (business/contact/phone/city/niche/score/qualification/date, 8 columns)
   - Calls table (time/business/phone/city/duration/status/outcome, 7 columns)
   - Charts (3): calls per day (line), leads by status (doughnut), leads by city (bar)
   - "Aaj ka Khaas" summary box (4 insights: hot leads/top city/cost saved/time saved)
   - Campaign filter dropdown (multi-campaign support)
   - Billing section (plan/period/minutes/invoices table, 5 invoice columns)
   - Billing actions (4 buttons: pause/resume/manage/cancel)
   - Daily content section (AI-generated posts with copy/WhatsApp share)
   - Webhooks management (J.1 — register/test/pause/deliveries/rotate/delete)
   - 2FA security (H.2 — enroll/confirm/disable TOTP)
   - Download CSV action (leads export)
   - CRM sync action (send leads to external CRM)
   - Responsive mobile layout (sidebar → horizontal navbar on mobile)
2. WHEN a feature uses live API, THE Assessment_System SHALL document the endpoint (e.g., `/api/customer/dashboard`, `/api/billing/subscription`)
3. WHEN a feature has demo/fallback data, THE Assessment_System SHALL flag it as "offline-safe"
4. THE Assessment_System SHALL generate a completeness_score = (complete_features / total_planned_features) * 100

### Requirement 3: Document Admin Dashboard Completeness

**User Story:** As an operations manager, I want to know what features are fully functional in the admin dashboard, so that I can efficiently manage all client accounts.

#### Acceptance Criteria

1. THE Assessment_System SHALL list ALL complete features in Admin_Dashboard:
   - KPI overview (8 metrics: clients/prospects/inquiries/emails/articles/content/calls/MRR)
   - Add Customer card (inline onboard form — product/business/niche/phone/city/email/plan/password, 8 fields)
   - Growth Pipeline chart (bar chart — revenue/cost over 6 months)
   - Prospects by Status chart (doughnut — lead distribution)
   - Aaj ki Activity chart (line chart — daily calls)
   - System Health panel (4 services: API/DB/Telephony/Scrapers)
   - AI Agents grid (6 agents with status/client/calls/leads cards)
   - Clients table (company/niche/plan/leads_delivered/status/MRR, 6 columns)
   - Campaigns table (campaign/client/niche/sources/progress/leads/status, 7 columns)
   - Niches & Pricing table (niche/tier/audience/avg_ticket/lead_price, 5 columns)
   - Billing lookup (per-client: subscription/usage/invoices + pause/resume/portal/cancel)
   - Navigation sidebar (3 sections: Overview/Operations/Business, 11 links)
   - Live/demo data toggle (automatic API fallback)
   - Auto-refresh (30s interval when live API responds)
   - Onboarding wizard link (`/app/onboard`)
2. THE Assessment_System SHALL document all admin API endpoints (e.g., `/api/admin/dashboard`, `/api/admin/customers/onboard`, `/api/billing/*`)
3. THE Assessment_System SHALL identify which features are READ-ONLY vs WRITE (create/update/delete actions)
4. THE Assessment_System SHALL calculate an admin_completeness_score based on operator workflow coverage

### Requirement 4: Identify Feature Gaps vs Competitive SaaS

**User Story:** As a product strategist, I want to compare our dashboards against competitive SaaS products (HubSpot, Stripe, Mixpanel, Intercom, Salesforce), so that I can identify missing "table stakes" features.

#### Acceptance Criteria

1. THE Assessment_System SHALL compare Customer_Dashboard against these competitive features:
   - Real-time notifications center (alerts/activity feed)
   - Search/filter across all data tables (global search bar)
   - Saved views / custom dashboard layouts
   - Bulk actions (select multiple leads → bulk export/tag/assign)
   - Inline editing (click-to-edit table cells)
   - Date range picker (dynamic time period selection)
   - Export options (PDF reports, not just CSV)
   - Onboarding checklist / getting started wizard
   - Empty state illustrations (when no data exists)
   - Keyboard shortcuts (power user features)
   - Dark mode toggle
   - Collaborative features (comments/notes on leads)
2. THE Assessment_System SHALL compare Admin_Dashboard against these competitive features:
   - Client search (instant filter clients by name/niche/status)
   - Bulk client actions (pause multiple subscriptions at once)
   - Advanced filters (multi-condition: status=active AND mrr>50000)
   - Client activity timeline (audit log of all actions per client)
   - Revenue analytics (MRR trend, churn rate, LTV calculation)
   - Alert rules (notify when client usage exceeds threshold)
   - Role-based access control (different admin permission levels)
   - API usage analytics (rate limit monitoring per client)
   - Webhook delivery dashboard (system-wide webhook health)
   - Multi-tenancy UI (switch between operator accounts if scaling)
3. FOR ALL gaps identified, THE Assessment_System SHALL create a gap_record: {gap_name, dashboard, competitive_reference, impact (high/medium/low), effort (high/medium/low)}
4. THE Assessment_System SHALL calculate a competitive_parity_score = (implemented_competitive_features / total_competitive_features) * 100

### Requirement 5: Assess UX Quality & Performance Issues

**User Story:** As a UX designer, I want to identify usability issues, accessibility gaps, and performance bottlenecks in both dashboards, so that I can improve user experience.

#### Acceptance Criteria

1. THE Assessment_System SHALL evaluate Customer_Dashboard for these UX dimensions:
   - Loading states (spinners/skeletons when fetching data)
   - Error states (user-friendly messages when API fails)
   - Empty states (helpful guidance when no leads/calls exist)
   - Action feedback (toast notifications, success/error messages)
   - Form validation (inline errors, clear required fields)
   - Touch targets (minimum 44×44px for mobile buttons)
   - Contrast ratios (WCAG AA compliance for text)
   - Focus indicators (visible keyboard navigation)
   - Screen reader support (semantic HTML, ARIA labels)
   - Responsive breakpoints (mobile/tablet/desktop layouts)
2. THE Assessment_System SHALL evaluate Admin_Dashboard for these UX dimensions:
   - All Customer_Dashboard criteria above
   - Data density (operator needs more info per screen)
   - Scan-ability (clear visual hierarchy, grouping)
   - Quick actions (minimize clicks for frequent tasks)
   - Context preservation (remember filters/sort when navigating)
3. THE Assessment_System SHALL evaluate performance issues:
   - Chart render time (target <500ms for all charts)
   - Table pagination (large datasets should paginate, not render all)
   - API response caching (avoid redundant fetches)
   - Image optimization (posters/avatars should be lazy-loaded)
   - Bundle size (vanilla JS is good, but check for bloat)
4. FOR ALL UX issues found, THE Assessment_System SHALL create an issue_record: {issue_name, severity (critical/major/minor), wcag_violation (yes/no), user_impact_description}
5. THE Assessment_System SHALL calculate a ux_quality_score based on: (issues_resolved / total_issues) * 100

### Requirement 6: Prioritize Improvements Using MoSCoW

**User Story:** As a product manager, I want gap analysis results prioritized by business impact and feasibility, so that I can make data-driven roadmap decisions.

#### Acceptance Criteria

1. THE Assessment_System SHALL classify ALL identified gaps and issues using MoSCoW:
   - **Must Have** = Critical for competitive parity OR blocking user workflows OR WCAG critical violations
   - **Should Have** = Significant UX improvement OR requested by multiple users OR standard in 3+ competitors
   - **Could Have** = Nice-to-have enhancement OR power user feature OR only in 1-2 competitors
   - **Won't Have** = Out of scope OR requires backend redesign OR conflicts with product vision
2. WHEN calculating priority, THE Assessment_System SHALL consider:
   - User impact (how many users affected × severity)
   - Competitive gap (is this table-stakes in the industry?)
   - Implementation effort (dev time estimate: 1 hour / 1 day / 1 week / 1 month)
   - Strategic alignment (does this support core business goals?)
3. THE Assessment_System SHALL produce a prioritized_backlog with fields: {item, dashboard, category, moscow, impact_score (0-10), effort_score (0-10), priority_rank}
4. THE Assessment_System SHALL generate a roadmap_summary: {must_count, should_count, could_count, wont_count, estimated_sprints}
5. THE Assessment_System SHALL output a visual priority_matrix: Effort (x-axis) vs Impact (y-axis), with all items plotted

### Requirement 7: Define "Complete Dashboard" Acceptance Criteria

**User Story:** As a product owner, I want clear acceptance criteria for what constitutes a "complete" dashboard, so that I know when the dashboards meet production-grade standards.

#### Acceptance Criteria

1. THE Assessment_System SHALL define Customer_Dashboard as "complete" WHEN:
   - Feature_Completeness_Score >= 90%
   - Competitive_Parity_Score >= 75% (not all competitor features are relevant)
   - UX_Quality_Score >= 85% (minor issues acceptable)
   - Zero WCAG critical violations (Level A compliance minimum)
   - All "Must Have" items from MoSCoW analysis are implemented
   - All core workflows are testable (login → view leads → export → billing)
2. THE Assessment_System SHALL define Admin_Dashboard as "complete" WHEN:
   - Feature_Completeness_Score >= 90%
   - Competitive_Parity_Score >= 80% (operator tools need higher bar)
   - UX_Quality_Score >= 85%
   - Zero WCAG critical violations
   - All "Must Have" items from MoSCoW analysis are implemented
   - All operator workflows are testable (onboard client → view health → manage billing)
3. THE Assessment_System SHALL generate a completion_report with:
   - Current scores vs target scores for both dashboards
   - Remaining "Must Have" items count
   - Estimated work (story points or dev days) to reach "complete"
   - Risk factors (dependencies on backend changes, third-party integrations)
4. THE Assessment_System SHALL produce a certification_checklist: {criteria, status (pass/fail), evidence}

### Requirement 8: Generate Assessment Report

**User Story:** As a stakeholder, I want a comprehensive assessment report in Markdown format, so that I can share findings with the team and track progress over time.

#### Acceptance Criteria

1. THE Assessment_System SHALL generate a report file `docs/DASHBOARD_ASSESSMENT_REPORT.md` with these sections:
   - Executive Summary (scores, key findings, recommendations)
   - Current State Inventory (feature catalogs for both dashboards)
   - Gap Analysis (competitive comparison tables)
   - UX Quality Assessment (issues by severity)
   - Prioritized Backlog (MoSCoW tables)
   - Roadmap to Completion (must-have items + effort estimates)
   - Appendix (API endpoint list, tech debt notes)
2. WHEN the report is generated, THE Assessment_System SHALL include:
   - Timestamp of assessment
   - Dashboard file versions (git commit hash or file modification date)
   - Competitive products analyzed (with version/date if public)
   - Assessment methodology (automated scan vs manual review)
3. THE Assessment_System SHALL support delta_reports (compare assessment_v1 vs assessment_v2 to show progress)
4. THE Assessment_System SHALL export key metrics to JSON: `docs/dashboard_metrics.json` for programmatic tracking

### Requirement 9: Identify Backend Dependencies

**User Story:** As a backend engineer, I want to know which dashboard improvements require new API endpoints or backend changes, so that I can plan backend work accordingly.

#### Acceptance Criteria

1. WHEN a gap requires a new API endpoint, THE Assessment_System SHALL document:
   - Proposed endpoint path (e.g., `/api/admin/clients/search?q=solar`)
   - HTTP method (GET/POST/PATCH/DELETE)
   - Request parameters (query params, body schema)
   - Response schema (expected JSON structure)
   - Authentication requirements (customer JWT, admin token, API key)
2. WHEN a gap requires backend logic changes, THE Assessment_System SHALL document:
   - Affected backend module (e.g., `app/api/admin.py`, `app/billing/usage.py`)
   - New data model fields (if database schema changes needed)
   - New business logic (e.g., MRR trend calculation, churn rate)
   - Dependencies on external services (Stripe, Razorpay, etc.)
3. THE Assessment_System SHALL classify each gap as:
   - **Frontend-only** (no backend changes)
   - **Backend + Frontend** (new API required)
   - **Backend-heavy** (requires significant backend refactor)
4. THE Assessment_System SHALL generate a backend_work_estimate: {endpoint_count, model_changes, estimated_backend_days}

### Requirement 10: Benchmark Against Industry Standards

**User Story:** As a CTO, I want to know how our dashboards compare to industry standards (B2B SaaS, analytics platforms), so that I can assess product-market fit.

#### Acceptance Criteria

1. THE Assessment_System SHALL benchmark Customer_Dashboard against these industry standards:
   - **SaaS Analytics Dashboards** (Mixpanel, Amplitude, Heap): real-time events, funnels, cohorts
   - **CRM Dashboards** (HubSpot, Pipedrive, Salesforce): contact management, activity feeds, deal pipelines
   - **Billing Dashboards** (Stripe, Chargebee, Recurly): subscription management, usage metering, invoices
2. THE Assessment_System SHALL benchmark Admin_Dashboard against these industry standards:
   - **Admin Panels** (Retool, Forest Admin, Django Admin): bulk actions, search, audit logs
   - **Monitoring Dashboards** (Grafana, Datadog, New Relic): system health, alerts, metrics
   - **Multi-tenant SaaS** (Zendesk, Intercom, Front): client switcher, per-tenant customization
3. THE Assessment_System SHALL produce a benchmark_matrix: {standard_feature, industry_prevalence (% of products), our_status (implemented/partial/missing)}
4. THE Assessment_System SHALL calculate an industry_standard_score = (our_standard_features / industry_standard_features) * 100
5. WHEN the score is <70%, THE Assessment_System SHALL flag the dashboard as "below industry standard" and highlight critical gaps

### Requirement 11: Parser Requirement — Assessment Report Parser

**User Story:** As a developer, I want to parse the generated assessment report programmatically, so that I can integrate findings into CI/CD pipelines and project management tools.

#### Acceptance Criteria

1. THE Report_Parser SHALL parse `docs/DASHBOARD_ASSESSMENT_REPORT.md` into structured JSON
2. THE Report_Parser SHALL extract: scores, gap_records, issue_records, prioritized_backlog, backend_dependencies
3. THE Pretty_Printer SHALL format the JSON back into a human-readable Markdown report
4. FOR ALL valid assessment reports, parsing then printing then parsing SHALL produce an equivalent JSON structure (round-trip property)

### Requirement 12: Continuous Assessment — Regression Detection

**User Story:** As a quality engineer, I want automated regression detection for dashboard features, so that I can ensure new changes don't break existing functionality.

#### Acceptance Criteria

1. THE Assessment_System SHALL support diff_mode: compare current dashboard state against baseline assessment
2. WHEN a previously "complete" feature is now broken, THE Assessment_System SHALL flag it as a regression
3. WHEN a gap is closed (new feature implemented), THE Assessment_System SHALL update the gap status to "resolved"
4. THE Assessment_System SHALL generate a regression_report: {new_issues, resolved_gaps, score_deltas}
5. THE Assessment_System SHALL support CI integration: exit code 1 if Feature_Completeness_Score drops >5% vs baseline

---

## Special Requirements Guidance

**Assessment Methodology:**
- This is an AUDIT feature — no code implementation, pure DOCUMENTATION and ANALYSIS.
- The "Assessment_System" is a conceptual entity representing the analysis process (could be manual review + scripts).
- Property-based testing is NOT applicable here (no parsers/algorithms to test at scale).
- Acceptance criteria are verification checklists, not executable tests.

**Deliverables:**
1. `docs/DASHBOARD_ASSESSMENT_REPORT.md` — comprehensive report
2. `docs/dashboard_metrics.json` — programmatic scores
3. `docs/PRIORITIZED_BACKLOG.md` — MoSCoW-sorted improvement list
4. `docs/BACKEND_DEPENDENCIES.md` — API changes needed

**Parser Requirement Justification:**
- Requirement 11 includes a parser for FUTURE automation — not for the initial manual audit.
- This follows the workflow guidance to call out parsers explicitly.
- Round-trip property ensures the report format is machine-readable and stable.

---

## Document Format

This requirements document follows the EARS pattern:
- **Ubiquitous**: "THE System SHALL [response]" for always-applicable requirements
- **Event-driven**: "WHEN [trigger], THE System SHALL [response]" for conditional logic
- **Complex**: "WHEN [condition], FOR ALL [items], THE System SHALL [response]" for iteration

All technical terms (Dashboard, Gap, MoSCoW_Priority, Assessment_System) are defined in the Glossary.

No escape clauses ("where possible"), no vague terms ("quickly"), no pronouns.

Active voice, testable conditions, solution-free (focuses on WHAT, not HOW).
