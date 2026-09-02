# reply() / reply_stream_sentences() Mirror Rule

`telecaller_brain.py` has TWO reply paths: `reply()` (full turn) and `reply_stream_sentences()` (streaming).

**Every guard, close-signal, or behaviour added to `reply()` MUST be mirrored in `reply_stream_sentences()`.**

Incident: close-signals were silently missing on the stream path — calls behaved differently depending on which path served the turn.

Checklist when touching either:

- [ ] Same guards in both paths
- [ ] Same close/handoff signals in both
- [ ] Voice behaviour change → run `scripts/agent_tester.py` scorecard before "done"
