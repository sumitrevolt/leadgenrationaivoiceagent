# Admin UI Actions

**Every consequential admin action (approve / reject / publish / deliver / force) requires a real in-page confirmation** — `actionConfirmModal(opts)` pattern (see `clients.html` ~line 409). Native `confirm()`/`prompt()` are not acceptable; zero confirmation is a severity-1 bug (ADR-104: found 5x in one audit, incl. forced customer delivery).

- Reuse existing data in the modal (what will happen, to whom) — never invent new detection logic client-side.
- **Dashboards must tell the truth:** health widgets count EVERY failure class — a `queue.dead` blind spot made 3 dashboards say "sab healthy" while jobs were dead (ADR-104 #2/#3).
- New admin feature ships API + UI tab together.
- Frontend is server-rendered HTML in `frontend/` — copy the neighbouring page's patterns (fetch + auth header + defensive JSON reads).
- In-network calls from workers/hooks: `http://app:8080/...`, never 8000.
