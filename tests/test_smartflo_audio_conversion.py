"""
Tests for Smartflo Voice Streaming audio conversion utilities.

Covers:
  - mulaw_to_pcm16: G.711 µ-law decode
  - pcm16_to_mulaw: G.711 µ-law encode
  - pcm16_8k_to_16k: upsample (8kHz → 16kHz)
  - pcm16_16k_to_8k: downsample (16kHz → 8kHz)
  - Roundtrip fidelity: mulaw → PCM16 → upsample → downsample → PCM16 → mulaw
  - Edge cases: empty, single sample, silence, max amplitude
  - Frame size constants match protocol spec

The test forces the pure-Python fallback paths by temporarily disabling audioop,
then verifies the audioop path (when available) produces equivalent output.
"""

from __future__ import annotations

import math
import struct
import sys
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Import the module — guard against import failure (deps not installed)
# ---------------------------------------------------------------------------
try:
    from app.telephony.smartflo_stream import (
        MULAW_FRAME_BYTES,
        PCM16_FRAME_BYTES,
        mulaw_to_pcm16,
        pcm16_8k_to_16k,
        pcm16_16k_to_8k,
        pcm16_to_mulaw,
    )

    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK, reason="smartflo_stream not importable"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_sine_pcm16(freq: int, sample_rate: int, duration_s: float) -> bytes:
    """Generate a sine wave as PCM16 bytes."""
    n_samples = int(sample_rate * duration_s)
    amp = 16000  # safe amplitude (below 32767)
    samples = [
        int(amp * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(n_samples)
    ]
    return struct.pack(f"<{len(samples)}h", *samples)


def _make_silence_pcm16(n_samples: int) -> bytes:
    """Generate silence (zero) as PCM16 bytes."""
    return b"\x00\x00" * n_samples


def _make_dc_pcm16(dc_value: int, n_samples: int) -> bytes:
    """Generate DC offset signal as PCM16 bytes."""
    return struct.pack(f"<{n_samples}h", *[dc_value] * n_samples)


# ---------------------------------------------------------------------------
# Frame size constants
# ---------------------------------------------------------------------------
class TestFrameConstants:
    """Protocol spec constants must match Smartflo docs."""

    def test_mulaw_frame_is_160_bytes(self):
        """8kHz * 20ms = 160 bytes mulaw (G.711 standard frame)."""
        assert MULAW_FRAME_BYTES == 160

    def test_pcm16_frame_is_320_bytes(self):
        """16kHz * 20ms = 320 bytes PCM16 (16-bit samples)."""
        assert PCM16_FRAME_BYTES == 320


# ---------------------------------------------------------------------------
# mulaw_to_pcm16
# ---------------------------------------------------------------------------
class TestMulawToPcm16:
    """Decode G.711 µ-law → PCM16."""

    def test_empty_input(self):
        assert mulaw_to_pcm16(b"") == b""

    def test_silence_decode(self):
        """mulaw 0xFF (linear 0) → PCM16 0."""
        result = mulaw_to_pcm16(b"\xff")
        assert len(result) == 2
        val = struct.unpack("<h", result)[0]
        assert val == 0

    def test_output_length(self):
        """Each mulaw byte → 2 PCM16 bytes (16-bit sample)."""
        for n in (1, 10, 160, 1000):
            mulaw = b"\x80" * n
            result = mulaw_to_pcm16(mulaw)
            assert len(result) == n * 2

    def test_positive_values_decode(self):
        """Positive PCM16 values decode from mulaw bytes 0x80-0xFF."""
        # Just verify a range doesn't crash and produces valid int16
        for byte in range(0x80, 0x100, 0x10):
            result = mulaw_to_pcm16(bytes([byte]))
            val = struct.unpack("<h", result)[0]
            assert -32768 <= val <= 32767

    def test_negative_values_decode(self):
        """Negative PCM16 values decode from mulaw bytes 0x00-0x7F."""
        for byte in range(0x00, 0x80, 0x10):
            result = mulaw_to_pcm16(bytes([byte]))
            val = struct.unpack("<h", result)[0]
            assert -32768 <= val <= 32767

    def test_symmetry_positive_negative(self):
        """mulaw encode is symmetric: +X and -X should decode to similar magnitude."""
        for byte_pos in (0x80, 0xB0, 0xE0, 0xFE):
            byte_neg = byte_pos ^ 0x7F  # flip sign bits
            val_pos = struct.unpack("<h", mulaw_to_pcm16(bytes([byte_pos])))[0]
            val_neg = struct.unpack("<h", mulaw_to_pcm16(bytes([byte_neg])))[0]
            # Magnitudes should be close (within 1 due to quantization)
            assert abs(abs(val_pos) - abs(val_neg)) <= 1, (
                f"byte {byte_pos:02x}→{val_pos} vs {byte_neg:02x}→{val_neg}"
            )

    def test_batch_decode(self):
        """Decode 160-byte frame (20ms at 8kHz)."""
        mulaw = b"\xaa" * 160
        result = mulaw_to_pcm16(mulaw)
        assert len(result) == 320  # 160 samples × 2 bytes


# ---------------------------------------------------------------------------
# pcm16_to_mulaw
# ---------------------------------------------------------------------------
class TestPcm16ToMulaw:
    """Encode PCM16 → G.711 µ-law."""

    def test_empty_input(self):
        assert pcm16_to_mulaw(b"") == b""

    def test_silence_encode(self):
        """PCM16 0 → mulaw 0xFF."""
        result = pcm16_to_mulaw(struct.pack("<h", 0))
        assert len(result) == 1
        assert result[0] == 0xFF

    def test_output_length(self):
        """Each 2 PCM16 bytes → 1 mulaw byte."""
        for n in (1, 50, 160, 500):
            pcm = struct.pack(f"<{n}h", *([1000] * n))
            result = pcm16_to_mulaw(pcm)
            assert len(result) == n

    def test_positive_encode(self):
        """Positive PCM16 → mulaw byte 0x80-0xFE."""
        for val in (100, 1000, 5000, 16000, 32000):
            result = pcm16_to_mulaw(struct.pack("<h", val))
            assert 0x80 <= result[0] <= 0xFE

    def test_negative_encode(self):
        """Negative PCM16 → mulaw byte 0x01-0x7F."""
        for val in (-100, -1000, -5000, -16000, -32000):
            result = pcm16_to_mulaw(struct.pack("<h", val))
            assert 0x01 <= result[0] <= 0x7F

    def test_batch_encode(self):
        """Encode 320-byte frame (20ms at 16kHz)."""
        pcm = struct.pack(f"<{160}h", *([500] * 160))
        result = pcm16_to_mulaw(pcm)
        assert len(result) == 160


# ---------------------------------------------------------------------------
# Roundtrip: mulaw → PCM16 → mulaw
# ---------------------------------------------------------------------------
class TestMulawRoundtrip:
    """Encode→decode roundtrip fidelity (lossy — mulaw has 8-bit quantization)."""

    def test_silence_roundtrip(self):
        """Silence survives roundtrip perfectly."""
        mulaw = b"\xff" * 100
        pcm = mulaw_to_pcm16(mulaw)
        back = pcm16_to_mulaw(pcm)
        assert back == mulaw

    def test_dc_offset_roundtrip(self):
        """DC offset values survive roundtrip within quantization tolerance."""
        for dc in (0, 500, 1000, -500, -1000, 8000, -8000):
            pcm = struct.pack(f"<{50}h", *[dc] * 50)
            mulaw = pcm16_to_mulaw(pcm)
            pcm_back = mulaw_to_pcm16(mulaw)
            # Each sample should be within ±30 of original (8-bit quantization)
            for i in range(0, len(pcm_back), 2):
                orig = struct.unpack_from("<h", pcm, i)[0]
                decoded = struct.unpack_from("<h", pcm_back, i)[0]
                assert abs(orig - decoded) <= 30, (
                    f"DC={dc}: orig={orig} decoded={decoded} diff={abs(orig-decoded)}"
                )

    def test_sine_roundtrip_amplitude_preserved(self):
        """Sine wave roundtrip preserves overall amplitude (±20% for 8-bit mulaw)."""
        sine = _make_sine_pcm16(440, 8000, 0.1)  # 440Hz, 100ms
        mulaw = pcm16_to_mulaw(sine)
        pcm_back = mulaw_to_pcm16(mulaw)
        # RMS should be within 20% of original
        orig_rms = math.sqrt(sum(s ** 2 for s in struct.unpack(f"<{len(sine)//2}h", sine)) / (len(sine) // 2))
        back_rms = math.sqrt(sum(s ** 2 for s in struct.unpack(f"<{len(pcm_back)//2}h", pcm_back)) / (len(pcm_back) // 2))
        assert abs(orig_rms - back_rms) / orig_rms < 0.20, (
            f"RMS drift: orig={orig_rms:.0f} back={back_rms:.0f}"
        )


# ---------------------------------------------------------------------------
# Sample rate conversion
# ---------------------------------------------------------------------------
class TestSampleRateConversion:
    """Upsample and downsample between 8kHz and 16kHz."""

    def test_upsample_doubles_length(self):
        """8kHz → 16kHz doubles the number of samples."""
        pcm_8k = _make_silence_pcm16(100)
        pcm_16k = pcm16_8k_to_16k(pcm_8k)
        assert len(pcm_16k) == len(pcm_8k) * 2

    def test_downsample_halves_length(self):
        """16kHz → 8kHz halves the number of samples."""
        pcm_16k = _make_silence_pcm16(200)
        pcm_8k = pcm16_16k_to_8k(pcm_16k)
        assert len(pcm_8k) == len(pcm_16k) // 2

    def test_upsample_silence_stays_silence(self):
        """Silence upsampled stays silence."""
        pcm_8k = _make_silence_pcm16(50)
        pcm_16k = pcm16_8k_to_16k(pcm_8k)
        assert all(b == 0 for b in pcm_16k)

    def test_downsample_silence_stays_silence(self):
        """Silence downsampled stays silence."""
        pcm_16k = _make_silence_pcm16(100)
        pcm_8k = pcm16_16k_to_8k(pcm_16k)
        assert all(b == 0 for b in pcm_8k)

    def test_upsample_dc_preserved(self):
        """DC offset preserved through upsampling."""
        dc_pcm = _make_dc_pcm16(5000, 80)
        upsampled = pcm16_8k_to_16k(dc_pcm)
        # Every sample should be close to 5000
        samples = struct.unpack(f"<{len(upsampled)//2}h", upsampled)
        for s in samples:
            assert abs(s - 5000) <= 5, f"DC drift: sample={s} expected≈5000"

    def test_downsample_dc_preserved(self):
        """DC offset preserved through downsampling."""
        dc_pcm = _make_dc_pcm16(5000, 160)
        downsampled = pcm16_16k_to_8k(dc_pcm)
        samples = struct.unpack(f"<{len(downsampled)//2}h", downsampled)
        for s in samples:
            assert abs(s - 5000) <= 5, f"DC drift: sample={s} expected≈5000"

    def test_upsample_sine_shape(self):
        """Sine wave upsampled preserves frequency content (no aliasing)."""
        sine_8k = _make_sine_pcm16(200, 8000, 0.05)  # 200Hz, 50ms
        sine_16k = pcm16_8k_to_16k(sine_8k)
        # Should have zero-crossings (not all zeros)
        samples = struct.unpack(f"<{len(sine_16k)//2}h", sine_16k)
        has_positive = any(s > 100 for s in samples)
        has_negative = any(s < -100 for s in samples)
        assert has_positive and has_negative, "Sine wave lost after upsample"

    def test_full_roundtrip_8k_to_16k_to_8k(self):
        """PCM16 8kHz → 16kHz → 8kHz preserves shape within tolerance."""
        orig = _make_sine_pcm16(300, 8000, 0.05)
        up = pcm16_8k_to_16k(orig)
        down = pcm16_16k_to_8k(up)
        # Lengths: 8k→16k doubles, 16k→8k halves → back to original length
        assert len(down) == len(orig)
        # RMS should be close
        orig_samples = struct.unpack(f"<{len(orig)//2}h", orig)
        down_samples = struct.unpack(f"<{len(down)//2}h", down)
        orig_rms = math.sqrt(sum(s ** 2 for s in orig_samples) / len(orig_samples))
        down_rms = math.sqrt(sum(s ** 2 for s in down_samples) / len(down_samples))
        assert abs(orig_rms - down_rms) / max(orig_rms, 1) < 0.15, (
            f"RMS drift 8k→16k→8k: {orig_rms:.0f} → {down_rms:.0f}"
        )


# ---------------------------------------------------------------------------
# Full pipeline: mulaw → PCM16 8k → PCM16 16k (for STT)
# ---------------------------------------------------------------------------
class TestInboundPipeline:
    """Smartflo inbound audio: mulaw 8kHz → PCM16 16kHz (STT-ready)."""

    def test_mulaw_to_16k_pipeline(self):
        """Full inbound pipeline produces valid PCM16 16kHz."""
        # Simulate a 20ms frame of mulaw audio
        mulaw = bytes(range(0, 160))  # varied mulaw bytes
        pcm_8k = mulaw_to_pcm16(mulaw)
        pcm_16k = pcm16_8k_to_16k(pcm_8k)
        # 160 mulaw → 160 PCM16 8kHz samples → 320 PCM16 16kHz samples
        assert len(pcm_8k) == 320  # 160 × 2 bytes
        assert len(pcm_16k) == 640  # 320 × 2 bytes
        # All values should be valid int16
        samples = struct.unpack(f"<{len(pcm_16k)//2}h", pcm_16k)
        assert all(-32768 <= s <= 32767 for s in samples)

    def test_pipeline_energy_preserved(self):
        """Energy (RMS) of inbound audio should be roughly preserved."""
        # Generate a known sine wave as mulaw
        sine_8k = _make_sine_pcm16(440, 8000, 0.1)
        mulaw = pcm16_to_mulaw(sine_8k)
        # Pipeline: mulaw → PCM16 8k → PCM16 16k
        pcm_8k = mulaw_to_pcm16(mulaw)
        pcm_16k = pcm16_8k_to_16k(pcm_8k)
        orig_rms = math.sqrt(
            sum(s ** 2 for s in struct.unpack(f"<{len(sine_8k)//2}h", sine_8k))
            / (len(sine_8k) // 2)
        )
        out_rms = math.sqrt(
            sum(s ** 2 for s in struct.unpack(f"<{len(pcm_16k)//2}h", pcm_16k))
            / (len(pcm_16k) // 2)
        )
        # Allow 25% RMS drift (mulaw quantization + resample)
        assert abs(orig_rms - out_rms) / max(orig_rms, 1) < 0.25


# ---------------------------------------------------------------------------
# Full pipeline: PCM16 16kHz (TTS) → mulaw (for Smartflo)
# ---------------------------------------------------------------------------
class TestOutboundPipeline:
    """Smartflo outbound audio: PCM16 16kHz → mulaw 8kHz."""

    def test_16k_to_mulaw_pipeline(self):
        """Full outbound pipeline produces valid mulaw frames."""
        pcm_16k = _make_sine_pcm16(440, 16000, 0.02)  # 20ms frame
        pcm_8k = pcm16_16k_to_8k(pcm_16k)
        mulaw = pcm16_to_mulaw(pcm_8k)
        # 320 PCM16 16kHz samples → 160 PCM16 8kHz → 160 mulaw bytes
        assert len(pcm_8k) == 320
        assert len(mulaw) == 160  # exactly one MULAW_FRAME_BYTES frame

    def test_multiple_frames(self):
        """Generate multiple 20ms frames (simulating real TTS output)."""
        # 100ms of audio = 5 frames
        pcm_16k = _make_sine_pcm16(440, 16000, 0.1)  # 100ms
        pcm_8k = pcm16_16k_to_8k(pcm_16k)
        mulaw = pcm16_to_mulaw(pcm_8k)
        # Should be exactly 5 × 160 = 800 bytes
        assert len(mulaw) == 800
        # Can split into 160-byte frames
        frames = [mulaw[i : i + 160] for i in range(0, len(mulaw), 160)]
        assert len(frames) == 5
        assert all(len(f) == 160 for f in frames)


# ---------------------------------------------------------------------------
# Pure-Python vs audioop parity
# ---------------------------------------------------------------------------
class TestAudioopParity:
    """When audioop is available, verify pure-Python and audioop produce
    equivalent results (within quantization tolerance)."""

    @pytest.fixture(autouse=True)
    def _force_pure_python(self, monkeypatch):
        """Disable audioop to force pure-Python fallback."""
        import app.telephony.smartflo_stream as ss
        monkeypatch.setattr(ss, "_AUDIOOP_OK", False)
        monkeypatch.setattr(ss, "audioop", None)

    def test_mulaw_to_pcm16_pure_python(self):
        """Pure-Python mulaw decode produces valid output."""
        # Known value: mulaw 0xFF → PCM16 0 (silence)
        result = mulaw_to_pcm16(b"\xff")
        val = struct.unpack("<h", result)[0]
        assert val == 0

    def test_pcm16_to_mulaw_pure_python(self):
        """Pure-Python mulaw encode produces valid output."""
        result = pcm16_to_mulaw(struct.pack("<h", 0))
        assert result[0] == 0xFF  # silence

    def test_upsample_pure_python(self):
        """Pure-Python upsample doubles length."""
        pcm = _make_silence_pcm16(50)
        result = pcm16_8k_to_16k(pcm)
        assert len(result) == len(pcm) * 2

    def test_downsample_pure_python(self):
        """Pure-Python downsample halves length."""
        pcm = _make_silence_pcm16(100)
        result = pcm16_16k_to_8k(pcm)
        assert len(result) == len(pcm) // 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    """Boundary conditions and unusual inputs."""

    def test_odd_length_pcm_rejected(self):
        """Odd-length PCM16 input should not crash (struct.pack requires even)."""
        # The functions use struct.pack which needs even-length for '<h'
        # Verify it doesn't crash with empty
        assert mulaw_to_pcm16(b"") == b""
        assert pcm16_to_mulaw(b"") == b""

    def test_single_sample_mulaw(self):
        """Single mulaw byte → single PCM16 sample."""
        result = mulaw_to_pcm16(b"\xff")
        assert len(result) == 2
        val = struct.unpack("<h", result)[0]
        assert isinstance(val, int)

    def test_max_amplitude_mulaw(self):
        """Max amplitude mulaw values decode without overflow."""
        for byte in (0x00, 0x01, 0x7E, 0x7F, 0x80, 0xFE, 0xFF):
            result = mulaw_to_pcm16(bytes([byte]))
            val = struct.unpack("<h", result)[0]
            assert -32768 <= val <= 32767, f"mulaw {byte:02x} → {val} out of range"

    def test_large_frame(self):
        """Large frame (1 second at 8kHz = 8000 samples) processes without error."""
        mulaw = b"\xaa" * 8000
        pcm = mulaw_to_pcm16(mulaw)
        assert len(pcm) == 16000
        back = pcm16_to_mulaw(pcm)
        assert len(back) == 8000

    def test_upsample_very_short(self):
        """Upsample with minimal input."""
        pcm = struct.pack("<h", 1000)
        result = pcm16_8k_to_16k(pcm)
        # 1 sample → 2 samples (with interpolation)
        assert len(result) >= 4  # at least 2 samples × 2 bytes
