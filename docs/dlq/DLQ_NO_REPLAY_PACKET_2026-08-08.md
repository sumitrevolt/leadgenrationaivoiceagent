# DLQ NO-REPLAY PACKET — the six historical `dlq:dead` prospect records

> **IMMUTABLE, dated, append-only.** This packet documents the historical dead-letter
> entries that docs reference as `dlq:dead` = 3 / 4 / 6 / 7 at different times. Its
> purpose is forensic provenance — **NOT** a replay authorization. No entry here may
> be re-queued, mutated, or deleted without the Owner-approval gate in §7.
>
> Created: 2026-08-08 · Author: WS3 (dial-truth-docs-dlq) · Branch: `chore/dial-truth-docs-dlq`

---

## 1. The six records being tracked (canonical evidence)

Raw forensic capture: **`forensics_billing_dlq.txt`** (repo root, on-disk, git-ignored,
30 KB). It holds exactly **7 JSONL task records**, all `args: ['prospect']`, all
`dead_reason: "max 3 auto-retries exhausted"`, timestamps **2026-07-17T14:59–19:36 UTC**.

**Six** of those seven failed with `SoftTimeLimitExceeded()` — **these six are the
"dlq-dead-6" set** referenced by the report branch
`freebuff/report-se-priority-clear-hai-dlq-dead-6-...` and by the 6th-instance bug-family
commits (`22ff63ec` / `0f0e4af3`, ADR-104 Phase F). The seventh (one record) failed with
`TimeLimitExceeded(600,)` and completes the `dlq:dead=7` snapshot. All seven are listed
below; the six-tracked are flagged.

| # | Task ID | Time (UTC) | Failure class | Tracked "six" |
|---|---------|-----------|---------------|:---:|
| 1 | `34bacfe1-fd82-4c78-a231-71f39182cc9d` | 2026-07-17 14:59:15 | `SoftTimeLimitExceeded()` | ✅ |
| 2 | `b512c8da-8fe7-4ab4-981d-88c2a8fcc76a` | 2026-07-17 17:40:29 | `SoftTimeLimitExceeded()` | ✅ |
| 3 | `45f219b7-a893-4b57-8d6c-9115a9220966` | 2026-07-17 18:07:39 | `SoftTimeLimitExceeded()` | ✅ |
| 4 | `8271b5c2-b99e-47b1-920f-1d867a7e4e36` | 2026-07-17 18:17:44 | `TimeLimitExceeded(600,)` | — |
| 5 | `36154695-0297-4f04-b966-6fc491adef35` | 2026-07-17 18:48:49 | `SoftTimeLimitExceeded()` | ✅ |
| 6 | `17c1bd64-1a7b-498d-aa71-8b85055f026f` | 2026-07-17 19:36:02 | `SoftTimeLimitExceeded()` | ✅ |
| 7 | `278db4ce-11f6-4f50-8770-798f1c6896b5` | 2026-07-17 (ts in capture) | `SoftTimeLimitExceeded()` | ✅ |

All seven: `args: ['prospect']`, `dead_reason: "max 3 auto-retries exhausted"` (Celery
`max_retries=2` + initial attempt = the 3-attempt window; `make_call_task` is
`bind=True, max_retries=3, rate_limit="20/m"`). No PII was retained in this packet; the
capture file itself is git-ignored and must stay out of git.

## 2. The `dlq:dead` counts across docs (3 / 4 / 6 / 7) — reconciled

Docs reference four different counts because they are different moments:

- **`dlq:dead=7`** = the 2026-07-17 prospect set above (the complete 7-record snapshot;
  `memory/incidents.md` §L90; `docs/archive/2026-07/SESSION_HANDOFF_2026-07-18.md` §L13
  "7 stale entries … all prospect SoftTimeLimitExceeded from 2026-07-17").
- **`dlq:dead=6`** = the six `SoftTimeLimitExceeded` prospect records of that set (the
  tracked set in §1; the `dlq-dead-6` branch name). The 7th (`TimeLimitExceeded(600,)`)
  is the same family but a distinct failure class — keep it in the same packet for
  completeness, never silently dropped.
