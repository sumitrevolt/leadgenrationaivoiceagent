# Swara responsive turns — local implementation

Owner request: improve Swara's response speed and natural turn-taking, avoiding
premature interruption and replies to unrelated conversation. This supersedes
the broad commercial audit. No provider calls, deploy, paid dependencies or
credential changes are part of this task.

Risk: high (voice). Preserve disclosure, consent and billing. Existing unrelated
dirty tests and prior Smartflo recovery work must remain intact.

Owned implementation: `app/telephony/smartflo_stream.py`; new focused tests
`tests/test_smartflo_responsive_turns.py`; this plan and a local runbook.
Read-only reviewer checks browser/voice paths independently.

1. Red-first tests: first audio can be sent while later TTS is blocked; cancel
   cancels pending synthesis; variable packet durations have equal interruption
   thresholds; resumed caller speech suppresses an obsolete answer.
2. Reuse FirstSentenceChunker for bounded one-chunk prefetch. Keep greeting as
   one piece to preserve disclosure. Reuse existing BARGE_GUARD settings with
   duration counters; preserve default behavior when guard is off.
3. Stamp actual first outbound audio send separately from reply readiness.
   Document that this excludes network playback and is not acoustic latency.
4. Evaluate explicit pause/resume for side conversation without claiming speaker
   identification or weakening opt-out. Implement only with safe scoped tests.
5. Run focused + neighboring voice tests with network blocked, prod_check,
   secrets scan and local-only voice scorecard. Label skipped external tests.

No new API, routes, scheduler or feature flags. Rollback: revert only this task's
diff. No Silero activation. Local profile uses existing turn settings; deployments
and live call acceptance remain separate.
