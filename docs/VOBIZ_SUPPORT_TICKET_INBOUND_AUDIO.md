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

## Update 2026-07-03 — additional diagnostic now shipping our side

We added raw WS frame-level counters (commit pending) that will tell us,
on the next real call, whether:
- We never receive a `"media"`-type event at all (points to your media relay
  not forwarding inbound audio) — this is what we currently suspect, or
- We receive `"media"` events but with an empty/different payload shape
  than documented (would point to a payload-format change on your side), or
- The payload arrives but isn't valid base64 (encoding mismatch).

Will share the exact breakdown from the next controlled test call once we
have it, which should narrow this down conclusively on our end regardless
of your investigation.
