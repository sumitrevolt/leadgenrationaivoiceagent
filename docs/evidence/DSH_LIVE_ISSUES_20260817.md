# DSH Live Issue Handoff — 2026-08-17

## Scope

Live admin/operator testing only. No code fix, deploy, billing activation,
outbound send, or compliance-gate change was authorized by this handoff.

## Guardrails

- Cold WhatsApp auto-send stays OFF.
- DND, TRAI window, consent, DLT, and DPDP gates stay fail-closed.
- UPI activation requires owner-confirmed bank credit.
- Never approve or mark a Hot Queue item done without a completed human action.

## Issues handed to DeepSeek Harness

### P0 — DSH authority cannot complete governed work

- Authority canary ends with `dsh_authority_no_capability_submission`.
- The internal LLM endpoint returned HTTP 200, but no capability submission
  reached the governed executor.
- Acceptance: one bounded canary must emit exactly one valid capability
  submission, preserve correlation/audit fields, terminate inside the timeout,
  and leave no duplicate execution.

### P0 — DeepSeek Harness interactive run does not terminate

- A live issue-triage prompt was submitted in the local DeepSeek Harness UI.
- The run retried the model once, attempted unsupported direct `todo_write`,
  then remained in `Deep diving...` for more than two minutes.
- Clicking `Stop generating` did not stop the run within four seconds.
- Browser tab was closed to release operator/browser resources.
- Acceptance: bounded run timeout; stop action reaches terminal cancelled state
  within five seconds; unsupported tool calls fail once and do not hang; final
  failure reason remains visible in session history.

### P1 — Admin dashboard is not decision-ready on first paint

- `/app/admin` initially shows `Loading...` with all scorecard metrics blank.
- Prior live probes observed admin APIs taking roughly 2–14 seconds.
- Acceptance: above-the-fold decision cards show cached/stale-labelled data or a
  bounded error within two seconds; refresh reaches terminal success/error;
  no indefinite loading state.

### P1 — Hot Queue mixes real intent with stale/noisy records

- One genuine SLA-breached inquiry was mixed with old drafts and
  `calling_flagged` records with contact-quality defects.
- A 47-day-old draft still contained time-sensitive wording.
- Examples included a percent-encoded email prefix and a company/domain mismatch.
- Acceptance: genuine inquiries sort first; stale wording blocks send until
  regenerated; malformed/mismatched contacts park automatically with reason;
  loaded and first-paint counts converge.

### P1 — Owner approval queue contains duplicate/no-op noise

- Repeated `outreach_quality` coordinator drafts represented the same issue at
  different counters.
- GOV canary no-op drafts appeared as owner decisions.
- Acceptance: semantic dedupe/idempotency collapses repeated drafts; no-op
  verification entries are separated from business approvals; owner queue shows
  one actionable decision per underlying problem.

### P1 — Security metadata exposure

- Anonymous `/api/agents/status` exposed DSH provider/allowlist/frozen counts.
- Privileged admin shell rendered before protected APIs returned 401.
- Acceptance: anonymous requests receive no internal workforce/runtime metadata;
  protected shell redirects/refuses before privileged content renders; regression
  tests cover both direct API and browser navigation.

### P1 — Deliverability risk

- Admin Deliverability panel reported a Spamhaus blacklist finding.
- Acceptance: reproduce against the authoritative DNS/IP check, record checked
  IP and timestamp without secrets, identify whether the listing is current, and
  keep outreach paused for the affected route until a clean recheck.

### P2 — UPI decision

- No owner-confirmed bank claim was visible, so no plan was activated.
- Acceptance: queue remains empty/neutral without a real claim; activation stays
  impossible until bank confirmation and tenant binding are both present.

## DeepSeek handoff result

- OmniRoute DeepSeek requests timed out twice.
- Local DeepSeek Harness accepted the prompt but did not produce a terminal
  response before the bounded stop; stop itself failed to terminate promptly.
- Therefore the issue list is **durably handed off but not acknowledged with a
  completed DeepSeek verdict**. Retry only after the harness cancellation/tool
  loop is healthy.

## DeepSeek work result (2026-08-17)

**Status:** BLOCKED_NO_EDIT (Time bound exceeded).

