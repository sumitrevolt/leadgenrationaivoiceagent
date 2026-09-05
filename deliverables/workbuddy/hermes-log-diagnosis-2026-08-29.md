# Hermes Log Diagnosis — 2026-08-29 16:20 IST

Analysis window: 2026-08-19 → 2026-08-29 (26 log sources, ~37 MB)
Host: `LAPTOP-93MJJE8N` · Gateway: `hermes_cli` v0.20.5 (`code_sha 29033a3f`) · Python 3.11.16 · win32

---

## Executive Summary

The stack is **up but degraded**. Five distinct faults are active right now. Two are
self-inflicted configuration problems with one-command fixes (they account for ~85% of all
error volume), one is a remote-service dependency, one is a duplicate-process/networking
issue, and one is a resource-pressure symptom.

| # | Severity | Issue | Volume (3 rotations) | Fixable in |
|---|----------|-------|----------------------|------------|
| 1 | **P0** | Cron `c7a092351190` — inference config drift, hard-skip | 863 failures | 1 command |
| 2 | **P0** | Cron `527c8915ee14` — provider auth expired + rate limits | 173 failures | Dashboard / key rotation |
| 3 | **P1** | MCP `leadgen` — stale SSE session → HTTP 404 storm | 415 failures | Gateway restart / server fix |
| 4 | **P1** | Telegram `getUpdates` conflict loop + API path flapping | Continuous | Process hygiene / network |
| 5 | **P2** | Gateway restart churn; WinError 1450 resource exhaustion | 15+ restarts | Cleanup |
| 6 | **P3** | `desktop-commander` MCP connect; subprocess reader races | Sporadic | Low priority |

---

## 1. P0 — Cron `c7a092351190` "EMERGENCY RECOVERY TASK — TERMINAL BACKEND DIAGNOS"

**Status: 100% failure rate. Every single invocation fails.**

```
Job 'c7a092351190': SKIPPED — global inference config drifted since creation
(provider 'gmi' -> 'custom'; model 'minimaxai/minimax-m3' -> 'hermes-engineer')
and this job is unpinned. Skipped to prevent unintended spend.
RuntimeError: [drift_skip:silent] ... See #44585.
```

| Log | Occurrences |
|-----|-------------|
| `errors.log` (today) | 78 |
| `errors.log.1` | 398 |
| `errors.log.2` | 387 |

**Root cause:** This is a deliberate safety mechanism, not a bug. At some point the global
inference config was switched from `gmi / minimaxai/minimax-m3` to `custom / hermes-engineer`.
Because the job carries no pinned provider/model, Hermes refuses to silently re-point the job
at a different (possibly expensive) backend and skips it instead.

**Why it matters beyond noise:** the job title indicates it is a *recovery* task. It has not
executed successfully in at least 6 days. It fires roughly every 20 minutes
(15:58 → 16:18 → …), so it is generating ~72 error lines/day and zero value.

**Fix (pick one):**
```bash
# Option A — re-point the job at the current config
hermes cron edit c7a092351190 --provider custom --model hermes-engineer

# Option B — restore the original config it was authored against
hermes cron edit c7a092351190 --provider gmi --model minimaxai/minimax-m3

# Option C — it is stale; retire it
hermes cron delete c7a092351190
```
Option A is recommended **only** if you accept the new backend's cost profile. Given the job
is titled "EMERGENCY RECOVERY" and dates back to an earlier incident, Option C is likely
correct.

---

## 2. P0 — Cron `527c8915ee14` "revenue-autopilot-driver"

**Status: failing on every run since at least 2026-08-27.**

Traffic routes through a **local aggregator** at `http://127.0.0.1:20128/v1`
(profile `custom`, model `leadgen-project-best`). The aggregator fans out to upstream
providers and is returning **HTTP 502** because *all* of its backends are failing:

```
HTTP 502: hfr/openai/gpt-oss-120b: auth — [openai-compatible-chat-conn:39015e75]
  All 1 connection(s) authentication expired — please reconnect in the dashboard (HTTP 401)
oc/deepseek-v4-flash-free: rate limit — [429] Rate limit exceeded
oc/big-pickle:            rate limit — [429] Rate limit exceeded
gemini/gemini-flash-latest: auth — [401] Your API key is invalid, blocked or out of funds
```

