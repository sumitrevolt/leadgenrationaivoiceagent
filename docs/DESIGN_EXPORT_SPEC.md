# Design System → Code: export contract + wiring plan

The **"LeadGen AI Design System"** is a separate Cowork project. Its tokens/components
do NOT live in this repo, so they can't be deployed until exported here and wired into
the frontend. This file is the **contract** so the export drops in cleanly and wiring is
deterministic.

## Step 1 — Export FROM the Design project INTO this repo
In the Design System project (it has access to the same `leadgenrationaiagent/` folder),
ask it to **export to these exact paths**:

| File | Content |
|------|---------|
| `frontend/design/tokens.css` | CSS custom properties (`:root { --brand-600: #...; }`) — colors, type scale, radii, spacing, shadows, dark-mode overrides. **Overwrite the scaffold already here** (same variable names). |
| `frontend/design/components.css` *(optional)* | Reusable component classes built on the tokens: `.lg-btn`, `.lg-card`, `.lg-modal`, `.lg-toast`, `.lg-tooltip`, `.lg-badge`, `.lg-field`, `.lg-tabs`, etc. |
| `frontend/design/_preview.html` *(optional)* | A static component gallery (buttons/cards/forms) for visual QA. |

Variable names must match `frontend/design/tokens.css` (already scaffolded): `--brand-*`,
`--ink-*`, `--bg*`, `--success/--warning/--danger/--info`, `--lead-hot/warm/cold`,
`--radius-*`, `--space-*`, `--shadow-*`, `--font-sans`, `--text-*`, `--leading-body`,
`--weight-*`. Add new ones freely; don't rename these (the wiring depends on them).

> Alternative: paste the token values (hex/px) in chat and I'll fill `tokens.css` directly.

## Step 2 — Wiring (I do this once the files land)
1. Serve the folder: add `app.mount("/design", StaticFiles(directory=str(FRONTEND_DIR/"design")))` in `app/main.py` (or a `/design/tokens.css` route). → reachable at `https://leadsgenai.in/design/tokens.css`.
2. Inject into every page `<head>` (dashboards `frontend/*.html` + `frontend/website/index.html`):
   ```html
   <link rel="stylesheet" href="/design/tokens.css">
   <!-- optional --> <link rel="stylesheet" href="/design/components.css">
   ```
3. **Adopt** the tokens per page: replace hard-coded colors/spacing in each page's existing
   CSS with the `var(--...)` tokens (this is the real per-page work — biggest effort; do it
   page-by-page so visual diffs stay reviewable). Pilot first, screenshot, then roll out.

## Step 3 — Verify + deploy (split-SSH, no long single session)
- Local: `python scripts/prod_check.py` + open each changed page.
- VPS: `git reset --hard origin/main` → **detached** `docker compose build app` (nohup, poll log) → `up -d --no-deps app` → `curl /health` + `/app/admin`, `/app/customer`, `/` 200.
- Rollback: `git revert <commit>` + rebuild; tokens.css change is CSS-only (low risk).

## Status
- `frontend/design/tokens.css` — scaffold present (functional Indigo→Violet defaults), awaiting export overwrite.
- Admin Console design (KPIs/ops-snapshot) is ALREADY implemented in code + LIVE (`d5e21cc`). The rest (customer dashboards, login/auth, components, dark-mode rollout) is design-only until exported + wired per above.