**Hypotheses falsified / Investigations:**
1. The `dsh_authority_no_capability_submission` error inside the Canary worker occurs because `run_store.get_submission(submission_id)` is returning `None` completely, despite `turn_complete` successfully firing (meaning DSH exited cleanly or retried until completion).
2. The proxy mapping in `free_ai_proxy.py` correctly converts `submit_tool` to `kwargs["tool_choice"]` as `{ "type": "function", "function": {"name": "dsh_capability_submit"} }`. However, whether LLM properly structures the returned `tool_call` when using models outside OpenAI SDK guarantees (e.g. Mistral/Cerebras) is suspect; if tools are omitted from the finish choice, `validate_response_tools` executes cleanly without raising, leading DSH to exit silently without calling the POST `/internal/dsh/capabilities/{capability}/submissions`.
3. The schema translation by `fastapi_mcp` creates an MCP tool `dsh_capability_submit` expecting a `capability: string` property (parsed as a path parameter). The proxy `tool_choice` forced function names work in isolated Groq simulation, but FastApiMCP intercepts the tool execution through an internal AsyncClient. FastApiMCP DOES correctly inject `authorization` headers from the context (`_forward_headers = ["authorization"]`). The internal `APIException(403)` happens if `cap` provided doesn't structurally match `run["action"]` inside `/internal/dsh/capabilities/{capability}/submissions` or fails in `dsh-jsonrpc-agent`.

**Next primitive probe:**
Run explicit unit test simulation that intercepts `app.api.dsh_internal` using a manually issued token and invoking `FastApiMCP._request` mock or direct `client.post` with the exact path param injected. Analyze whether `FastApiMCP` properly parses the `path` replacing `{capability}` when provided in `arguments`.

**Note:** The Admin Dashboard P1 (authenticated `/api/admin/dashboard` returning HTTP 200 but first-paint/Refresh showing 0 clients/MRR or 'Data load nahi hui') remains unstarted and queued.

## Additional live findings (10:35–10:40 IST)

### P0 — Revenue/customer truth conflicts across admin surfaces

- Admin scorecard showed `0` paid today and one UPI owner-bind item.
- Delivery Cockpit showed **2 paying**, MRR **₹3,998**, and a trial customer in
  `Payment Received`.
- The same live event timeline reported weekly MRR **₹1,999**.
- No owner-confirmed bank evidence was present for the trial customer, so the
  admin decision was **do not confirm, bind, or activate**.
- Acceptance: all admin surfaces derive paying/MRR/payment-stage from the same
  invoice-backed, owner-confirmed UPI ledger; the known paying count and MRR
  reconcile exactly; trial/inquiry records cannot enter `Payment Received`
  without a bound confirmed payment.

### P0 — Paid-customer delivery assurance is internally inconsistent

- Delivery Cockpit showed 5 active, 2 paying, 4 at risk, and 144 approvals.
- Admin scorecard showed 331 delivery-at-risk items.
- Event timeline reported `2 missed / 2 at-risk of 2 paid`.
- The revenue digest in the same timeline reported only ₹1,999 MRR.
- Admin decision: prioritize the real paying customer's overdue setup/delivery;
  do not bulk-generate or bulk-approve content for self/test/trial records.
- Acceptance: one canonical cohort defines paying customers; risk count is
  tenant-count, approval count is item-count, and labels make that distinction
  explicit; self/test/trial tenants are excluded from paid-delivery SLA.

### P1 — Approval totals disagree and contain old/non-live inventory

- Mission Control reported 331 approval items, oldest 56 days, across campaign,
  festival, GBP, post, poster, reel, review reply, video, and WhatsApp.
- Delivery Cockpit reported 144 pending approvals.
- Admin decision: no bulk owner approval. Remind only verified live customers;
  orphan/test inventory requires fail-closed retirement/dry-run review.
- Acceptance: both surfaces expose the same source breakdown, live-tenant count,
  orphan/test count, and age; terminal/orphaned rows never block live generation.

### P1 — Scheduler and budget health contradicts headline status

- Attention panel reported 20 budget-skipped engine runs and 2 dead/exhausted
  tasks.
- Event timeline reported `scheduler_stalled`, while the page also described
  automation health as degraded with `0 overdue, 0 never-ran`.
