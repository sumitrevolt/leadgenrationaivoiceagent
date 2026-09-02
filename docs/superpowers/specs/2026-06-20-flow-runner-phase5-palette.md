# Flow Runner — Phase 5: Richer node palette + more executors — Design Spec

> **Status:** Drafted 2026-06-20 — ready for implementation plan.
> **Builds on:** `docs/superpowers/specs/2026-06-20-flow-runner-design.md` (Phase 1, shipped — linear runner, 9 executors).
> **Scope discipline:** ADDITIVE only. New executors + one allowlisted HTTP node + palette items. **NO** branching (Phase 2), triggers (Phase 3), or data-passing (Phase 4) — seams noted, not built.
> **The #1 rule (verbatim from constraints):** EVERY new executor must be **draft-safe or breakpoint-gated**. No new auto-send / auto-call / auto-publish surface. Compliance (TRAI/DLT/DND/WhatsApp-ban) stays **server-side in the engines themselves** — the flow runner never weakens it.

---

## 1. Why (problem)

Phase 1 made visually-built flows **executable** but with a deliberately tiny palette: 9 executors, all lead/content/revenue oriented. An admin cannot yet compose a flow that touches the *communication* and *reporting* surfaces the platform already owns (email digest, Telegram/WhatsApp **drafts**, CRM queue, SEO blog, brand pulse, review monitor, client report) — even though all those engines exist and are already draft-safe in their daily-scheduler form.

There is also a recurring "n8n envy" gap: every external automation tool has an **HTTP Request** node. Without one, any "ping our own status webhook / fetch an allowlisted partner API" step forces a code change. But a naive HTTP node is a **compliance foot-gun** — it would let an admin bypass every TRAI/DLT/WhatsApp gate by POSTing directly to a provider. Phase 5 ships an HTTP node that **cannot** do that (host allowlist + no provider hosts on it + no secret interpolation).

Phase 5 expands **what flows can DO** while keeping the safety envelope identical to Phase 1.

## 2. Goal / Non-goals

