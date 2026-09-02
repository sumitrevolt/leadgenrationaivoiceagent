# ADR-104 Voice QA incident fix — commit / deploy / acceptance runbook

Prepared by Claude (implementation + local test session, 2026-07-15). Per your
explicit scope decision, no `git add`/`commit`/`push`/SSH/deploy was run — this
is the exact command sequence for you to run yourself. Full technical detail:
`memory/decisions.md` ADR-104 addenda #1-#8, and the "Loop Run" entry at the
top of `progress.md`.

## What was implemented (all local, all test-verified)

1. **`app/voice_agent/telecaller_brain.py`** — `_kb_facts()` fully rewritten.
   The live voice reply path no longer bootstraps/seeds the full 39-niche KB
   catalog inline. Old `_get_kb()` / `_KB_SINGLETON` / `_KB_TRIED` /
   `_KB_LOADED_AT` removed entirely (grep-confirmed unused elsewhere).
2. **`app/tasks/kb_niche_refresh.py`** (new) — owned, deduplicated Celery task
   for single-niche KB refresh. Redis lease (SET NX EX + owner-token release),
   verifies success via the same `count_niche_catalog_points` the voice path
   trusts (not just "seed said ok"). Registered in `app/worker.py`'s `include`
   list (default queue — `task_routes` untouched).
3. **`app/voice_agent/kb_loader.py`** — `load_niche_faqs` now passes
   `replace_source=True` at all 4 `add_documents()` call sites, activating the
   pre-existing delete-before-reseed dedup mechanism it was never invoking.
   This was the measured root cause of ~185x duplicate vectors in `kb_main`
   (217,169 points vs an expected ~1-2k).

Tests: `tests/test_kb_facts_adr104_v3.py` (9 tests) +
`tests/test_kb_niche_refresh_task.py` (7 tests) = **16/16 pass**, run against
the real `kb_readiness.py`/`kb_niche_refresh.py` logic with fakes only at the
Qdrant/Redis/knowledge_base boundary. This sandbox could not run the repo's
real `pytest`/`prod_check.py` (missing `sqlalchemy`, pip installs kept timing
out — sandbox networking, not a repo issue) — **please run the real suite
yourself before/after committing** (commands below).

## 1. Clean up session scratch files first (optional but recommended)

These are verification-only artifacts from this session, never meant to ship.
They are untracked, so skipping `git add` on them is enough, but deleting them
keeps the tree tidy:

```
del app\voice_agent\_synctest.py
del app\voice_agent\_verify_telecaller_brain.py
del tests\test_kb_facts_adr104.py
del tests\test_kb_facts_adr104_v2.py
```

(`test_kb_facts_adr104.py` / `_v2.py` are empty placeholder stubs — dead
drafts superseded by `test_kb_facts_adr104_v3.py`, which IS the real suite.)

## 2. Run the real test suite locally

```
.venv\Scripts\python.exe -m pytest tests/test_kb_facts_adr104_v3.py tests/test_kb_niche_refresh_task.py tests/test_kb_readiness.py tests/test_kb_loader_scoped.py tests/test_kb_point_id.py tests/test_kb_delete_before_reseed.py tests/test_celery_queue_routing.py -v
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe scripts\check_secrets.py
```

All must be green before you commit.

## 3. Surgical `git add` — exactly these paths, never `git add -A`

Your working tree has unrelated dirty files from other sessions/Cursor (per
ADR-104 addendum #7's working-tree-safety note — confirmed again this
session: `AGENTS.md`, `CLAUDE.md`, `app/api/growth_automation.py`,
`app/marketing/postiz_publish.py`, `app/platform/email_warmup.py`,
`app/platform/team.py`, `tests/test_telecaller_brain.py`, several `data/*`
jsonl files, and the whole `unity/` tree are ALL untouched by this fix — do
not add them here).