- **`dlq:dead=4`** = the earlier **qa/trainer** dead records (2026-07-12..15,
  ADR-104 Phase D / `docs/archive/2026-07/ADR104_SESSION_FINAL_REPORT_2026-07-15.md`
  §L69-74): `5d1f2ace…` (qa — resolved by `8383eec` via live rerun 218.86s),
  `3e71690b…` (qa), `d2866a56…` + `82907ace…` (trainer — monitor-only). Left as history
  (`commit d355c158` "ops: clear approved qa dead letter entries").
- **`dlq:dead=3`** = a transient mid-state (e.g. between a replay/clear and a new
  arrival); no literal `=3` line was found in git docs — it is a point-in-time depth,
  not a distinct record class. The **six tracked records are the six in §1** regardless.

## 3. Disposition history (already done — do NOT redo)

- **Archived:** 2026-07-18 the 7 records were exported to
  `data/dlq_dead_archive_20260718.jsonl` (immutable archive file; the 7 task IDs match
  §1) — see `docs/archive/2026-07/SESSION_HANDOFF_2026-07-18.md` §L13.
- **Purged (authorized, post-verification):** `dlq:dead` was emptied ONLY after a
  successful prospect campaign run — "ops E: one successful prospect run then purge
  dlq:dead=7" (`progress.md` §L1067/§L1080); purge completed (§L269), and all of
  `dlq:dead` / `dlq:failed_tasks` / `celery` = 0 verified 2026-07-19
  (`docs/context/CURRENT_STATE.md`).
- **Unchanged across canary evidence:** `docs/agent_runtime/*PROD_CANARY*` reports kept
  `dlq:dead=7` as pre-existing, **never replayed**.

## 4. Why no-replay

- These are **soft/hard time-limit timeouts from a 2026-07-17 bottleneck** — the task
  body is a prospect id, not a payload worth preserving; the 2026-07-18 containment and
  the app's retry/DLQ health (all zero since 2026-07-19) mean there is no pending work
  lost in these records.
- **`redis-cli DEL dlq:dead` is a proven anti-pattern** — `docs/archive/2026-07/DEPLOYMENT_SESSION2_2026_07_11.md` §L99-101 documents a prior session doing exactly this.
  Deleting a dead-letter queue without archive + owner gate destroys the audit trail.
  **This packet forbids it.** The only legitimate path is §7.

## 5. Compliance guards (unchanged while this packet is open)

- DND scrub **fail-CLOSED** (lookup failure = promotional BLOCK).
- AI-disclosure at call start; promo calling window code-conservative **09:00–19:00 IST**
  (TRAI window is 09:00–21:00 IST).
- Consent-ledger opt-out = INSTANT cross-channel suppression.
- 90-day recording retention; DPDP purpose-limitation applies to any re-contact.
- `VOICE_LAUNCH_KILL` / `DIAL_TEST_MODE` / `PLATFORM_DIAL_DAILY` / `PLATFORM_DIAL_LIMIT`
  remain the only legal arming path (see `docs/context/CURRENT_STATE.md` §ops-facts).

## 6. Change history (append-only)

- 2026-08-08 — Packet created (WS3). Six tracked records fixed in §1; counts reconciled
  in §2; disposition + no-replay rationale in §3–§4. No record replayed, deleted, or
  mutated.

## 7. Owner-approval gate (if ever reconsidered)

Replaying any record requires, IN ORDER, all of:

1. **Explicit Owner sign-off** in this file (name + UTC timestamp).
2. **Export, never DELETE**: `redis-cli --no-raw LRANGE dlq:dead 0 -1 > dlq_replay_candidate_<date>.jsonl` first, verify the record set, then re-queue by task id with the ORIGINAL `args` untouched.
3. **Prereqs live**: `VOICE_LAUNCH_KILL=0`, `DIAL_TEST_MODE=0`, TRAI window open, DLT approved, campaign lock free, DLQ/celery depths 0.
4. **Canary-first**: replay exactly ONE record; observe the campaign run end-to-end; roll back to packet state if any compliance gate trips.
5. **Record** every step back into §6.

Until the Owner signs §7.1, these records stay **archived, not replayable, and never deleted.**
