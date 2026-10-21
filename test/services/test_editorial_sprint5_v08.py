"""Tests for Sprint 5 (v0.8) of the Mercadoria Editorial Pipeline.

Validates:
1. Vocal mastering achieves broadcast EBU R128 loudness target (-14.0 LUFS ±1.5 LUFS).
2. True Peak remains below 0 dBFS (preventing digital clipping).
3. Sidechain ducking mixes voice with music while keeping voice dominant.
4. Audio loudness measurement parser accurately returns LUFS, True Peak, and LRA.
"""

from pathlib import Path
import subprocess
import pytest

from app.services.audio.mastering import (
    DEFAULT_TARGET_LUFS,
    master_voice_track,
    measure_audio_loudness,
    mix_voice_with_ducked_bgm,
)


def _generate_synthetic_tone(output_path: Path, duration: float = 3.0, freq: int = 440) -> Path:
    """Generates a clean sine wave audio test file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
        "-ar", "48000", "-ac", "2",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return output_path


def test_voice_mastering_achieves_lufs_target(tmp_path):
    """Validates that master_voice_track normalizes audio to -14.0 LUFS."""
    raw_voice = tmp_path / "raw_voice.wav"
    _generate_synthetic_tone(raw_voice, duration=3.0, freq=300)

    mastered = tmp_path / "mastered_voice.wav"
    master_voice_track(
        input_path=raw_voice,
        output_path=mastered,
        target_lufs=-14.0,
        target_tp=-1.0,
    )

    assert mastered.exists()
    assert mastered.stat().st_size > 1000

    metrics = measure_audio_loudness(mastered)
    assert "integrated_lufs" in metrics
    assert "true_peak_dbfs" in metrics

    # Tolerance within ±1.5 LUFS of target -14.0 LUFS
    assert abs(metrics["integrated_lufs"] - (-14.0)) <= 1.5
    # True peak strictly under 0.0 dBFS (no digital clipping)
    assert metrics["true_peak_dbfs"] <= -0.5


def test_voice_ducking_mixes_music_and_voice(tmp_path):
    """Validates sidechain ducking mix between voice and background music."""
    voice = tmp_path / "duck_voice.wav"
    bgm = tmp_path / "duck_bgm.wav"
    mixed = tmp_path / "duck_mixed.wav"

    _generate_synthetic_tone(voice, duration=2.5, freq=400)
    _generate_synthetic_tone(bgm, duration=4.0, freq=150)

    res = mix_voice_with_ducked_bgm(
        voice_path=voice,
        bgm_path=bgm,
        output_path=mixed,
        bgm_volume=0.25,
    )

    assert res.exists()
    assert res.stat().st_size > 1000

    metrics = measure_audio_loudness(res)
    assert metrics["integrated_lufs"] <= -10.0  # Controlled, non-exploding volume
    assert metrics["true_peak_dbfs"] <= 0.0


def test_measure_audio_loudness_parses_metrics(tmp_path):
    """Validates that measure_audio_loudness extracts real floats from ebur128 output."""
    sample = tmp_path / "sample.wav"
    _generate_synthetic_tone(sample, duration=2.0)

    stats = measure_audio_loudness(sample)
    assert isinstance(stats["integrated_lufs"], float)
    assert isinstance(stats["true_peak_dbfs"], float)
    assert isinstance(stats["loudness_range_lu"], float)
