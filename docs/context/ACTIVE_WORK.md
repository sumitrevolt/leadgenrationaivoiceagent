# ACTIVE_WORK - max 3 workstreams

---

## WS-1 Mission Control + Core Marketing launch - ACTIVE
- **ID:** WS-1
- **Business outcome:** Chat-first mission packets + revenue launch without 24h soak blocker
- **Current state:** Code in worktree `lg-mission-launch` branch `feat/mission-control-revenue-launch`; soak cancelled; durable idempotency index; AMBER parked from chat; executors honest (no fake sessions)
- **Next exact action:** Commit → PR → CI → merge → `deploy_vps.sh <sha>` → 20m burn-in
- **Out of scope:** WA auto · dial · reply-auto · UPI auto · SI loop · Swara/voice

---

## WS-2 GTM Hot Queue → 2nd paid customer - ACTIVE
- **ID:** WS-2
- **Business outcome:** Second Marketing paid customer
- **Current state:** Estique packet ready; human 1-click send
- **Next exact action:** Owner send decision
- **Out of scope:** cold auto-calls · bulk WA

---

## WS-3 External Agent Runner v1 - PARKED
- **ID:** WS-3
- **Business outcome:** Unattended GREEN Cursor→Claude with lease/heartbeat
- **Current state:** Draft on separate worktree; not this launch lane
- **Next exact action:** Owner decision after Core Marketing launch
- **Out of scope:** prod runner enable · calling
