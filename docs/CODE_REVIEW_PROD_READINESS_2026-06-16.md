# Code Review — Production Readiness (2026-06-16)

> **STATUS: FIXES APPLIED & VERIFIED (2026-06-16).** Saare 4 Critical + 7 High + key Mediums fix ho gaye, 87 targeted tests green + import/compile/functional checks pass. Detail niche **"Fixes Applied"** section me. Kuch perf/voice items deferred (reasons listed).


**Scope:** Repo `main` clean tha (koi uncommitted diff nahi), isliye review production-readiness lens se critical paths pe focused hai — billing/payments, public request-path, telephony/webhooks, aur recently-changed code + voice streams. Focus: Correctness, Performance, Maintainability, Security.

**Method:** 4 parallel review-agents ne deep-read kiya, phir top/critical findings main ne khud **Windows source (Read tool)** se verify kiye — kyunki Linux sandbox mount stale tha (ek agent ne `free_ai.py` truncated dekha; CLAUDE.md bhi yahi warn karta). Line numbers Windows source ke hain.

**Confidence column:** `✓` = main ne source me khud confirm kiya · `○` = agent-reported, code-pattern se consistent (line number thoda drift ho sakta — fix karne se pehle ek nazar daal lena).

---

## Verdict: NOT prod-ready for the first paying customer

4 **launch-blocker (Critical)** + ~7 **High** issues hain. Inme se zyadatar choti, contained fixes hain (ek focused PR me nikal jaayenge). Architecture/design strong hai — problem mostly **edges** pe hai: auth missing, fail-open jahan fail-closed chahiye, aur ek live webhook route jo no-op stub se shadowed hai.

| Severity | Count | Sabse bada risk |
|---|---|---|
| 🔴 Critical | 4 | Cross-tenant IDOR, forged webhooks, dead Exotel billing/opt-out, SSRF |
| 🟠 High | 7 | Double-credit, false opt-out, client-driven payment state, worker-starvation |
| 🟡 Medium | ~10 | Hot-path full-file scans, GST race, fail-open consent writes |
| ⚪ Low | ~8 | Money truncation, off-by-one quota, bare-except leaks |

---

## 🔴 Critical — launch blockers (verified)

| # | File:Line | Issue | Prod risk | Conf. |
|---|---|---|---|---|
| C1 | `app/api/billing.py:362,440,487,…` (router mounted `main.py:276`, no `dependencies=`) | Har billing mutation sirf ek **query param** pe gated: `client_id: str = Query(...)` — koi auth/session/ownership check nahi. checkout, verify-payment, cancel, upgrade, balance, sab. | Koi bhi unauthenticated caller kisi bhi `client_id` ka plan cancel/upgrade kar sakta, balance credit kar sakta, ya fake payment record bana sakta — **poore tenant-base pe IDOR**. | ✓ |
| C2 | `app/api/webhooks.py:68-72` (Twilio), `109-113` (Exotel) + `app/integrations/whatsapp.py` verify | Signature verify **fail-OPEN** jab env secret unset: `if not auth_token: … return True`. Is box pe env unset hona proven hai (Razorpay placeholder keys). | Agar `TWILIO_AUTH_TOKEN`/`EXOTEL_*`/`WHATSAPP_APP_SECRET` live box pe set nahi → har telephony/WhatsApp webhook **unauthenticated**. Forged callbacks se call-state drive, opt-out suppression DoS, billing side-effects. | ✓ |
| C3 | `app/api/webhooks.py:215-225` stub **shadows** `app/telephony/webhooks.py:192-232` (mount order `main.py:265` se pehle `271`) | Live `/api/webhooks/exotel/status` ek **no-op stub** hai (`return {"status":"received"}`). Rich handler (AMD + `handle_call_completed` + minute-metering + `record_qualified_lead` + opt-out-on-outcome) dead hai. Code-comment khud admit karta: *"yeh route effectively shadowed hai"*. | Exotel calls ke liye completion, **minute metering, qualified-lead billing, aur post-call opt-out kabhi fire nahi hote** → revenue leak + compliance gap. (Confirm: metering ka koi alternate path stream-session me to nahi.) | ✓ |
| C4 | `app/marketing/website_auditor.py:56-71` (public `/site-audit`, `/api/growth/tools/website-audit`) | **SSRF**: user-supplied URL bina kisi host/IP validation ke fetch hoti hai — `httpx.AsyncClient(follow_redirects=True).get(u, timeout=12)`. Response body JSON me reflect hoti. | Attacker `http://169.254.169.254/...` (cloud metadata), `127.0.0.1:6333` (Qdrant), `leadgen_db:5432`, `redis:6379` hit kar sakta. `follow_redirects=True` se public→internal redirect bhi. Internal-service probing/exfil. | ✓ |

