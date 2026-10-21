"""Unit and integration tests for Sprint 5: EBU R128 Audio Mastering, Dynamic Ducking and Smoke Test."""

from pathlib import Path
import subprocess
import tempfile
import pytest

from app.services.audio.mastering import (
    DEFAULT_TARGET_LUFS,
    PHASE_MULTIPLIERS,
    build_adaptive_volume_expr,
    master_voice_track,
    measure_integrated_lufs,
    mix_voice_with_adaptive_bgm,
)


class TestAudioMasteringEBUR128:
    """Tests broadcast loudness standards and narrative phase automation."""

    @pytest.fixture
    def audio_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Create a 3-second test tone using ffmpeg lavfi
            raw_tone = tmp_path / "raw_tone.wav"
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                "-ar", "48000", "-ac", "2",
                str(raw_tone),
            ]
            subprocess.run(cmd, check=True)
            yield tmp_path, raw_tone

    def test_phase_multipliers_cover_all_presets(self):
        # Check that phases from all 4 presets are mapped
        expected_phases = [
            "aspiration", "commodity", "production", "labor", "reveal",
            "enigma", "mecanismo", "experimento", "implicacao", "conclusao",
            "tese", "contexto", "evidencia", "analise", "sintese",
            "hook_pop", "desconstrucao", "humor_literal", "plot_twist", "remix",
        ]
        for p in expected_phases:
            assert p in PHASE_MULTIPLIERS, f"Missing phase multiplier for '{p}'"
            mult = PHASE_MULTIPLIERS[p]
            assert 0.05 <= mult <= 1.0, f"Multiplier for '{p}' out of range: {mult}"

    def test_build_adaptive_volume_expr_handles_new_phases(self):
        segments = [
            {"start": 0.0, "end": 2.5, "phase": "enigma"},
            {"start": 2.5, "end": 5.0, "phase": "mecanismo"},
            {"start": 5.0, "end": 7.5, "phase": "conclusao"},
        ]
        expr = build_adaptive_volume_expr(segments, base_volume=0.20)
        assert "between(t,0.00,2.50)" in expr
        assert "between(t,2.50,5.00)" in expr
        assert "between(t,5.00,7.50)" in expr

    def test_master_voice_track_and_lufs_measurement(self, audio_dir):
        tmp_path, raw_tone = audio_dir
        mastered_wav = tmp_path / "mastered.wav"

        # Master tone to -14.0 LUFS
        res = master_voice_track(raw_tone, mastered_wav, target_lufs=-14.0)
        assert res.exists()
        assert res.stat().st_size > 1000

        # Measure LUFS
        measured = measure_integrated_lufs(mastered_wav)
        # Should be within ±1.5 LUFS of target -14.0 LUFS for synthetic tone
        assert abs(measured - (-14.0)) < 1.5, f"Measured LUFS {measured} deviated from -14.0 LUFS"

    def test_mix_voice_with_adaptive_bgm_execution(self, audio_dir):
        tmp_path, raw_tone = audio_dir
        # Create a 5-second background music tone
        bgm_wav = tmp_path / "bgm.wav"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=5",
            "-ar", "48000", "-ac", "2",
            str(bgm_wav),
        ]
        subprocess.run(cmd, check=True)

        mixed_out = tmp_path / "final_mix.wav"
        segments = [
            {"start": 0.0, "end": 2.0, "phase": "tese"},
            {"start": 2.0, "end": 4.0, "phase": "sintese"},
        ]
        result = mix_voice_with_adaptive_bgm(
            voice_path=raw_tone,
            bgm_path=bgm_wav,
            output_path=mixed_out,
            phase_segments=segments,
            base_volume=0.15,
        )
        assert result.exists()
        assert result.stat().st_size > 1000
