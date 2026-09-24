# WORKBUDDY-EMAIL-002 — TypeSafe live trace (REDACTED) → observed code action

**Date:** 2026-09-24 · **Model:** `jev-latest` (resolved `jev-1.13.0`) · **Credential:** env `TYPESAFE_API_KEY` (fingerprint `2e13ca55f7f8`, NOT in the compromised tripwire).
**PII policy:** all business names / niches / emails are stripped (`<REDACTED-*>`). No API key, no VPA, no customer PII in this file.

This file links **live, real TypeSafe System One calls** to the **observed code action**
in `app/platform/reply_agent.py`. No email was sent. Test runs are hermetic (faked
services); the lines below are the live API results.

---

## 1. Triage (`_typesafe_triage_evidence` → canonical `TypeSafeReplyTriage`)

| Case (redacted body) | LLM `_classify` | TypeSafe `mapped_intent` | `is_hot` | `urgency` | `suggested_action` | `model` | `latency` | `conflict` | Observed code action in `run_reply_triage` |
|---|---|---|---|---|---|---|---|---|---|
| "can you demo this week? what does monthly cost?" | interested | interested | true | same_day | schedule_call | jev-1.13.0 | 1.165s | false | PROCEED → interested/question path (draft + optional follow-up task) |
| "no we are not interested, please remove us from your list" | interested | unsubscribe | false | low | suppress_dnd | jev-1.13.0 | 1.142s | **true** | **DEMOTE to `other` + `held_for_review`** → NO deal, NO cadence, NO auto-send; explicit TypeSafe-`unsubscribe` conflict persists to global suppression (idempotent on delivery key) |

**Why it matters (§4 of the brief):** a reply that only *looks* positive to the LLM
("positive language") but is actually a DnD is demoted to review, never minted as a
qualified opportunity. Uncertain/decline → review hold, not invented intent.

## 2. Content pre-send gate (`_typesafe_content_gate` → canonical `TypeSafeContentQA`)

| Draft (redacted) | `state` | `passed` | `needs_review` | model | latency | observed auto-send outcome |
|---|---|---|---|---|---|---|
| clean 15-min demo + pricing + "reply REMOVE" | `ok` | true | false | jev-1.13.0 | 1.082s | PROCEED to claim/send (deterministic gates still hold the line) |
| "GUARANTEED 10x in 7 days… pay bank transfer now" | `rejected` | false | true | jev-1.13.0 | 0.701s | **HOLD for review** (`auto_send_status=held_for_review`) |
| API 503 / timeout (verifier down) | `error` | false | true | — | — | **HOLD** (unverifiable draft must not ship) |
| success but empty answer | `empty_answer` | false | true | — | — | **HOLD** (no verdict to trust) |

**Inert (no API key) is the ONLY fail-open case** (`state=inert`, advisory): the gate
is not armed, so the bounded deterministic gates (consent / suppression / flood /
unknown-prospect / age / scan / injection) remain the sole authority.

---

## 3. API-failure regression coverage (test, hermetic — no network)
- `tests/test_reply_typesafe_triage.py::test_content_gate_api_error_holds` → assert `state=error, needs_review=True`.
- `tests/test_reply_typesafe_triage.py::test_content_gate_empty_answer_holds` → assert `state=empty_answer, needs_review=True`.
- `tests/test_reply_typesafe_triage.py::test_followup_task_targets_orchestrator_ledger` → follow-up task lands in `data/orchestrator_ledger.db` (worker ledger), durable id + owner + idempotency, NOT `admin_tasks.db`.