**C1 fix:** billing router pe ek auth dependency lagao (customer session/JWT se `client_id` derive karo, query param se nahi). Server-side ownership check har mutation pe.
**C2 fix:** production me fail-**CLOSED** — `if ENV=="production" and not secret: raise HTTPException(503)`. Skip sirf dev me. WhatsApp ke `except: pass` ko hatao (verify error = reject).
**C3 fix:** `app/api/webhooks.py` ke stub Exotel/Twilio handlers delete karo (ya delegate karo), ek hi implementation rakho; route-map se verify karo. Razorpay/Stripe webhooks ka idempotent pattern yahan copy karo.
**C4 fix:** fetch se pehle URL parse → non-http(s) reject; hostname resolve karke private/loopback/link-local/reserved ranges (`ipaddress` `.is_private/.is_loopback/.is_link_local/.is_reserved`) + docker-hostnames reject; redirects disable ya har hop re-validate; ports 80/443 pin; response-size cap (800k already hai).

---

## 🟠 High

| # | File:Line | Issue | Prod risk | Conf. |
|---|---|---|---|---|
| H1 | `app/api/billing.py:458-468` | `verify-payment` signature ke baad **₹0 COMPLETED** `Payment` row banata hai (`amount=Decimal("0")`, `status=COMPLETED`) frontend call se. Signature sirf order↔payment ID link prove karta — capture/amount nahi. | Client-driven payment state. C1 (no-auth) ke saath: koi bhi `client_id` ke liye COMPLETED ₹0 rows spam kar sakta; agar koi provisioning "COMPLETED payment exists" pe key karta hai → free service. | ✓ |
| H2 | `app/telephony/webhooks.py:251-259` (`/exotel/voice`, press-9) | Inbound press-9 opt-out user ko bolta *"aapka number hata diya gaya"* par **`record_opt_out()` call hi nahi** — persist kuch nahi hota. | TCCCPR false-opt-out handling — number dobara callable. ₹10L-class exposure. (Route reachability IVR-wiring pe depend karti — verify.) | ✓ |
| H3 | `app/platform/reply_agent.py:368-373` vs `app/integrations/email_sender.py:60-68` | `REPLY_AUTO_SEND` path `send_email(to_email=…, body_text=…, body_html=…)` call karta — par real signature `send_email(to_emails: list, subject, body, html_body=…)` hai. **Galat kwargs → TypeError har baar**, `except` me INFO pe swallow, `auto_sent` kabhi nahi badhta. | Flag `REPLY_AUTO_SEND=1` karte hi "Smartlead-style auto-reply" feature **100% silently dead**. 1-click draft chalta rehta hai isliye flag-flip tak pata nahi chalega. (Abhi flag OFF — live blocker nahi, par footgun.) | ✓ |
| H4 | `app/api/webhooks.py` Razorpay legacy handler (`order.paid` + balance top-up) | Legacy handler me **idempotency guard nahi** (sirf newer `/billing/webhooks/razorpay` me `idempotency.seen_before`). `order.paid` credit bina dedup ke. | Razorpay at-least-once delivery → retried event pe **account balance double-credit**. Do diverging handlers = galat URL configure hone ka risk. | ○ |
| H5 | `app/api/webhooks.py:62-72,77-84` (Twilio) | Hand-rolled Twilio signature `url = str(request.url)` use karta — Caddy reverse-proxy (`127.0.0.1:8000`) ke peeche yeh internal URL deta, Twilio ne public https URL sign kiya tha. | Saare genuine Twilio webhooks **401** (self-DoS), ya fail-open (C2) pe sab pass. Dono galat. Standard `RequestValidator` use karo public base-URL ke saath. | ✓ |
| H6 | `app/api/public_site.py` `/ai-demo` → `niche_pack.build_pack` (+ `free_ai.chat` chain) | Public unauth `/ai-demo` me **4 sequential LLM round-trips**; `chat()` ~13-provider chain me per-call 8s timeout par **koi overall deadline nahi**. `WEB_CONCURRENCY=2`. | Provider degradation pe ek request worker ko 30s+ hold karti → kuch demo hits saare HTTP workers starve. Yeh wahi outage-class hai jo pehle 3 baar hua. | ○ |
| H7 | `app/billing/gst_invoice.py` `next_number` → `create_invoice` | Invoice number = `count(rows)+1`, read aur append ke beech **lock nahi**. Celery worker concurrency=4 / do webhook deliveries same `n` compute karte. | **Duplicate Rule-46 invoice numbers** (`INV/2026-27/0001` do baar) — GST compliance violation + audit fail. | ○ |

