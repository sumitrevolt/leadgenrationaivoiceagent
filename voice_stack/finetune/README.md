# voice_stack/finetune — the data → fine-tune pipeline (Phases 2–6)

Offline tooling that turns our **own call recordings** into IndicConformer training data.
Standalone — these scripts do **not** import or modify the live app; they only read the
files the app already writes. Full design: `docs/VOICE_SELFHOST_FINETUNE_PIPELINE.md`.

```
recordings ──extract──▶ raw.jsonl ──label──▶ labeled.jsonl ─human─▶ train set ─NeMo─▶ eval_gate ─▶ deploy ─▶ (loop)
 (the app)             (Phase 2)   IndicWhisper (Phase 3)  (Phase 3b)    (Phase 4)   (Phase 5)
```

## Phase 2 — extract  (`extract_dataset.py`)
Builds `data/voice_train/raw.jsonl` from `data/call_recordings/<date>/`:
- phone `call_{sid}.wav` (merged) / `call_{sid}_caller.wav` (customer-only, **best**)
- web `webcall_{id}.{webm,…}` (mixed mic+bot) + customer text joined from `data/web_call_sessions.jsonl`

```bash
python voice_stack/finetune/extract_dataset.py
```

## Phase 3 — label  (`label_dataset.py`)
Weak-labels each recording with **IndicWhisper** (accuracy-first; offline so latency is irrelevant),
writes `labeled.jsonl` + flags a `review_queue.jsonl` subset for human correction.

```bash
pip install transformers torch torchaudio librosa soundfile jiwer   # + ffmpeg on PATH (webm decode)
python voice_stack/finetune/label_dataset.py            # all new rows
python voice_stack/finetune/label_dataset.py --limit 200 --disagree 0.4
```
- Default model `vasista22/whisper-hindi-large-v2` (override `INDICWHISPER_MODEL`).
- `needs_human` = empty / very short / no baseline / high disagreement vs the live STT.
- Resumable (skips already-labeled `audio_path`).

### Phase 3b — human correction (manual)
Open `review_queue.jsonl`, fix the `text`, set `"source":"human"`. Human rows outrank
`auto_indicwhisper` when you assemble the train set. Correct a **stratified** subset
(low-confidence / per-accent / per-niche) — not everything.

## Phase 4–6 (next, not in this skeleton yet)
- **4 fine-tune:** NeMo fine-tune IndicConformer on `labeled.jsonl` (source=human ∪ high-confidence auto),
  with telephony 8kHz augmentation. Warm-start first on public telephony data
  (GramVaani SLR118 / Kathbath) before our calls accrue — see the plan doc's dataset table.
- **5 eval_gate:** new checkpoint vs current on a held-out test set (incl. **Lahaja** accent set) —
  WER + `voice_turn_score`. Deploy only if better (reuse `app/agents/eval_gate.py`,
  `app/platform/regression_detector.py`, `scripts/agent_tester.py`). Never auto-apply to live.
- **6 loop:** re-run monthly / per N-thousand calls. Wire into `self_improve`.

## Known refinement (documented, not a bug)
`merged` (phone) and `mixed` (web) tracks contain bot audio too. For cleanest STT supervision,
diarize/segment per turn (customer-only) before training — the `caller` split track is already
clean. Segmentation = a later step; nothing is dropped here.

## Compliance / license
- Train **only on consented recordings** (app consent ledger + 90-day retention govern disk).
- Public warm-start datasets: **verify commercial-use license per set** before training a prod model
  (Common Voice CC0 ✓; Kathbath/SYSPIN CC-BY-4.0 ✓; "research release" sets may restrict).
