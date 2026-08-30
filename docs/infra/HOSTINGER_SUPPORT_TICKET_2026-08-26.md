# Hostinger Support Ticket — Node Instability / Migration Request

**Drafted:** 2026-08-26 06:10Z by @platform  
**For:** Owner to review & send to Hostinger Support  
**VPS:** 72.61.245.204 (Mumbai, hpanel)  
**Severity:** P1 — production revenue path blocked during outages

---

## Subject
Repeated VPS outages (3+ flakes in 6 hours) — request immediate node migration to a stable host

## Body

Hi Hostinger Support,

Our VPS at IP **72.61.245.204** has experienced **3 separate connectivity
outages within the last 6 hours** today (2026-08-26). Pattern suggests
host-node instability, not application-level failure (containers & services
restart cleanly each time VPS returns). This is a production environment
running customer-facing revenue flows.

### Timeline (UTC, 2026-08-26)

| # | Window (UTC) | Symptom | Evidence |
|---|--------------|---------|----------|
| 1 | ~05:00–~05:30Z | HTTPS 000, ping 100% loss, SSH timeout | board probe, pilot SSH probe |
| 2 | ~05:30–~06:50Z | Service restored, ~1h44m uptime | /health=200 verified |
| 3 | ~05:17Z (re-probe) | /health timeout, TCP 443 unreachable | board re-probe during restoration window |
| 4 | 06:06Z | NOW: SSH OK, /health=200, public HTTPS 200 (38ms) | SSH probe + curl leadsgenai.in/health |

### What is healthy right now

- All 25+ containers (app, workers, scheduler, redis, postgres, temporal,
  buzz, postiz, waha, pgbouncer, caddy, litellm, cadvisor) = Up (healthy)
- Redis queues `celery`, `dlq:failed_tasks`, `dlq:dead` = 0/0/0 (no
  backlog, no failed jobs)
- Caddy reverse-proxy = active (since 04:09Z today)
- `/health.version` = `165752bd`, `environment: production`
- Public HTTPS response = 200 in 38 ms

### Requested Action

Please **migrate this VPS to a different physical/host node** at your
earliest convenience. The same control panel + IP can be preserved if
possible, otherwise we will update DNS. Service-level objective: zero
unplanned outages during weekday business hours (IST 09:00–21:00).

If migration is not immediately possible, please escalate to L2 with the
specific host-node identifier for the underlying stability issue.

### Contact

Reply via hpanel ticket system. Reference IPs/timestamps above.

Thank you,
LeadGen AI Platform Team

---

## Internal Notes (Owner — strip before sending)

- Do NOT mention internal agent names (pilot/board/platform/hermes) in
  the Hostinger-facing copy. Keep it professional.
- VPS SSH access is at root@72.61.245.204 (key-based, hpanel rescue
  not required for normal ops).
- If Hostinger asks for proof of outage, attach: `curl --connect-timeout
  5 https://leadsgenai.in/health` outputs during the windows above
  (saved in internal evidence pack, not in this draft).
- Rollback = delete this file. No code/config touched.