**H1 fix:** verify-payment ko entitlement ka source-of-truth mat banao; amount ko gateway se fetch/verify karo, ya provisioning sirf idempotent webhook pe karo.
**H3 fix:** `await sender.send_email([frm], re_subj, draft, html_body=f"<p>{draft.replace(chr(10),'<br>')}</p>")` — positional list + `html_body=`. (`booking_reminders.py:122` already sahi call karta — reference.)
**H4/H7 fix:** ek hi idempotent webhook handler; invoice numbering pe read+append lock (ya DB sequence).
**H6 fix:** poore demo build pe ek `asyncio.wait_for(...,~15s)` hard deadline; per-theme calls `asyncio.gather` se concurrent; deadline pe static fallback pack.

---

## 🟡 Medium (condensed)

- **Consent-ledger fail-open writes** — `app/telephony/consent_ledger.py` `_append`/`record_opt_out` disk-write error swallow karke `{"suppressed": True}` return karta. Disk-full/stale-mount pe opt-out "successful" report par persist nahi → illegal. `○`
- **Hot-path full-file scans** — `lead_usage.py` har quota-check pe poori `lead_usage.jsonl` parse karta; `consent_ledger.is_suppressed()` per-call poori jsonl read (async loop pe blocking I/O); `gst_invoice.next_number()` poori file count. Ledger badhne pe latency linear. In-memory set + mtime-refresh, ya `to_thread`. `○`
- **GST 0.18 unconditional** — `app/billing/subscription.py` `BillingManager.generate_invoice` `tax_rate=0.18` always lagata, `GST_GSTIN` gate ignore karta (jabki sibling `calculate_price` sahi honor karta). Unregistered pe illegal 18% charge. `○`
- **Webhook 200-on-error** — `app/telephony/webhooks.py:185-186,230-232` exception pe **HTTP 200** + error body return karta → provider retry nahi karega, transient failure pe metering/suppression permanently lost. 5xx return karo. `○`
- **Worker-local call completion** — `call_manager.py` `active_calls` in-process dict; status-webhook dusre worker pe land hua to `No context found` → completion/metering skip. Redis registry me minimal completion-inputs persist karo. `○`
- **Sync DB in async public handler** — `public_site.py` `_save_lead_db`/`list_inquiries` event loop pe sync SQLAlchemy commit, no statement timeout. `to_thread` + `statement_timeout`. `○`
- **`ai-image-proxy` 90-120s timeout** — public unauth, cache-miss burst pe worker exhaustion. ~15-20s + concurrency semaphore. `○`
- **Voice: Exotel sub-3.2KB tail frame** — `exotel_stream.py:172-199` PCM sirf 320B-multiple tak pad hota, final chunk Exotel ke 3.2KB min se chhota → reply ka aakhri word cut. Pure `chunk_size` tak pad karo. `○`
- **Voice: filler/barge-in `_interrupt` clobber** — `phone_stream.py:783-821` filler `_send_audio` `_interrupt=False` unconditionally clear karta → think-window me hua barge-in lost, real reply caller pe over-play. `○`
- **`prospector.py:651` blocking** — async run me `time.sleep(1)` + `urllib...urlopen(timeout=25)` event loop pe. `await asyncio.sleep` + `to_thread`/httpx. (Sirf Celery pe chale, web loop pe kabhi nahi.) `○`