| Failure mode | `errors.log` | `errors.log.1` |
|--------------|--------------|----------------|
| `gemini-flash-latest` 401 (invalid/blocked/unfunded key) | 28 | 140 |
| `hfr/openai/gpt-oss-120b` 401 (connection expired) | 5 | — |
| Telegram delivery `ConnectError` (target `telegram:1621120182`) | 2 | — |

**Three independent root causes, all actionable:**

1. **HFR connection expired** — the aggregator requires an interactive reconnect in its
   dashboard. This is an OAuth-style session, not an API key; it cannot be fixed from config.
2. **Gemini API key invalid/blocked/out of funds** — replace or top up the key.
3. **OpenRouter free-tier models (`oc/*`) rate-limited** — the job retries 3× with backoff and
   still exhausts. Free tiers will not sustain a 20-minute cadence.

Note also the **63–86 s elapsed time per failed attempt** before the 502 returns. The job is
burning wall-clock and retries against dead backends on every tick.

**Fix order:** reconnect HFR in the aggregator dashboard → replace the Gemini key → either
pin the job to a paid model or extend its interval so free-tier quotas recover.

---

## 3. P1 — MCP server `leadgen` (`https://leadsgenai.in/mcp`) — HTTP 404 storm

```
httpx2.HTTPStatusError: Client error '404 Not Found' for url
'https://leadsgenai.in/mcp/messages/?session_id=<uuid>'
```

| Log | Occurrences |
|-----|-------------|
| `errors.log` | 45 |
| `errors.log.1` | 201 |
| `errors.log.2` | 169 |

**Diagnostic work already done — token expiry is ruled out:**

- Bearer JWT (config.yaml:2929) `iat` = 2026-08-23, **`exp` = 2031-08-22** (1818 days remaining).
- Live probe of `https://leadsgenai.in/mcp` returned **HTTP 401** in 0.46 s — the host is
  reachable and the auth gate is functioning (401 is the correct response to a
  credential-less request).

**Actual root cause:** the failure is on the **POST-back channel** with a `session_id`
query parameter. The SSE stream is established, but the server's session registry no longer
recognises the session when Hermes posts to it. This is the classic stale-session signature:
the upstream server restarted, horizontally scaled without shared session state, or expired
idle sessions while the local client kept its cached `session_id`. Hermes then reuses a dead
session indefinitely instead of renegotiating.

**Fix:**
1. Immediate: restart the gateway so the SSE session is renegotiated from scratch.
2. Durable (server side): make the MCP endpoint either stateless-per-request or back the
   session registry with shared storage. A restart should not orphan live client sessions.
3. Client side: this warrants a bug report — the client should detect a 404 on the
   message channel and trigger automatic session renegotiation rather than retrying forever.

---

## 4. P1 — Telegram `getUpdates` conflict loop + API path flapping

**Two compounding problems.**

### 4a. Polling conflict — repeated every ~60 s

```
[Telegram] Telegram polling conflict (1/5) — previous session still held open on
Telegram's servers. Waiting 20s for it to expire.
Error: Conflict: terminated by other getUpdates request;
make sure that only one bot instance is running
```

The polling generation counter is climbing steadily — **generation 4 at 16:15 → generation 8
at 16:20**, i.e. the poller restarts roughly every 60–75 seconds and never stabilises.

**Evidence of duplicate instances on this host:**

```
PID 27900  python.exe    4.9 MB   ...venv\Scripts\python.exe -m hermes_cli.main gateway run
PID 27956  python.exe  175.6 MB   ...cpython-3.11...\python.exe -m hermes_cli.main gateway run
```

Two processes are running `gateway run` simultaneously. `gateway_state.json` names **27956**
as the registered writer (`telegram: state=connected`), which makes 27900 an unregistered
duplicate — and the prime suspect for the conflict.

> ⚠️ Both PIDs must be confirmed before any action. 27900 may be a legitimate supervisor
> stub. Do not kill processes blindly — inspect the parent/child relationship first.

### 4b. Network path instability

```
[Telegram] Sticky Telegram path api.telegram.org failed; re-walking IPv4 literals
[Telegram] Dual-stack api.telegram.org path failed ()
[Telegram] IPv4 Telegram API IP 149.154.166.110 failed:
[Telegram] Using sticky IPv4 Telegram API path 149.154.166.110 (dual-stack hostname tried last — #87015)
[Telegram] Discovering Telegram API fallback IPs via DNS-over-HTTPS…
```