- Admin decision: do not blindly raise the global budget; isolate heavy engines
  into bounded jobs with their own timeout/retry/DLQ/heartbeat.
- Acceptance: stalled reason names the scheduler/job; skipped engines have
  per-engine counters and last timestamp; dead tasks expose task id/type and
  failure reason before any retry/clear action.

### P1 — Deliverability signal flaps within minutes

- Timeline alternated between `deliverability_check OK` and
  `IP blacklisted: zen.spamhaus.org` within minutes.
- Admin decision: treat as unverified/degraded, not a stable blacklist verdict;
  pause affected outbound route until authoritative recheck identifies the
  queried IP and DNS response semantics.
- Acceptance: checks record timestamp, queried IP hash/prefix-safe identity,
  resolver class, raw DNSBL return code classification, and require two
  consistent authoritative results before changing route state.

### P1 — Compliance readiness is scored green despite missing evidence

- Telephony readiness displayed `95/100 | missing: compliance_flags` but event
  severity was `ok`.
- Admin decision: no calling readiness promotion from this score.
- Acceptance: any missing compliance evidence forces non-green/fail-closed
  readiness and names the missing gate without exposing values.

### P1 — Unsafe-channel experiment recommendations entered the live timeline

- Growth optimizer recommended channel experiments including `whatsapp_group`
  and `linkedin_dm`.
- Admin decision: reject unbounded generic growth plan; no automated cold WA,
  group messaging, or ToS-blocked automation.
- Acceptance: banned channels are filtered before assignment; allowed
  experiments are draft-only, human-reviewed, tenant-scoped, and idempotent.

## Live loop tick follow-up (2026-08-17 ~10:48 IST)

### P1 — Prod container recreate mid-loop (same SHA)

- Dual probe: `/health` stayed `a9dd64fb` / healthy / production, but uptime
  dropped from ~47m to ~20m then advanced 20m33s → 20m35s.
- Label: DIRECT_HOST_VERIFIED recreate/restart of same image, not a version
  change. Cause unknown from this shell (do not invent).
- Acceptance: operator notify on non-deploy recreate; event/log names who/what
  restarted; `/health.version` + uptime discontinuity appear together in ops
  timeline.

### P1 — Vague coordinator growth/ops draft reappears after reject

- Admin rejected the unbounded “Aaj ka team plan growth+ops” draft multiple
  times in this live loop; it reappears in OpenClaw/Boss pending approvals.
- Acceptance: rejected drafts stay terminal; regenerating the same semantic
  plan within a cooldown is blocked or collapsed by idempotency key.

## DeepSeek work result (2026-08-17 ~11:38 IST)

Status: **BLOCKED_NO_EDIT** (Cursor append — DeepSeek harness edit returned
`FS_NOT_OBSERVED` after bound exceeded).

### What DeepSeek did

- Session “WORK the live handoff” ran 70+ steps / ~4.8M input tokens.
- Local suite `tests/test_dsh_workforce_runtime.py` green; no production
  capability-submission canary re-run from this session.
- No durable code edit landed for `dsh_authority_no_capability_submission`.

### Hypotheses touched (not proven as fix)

1. LLM returns 200 / turn_complete but no durable capability submission row.
2. Proxy forces `dsh_capability_submit` tool shape; MCP/`FastApiMCP` wiring and
   submission store read-back still under-probed.
3. `mask_customer_data` structural tool-name masking was previously fixed
   elsewhere — not re-verified as the live canary cause here.

### Exact next primitive probe (owner/Cursor)

1. One bounded DSH canary with Redis submission-store available.
2. Capture: LLM chat/completions body (tool_calls names), MCP submit request,
   `run_store` submission id + status, cancel reason string.
3. Only then edit the smallest fail-closed path + one regression test.

### Live-test P1 noted same session

- Admin first-paint / Refresh can show `0` clients / MRR / “Data load nahi
  hui” while authenticated `GET /api/admin/dashboard`, `/api/clients`, and
  `/api/admin/revenue-analytics` return **200**. Treat as UI/client-state
  race, not billing truth.

Acceptance for P0 DSH: **FAILED** (no fix, no targeted proof).
Files changed by DeepSeek: **none**.