---

## ⚪ Low (note kiye, blocker nahi)

Money truncation `int(amount*100)` (Decimal `quantize`/round policy nahi, paise undercharge) · quota off-by-one (`used > limit` strict, limit-th unit hamesha allowed) · bare `except → HTTPException(500, str(e))` raw gateway error client ko leak karta · `X-Forwarded-For` first-hop trust (direct hit pe rate-limit spoof bypass) · `/sitemap.xml` uncached full-scan per hit · `reply_agent.py:21,24` duplicate `import json` · deprecated `asyncio.get_event_loop()` voice paths me · filler-synth module-global do sessions me double-populate.

---

## What looks good

- **Pre-dial ComplianceGate genuinely fail-CLOSED** — unverified DND → `dnd_lookup_failed` promotional block; DLT/140/10am-7pm window enforce; AI-disclosure greeting unconditional (`agent.py:169,178`). Core outbound design solid hai.
- **Payment signature verify (jahan present hai) sahi** — Razorpay HMAC-SHA256 + `hmac.compare_digest` (constant-time) **parse se pehle**; Stripe `construct_event`. `idempotency.py` khud bhi achha (atomic Redis `SET NX EX`, 14-din TTL). Problem sirf legacy handler me wire nahi (H4).
- **`mini_site.py` exemplary public renderer** — pure stdlib, har interpolation `_e()` HTML-escape se, color CSS-injection blocked, zero await, absolute fallback (kabhi 500 nahi). Path-traversal bhi `ai-img-file` pe `re.fullmatch` se band.
- **Public inquiry flow resilient** — jsonl-first "never-lose" persistence, honeypot, saare side-effects fire-and-forget strong task-refs ke saath.
- **Voice graceful-degradation consistent** — STT/TTS/brain lazy-import + wrapped fallback, missing dep/quota kabhi socket crash nahi karta. Fire-and-forget tasks `set` + `add_done_callback` se GC-safe.

---

## Suggested fix order (ek focused PR)

1. **C1** billing router auth (sabse bada blast-radius).
2. **C3** Exotel webhook stub hatao → metering/billing/opt-out wapas zinda.
3. **C2 + H5** webhook signatures: prod me fail-closed + Twilio `RequestValidator`.
4. **C4** SSRF guard site-audit me.
5. **H1** verify-payment ₹0 COMPLETED hatao.
6. **H2** press-9 → `record_opt_out` wire.
7. **H4/H7** single idempotent webhook handler + invoice numbering lock.
8. **H3** reply_agent `send_email` kwargs fix (flag flip se pehle).
9. Medium batch (consent fail-open, full-file scans, GST gate) next sprint.

---

### Verification note

C1-C4, H1-H3, H5 main ne Windows source me **khud confirm** kiye. H4/H6/H7 aur saare Medium/Low review-agents ne flag kiye — code-pattern se consistent par line numbers Windows source pe ek baar verify karke fix karna (sandbox mount stale tha). C3 (metering dead) ke liye ek extra check: confirm karo ki Exotel minute-metering ka koi alternate path (stream-session end) to nahi — agar hai to severity High ho jaati.

---

## ✅ Fixes Applied (2026-06-16)

Sab fixes Windows source pe (source of truth) — verified: **py_compile OK (12 files)**, **import smoke OK (12 modules)**, **functional tests PASS (SSRF guard + invoice race-lock)**, **87 targeted pytest green** (billing-truth, payment-webhooks, consent-ledger, compliance, customer-portal, billing-tenant, provisioning, product-split, exotel-stream).