Both the hostname (`api.telegram.org`, dual-stack) **and** the hardcoded fallback IP
(`149.154.166.110`) are failing, which forces DNS-over-HTTPS IP discovery. This pattern
indicates egress filtering or DNS interception on the local network — not a Telegram outage.
The adapter recovers each time, so this is latency/robustness degradation rather than a hard
outage.

**Fix:** eliminate the duplicate gateway process; if 4b persists, check firewall/proxy/DNS
settings for `api.telegram.org` egress.

---

## 5. P2 — Gateway restart churn and resource exhaustion

### 5a. Restart churn (2026-08-28 → 08-29)

`gateway-exit-diag.log` shows 15+ gateway PIDs with lifetimes of **2–6 minutes**, including
several flagged `gateway.previous_unclean_exit`:

| Window | Behaviour |
|--------|-----------|
| 08-28 18:05 – 18:30 | 8 start/stop cycles, 2 unclean exits |
| 08-29 01:00 – 02:42 | 6 start/stop cycles, 3 unclean exits |
| 08-29 10:37 → | Current session (PID 27956), stable |

Mitigating factor: nearly all recorded exits are `asyncio.run.returned` with
`"success": true` and `gateway.exit_clean` — these are **controlled restarts, not crashes**.
The pattern is consistent with an update/retry loop rather than a fault.

### 5b. WinError 1450 — system resource exhaustion

```
=== thread exception · 2026-08-25 13:09:08 · thread=desktop-cron-ticker ===
OSError: [WinError 1450] Insufficient system resources exist to complete the requested service:
'C:\Users\Ratanshila\AppData\Local\hermes\profiles\hunter'
  ... cron\scheduler_provider.py line 711, in _start_multiplex
  ... cron\jobs.py line 175, in use_cron_store
```

This killed the `desktop-cron-ticker` thread outright. WinError 1450 at `realpath()` on a
16 GB / 16-core machine points to **handle or non-paged-pool exhaustion**, not RAM.

**Current footprint:** `Hermes.exe` + `python.exe`/`pythonw.exe` = **1,367 MB** across 21
processes (5 Hermes.exe incl. Electron GPU/renderer/utility children, 11 python.exe,
2 pythonw.exe). Not critical today, but the headroom is thinner than it looks given the
duplicate gateway and the 502-retry storms.

---

## 6. P3 — Low-priority observations

| Observation | Detail | Assessment |
|-------------|--------|-----------|
| `desktop-commander` MCP | `Failed to connect ... (command=npx): CancelledError` (16:09) | Startup timeout via `npx`; self-recovers. Prefer a local install over `npx` to remove the resolution latency. |
| `ValueError: read of closed file` | 3× on 08-28 in `subprocess.py _readerthread` | Benign shutdown race — the pipe closes while the reader thread drains. Cosmetic. |
| Telegram delivery failures | `ConnectError` targeting `telegram:1621120182` (2×) | Downstream of §4b, not a separate fault. |

## 7. Healthy sub-systems (no action required)

- **Skills Hub** — `curator` ran cleanly on 08-24 and 08-28 (87→88 memories checked,
  0 stale / 0 archived). Consolidation is intentionally off.
- **`hermes doctor`** (last full run 08-28 04:23) — **all checks passed**. 55 plugins
  discovered, 49–50 enabled; 9 profiles configured (`hunter`, `guardian`, `sales`, `pilot`,
  `platform`, `board`, `engineering`, `operations`, `success`).
- **Skill installs** — `kanban-video-orchestrator` installed 08-23 after a clean
  `skills-guard-v1` scan (verdict: ALLOWED, builtin source). Three MEDIUM findings flagged
  (`subprocess.run` in `monitor.py`, f-string patterns in `bootstrap_pipeline.py`) were
  accepted as expected for a pipeline skill.
- **Updater** — `skills-update` ran 08-23 and 08-24, "No updates available" both times.
  Bootstrap rebuild completed successfully on 08-24 (379 s, Electron 40.10.2).
- **Known-missing optional deps** (from doctor) — `browser`, `image_gen`, `video_gen`,
  `feishu`, `homeassistant`, `spotify`; `DISCORD_BOT_TOKEN` and `XAI_API_KEY` unset.
  These are configuration choices, not failures.

