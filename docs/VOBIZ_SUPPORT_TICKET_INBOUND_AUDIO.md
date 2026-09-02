# Vobiz Support Ticket — Bidirectional streaming: inbound audio frequently missing

> Drafted 2026-07-02, never sent (was sitting in an ephemeral session scratchpad).
> Rescued to a durable location 2026-07-03. **User action: send this to Vobiz support.**
> See also: [[phone-agent-deaf-stt-zero]] memory, `app/telephony/vobiz_handler.py::build_stream_xml`.

**Account ID:** 519192

**Issue:** On outbound calls placed via the Direct Call REST API with a
`<Stream bidirectional="true" keepCallAlive="true" audioTrack="inbound"
contentType="audio/x-l16;rate=16000">` response, the call connects and our
WebSocket receives the `start` event correctly (with `tracks: ["inbound"]`
acknowledged), and we successfully stream audio TO the caller (TTS via
`playAudio`) — but on most calls we receive **zero inbound media frames**
from the caller for the entire call duration, despite the call being
genuinely answered and the person speaking (confirmed manually).

**Frequency:** 4 out of 5 answered/connected calls on 2026-07-02 had
zero inbound audio for their full duration (57-85s each). Only 1 call
correctly delivered inbound audio (and worked end-to-end).

**That day's data (2026-07-02, ~15:22-15:24 IST outbound batch + afternoon retests):**
Of the calls that actually connected (callee-side hangup, billed duration >0),
5 out of 6 delivered ZERO inbound audio frames for their full duration; only 1
worked correctly.

**Example call UUID with 0 inbound frames despite a full 40s connected/billed call:**
- `bfe2df4f-6d7d-47d6-9c75-2c6ab885ce2c` (bill_duration=40, hangup_source=Vobiz,
  call fully connected, human spoke, we received 0 audio bytes on our WS)

Happy to provide the remaining call_uuids from the 15:22-15:24 batch on request
(correlated via your Call Detail Record API by to_number/initiation_time).

**Separately observed:** setting `audioTrack="both"` instead of `"inbound"`
made things WORSE — the call is answered and then immediately hung up BY
VOBIZ (`bill_duration: 0`, `hangup_source: "Vobiz"`), reproduced on 2
consecutive calls (call_uuid `5318a044-4af0-42dd-81ab-2552a022a9c4` and
`18037813-02f7-4e3c-bb8d-cc9109ba1ce2`). Please confirm whether `audioTrack="both"`
is a supported value for our account/plan.

**Ask:** Please check why inbound media frames are not being delivered over
the bidirectional WebSocket stream on ~80% of calls despite `tracks:
["inbound"]` being acknowledged in the start event. Is there an account-level
setting, codec negotiation issue, or known intermittent bug on your media
relay for `audioTrack="inbound"` streams?

---

## Update 2026-07-03 — frame-level diagnostic results (conclusive)

We added raw WS frame-level counters and ran controlled test calls the same
day. Two fresh instances, both to our own number (+918261030181):

**FAILED call — `call_uuid c76bc2b9-ad8f-491b-ad56-ce6539e581ce` (21:33 IST):**
- Your CDR: `answer_time 21:33:13`, `end_time 21:33:53`, `bill_duration=40`,
  **`hangup_source=Vobiz`**, `hangup_cause=NORMAL_CLEARING` — the call was
  answered, billed 40s, and hung up BY VOBIZ.
- Your WS start event arrived and ACKed `tracks: ["inbound"]`
  (`streamId e7c67133-9a64-4f43-8fc7-324fa66c814b`).
- Our frame-level counters for the ENTIRE call:
  `event_types={'start': 1}  media_events=0  media_empty_payload=0
  media_decode_fail=0  nonjson_frames=0`
- i.e. after the start event, your relay sent us **zero WebSocket frames of
  any kind** for the full 40 billed seconds, then terminated the call itself.

**WORKING call ~3.5h earlier, same code, same config — `streamId
6fdc02d9-9c64-4fa2-a65f-ad4d646da448`:** `media_events=7479`,
`inbound_frames=7479`, clean 150s two-way conversation. Another earlier
same-day call (`streamId 875fbe89-...`, 15:01 IST) failed identically to the
21:33 one (`event_types={'start': 1}`, `media_events=0`, answered ~44s).

This rules out anything on our side (payload parsing, decoding, VAD, STT) —
on failing calls nothing ever reaches our socket after `start`. The failure
is intermittent on your media relay for `audioTrack="inbound"` bidirectional
streams: same endpoint, same code, minutes apart — one call streams
perfectly, the next delivers nothing and is then hung up by Vobiz.

**Ask (updated):** please investigate the media-relay path for the two failing
call_uuids above (plus `bfe2df4f-...` from 2026-07-02). We can reproduce
within a few calls and are happy to run a live test while you watch your side.