`app/voice_agent/kb_readiness.py`, `tests/test_kb_readiness.py`, and
`tests/test_kb_loader_scoped.py` show as untracked (`??`) too — they're
earlier ADR-104 phases (A4.2/A4.3) that were implemented and tested in a
prior session but never actually committed. This fix's task
(`kb_niche_refresh.py`) imports `kb_readiness.py` directly, so it MUST be
included or the deploy will break on import.

```
git add app/voice_agent/telecaller_brain.py
git add app/voice_agent/kb_loader.py
git add app/voice_agent/kb_readiness.py
git add app/worker.py
git add app/tasks/kb_niche_refresh.py
git add tests/test_kb_readiness.py
git add tests/test_kb_loader_scoped.py
git add tests/test_kb_facts_adr104_v3.py
git add tests/test_kb_niche_refresh_task.py
git add memory/decisions.md
git add progress.md
git status
```

Check the `git status` output matches exactly this list (plus whatever else
you intentionally staged) before committing.

Note: `memory/decisions.md` and `progress.md` are running ledgers other
sessions also append to (that's by design — append-only ADR pattern). If
`git status` shows them already partially staged/committed by another
session's work, that's expected; just make sure the ADR-104 addendum #8 /
"Loop Run" content from this session is present in what you commit.

## 4. Commit

```
git commit -m "fix(voice): ADR-104 — remove inline KB bootstrap from live reply path

- _kb_facts() no longer seeds the 39-niche catalog inline on cold calls
  (was the incident: unbounded asyncio.to_thread bootstrap + abandoned
  future on timeout blocked Celery executor shutdown until 600s hard kill)
- new owned, deduplicated app.tasks.kb_niche_refresh Celery task requests
  a single-niche refresh instead, verified via kb_readiness before marking ready
- load_niche_faqs now passes replace_source=True at all 4 add_documents()
  call sites, fixing ~185x duplicate vector writes in kb_main
- includes prior-session A4.2/A4.3 work (kb_readiness.py) that was
  implemented/tested but never committed

16/16 new tests pass (test_kb_facts_adr104_v3.py, test_kb_niche_refresh_task.py)
memory/decisions.md ADR-104 addendum #8 has full detail"
```

## 5. Push

```
git push origin main
```

## 6. Deploy (canonical script — do not hand-write docker commands)

```
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git pull --ff-only && APP_VERSION=$(git rev-parse --short HEAD) setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &"
```

Then poll:

```
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "tail -n 100 /tmp/dep.log"
```

Wait for `=== DEPLOYED <sha> OK ===`. If it errors, do NOT `reset --hard` or
blind-rebuild (CLAUDE.md landmine) — read the log and fix forward.

## 7. Post-deploy verification

```
curl -s https://leadsgenai.in/health
```

Confirm `version` == the short SHA you deployed and `environment: production`
(never `"latest"` — ADR-097 gate).

```
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "docker exec leadgen_app python -c \"from app.tasks.kb_niche_refresh import request_niche_refresh; print('import OK')\""
```

Confirms the new task module actually imports cleanly inside the deployed
container (catches anything this sandbox's staleness could have hidden).

## 8. Two live Voice QA acceptance runs

Run your existing Voice QA / `scripts/agent_tester.py` scorecard against a
COLD niche (one that has never been called this deploy) twice:

1. **First call to a cold niche** — expect the reply path to degrade
   gracefully (no KB facts this turn) rather than hang; watch
   `docker logs leadgen_worker` for `[kb-niche-refresh] requested niche=...`
   and confirm the refresh task completes (`[kb-niche-refresh] niche=... ok`
   or check `redis-cli get kb:niche_refresh:state:<niche>` → `ready`).
2. **Second call to the same niche** (after the refresh task has finished) —
   expect KB-grounded facts to appear in the reply this time.

Also confirm no Celery executor-shutdown hang: `docker logs leadgen_worker`
should show no `600s` timeout / hard-kill entries around either call, and
`redis-cli llen celery` should stay near-zero (not building up).

## 9. Report back

Once deployed and both acceptance calls are done, let me know the results
(especially anything in step 8 that didn't match expectations) and I'll pick
up the next item — the admin status-truth fix.
