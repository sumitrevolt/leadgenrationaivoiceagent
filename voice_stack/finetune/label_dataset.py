"""
Phase 3 — LABEL: weak-label our recordings with IndicWhisper (offline, accuracy-first).
============================================================================
Standalone OFFLINE tool — run on a GPU box / Colab (transformers + ffmpeg). It does
NOT touch the live app. Latency does not matter here (offline) → we use the more
accurate IndicWhisper, not the fast live Conformer.

Reads:   data/voice_train/raw.jsonl              (from extract_dataset.py)
Writes:  data/voice_train/labeled.jsonl          {..row, text, source, model, agree_wer, needs_human}
         data/voice_train/review_queue.jsonl     subset needing human correction

Model:   default vasista22/whisper-hindi-large-v2 (AI4Bharat IndicWhisper Hindi checkpoint)
         override with env INDICWHISPER_MODEL=<hf-id>

Confidence signal (cheap, no logprobs needed): compare the IndicWhisper text with the
live STT baseline ("live_hypothesis", web calls). High disagreement / empty / very short
=> needs_human=True => goes to review_queue.jsonl for a human to correct a stratified
subset. Corrected rows (source=human) outrank auto ones when you build the train set.

Resumable: skips audio_path already present in labeled.jsonl.

Deps:  pip install transformers torch torchaudio librosa soundfile jiwer
       + ffmpeg on PATH (needed to decode browser webm/opus web-call recordings).

Run:   python voice_stack/finetune/label_dataset.py
       python voice_stack/finetune/label_dataset.py --limit 200 --disagree 0.4
"""
from __future__ import annotations

import argparse
import json
import os

DEFAULT_MODEL = os.environ.get("INDICWHISPER_MODEL", "vasista22/whisper-hindi-large-v2")
IN_DEFAULT = os.path.join("data", "voice_train", "raw.jsonl")
OUT_DEFAULT = os.path.join("data", "voice_train", "labeled.jsonl")
REVIEW_DEFAULT = os.path.join("data", "voice_train", "review_queue.jsonl")


def _read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _done_paths(out_path: str) -> set[str]:
    return {r.get("audio_path") for r in _read_jsonl(out_path) if r.get("audio_path")}


def _wer(a: str, b: str):
    """Word error rate between two strings (lower = more agreement). None if uncomputable."""
    try:
        import jiwer
        a, b = (a or "").strip(), (b or "").strip()
        if not a or not b:
            return None
        return float(jiwer.wer(a, b))
    except Exception:
        return None


def _build_asr(model_id: str):
    """IndicWhisper via HF pipeline. Returns a callable path->text."""
    from transformers import pipeline
    import torch

    device = 0 if torch.cuda.is_available() else -1
    gen = {"language": "hi", "task": "transcribe"}
    try:
        pipe = pipeline(
            "automatic-speech-recognition", model=model_id, device=device,
            chunk_length_s=20, generate_kwargs=gen,
        )
    except Exception:
        # some checkpoints reject generate_kwargs at construction — retry bare
        pipe = pipeline("automatic-speech-recognition", model=model_id, device=device,
                        chunk_length_s=20)

    def _transcribe(path: str) -> str:
        res = pipe(path)
        if isinstance(res, dict):
            return str(res.get("text") or "").strip()
        return str(res).strip()

    return _transcribe


def label(in_path: str, out_path: str, review_path: str, model_id: str,
          limit: int = 0, disagree: float = 0.5) -> dict:
    rows = _read_jsonl(in_path)
    if not rows:
        print(f"[label] no rows in {in_path} — run extract_dataset.py first")
        return {"labeled": 0, "review": 0}

    done = _done_paths(out_path)
    todo = [r for r in rows if r.get("audio_path") and r["audio_path"] not in done]
    if limit:
        todo = todo[:limit]
    if not todo:
        print(f"[label] nothing new (all {len(rows)} already in {out_path})")
        return {"labeled": 0, "review": 0}

    print(f"[label] loading IndicWhisper '{model_id}' ...")
    transcribe = _build_asr(model_id)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    n_lab = n_rev = 0
    with open(out_path, "a", encoding="utf-8") as out_f, \
            open(review_path, "a", encoding="utf-8") as rev_f:
        for i, row in enumerate(todo, 1):
            ap = row["audio_path"]
            try:
                text = transcribe(ap)
                err = ""
            except Exception as e:  # decode/model error on one file must not kill the run
                text, err = "", str(e)[:160]

            live = (row.get("live_hypothesis") or "").strip()
            agree = _wer(text, live) if live else None
            needs_human = bool(
                err
                or not text
                or len(text.split()) < 2
                or agree is None  # no cross-check baseline -> verify by hand
                or (agree is not None and agree > disagree)
            )

            rec = {
                **row,
                "text": text,
                "source": "auto_indicwhisper",
                "model": model_id,
                "agree_wer": agree,
                "needs_human": needs_human,
            }
            if err:
                rec["error"] = err
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_lab += 1
            if needs_human:
                rev_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_rev += 1
            if i % 25 == 0:
                print(f"  {i}/{len(todo)} labeled ({n_rev} flagged for review)")

    print(f"[label] done: {n_lab} labeled -> {out_path} | {n_rev} need human -> {review_path}")
    print("  next: human-correct the review_queue (source='human'), then fine-tune (Phase 4).")
    return {"labeled": n_lab, "review": n_rev}


def main() -> None:
    ap = argparse.ArgumentParser(description="Weak-label recordings with IndicWhisper.")
    ap.add_argument("--in", dest="in_path", default=IN_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--review", default=REVIEW_DEFAULT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=0, help="0 = all new rows")
    ap.add_argument("--disagree", type=float, default=0.5,
                    help="WER vs live baseline above this => needs_human")
    args = ap.parse_args()
    label(args.in_path, args.out, args.review, args.model, args.limit, args.disagree)


if __name__ == "__main__":
    main()