---

## Recommended Action Sequence

1. **Decide the fate of cron `c7a092351190`** — pin it or delete it. This alone removes the
   single largest source of log noise and stops a recovery job from silently no-op'ing.
2. **Repair the `revenue-autopilot-driver` credential chain** — reconnect HFR in the
   aggregator dashboard, replace the Gemini key, and stop scheduling against free-tier models.
3. **Restart the gateway once** — clears the stale `leadgen` SSE session (§3) and lets you
   confirm whether a single clean gateway instance resolves the Telegram conflict (§4a).
4. **Verify PID 27900 vs 27956** — establish which is the supervisor and which is a stray,
   before touching either.
5. **Raise two upstream bugs** — MCP client should renegotiate on message-channel 404;
   `leadsgenai.in` should not orphan sessions on restart.

---

*Prepared from 26 log sources under `C:\Users\Ratanshila\AppData\Local\hermes\logs\`
(~37 MB), plus live probes of `leadsgenai.in` and `127.0.0.1:20128`, and live process
inspection. No configuration was modified during this analysis.*

---
---

# Addendum — Second Pass, 16:35 IST

A follow-up pass resolved the open question from §4a by walking the **full process tree with
parent PIDs and command lines** (`Win32_Process`), instead of counting processes by image name.
Two conclusions in the report above are **wrong** and are corrected here.

## A. CORRECTION — There is only ONE Hermes app and ONE gateway

Process-name counts are misleading because Electron and the Python launcher both fork
children that keep the same image name. The real tree:

```
explorer.exe (13104)
└─ Hermes.exe 17080                    ← the only Hermes application
   ├─ Hermes.exe 15768  --type=gpu-process
   ├─ Hermes.exe 30588  --type=utility --utility-sub-type=network.mojom.NetworkService
   ├─ Hermes.exe 3004   --type=renderer
   ├─ Hermes.exe 30908  --type=utility --utility-sub-type=audio.mojom.AudioService
   └─ python.exe 30992  --profile default serve --host 127.0.0.1 --port 0   (desktop backend)
      └─ python.exe 3140   (managed runtime)
         └─ python.exe 20460 (cpython 3.11.16)
```

The four extra `Hermes.exe` PIDs are **Electron's own GPU / network / renderer / audio
children** of 17080 — not duplicate app instances. §5b's "5 Hermes.exe" was correct in count
but its implied severity should be discounted by ~four.

The gateway is likewise a single, healthy three-level tree — **not two competing gateways**:

```
python.exe 27900   (venv)      -m hermes_cli.main gateway run     ← launcher / supervisor
└─ python.exe 27956 (runtime)  -m hermes_cli.main gateway run     ← the actual gateway
   └─ python.exe 14440 (cpython 3.11.16)
```

`gateway_state.json` confirms it: `writer_pid: 27956`, `state: "connected"`,
`needs_attention: false`, `active_agents: 0`, `code_sha 29033a3f`.

> **§4a is therefore retracted.** PID 27900 is not a stray duplicate — it is 27956's own
> parent launcher. Do not kill it; killing 27900 would take the gateway down with it.
> The warning not to kill PIDs blindly was correct, but the suspicion against 27900 was not.

## B. NEW CONCLUSION — The Telegram 409 conflict is NOT local

Since exactly one `gateway run` tree exists on this host, Telegram's
*"terminated by other getUpdates request; make sure that only one bot instance is running"*
cannot be caused by a local duplicate. The conflicting long-poll caller is **another host
holding the same bot token** — almost certainly the LeadGen production/VPS stack referenced
throughout `desktop.log` (which already routes Telegram deliveries to `telegram:1621120182`).

This also explains why the adapter's own recovery works: it reconnects successfully each time
(generations 4→10 in twelve minutes) and then is immediately displaced again by the remote
poller. **Restarting the local gateway will not fix this.**

**Fix:** audit every host that has this bot token configured and leave exactly one of them
polling. If both the laptop and the VPS must receive updates, the bot needs to move to a
webhook on one host rather than long-polling from two.

## C. NEW — Duplicate `graphify` MCP server

Two independent instances are running against the **same** graph file:

```
graphify-mcp.exe 17488  (parent 27956 — gateway)      → python.exe 3452  → 13084
graphify-mcp.exe 20152  (parent 3140  — desktop)      → python.exe 19716 → 26816
   both: --graph ...\leadgenrationaivoiceagent\app\graphify-out\graph.json
