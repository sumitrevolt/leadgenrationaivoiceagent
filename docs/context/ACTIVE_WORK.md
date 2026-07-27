# ACTIVE_WORK - max 3 workstreams

---

## WS-1 Automation-Max (MAIN GOAL) - PHASE-1 LIVE + follow-on fixes
- **ID:** WS-1
- **Business outcome:** Safe automation ON; humans approve high-impact/external only
- **Current state:** LIVE on prod ancestry; not this session's focus
- **Next exact action:** Owner ops as needed
- **Out of scope:** WA auto · dial · reply-auto-send · sales-autopilot

---

## WS-2 GTM Hot Queue → 2nd paid customer - ACTIVE
- **ID:** WS-2
- **Business outcome:** Second Marketing paid customer
- **Current state:** Estique packet ready; human 1-click send
- **Next exact action:** Owner send decision
- **Out of scope:** cold auto-calls · bulk WA

---

## WS-3 External Agent Runner v1 (post #146) - DRAFT PR
- **ID:** WS-3
- **Business outcome:** Unattended GREEN Cursor→Claude invocation with lease/heartbeat/review on local canary
- **Evidence:** ADR-149; dogfood `msn_b2a592093c484efa` REVIEW_PASSED; `EXTERNAL_AGENT_RUNNER` default OFF; 66 external-agent tests + regressions green
- **Current state:** Code on `feat/external-agent-runner-v1` worktree `lg-external-runner`; foundation #146 merged at `e64b8a9d`; prod still `f096a08d` flags OFF
- **Next exact action:** Owner decision — merge runner PR only (NOT deploy/flag flip). Then separate Windows canary enablement.
- **Out of scope:** prod runner enable · deploy · calling · Swara · dogfood merge
