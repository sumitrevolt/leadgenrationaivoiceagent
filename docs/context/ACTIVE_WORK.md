# ACTIVE_WORK — max 3 workstreams

Completed/abandoned streams must be removed, not archived here forever.

---

## WS-1 Delivery assurance operator surface
- **ID:** WS-1
- **Business outcome:** Admin can see which paid customers are missed/at-risk (canonical ids) without guessing from chat
- **Owner:** Context Recovery / Delivery Ops (nikhil attribution)
- **Branch or worktree:** `main` @ `79ef3dc` + this session commits
- **Allowed files:**
  - `app/marketing/delivery_assurance.py` (exists)
  - `app/marketing/product_one_delivery.py`
  - `app/api/admin_dashboard.py`
  - `frontend/delivery_command_center.html`
  - `tests/test_delivery_assurance.py` (+ related admin/HTML guards)
  - `docs/context/*`
- **Protected files:** all `app/voice_agent/**`, `app/telephony/**`, Swara prompts, VAD/STT/TTS, voice workers/dashboards
- **Dependencies:** deploy of HEAD after `8ad64db7` (user authorize)
- **Acceptance criteria:**
  - Cockpit JSON includes `assurance` summary (never-raise)
  - `GET /api/admin/delivery-assurance` admin-gated, read-only
  - Command Center feeds At Risk KPI from assurance
  - Targeted pytest green; no Swara paths in diff
- **Current state:** CODE-PRESENT module+tests on origin; admin/UI wire IN PROGRESS this session; NOT PRODUCTION-PROVEN
- **Next exact action:** complete route+UI+tests, commit, update SESSION_HANDOFF
- **Next exact command:** `.venv\Scripts\python.exe -m pytest tests/test_delivery_assurance.py -q`

---

## WS-2 Jiya proof (last 10%)
- **ID:** WS-2
- **Business outcome:** Paying customer sees published/scheduled proof on own channels
- **Owner:** Human + Zara path (approval-gated)
- **Branch:** n/a (ops + Meta)
- **Allowed files:** content approval / social publish paths only when explicitly activated
- **Protected files:** Swara/voice entire tree
- **Dependencies:** Meta Advanced Access for customer pages OR admin 1-click manual publish + customer approval of `approval_pending`
- **Acceptance criteria:** deliverable `proof` = done for `jiya-makeover` with ledger evidence
- **Current state:** HONEST-blocked EXTERNAL — PARTIAL
- **Next exact action:** customer approve pending drafts OR connect Jiya channels after Meta review
- **Next exact command:** (ops) open `/app` delivery / approvals for jiya-makeover — no code until path chosen

---

## WS-3 (slot reserved — empty)
No third concurrent implementation. Parked ideas (24/7 agent enablement docs, coordinator rate-cap test, automation_health ntfy) stay untracked/local until WS-1 or WS-2 frees a slot.
