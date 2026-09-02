# Browser Evidence Template (Phase E)

Copy these tables into the final deliverable after the Phase E browser pass.
Fill every row — an empty cell means "unverified", never "passed". Evidence
without a row is not evidence.

## Admin button matrix

| Surface | Control | Click result | DOM update | Console | Network | Pass/Fail |
|---|---|---|---|---|---|---|
| `/app/admin` |  |  |  |  |  |  |
| `/app/automation` |  |  |  |  |  |  |
| `/app/control-center` |  |  |  |  |  |  |
| `/app/office` |  |  |  |  |  |  |

Add one row per visible button/tab/form you actually clicked.

## End-to-end workflow matrix

| Journey hop | Route / engine | Works | Broken | Unverified |
|---|---|---|---|---|
| Lead capture → magnet | `/audit` `/site-audit` `/demo` |  |  |  |
| Outreach → reply → Hot Queue | `/app/inbox` |  |  |  |
| Pricing → `/start` → UPI | `/api/upi/submit` |  |  |  |
| Onboarding → delivery/reporting |  |  |  |  |
| Retention |  |  |  |  |

## Evidence rules (all must hold)

- **Console:** zero uncaught JS errors.
- **Network:** backing API 2xx/expected; no silent 4xx/5xx; no in-network
  port trap (host `8000` vs in-network `8080` confusion).
- **Auth/RBAC:** unauth = redirect/401; wrong tenant = no leak.
- **Destructive actions:** delete/purge/disable have a confirm gate.
- **Render:** mobile 380px + dark mode OK.
- Old Explorer fallback still works while Control Center graphs are tested.
