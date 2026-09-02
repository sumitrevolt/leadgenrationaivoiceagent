"""Tests for app/voice_agent/voice_metrics.py — objective voice-eval metrics."""

from app.voice_agent import voice_metrics as vm


def test_wer_identical_is_zero():
    assert vm.wer("turn on the lights", "turn on the lights") == 0.0


def test_wer_one_substitution():
    # 1 sub in 4-word ref = 0.25
    assert vm.wer("turn on the lights", "turn on the light") == 0.25


def test_wer_normalization_ignores_case_and_punct():
    assert vm.wer("Turn ON the lights!", "turn on the lights") == 0.0


def test_wer_empty_reference():
    assert vm.wer("", "") == 0.0
    assert vm.wer("", "extra words") == 1.0


def test_wer_deletion_and_insertion():
    # ref 3 words, hyp drops 1 → 1 deletion / 3 = 0.333
    assert round(vm.wer("book a demo", "book demo"), 3) == 0.333
    # ref 2 words, hyp adds 1 → 1 insertion / 2 = 0.5
    assert vm.wer("book demo", "book a demo") == 0.5


def test_cer_character_level():
    # "light" vs "lite": l-i-... 5 chars ref; needs 2 edits (g->t? ) -> just check >0 and bounded
    c = vm.cer("light", "lite")
    assert 0.0 < c <= 1.0


def test_normalize_text():
    assert vm.normalize_text("  Hello,  WORLD!! ") == "hello world"
    assert vm.normalize_text("") == ""


def test_percentile_basic():
    vals = list(range(1, 101))  # 1..100
    assert vm.percentile(vals, 50) == 50.5
    assert vm.percentile(vals, 99) >= 99.0
    assert vm.percentile([], 95) == 0.0
    assert vm.percentile([42], 95) == 42.0


def test_latency_summary_shape():
    s = vm.latency_summary([100, 200, 300, 400, 1000])
    assert s["n"] == 5
    assert s["p50"] == 300.0
    assert s["max"] == 1000.0
    assert s["p99"] >= s["p95"] >= s["p50"]


def test_latency_summary_empty():
    s = vm.latency_summary([])
    assert s == {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}


def test_roundtrip_wer_with_fakes():
    texts = ["book a demo", "call me tomorrow"]
    # perfect fake: transcribe returns the exact synthesized text
    out = vm.roundtrip_wer(texts, synth_fn=lambda t: t, transcribe_fn=lambda a: a)
    assert out["mean_wer"] == 0.0
    assert out["flagged"] == []


def test_roundtrip_wer_flags_bad_intelligibility():
    texts = ["book a demo today please"]
    # garbled transcription → high WER → flagged
    out = vm.roundtrip_wer(texts, synth_fn=lambda t: t, transcribe_fn=lambda a: "xxxx")
    assert out["flagged"] == texts


def test_roundtrip_wer_never_raises_on_synth_error():
    def boom(_):
        raise RuntimeError("tts down")

    out = vm.roundtrip_wer(["hi"], synth_fn=boom, transcribe_fn=lambda a: a)
    assert out["rows"][0]["wer"] is None
    assert "error" in out["rows"][0]


def test_score_asr_aggregate():
    pairs = [("book a demo", "book a demo"), ("call me", "call her")]
    out = vm.score_asr(pairs)
    assert out["n"] == 2
    assert out["wer"] == 0.25  # (0 + 0.5) / 2
    assert out["worst"][0]["wer"] == 0.5


def test_vaqi_summary_missed_response_rate():
    out = vm.vaqi_summary(latencies_ms=[100, 200, 300], turns_total=4, missed_count=1)
    assert out["missed_response_rate"] == 0.25
    assert out["missed_count"] == 1
    assert out["turns_total"] == 4
    assert out["latency"]["n"] == 3


def test_vaqi_summary_no_turns_gives_none_rate():
    out = vm.vaqi_summary(latencies_ms=[], turns_total=0, missed_count=0)
    assert out["missed_response_rate"] is None
    assert out["latency"]["n"] == 0


def test_vaqi_summary_interruption_rate_optional():
    # not supplied -> None, not misleadingly 0.0
    out = vm.vaqi_summary(turns_total=5, missed_count=0)
    assert out["interruption_rate"] is None
    # supplied -> computed
    out2 = vm.vaqi_summary(
        turns_total=5, missed_count=0, interruptions_total=4, premature_interruptions=1
    )
    assert out2["interruption_rate"] == 0.25
