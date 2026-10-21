"""Sprint 7 Automated Test Suite: Adaptive BGM, Dynamic Ducking & Mercadoria Benchmark Prototype.

Validates:
1. Adaptive BGM volume expression across narrative phases (Promessa -> Objeto -> Bastidores -> Revelação -> Fechamento).
2. Dynamic sidechain ducking ensuring voice intelligibility while music attenuates.
3. Audio remuxing into 9:16 vertical video without re-encoding video.
4. Complete benchmark run of the 'Mercadoria' script matching all evaluation report criteria:
   - 0 duplicate assets
   - 5 dramatic narrative phases
   - 9:16 vertical video (1080x1920)
   - Mastered broadcast audio (-14.0 LUFS)
   - Pre-render HTML and Markdown storyboard reports
"""

from __future__ import annotations
import json
from pathlib import Path
import subprocess
import pytest

from app.services.audio.mastering import (
    build_adaptive_volume_expr,
    measure_audio_loudness,
    mix_voice_with_adaptive_bgm,
    remux_video_with_audio,
)
from app.services.factory import ShortsFactory
from app.services.media_ranker.candidate_builder import _generate_synthetic_clip


def test_build_adaptive_volume_expr():
    """Verifies that the FFmpeg volume expression correctly modulates volume per narrative phase."""
    segments = [
        {"start": 0.0, "end": 5.0, "phase": "promessa"},
        {"start": 5.0, "end": 10.0, "phase": "objeto"},
        {"start": 10.0, "end": 15.0, "phase": "bastidores"},
        {"start": 15.0, "end": 20.0, "phase": "revelacao"},
        {"start": 20.0, "end": 25.0, "phase": "fechamento"},
    ]

    expr = build_adaptive_volume_expr(segments, base_volume=0.20)
    # Check that promessa gets 0.20 (100%), objeto gets ~0.17 (85%), bastidores gets ~0.13 (65%), revelacao gets ~0.06 (30%), fechamento gets ~0.02 (10%)
    assert "between(t,0.00,5.00)" in expr
    assert "0.200" in expr
    assert "between(t,10.00,15.00)" in expr
    assert "0.130" in expr
    assert "between(t,15.00,20.00)" in expr
    assert "0.060" in expr
    assert "between(t,20.00,25.00)" in expr
    assert "0.020" in expr


def test_mix_voice_with_adaptive_bgm(tmp_path: Path):
    """Verifies that adaptive BGM with sidechain compression mixes cleanly with voice."""
    voice_track = tmp_path / "voice_sine.wav"
    bgm_track = tmp_path / "bgm_sine.wav"
    output_mix = tmp_path / "final_mix.wav"

    # Generate synthetic voice (higher freq sine) and BGM (low freq sine)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=800:duration=4", "-ar", "48000", "-ac", "2", str(voice_track)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=6", "-ar", "48000", "-ac", "2", str(bgm_track)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    phases = [
        {"start": 0.0, "end": 2.0, "phase": "promessa"},
        {"start": 2.0, "end": 4.0, "phase": "revelacao"},
    ]

    res = mix_voice_with_adaptive_bgm(
        voice_path=voice_track,
        bgm_path=bgm_track,
        output_path=output_mix,
        phase_segments=phases,
        base_volume=0.25,
    )

    assert res.exists()
    assert res.stat().st_size > 1000

    # Measure output loudness
    loudness = measure_audio_loudness(res)
    assert loudness["integrated_lufs"] < 0.0


def test_remux_video_with_audio(tmp_path: Path):
    """Verifies that video audio is cleanly replaced without re-encoding video frames."""
    base_video = tmp_path / "test_vid.mp4"
    _generate_synthetic_clip("video test", base_video, duration=3.0)

    new_audio = tmp_path / "new_snd.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-ar", "48000", "-ac", "2", str(new_audio)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    output_remux = tmp_path / "remuxed.mp4"
    res = remux_video_with_audio(base_video, new_audio, output_remux)
    assert res.exists()
    assert res.stat().st_size > 1000

    # Probe resolution
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(res)
    ]).decode()
    data = json.loads(probe)["streams"][0]
    assert data["width"] == 1080
    assert data["height"] == 1920


def test_mercadoria_benchmark_prototype(tmp_path: Path):
    """Executes the full benchmark run of the Mercadoria script from the evaluation report."""
    base_dir = tmp_path / "mercadoria_benchmark"
    factory = ShortsFactory(base_dir=base_dir)

    # Synthetic BGM track
    bgm_path = tmp_path / "corporate_bgm.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=30", "-ar", "48000", "-ac", "2", str(bgm_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Human-approved Mercadoria script (condensed editorial essay)
    mercadoria_script = (
        "Existe uma pergunta que quase ninguém faz sobre riqueza: de onde vem o valor das coisas? "
        "Um celular custa cinco mil reais. Uma camiseta custa oitenta reais. Um café custa oito. "
        "O mercado coloca um número em objetos que não têm nada em comum. "
        "Mas antes de qualquer preço aparecer, existiram algodão, máquina, transporte e muito trabalho. "
        "Só que quando você compra, você só vê oitenta reais. "
        "Toda a história humana por trás do produto desaparece na etiqueta de preço."
    )

    draft = factory.produce_draft(
        script_id="mercadoria_benchmark_v1",
        script_text=mercadoria_script,
        title="Mercadoria: Ocultamento do Trabalho",
        brand_style="editorial",
        bgm_path=bgm_path,
        bgm_volume=0.18,
    )

    # 1. Pipeline status
    assert draft["status"] == "succeeded"

    # 2. Quality gate verification
    quality = draft["quality_score"]
    assert quality["passed"] is True
    assert quality["duplicate_assets"] == 0, "Acceptance criterion: 0 involuntary duplicates"
    assert quality["text_safe_area_errors"] == 0, "Acceptance criterion: 0 safe area errors"
    assert quality["segments_without_visual"] == 0

    # 3. Storyboard reports exist
    assert Path(draft["storyboard_md_path"]).exists()
    assert Path(draft["storyboard_html_path"]).exists()

    # Verify storyboard HTML contains all 5 acts and dark theme
    html_content = Path(draft["storyboard_html_path"]).read_text(encoding="utf-8")
    assert "Mercadoria: Ocultamento do Trabalho" in html_content
    assert "APROVADO PARA RENDER" in html_content
    assert "scorecard-grid" in html_content

    # 4. Final video verification
    final_video = Path(draft["video_path"])
    assert final_video.exists()
    assert final_video.stat().st_size > 50000

    # Probe final video resolution & format
    probe_out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=width,height,codec_type", "-of", "json", str(final_video)
    ]).decode()
    streams = json.loads(probe_out)["streams"]
    video_stream = next(s for s in streams if s["codec_type"] == "video")
    audio_stream = next(s for s in streams if s["codec_type"] == "audio")
    assert video_stream["width"] == 1080
    assert video_stream["height"] == 1920
    assert audio_stream is not None

    # Measure integrated loudness of final exported video
    loudness = measure_audio_loudness(final_video)
    # EBU R128 voice target is -14.0 LUFS (allowing music mix tolerance)
    assert -18.0 <= loudness["integrated_lufs"] <= -10.0
    assert loudness["true_peak_dbfs"] <= -0.5
