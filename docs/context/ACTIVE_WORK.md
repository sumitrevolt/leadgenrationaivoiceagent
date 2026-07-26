# ACTIVE_WORK - max 3 workstreams

---

## WS-1 Automation-Max (MAIN GOAL) - PHASE-1 LIVE + follow-on fixes
- **ID:** WS-1
- **Business outcome:** Safe automation ON; humans approve high-impact/external only
- **Evidence:** Flags LIVE; cadence OK (Anika events); Kavya/Arnav resumed; approval allowlist=jiya-makeover (file); boot_grace lost-defer → content recovered via run_due
- **Current state:** LIVE. Content job re-dispatched 11:31Z after morning boot_grace miss.
- **Next exact action:** Merge PR #135 when CI green; durable deploy with APP_VERSION
- **Out of scope:** WA auto · dial · reply-auto-send · sales-autopilot

---

## WS-2 GTM Hot Queue → 2nd paid customer - ACTIVE
- **ID:** WS-2
- **Business outcome:** Second Marketing paid customer
- **Current state:** Estique packet ready; human 1-click send
- **Next exact action:** Owner send decision
- **Out of scope:** cold auto-calls · bulk WA

---

## WS-3 External Agent Orchestrator (Cursor+Claude missions) - IN PR #146
- **ID:** WS-3
- **Business outcome:** Cursor/Claude work is dispatched with leases, path ownership, independent review and evidence instead of manual coordination
- **Evidence:** ADR-148 + `app/dev_control/external_agents/`; 38 targeted + 132 regression tests green; prod_check PASS; dogfooded mission reached REVIEW_REQUIRED; `force merge` probe refused RED
- **Current state:** Draft PR #146 on `feat/external-agent-orchestrator` (base 53b000d0); flag `EXTERNAL_AGENT_ORCHESTRATOR` OFF everywhere
- **Next exact action:** CI green → mark PR ready → owner reviews the branch-protection finding in the runbook (main is currently UNPROTECTED while auto-merge.yml exists)
- **Out of scope:** flag flip in prod (AMBER) · branch-protection change (AMBER, owner) · voice/Swara · dial · any deploy

---

## WS-3b OpenClaw Automation agents (observe) - MERGED (#135)
- **ID:** WS-3
- **Business outcome:** Copilot sees Automation-Max agents (Anika/Kavya/Isha/Rohan/Neha) via GREEN commands
- **Evidence:** `automation.status` + `automation.agents` + `agent.status` openclaw_automation package; tests green
- **Current state:** Code on PR branch; prod needs module deploy + allowlist append if OPENCLAW_ALLOWED_COMMANDS is pinned
- **Next exact action:** Merge/deploy; verify Gateway `automation.status` SUCCEEDED
- **Out of scope:** New STAFF personas · AMBER auto-approve · voice/Swara edits · dial