```

One is spawned by the gateway, one by the desktop backend. This doubles the memory cost
(~50 MB) and risks concurrent writes to a shared `graph.json`. Low severity, but it is a real
duplicate where the report above assumed none existed.

## D. NEW — The update actually failed (contradicts §7)

`logs/update_receipts/latest.json` records a **failed** update, not a healthy one:

```json
"outcome": "failed", "exit_code": 1, "stop_reason": "sys.exit(1)",
"steps": [{"name": "pre_update_backup", "ok": false, "detail": "disabled or failed"}],
"pre_update":  {"sha": "91e867631e9d2eb9fbd69edd4459475d38070979", "version": "0.20.5"},
"post_update": {"sha": "91e867631e9d2eb9fbd69edd4459475d38070979", "version": "0.20.5"}
```

Pre- and post-update SHAs are identical — nothing changed. The single recorded step,
`pre_update_backup`, failed, and the run aborted there. §7's "updater fine" was based on the
`bootstrap-installer` log and `skills-update`; the **core updater** is in fact broken and the
install is pinned at v0.20.5 / `91e86763`.

**Fix:** re-enable or repair the pre-update backup, then re-run `hermes update`. Until then no
core updates will land.

## E. REFINEMENT — `leadgen` MCP 404s are intermittent, not permanent

§3 treats the 404 storm as a stuck stale session. A live tail shows the server recovering on
its own at 16:26:

```
16:26:40  MCP 'leadgen' keepalive failed → degraded → reconnect
16:26:41  GET  https://leadsgenai.in/mcp                        → 200 OK
16:26:41  POST https://leadsgenai.in/mcp/messages/?session_id=  → 202 Accepted  (×3)
```

So the pattern is **keepalive timeout → teardown → successful renegotiation**, repeating. The
server is alive and the client does recover — the 404s are the window where a request lands
against an already-discarded session. That softens §3 from "restart the gateway to fix" to
"expect intermittent 404s; the durable fix is still server-side session handling."

## F. Other new measurements

| Item | Value | Note |
|------|-------|------|
| Cron failure totals | 1,030 (`c7a092351190`: 746, `revenue-autopilot-driver`: 284) | grep on `Job '<name>' failed`, all 3 rotations |
| `drift_skip` events | 1,648 (`c7a092351190`: 743, `527c8915ee14`: 77) | matches §1's scale |
| HTTP 502 / bad_gateway | 478 (278 today, 144 + 56 prior) | rising day over day |
| `authentication expired` | 170 | rising day over day |
| `Rate limit exceeded` | 187 | rising day over day |
| Gateway lifecycle | 46 starts, 15 `previous_unclean_exit` since 08-21 | current PID 27956 stable since 10:37 UTC |
| Disk C: | 87% used — 44 GB free of 316 GB | backup failure in §D may be related |
| Python + Hermes footprint | 1,173 MB across 17 processes | lower than §5b's 1,367 MB / 21 — processes have churned |

The 502 / 401 / 429 curves all **increase** across the three rotations (56 → 144 → 278 for
502s), so the credential rot in §2 is still spreading, not stabilising.

## G. Revised action sequence

1. **Cron `c7a092351190`** — pin or delete (unchanged, still the single largest noise source).
2. **Telegram bot token audit across hosts** (§B) — this replaces "verify PID 27900 vs 27956",
   which is now settled as a non-issue. Do not restart the gateway expecting a fix.
3. **Repair the pre-update backup, then re-run `hermes update`** (§D) — the install is frozen
   at v0.20.5.
4. **Reconnect HFR + replace the Gemini key** (§2) — the failure rate is still climbing.
5. **De-duplicate `graphify` MCP** (§C) — disable it in either the gateway or the desktop
   backend, not both.
6. **`leadgen` MCP** (§E) — lower priority; it self-recovers.

*Addendum method: `Win32_Process` enumeration (PID, parent PID, full command line) for
`Hermes.exe` / `python.exe` / `pythonw.exe`, `gateway_state.json`, `update_receipts/latest.json`,
and live tails of `agent.log` / `errors.log`. Read-only — no process was terminated and no
configuration was modified.*