**Goal (Phase 5):**
1. Add **8 new draft-safe / breakpoint-gated executors** to `process_library.EXECUTORS`, each wrapping a real existing engine — no rebuild, same `_exec_*` pattern, never-raise.
2. Add ONE **allowlisted "HTTP Request"** executor — admin-only, host-allowlist (env-config), GET/POST, timeout-bounded, never-raise, SSRF-guarded, **no secret interpolation in V5**, and structurally **incapable** of hitting telephony/WhatsApp/email-provider hosts (they're simply never on the allowlist).
3. Add the matching **`NODE_TEMPLATES`** palette entries in `frontend/explorer.html` so each new action is draggable in the builder.

**Non-goals (sequenced into the §11 roadmap of the Phase-1 spec, not dropped):**
- Branching / conditionals / fan-out (Phase 2) — engine stays linear.
- Cron / event triggers (Phase 3) — manual Run only.
- Node-output → downstream-input data-passing & per-node param editor (Phase 4) — run-level `inputs` still flows to every executor; HTTP node reads its target from `inputs`, not from an upstream node.
- **Any auto-send.** No executor here transmits to an end-user. Send-capable engines are wrapped at their **draft-only** entrypoint or sit behind an explicit breakpoint.
- Secret/header interpolation, auth, or response-mapping for the HTTP node (deferred — see Open Questions).

## 3. New executors — the TABLE (draft-safety is the load-bearing column)

All wrappers follow the exact Phase-1 `_exec_*` contract:

```python
async def _exec_<name>(inputs: dict) -> dict:   # returns {"ok": bool, "count": int, "detail": str}
```

— never-raise (wrap the engine call in try/except → `{"ok": False, ...}` on failure), import inside the function (import-safe), reuse an existing engine, side-effect-free or gated.

| # | New action key | Wrapped function (verified) | Draft-safe? | Notes / why it can't auto-send |
|---|---|---|---|---|
| 1 | `email_digest` | `app/platform/revenue_digest.run(force=True)` | **CONDITIONAL → wrapped draft-only** | `run()` emails only if `REVENUE_DIGEST=1` **and** `NOTIFY_EMAIL` set (internal admin address, never a customer). Wrapper calls it as-is: worst case it mails the **admin's own** ops digest — not an outreach surface. Default (flags unset) = compose-only, no send. **No customer-facing transmission possible.** |
| 2 | `telegram_draft` | `app/marketing/telegram_publish.run_due()` | **CONDITIONAL → safe by default + breakpoint-required** | `run_due()` posts **only** when `TELEGRAM_AUTO_PUBLISH=1` **and** `TELEGRAM_BOT_TOKEN` set; default returns `{"ran": False, ...}` inert. Telegram is the project's one *true* auto-post channel, so this node is **flagged in the palette as "publish-capable"** and the spec REQUIRES an upstream breakpoint when the auto-publish flag is on (compiler hint, §6). |
| 3 | `whatsapp_draft` | `app/marketing/whatsapp_campaign.send_campaign(items)` | **YES (draft-first by design)** | When `WHATSAPP_AUTO_SEND` unset (default), every send **downgrades to a `wa.me/` 1-click link** — no Cloud API call. Wrapper passes a small `items` batch from `inputs`; even "sent" count = links generated, not messages pushed. Cloud API fires ONLY with flag + approved template + creds. Ban-safe default. |
| 4 | `crm_queue` | `app/platform/crm_sync` — gated wrapper around `push_lead` | **CONDITIONAL → wrapped breakpoint-gated** | `push_lead()` pushes **live** to Zoho/HubSpot on every direct call (the `CRM_SYNC` flag only gates the auto-hook, NOT the fn). So the executor MUST NOT call `push_lead` unconditionally. Wrapper rule: only push when `CRM_SYNC` flag is on **and** an upstream breakpoint was approved; otherwise it **counts eligible leads and returns a draft summary** (no push). Treated as a side-effecting node → breakpoint-required in palette. |
| 5 | `seo_blog_draft` | `app/marketing/seo_blog.generate_article(niche, city, topic)` | **YES** | Pure free-LLM generation → returns `{slug,title,html_body,...}`. **Does not save or publish** (`save_article`/`run_daily_blog` are separate). No external POST. Wrapper returns `count=1`, detail=title. |
| 6 | `brand_pulse` | `app/platform/brand_pulse.scan(business_name, city, niche)` | **YES** | Read-only Google-News-RSS + Reddit-JSON fetch → mentions + **reply DRAFTS** (never posted, by module design). Gated by `BRAND_PULSE=1` (returns `{"ok":False,"reason":"flag_off"}` when off — still safe). No send anywhere. |
| 7 | `review_scan` | `app/marketing/review_monitor.run_check(max_clients)` | **YES** | Gated `REVIEW_MONITOR=1` + `GOOGLE_MAPS_API_KEY`; reads reviews + writes AI reply **drafts** to `data/review_monitor_drafts.jsonl`. **No GBP auto-post** (API approval pending — human 1-click only). Off/no-key = silent skip. |
| 8 | `client_report_draft` | `app/marketing/client_report.build_report(client_id, month, send=False)` | **CONDITIONAL → wrapped draft-only** | Always writes the report HTML to disk; emails only if `CLIENT_REPORTS=1` OR `send=True`. Wrapper **hard-codes `send=False`** → file generated, **never emailed**. Returns `count=1`, detail=path. |

**HTTP node (separate design, §4):**

| # | New action key | Implementation | Draft-safe? | Notes |
|---|---|---|---|---|
| 9 | `http_request` | NEW `app/automation/flow_http.py` (stdlib-mirror of `website_auditor` SSRF guard + `httpx`) | **YES (allowlist-fenced)** | Admin-only, host-allowlist env, GET/POST, timeout-bounded, SSRF-guarded, no secrets, never-raise. Cannot reach provider hosts (none on allowlist). §4. |

**Count: 8 engine-wrapping executors + 1 HTTP node = 9 new actions.** Draft-safe outright: `whatsapp_draft`, `seo_blog_draft`, `brand_pulse`, `review_scan`, `http_request` (5). Wrapped-to-draft-only: `email_digest`, `client_report_draft` (2). **Breakpoint-required** (side-effect-capable, palette-flagged): `telegram_draft`, `crm_queue` (2).

### 3.1 Exact `_exec_*` signatures (build-ready)

Add to `app/agents/process_library.py`, following the existing pattern verbatim (import-inside, never-raise, `{ok,count,detail}`):

```python
async def _exec_email_digest(inputs: dict) -> dict:
    from app.platform import revenue_digest
    try:
        res = await revenue_digest.run(force=bool(inputs.get("force", True)))
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"digest err: {e}"[:150]}
    sent = bool(res.get("sent"))
    return {"ok": True, "count": 1 if sent else 0,
            "detail": f"digest {res.get('week','')}: {'emailed-admin' if sent else 'composed'}"}


async def _exec_telegram_draft(inputs: dict) -> dict:
    # NOTE: posts only if TELEGRAM_AUTO_PUBLISH=1 + token. Default = inert draft.
    from app.marketing import telegram_publish
    try:
        res = await telegram_publish.run_due()
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"telegram err: {e}"[:150]}
    if not res.get("ran"):
        return {"ok": True, "count": 0, "detail": f"telegram inert ({res.get('reason','off')})"}
    return {"ok": True, "count": int(res.get("sent", 0) or 0),
            "detail": f"telegram published={res.get('sent',0)} (AUTO_PUBLISH on)"}


async def _exec_whatsapp_draft(inputs: dict) -> dict:
    # Default (WHATSAPP_AUTO_SEND unset) = wa.me links only, no Cloud API.
    from app.marketing import whatsapp_campaign
    items = inputs.get("items") or []
    if not isinstance(items, list):
        items = []
    try:
        res = await whatsapp_campaign.send_campaign(items[:50])
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"wa err: {e}"[:150]}
    live = bool(res.get("live"))
    n = int(res.get("links", res.get("sent", 0)) or 0)
    return {"ok": True, "count": n,
            "detail": f"whatsapp {'SENT' if live else 'links'}={n}"}


async def _exec_crm_queue(inputs: dict) -> dict:
    # Side-effecting: pushes ONLY when CRM_SYNC flag on AND breakpoint approved upstream.
    # Default = count eligible, no push (draft summary).
    import os
    from app.platform import crm_sync
    leads = inputs.get("leads") or []
    if not isinstance(leads, list):
        leads = []
    flag_on = os.environ.get("CRM_SYNC", "0").strip().lower() in ("1", "true", "yes")
    if not flag_on:
        return {"ok": True, "count": 0,
                "detail": f"crm draft: {len(leads)} eligible (CRM_SYNC off — no push)"}
    pushed = 0
    for ld in leads[:25]:
        try:
            r = await crm_sync.push_lead(ld, client_id=str(inputs.get("client_id", "")))
            if r.get("ok"):
                pushed += 1
        except Exception:
            pass
    return {"ok": True, "count": pushed, "detail": f"crm pushed={pushed} (flag on)"}


async def _exec_seo_blog_draft(inputs: dict) -> dict:
    from app.marketing import seo_blog
    try:
        art = await seo_blog.generate_article(
            niche=str(inputs.get("niche", "general")),
            city=str(inputs.get("city", "")),
            topic=inputs.get("topic"),
        )
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"blog err: {e}"[:150]}
    title = (art or {}).get("title", "")
    return {"ok": bool(title), "count": 1 if title else 0, "detail": f"blog draft: {title[:80]}"}


async def _exec_brand_pulse(inputs: dict) -> dict:
    from app.platform import brand_pulse
    bn = str(inputs.get("business_name") or inputs.get("brand") or "")
    if not bn:
        return {"ok": False, "count": 0, "detail": "brand_pulse: business_name required"}
    try:
        res = await brand_pulse.scan(bn, city=inputs.get("city"), niche=inputs.get("niche"))
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"pulse err: {e}"[:150]}
    m = len(res.get("mentions") or [])
    return {"ok": bool(res.get("ok", True)), "count": m,
            "detail": f"brand mentions={m}, drafts={len(res.get('reply_drafts') or [])}"}


async def _exec_review_scan(inputs: dict) -> dict:
    from app.marketing import review_monitor
    try:
        res = await review_monitor.run_check(max_clients=int(inputs.get("max_clients", 15)))
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"review err: {e}"[:150]}
    if not res.get("enabled"):
        return {"ok": True, "count": 0, "detail": "review_monitor off (REVIEW_MONITOR unset)"}
    n = int(res.get("new_reviews", 0) or 0)
    return {"ok": True, "count": n, "detail": f"review drafts +{n}"}


async def _exec_client_report_draft(inputs: dict) -> dict:
    from app.marketing import client_report
    cid = str(inputs.get("client_id", ""))
    if not cid:
        return {"ok": False, "count": 0, "detail": "client_report: client_id required"}
    try:
        res = await client_report.build_report(cid, month=str(inputs.get("month", "")), send=False)
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"report err: {e}"[:150]}
    return {"ok": bool(res.get("ok")), "count": 1 if res.get("ok") else 0,
            "detail": f"client report: {res.get('path','')} (send=False)"}


async def _exec_http_request(inputs: dict) -> dict:
    # Allowlisted, admin-only, GET/POST, timeout-bounded, never-raise. See §4.
    from app.automation import flow_http
    return await flow_http.run(inputs or {})
```

Then extend the registry (additive — existing 9 untouched):

```python
EXECUTORS = {
    # ... existing 9 ...
    "email_digest": _exec_email_digest,
    "telegram_draft": _exec_telegram_draft,
    "whatsapp_draft": _exec_whatsapp_draft,
    "crm_queue": _exec_crm_queue,
    "seo_blog_draft": _exec_seo_blog_draft,
    "brand_pulse": _exec_brand_pulse,
    "review_scan": _exec_review_scan,
    "client_report_draft": _exec_client_report_draft,
    "http_request": _exec_http_request,
}
```

Because the compiler whitelist (`flow_compiler.compile_flow`) reads `EXECUTORS.keys()` at compile time, **no compiler change is needed** — the new keys are automatically allowlisted. `execute_step`/`check_gate`/`get_process` unchanged.

## 4. HTTP Request node — design + allowlist

NEW module `app/automation/flow_http.py` — a self-contained, never-raise async runner. Mirrors the **verified** SSRF guard in `app/marketing/website_auditor.py` (`_resolve_is_public`) and uses the project's existing `httpx` async client (no new dep).

### 4.1 Contract

```python
# app/automation/flow_http.py
"""Allowlisted HTTP node for Flow Runner Phase 5.
Admin-only (enforced at API layer), GET/POST only, host-allowlist (env),
timeout-bounded, SSRF-guarded (no private IPs), NEVER raises, NO secrets.
"""
from __future__ import annotations
import ipaddress, os, re, socket
from urllib.parse import urlparse

_ALLOWLIST_ENV = "FLOW_HTTP_ALLOWLIST"   # comma/space/newline-separated host suffixes
_TIMEOUT_S = 8.0
_MAX_BODY = 200_000                       # response truncation cap (chars)

def _allowlist() -> list[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    return [h.strip().lower().lstrip(".") for h in re.split(r"[,\s]+", raw or "") if h.strip()]

def _host_allowed(host: str, allow: list[str]) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h or not allow:
        return False
    return any(h == a or h.endswith("." + a) for a in allow)

def _is_public(host: str) -> bool:
    # copied idiom from website_auditor._resolve_is_public — blocks loopback/private/link-local
    low = (host or "").strip().lower().rstrip(".")
    if not low or low == "localhost" or low.endswith((".local", ".internal")):
        return False
    try:
        infos = socket.getaddrinfo(low, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        ip = str(info[4][0]).split("%")[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True

async def run(inputs: dict) -> dict:
    """inputs: {url, method?('GET'|'POST'), json?(dict), headers?(SAFE static only)}.
    Returns {ok, count, detail} (Phase-1 executor contract)."""
    import asyncio
    try:
        url = str(inputs.get("url", "")).strip()
        method = str(inputs.get("method", "GET")).strip().upper()
        if method not in ("GET", "POST"):
            return {"ok": False, "count": 0, "detail": f"method {method} not allowed (GET/POST only)"}
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return {"ok": False, "count": 0, "detail": "url must be http(s) with a host"}
        allow = _allowlist()
        if not _host_allowed(p.hostname, allow):
            return {"ok": False, "count": 0, "detail": f"host '{p.hostname}' not in FLOW_HTTP_ALLOWLIST"}
        # SSRF: resolve in a thread, block private IPs (re-check after allowlist — defense in depth)
        if not await asyncio.to_thread(_is_public, p.hostname):
            return {"ok": False, "count": 0, "detail": f"host '{p.hostname}' resolves to a private/blocked IP"}
        import httpx
        # headers: ONLY a static dict of str:str from inputs; NO env/secret interpolation in V5.
        raw_hdrs = inputs.get("headers") if isinstance(inputs.get("headers"), dict) else {}
        headers = {str(k): str(v) for k, v in list(raw_hdrs.items())[:10]}
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=False) as cx:
            if method == "GET":
                r = await cx.get(url, headers=headers)
            else:
                body = inputs.get("json") if isinstance(inputs.get("json"), (dict, list)) else None
                r = await cx.post(url, headers=headers, json=body)
        text = (r.text or "")[:_MAX_BODY]
        ok = 200 <= r.status_code < 400
        return {"ok": ok, "count": 1 if ok else 0,
                "detail": f"{method} {p.hostname} -> {r.status_code} ({len(text)}b)"}
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"http err: {str(e)[:120]}"}
```

### 4.2 Allowlist mechanism (the whole point)

- **Env-config:** `FLOW_HTTP_ALLOWLIST` = comma/space/newline-separated host **suffixes** (e.g. `leadsgenai.in, ntfy.leadsgenai.in, hooks.zapier.com`). Parsed with the project's canonical `re.split(r"[,\s]+", ...)` idiom.
- **Match rule:** request host must `==` an entry or end with `"." + entry` (suffix match — so `ntfy.leadsgenai.in` is covered by `leadsgenai.in`). **Empty allowlist (default) = every host denied** → the node is inert until an admin deliberately populates the env list on the VPS.
- **Two-layer fence:** (1) allowlist membership, then (2) DNS-resolve + private-IP block (SSRF guard, mirrored from `website_auditor`). A host can be on the allowlist *and still* be rejected if it resolves to a private IP (defense-in-depth against DNS-rebind / `partner.example.com → 127.0.0.1`).
- **No redirects** (`follow_redirects=False`) — an allowlisted host can't 302 you to a non-allowlisted/private target.
- **GET/POST only**, **8s timeout**, **200KB response cap**, **never-raise**.

### 4.3 Why it can't bypass TRAI / DLT / DND / WhatsApp gates

- **Provider hosts are never on the allowlist.** The allowlist is operator-curated on the VPS `.env`. Telephony (Vobiz/Twilio), WhatsApp Cloud API (`graph.facebook.com`), SMTP/email-API hosts, Telegram (`api.telegram.org`) — none belong on it, and the ops runbook explicitly forbids adding them. The node is for *neutral* targets (own status webhook, ntfy push, allowlisted partner data APIs).
- **No secret interpolation (V5):** headers/body are static strings from the builder; there is **no** mechanism to inject `${VOBIZ_AUTH_TOKEN}` or any env secret. So even if a provider host were mistakenly allowlisted, the node could not authenticate to it.
- **All compliance gates live inside the engines, not the runner.** DND fail-closed, AI-disclosure, 10am-7pm window, DLT, WhatsApp template-approval/ban-safe-default — these are enforced in `telephony/`, `whatsapp_campaign.py`, etc. The HTTP node never calls those engines and never touches the dialer/messaging code paths. There is **no flow-runner path** that reaches a send without going through a gated engine executor (which itself defaults to draft).
- **Admin-only + flag-gated** (`FLOW_RUNNER`) — same envelope as Phase 1. The HTTP node additionally needs `FLOW_HTTP_ALLOWLIST` populated to do anything at all.

## 5. Builder palette changes (`NODE_TEMPLATES`)

Append to the `NODE_TEMPLATES` array in `frontend/explorer.html` (after the existing `revenue_sweep` item, before the `APPROVE` breakpoint item). Each carries an `action` mapping 1:1 to an `EXECUTORS` key. Two items (`telegram_draft`, `crm_queue`) get a visible `warn:'breakpoint'` hint so the admin is nudged to place an Approval node before them.

```javascript
  {type:'platform', badge:'DIGEST',   title:'Revenue Digest',   desc:'Compose admin ops digest (draft)', action:'email_digest', files:'revenue_digest.py', color:'#60a5fa'},
  {type:'external', badge:'TELEGRAM', title:'Telegram Publish',  desc:'Auto-post draft (publish-capable — add Approval!)', action:'telegram_draft', files:'telegram_publish.py', color:'#4ade80', warn:'breakpoint'},
  {type:'external', badge:'WHATSAPP', title:'WhatsApp Draft',    desc:'wa.me links (ban-safe default)', action:'whatsapp_draft', files:'whatsapp_campaign.py', color:'#4ade80'},
  {type:'data',     badge:'CRM',      title:'CRM Queue',         desc:'Push to Zoho/HubSpot (gated — add Approval!)', action:'crm_queue', files:'crm_sync.py', color:'#22d3ee', warn:'breakpoint'},
  {type:'marketing',badge:'BLOG',     title:'SEO Blog Draft',    desc:'Generate article (no publish)', action:'seo_blog_draft', files:'seo_blog.py', color:'#3b82f6'},
  {type:'monitor',  badge:'PULSE',    title:'Brand Pulse',       desc:'Mentions scan + reply drafts', action:'brand_pulse', files:'brand_pulse.py', color:'#fbbf24'},
  {type:'monitor',  badge:'REVIEWS',  title:'Review Scan',       desc:'Reviews → reply drafts', action:'review_scan', files:'review_monitor.py', color:'#fbbf24'},
  {type:'marketing',badge:'REPORT',   title:'Client Report',     desc:'Build report HTML (send=False)', action:'client_report_draft', files:'client_report.py', color:'#3b82f6'},
  {type:'external', badge:'HTTP',     title:'HTTP Request',      desc:'Allowlisted GET/POST (admin)', action:'http_request', files:'flow_http.py', color:'#4ade80'},
```

Optional builder UX (cheap, additive): when an admin drops a `warn:'breakpoint'` node, show a one-line toast ("Tip: place a Human Approval node before this publish/CRM step"). No hard enforcement in V5 (kept simple) — the compiler hint in §6 is the safety net.

## 6. Safety & compliance

- **Flag-gated** `FLOW_RUNNER=1` (default OFF → flows non-runnable, all routes 503) — unchanged from Phase 1. HTTP node additionally inert until `FLOW_HTTP_ALLOWLIST` is set.
- **Admin-only** (`require_admin` on all flow routes — inherited from Phase 1, no new routes added).
- **Whitelist-only executors** — the compiler already rejects any action not in `EXECUTORS`. New keys are additive; no arbitrary code.
- **Draft-safe or breakpoint-gated (the #1 rule):** per the §3 table — 5 outright draft-safe, 2 wrapped-to-draft-only (`email_digest` admin-only, `client_report_draft` `send=False` hard-coded), 2 side-effect-capable (`telegram_draft`, `crm_queue`) that are **palette-flagged** and **spec-required** to sit downstream of a breakpoint.
- **Compiler safety hint (small, additive):** define `SIDE_EFFECT_ACTIONS = {"telegram_draft", "crm_queue"}` in `flow_compiler`. In `compile_flow`, if any node uses a side-effect action **and** no `breakpoint` node precedes it in topological order, append a **non-fatal warning** to the returned errors-companion list (or, behind `FLOW_AUTO_BREAKPOINT=1`, auto-insert a breakpoint before it). V5 default = warn-only (keeps compiler deterministic + simple); the auto-insert switch is the hardening lever. This is the server-side safety net independent of the UI toast.
- **Never-raise everywhere** — every `_exec_*` wraps its engine call in try/except; `flow_http.run` is fully guarded. Import-safe (all imports inside functions).
- **No new deps, container, or DB** — reuses `httpx` (already in lockfile), `./data` jsonl, existing Celery `process_tick`, existing `growth_process.py` routes.
- **Compliance stays server-side:** TRAI/DLT/DND/AI-disclosure/WhatsApp-ban-safe defaults live in the engines. The runner only ever calls **draft/gated** entrypoints. The HTTP node cannot reach provider hosts (§4.3).

## 7. Testing plan

- `tests/test_flow_executors_phase5.py` — for each of the 8 new `_exec_*`: monkeypatch the wrapped engine fn to a fake async returning a known dict; assert the executor returns `{ok,count,detail}` with correct mapping; assert it **never raises** when the engine raises (patch to raise → expect `ok:False`). Specifically assert: `client_report_draft` calls `build_report` with `send=False`; `crm_queue` does **not** call `push_lead` when `CRM_SYNC` unset (monkeypatch env); `whatsapp_draft` returns link-count when `WHATSAPP_AUTO_SEND` unset.
- `tests/test_flow_http.py` — unit (no network): `_host_allowed` suffix logic (allow `leadsgenai.in` → `ntfy.leadsgenai.in` passes, `evil.com` fails, empty allowlist → all fail); `_is_public` blocks `127.0.0.1`/`10.x`/`localhost`/`*.internal`; `run()` rejects non-GET/POST, rejects non-http scheme, rejects host not on allowlist (returns `ok:False`, never raises); monkeypatch `httpx.AsyncClient` to assert GET/POST dispatch + truncation cap. Assert provider hosts (`api.telegram.org`, `graph.facebook.com`) are rejected with an empty/realistic allowlist.
- `tests/test_flow_compiler_phase5.py` — extend existing compiler tests: a flow using the new keys compiles (whitelist auto-includes them); side-effect-action-without-upstream-breakpoint produces the warning (warn-only mode); `FLOW_AUTO_BREAKPOINT=1` auto-inserts a breakpoint.
- Regression: `scripts/explorer_sync.py --check` green (new palette actions resolve to executors; `flow_http.py` added to the flow_runner node's `files`); `.venv\Scripts\python.exe scripts/prod_check.py` ALL PASSED; targeted `scripts\run_tests.bat` on the three new suites (read `pytest_run.log`).
- Import-safety smoke: `.venv\Scripts\python.exe -c "import app.agents.process_library, app.automation.flow_http"` → no error with all flags unset.

## 8. Rollout

1. Ship code with `FLOW_RUNNER` **OFF** and `FLOW_HTTP_ALLOWLIST` **unset** → deploy (recreate app **+ worker** — executors run in worker via `process_tick`).
2. Set `FLOW_RUNNER=1` (already on if Phase 1 enabled). New executors immediately available in palette.
3. HTTP node: set `FLOW_HTTP_ALLOWLIST=leadsgenai.in,ntfy.leadsgenai.in` (own infra only to start) → recreate app + worker.
4. Smoke: build a draft-only flow (`brand_pulse` → `seo_blog_draft` → breakpoint → `telegram_draft`) → Run → confirm pause at breakpoint, drafts produced, no auto-publish until approved + flag.
5. Smoke HTTP: 1-node `http_request` flow with `inputs.url = https://leadsgenai.in/health` → confirm `200`. Then a non-allowlisted URL → confirm `ok:False, "not in FLOW_HTTP_ALLOWLIST"`.
**Rollback:** remove the new keys from `EXECUTORS` (palette items become un-compilable → clear error) **or** simply unset `FLOW_RUNNER`. HTTP node: unset `FLOW_HTTP_ALLOWLIST` → node inert. No other surface touched.

## 9. File touch-list

**New:**
- `app/automation/flow_http.py` — allowlisted HTTP runner (§4).
- `tests/test_flow_executors_phase5.py` · `tests/test_flow_http.py` · `tests/test_flow_compiler_phase5.py`

**Edit (additive only):**
- `app/agents/process_library.py` — 9 new `_exec_*` functions + 9 new `EXECUTORS` entries (§3.1). No change to `execute_step`/`check_gate`/`get_process`.
- `app/automation/flow_compiler.py` — `SIDE_EFFECT_ACTIONS` set + warn-only breakpoint hint (+ optional `FLOW_AUTO_BREAKPOINT` auto-insert) (§6). Whitelist needs no change (reads `EXECUTORS.keys()`).
- `frontend/explorer.html` — 9 new `NODE_TEMPLATES` entries (§5) + optional `warn:'breakpoint'` toast; update the `flow_runner` explorer node `files:` to include `flow_http.py`.
- `app/api/growth.py` — add `"FLOW_HTTP_ALLOWLIST"`-presence note (optional; `FLOW_RUNNER` already registered in Phase 1). No new flag *gate* needed beyond the env allowlist.

**No new:** router/endpoint (run/approve/status reused via `growth_process.py` + key `flow:<id>`), worker job (`process_tick` reused), container, DB, or dependency (`httpx` already present).

## 10. Seams left for later phases (noted, NOT built)

- **Data-passing (Phase 4):** `http_request`, `crm_queue`, `whatsapp_draft`, `client_report_draft` read their target (`url`/`leads`/`items`/`client_id`) from the **run-level `inputs`** today. When Phase 4 lands node-output→input mapping, these become the natural first consumers (e.g. `scrape` output → `crm_queue.leads`). No engine change needed — `inputs` is already the carrier.
- **Branching (Phase 2):** the `SIDE_EFFECT_ACTIONS` warn-hint generalizes into per-branch gate enforcement later.
- **Triggers (Phase 3):** `email_digest`/`review_scan`/`brand_pulse` are obvious cron-trigger candidates (they already run on the daily scheduler standalone).
- **HTTP node V6+:** auth/secret-interpolation (allowlisted secret names only), response→`inputs` mapping, methods beyond GET/POST — all explicitly deferred.

## 11. Open questions

1. **`telegram_draft` / `crm_queue` enforcement:** V5 = palette flag + compiler **warn**. Should `FLOW_AUTO_BREAKPOINT` default to **ON** (auto-insert breakpoint before side-effect nodes) for extra safety, accepting the slightly less-deterministic compile? (Spec recommends: ship warn-only default, ON via flag.)
2. **`email_digest` scope:** `revenue_digest.run()` mails the **admin** ops digest (not customers) — acceptable as "draft-safe"? (Spec treats yes, since no customer surface; alternative = add a `compose_only` path to `revenue_digest` that never sends.)
3. **HTTP allowlist granularity:** host-suffix only in V5. Do we ever need path-prefix allowlisting (`hooks.zapier.com/abc/*`)? (Deferred — host-suffix covers the near-term use cases.)
4. **`whatsapp_draft` items source:** until Phase 4 data-passing, `items` comes from run-level `inputs`. Is a standalone "build wa items from leads" pre-step worth a 9th-ish executor, or wait for Phase 4? (Spec: wait for Phase 4.)