| ID | Fix | Files |
|---|---|---|
| C1 | Billing endpoints ab token se `client_id` derive karte (`_authed_client_id` dep) — query-param IDOR khatam. Customer token → apna id; admin token → explicit client_id. `upgrade_subscription` admin-only (free self-upgrade band). Frontend already Bearer bhejta (admin/customer dash); `pricing.html` checkout+verify ko Authorization header add kiya. | `app/api/billing.py`, `frontend/pricing.html` |
| C2 | Twilio/Exotel/WhatsApp signature verify **prod me fail-CLOSED** (secret unset → 503, dev me hi skip). WhatsApp ka blanket `except: pass` hata (verify error = reject). | `app/api/webhooks.py`, `app/integrations/whatsapp.py` |
| C3 | Shadowed Exotel `/exotel/status` stub hata → telephony ka rich handler (metering/billing/opt-out) ab live. Broken Twilio inbound stub (galat `queue_call` sig) bhi clean. | `app/api/webhooks.py` |
| C4 | SSRF guard: `audit_url` ab har redirect-hop ka host resolve karke sirf public IPs allow karta (metadata/loopback/private/link-local/reserved + docker hosts block), redirects manually capped. | `app/marketing/website_auditor.py` |
| H1 | `verify-payment` ab **PENDING** row banata (COMPLETED ₹0 nahi); webhook (idempotent) real amount bhar ke COMPLETED karta. | `app/api/billing.py`, `app/api/webhooks.py` |
| H2 | Press-9 IVR opt-out ab actually `record_opt_out()` persist karta (cross-channel suppression). | `app/telephony/webhooks.py` |
| H3 | `reply_agent` `send_email` sahi signature pe (positional list + `html_body=`) — `REPLY_AUTO_SEND` ab TypeError nahi dega. | `app/platform/reply_agent.py` |
| H4 | Razorpay webhook event-id idempotency guard — retried `order.paid`/top-up double-credit band. | `app/api/webhooks.py` |
| H5 | Twilio signature `RequestValidator` + public-base-url se (proxy ke peeche genuine webhooks ab 401 nahi). | `app/api/webhooks.py` |
| H6 | `/ai-demo` public endpoint pe hard `asyncio.wait_for(20s)` deadline → worker-starvation band. | `app/api/public_site.py` |
| H7 | GST invoice numbering atomic (`_reserve_number_and_append` flock+threading lock) — duplicate Rule-46 number band. | `app/billing/gst_invoice.py` |
| M1 | `BillingManager.generate_invoice` GST ab `GST_GSTIN`-gated (unregistered pe illegal 18% nahi). | `app/billing/subscription.py` |
| M2 | Live Exotel status handler me call_id idempotency — duplicate completion pe double-meter/bill band. | `app/telephony/webhooks.py` |
| M3 | `consent_ledger._append` ab success return karta; suppression write fail hone pe `record_opt_out` `suppressed:False` deta (fail-open misreport band) + ERROR log. | `app/telephony/consent_ledger.py` |
| L+ | Money: `int(amount*100)` → `int(round(...))` (truncation→round, 6 sites). reply_agent duplicate `import json` hata. ai-image-proxy timeouts 90/120s → 45/60s. | `app/billing/payment_gateway.py`, `app/platform/reply_agent.py`, `app/marketing/ai_image.py` |

### Deferred (reason: regression-risk / needs live testing — recommend next PR)
- **Hot-path full-file scans** (`lead_usage` quota-check, `consent_ledger.is_suppressed`): in-memory cache + mtime-invalidation chahiye + tests — perf only, abhi break nahi.
- **Worker-local `active_calls` completion** (telephony): Redis registry me completion-context carry karna — design change.
- **Voice audio-loop**: Exotel sub-3.2KB tail-frame padding + filler/barge-in `_interrupt` clobber — live audio testing chahiye.
- **Sync DB in async public handler** (`public_site._save_lead_db` → `to_thread`): jsonl-first already data-loss rokta, perf-only.
- **Low**: quota off-by-one boundary, X-Forwarded-For spoof hardening, sitemap caching, `get_event_loop` deprecation, filler-global double-populate.

### Deploy note
Saare changes additive/contained. Deploy se pehle: (1) `pricing.html` ka signup→pay flow live test karo (token ab checkout/verify pe jaata hai); (2) prod `.env` me `TWILIO_AUTH_TOKEN`/`EXOTEL_*`/`WHATSAPP_APP_SECRET`/`RAZORPAY_WEBHOOK_SECRET` set hain confirm karo — warna ab webhooks 503 denge (by design, fail-closed). Razorpay live keys wala pending blocker alag hai (CLAUDE.md).
