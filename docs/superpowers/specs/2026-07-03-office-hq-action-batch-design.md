# Office HQ Action Batch — Design (2026-07-03)

> Brainstorm source: 13-agent workflow (3 code-inventory + 4 web deep-research + 5 ideation
> lenses + synthesis chairman), 60 raw ideas → 22 survivors. User ne Tier-1 recommended batch
> approve kiya ("ok karo"). Yeh spec us pehle batch ke 4 functions ka design hai.

**Goal:** `/app/office` (Operating HQ) ko passive viewer se **actionable HQ** banana — admin
map se hi kaam DISPATCH kare, failures REPAIR kare, revenue-queue WORK kare, aur din ki
briefing SUNE. Sab existing engines pe grounded — koi fabricated data nahi, koi auto-send nahi.

**Files touched:** `frontend/office_map.html` (sab 4 features — isliye implementation
SEQUENTIAL, parallel same-file edit forbidden), `app/platform/office_hq.py` +
`app/api/office_hq.py` (F3/F4 thin endpoints), `app/platform/office_briefing.py` (naya, F4),
tests under `tests/`.

**Conventions (har feature pe lagoo):**
- Backend never-raise (office_hq.py ka har fn try/except + safe default), sab naye endpoints
  `Depends(require_admin)`, naya route add karne se pehle duplicate-route grep.
- Frontend: `OFFICE.*` namespace, `esc()` for any injected text, `hdrs()` for auth, panel-box
  card pattern; canvas ≤760px hidden hai → HAR feature ka DOM entry point bhi (panel/card),
  sprite sirf desktop flourish.
- Confirm-before-mutate on destructive actions. Koi auto-send nahi. ₹ figures "potential
  (estimate)" labelled.
- Evidence gate: targeted pytest green + `scripts/prod_check.py` PASS + import-check; deploy
  alag explicit-auth step.

---

## F1 — DLQ Repair Desk (effort S)

**Kya:** Platform-engineering room me Hermes ke desk pe crumpled-paper pile sprite = live DLQ
depth (0 = saaf desk). Click (ya Reliability section ka naya "DLQ Repair" card) → drawer:
failed tasks list (job, error, kab) + per-item **Retry** / **Discard** + **Retry all** —
sab confirm-before-mutate.

**Data/API (existing, koi naya backend nahi):** `GET/POST/DELETE /api/growth/infra/dlq*`
(app/api/growth.py:952-1029, `app/platform/dlq_retry.py`). Implementer pehle exact
routes/response-shape ko code se confirm kare (guess nahi).

**Error handling:** fetch fail → card me "DLQ status load nahi hua" + retry; empty DLQ →
sprite hidden + card me "🎉 Koi failed task nahi".

## F2 — Reception Hot-Tray (effort S)

**Kya:** Coordinator room ke front-desk pe tray sprite + badge: Hot Queue count + "potential
₹X (estimate)" (count × Main plan monthly price). Click (ya naya panel card near approvals) →
drawer: har reply (from, snippet, AI draft), buttons **Draft copy karo** (clipboard) + **Ho
gaya** (mark-handled) + deep-link **/app/inbox** pe. Koi auto-send NAHI.

**Data/API (existing):** `GET /api/growth/reply/hot-queue` + mark-handled POST
(reply_agent.py `hot_queue()`/`mark_handled()` — exact route code se confirm karna). ₹ =
`get_public_packages()` ka `starter` price — frontend public packages endpoint se le (hardcode
nahi; billing-truth rule).

## F3 — Kaam Do: map se task dispatch (effort M)

**Kya:** Agent drawer me naya "🎯 Kaam do" section: Hinglish goal textarea + scope choice
**"Sirf yeh agent"** / **"Team lagao (coordinator)"** + Run. Golden token boss→agent (existing
`spawnWorkflowToken` reuse). Result drawer me (truncated) + note "pura result ticker/events me
aayega".

**Backend:** thin naya endpoint `POST /api/platform/office/agents/{member}/task`
(require_admin, body `{goal, scope}`):
- scope=solo → existing team run path (`/api/platform/team/run/{member}` jo mechanism use
  karta hai wahi reuse; agar wo goal accept nahi karta to coordinator single-agent mode).
- scope=team → `coordinator.coordinate()/fanout()` DRAFT-SAFE mode, bounded (k chhota,
  timeout) — EXACTLY jaise `POST /api/agents/council` live endpoint web process me bounded run
  karta hai (precedent). Web process me unbounded heavy job NAHI.
- Response: `{ok, run_id/summary}`; failure → `{ok:False, error}` (never-raise).
- Frontend timeout handling: >60s pe "background me chal raha hai, events dekho" message.

**Tests:** endpoint admin-gate + draft-safe default + coordinator mocked (happy + failure
path).

## F4 — Subah ki Briefing: EdgeTTS bulletin (effort M)

**Kya:** Topbar button "📻 Briefing" → modal: aaj/raat ka 6-8 line Hinglish bulletin (text) +
▶ audio (Swara — EdgeTTS `hi-IN-SwaraNeural`, existing voice stack ka TTS helper reuse).

**Backend:** naya module `app/platform/office_briefing.py`:
- `build_briefing(force=False) -> {ok, date, text, audio_path}` — collects REAL numbers:
  automation_health.health() (overdue/failed jobs), DLQ depth, hot-queue count, aaj ke
  agent_events counts (top actives), naye leads/qualified (office_hq ke existing metric
  helpers reuse) → `free_ai.chat` se bulletin compose (1 call) → EdgeTTS mp3.
- **Cache:** `data/office_briefing/{IST-date}.json` + `.mp3` — din me ek hi LLM/TTS call;
  `force=1` regenerate.
- **Degrade ladder (never-raise):** LLM fail → template bulletin (raw numbers, no LLM); TTS
  fail → text-only (`audio: null`); sab fail → `{ok:False}`.
- Endpoints: `GET /api/platform/office/briefing?force=` → JSON; `GET
  /api/platform/office/briefing/audio` → mp3 FileResponse. Dono require_admin.
- Frontend audio: `<audio>` tag Authorization header nahi bhej sakta → fetch blob with
  `hdrs()` → objectURL.

**Tests:** compose with mocked free_ai + mocked TTS (cache write, force-regen, LLM-fail
template fallback with real numbers, never-raise).

---

## Rollback
Sab additive: frontend cards/sprites CSS-hidden ya revert-commit; naye endpoints unused rehne
pe inert; F4 module import-safe (edge-tts already prod dep). Koi flag zaroori nahi (admin-only
read/action surfaces, existing engines) — par F3 dispatch + F4 briefing dono apne endpoint ke
andar graceful-fail hain.

## Verification plan
1. Har feature ke changed-file targeted pytest green (Windows `.venv\Scripts\python.exe`).
2. `scripts/prod_check.py` PASS + app import-check.
3. `git diff` pe code-reviewer pass (bug/security/signature-drift lens).
4. Browser preview best-effort local; final visual verify deploy ke waqt live pe.
5. Deploy = alag explicit-auth step (surgical docker cp pattern; batch-2 38cf0a8 bhi pending).
