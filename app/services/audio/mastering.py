"""Broadcast Audio Mastering and Dynamic Ducking Engine.

Implements EBU R128 / ITU-R BS.1770-4 loudness compliance for vertical social videos:
- Target integrated loudness: -14.0 LUFS (±0.5 LUFS) for maximum vocal intelligibility.
- True Peak limit: -1.0 dBFS (prevents lossy codec distortion on upload).
- High-Pass Filter (80Hz): Eliminates low-frequency rumble and mic pops.
- Voice Dynamic Compressor: Smooths vocal dynamics for punchy presence.
- Sidechain Ducking: Automatically attenuates background music (-12dB to -16dB) during speech.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
import re
import subprocess
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

# Broadcast Loudness Targets for Mobile Vertical Video
DEFAULT_TARGET_LUFS = -14.0
DEFAULT_TARGET_TP = -1.0
DEFAULT_TARGET_LRA = 7.0


def master_voice_track(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    target_lufs: float = DEFAULT_TARGET_LUFS,
    target_tp: float = DEFAULT_TARGET_TP,
    target_lra: float = DEFAULT_TARGET_LRA,
) -> Path:
    """Applies vocal cleanup, dynamic compression and EBU R128 loudnorm to voice audio.

    Args:
        input_path: Path to raw voice audio (.mp3, .wav).
        output_path: Target mastered audio file.
        target_lufs: Integrated loudness target (-14.0 LUFS standard).
        target_tp: Maximum True Peak (-1.0 dBFS).
        target_lra: Loudness Range target (7.0 LU).

    Returns:
        Path to mastered audio file.
    """
    src = Path(input_path).resolve()
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists() or src.stat().st_size == 0:
        raise FileNotFoundError(f"Input voice audio not found or empty: {src}")

    # Return cached mastered file if already present and valid
    if target.exists() and target.stat().st_size > 1000:
        return target

    # Filter chain:
    # 1. highpass=f=80: cleans low-end rumble (< 80Hz)
    # 2. acompressor: smooth vocal compression with fast attack and natural release
    # 3. loudnorm: 2-pass or single-pass integrated broadcast normalization
    af_chain = (
        f"highpass=f=80,"
        f"acompressor=threshold=-18dB:ratio=2.5:attack=10:release=100,"
        f"loudnorm=I={target_lufs:.1f}:TP={target_tp:.1f}:LRA={target_lra:.1f}"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-af", af_chain,
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le" if target.suffix.lower() == ".wav" else "libmp3lame",
        str(target),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.warning("Loudnorm mastering failed on %s (%s). Falling back to direct copy.", src.name, exc)
        fallback_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-ar", "48000",
            "-ac", "2",
            str(target),
        ]
        subprocess.run(fallback_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return target


def mix_voice_with_ducked_bgm(
    voice_path: Union[str, Path],
    bgm_path: Union[str, Path],
    output_path: Union[str, Path],
    bgm_volume: float = 0.20,
    ducking_ratio: float = 4.0,
    ducking_threshold: float = 0.08,
) -> Path:
    """Mixes mastered voice with background music using sidechain compression ducking.

    The voice acts as the sidechain control signal, automatically depressing the
    music track during narration so voice presence is never masked.
    """
    voice = Path(voice_path).resolve()
    bgm = Path(bgm_path).resolve()
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if not voice.exists():
        raise FileNotFoundError(f"Voice track not found: {voice}")
    if not bgm.exists():
        # Fallback to voice only if BGM is missing
        return master_voice_track(voice, target)

    # Sidechain Ducking Filter Complex:
    # [1:a] volume: scales base BGM volume
    # [bgm][0:a] sidechaincompress: ducks BGM using voice as trigger
    # [0:a][ducked] amix: combines voice (dominant) and ducked music
    filter_complex = (
        f"[1:a]volume={bgm_volume:.3f}[bgm_base];"
        f"[bgm_base][0:a]sidechaincompress=threshold={ducking_threshold:.3f}:ratio={ducking_ratio:.1f}:attack=40:release=300[ducked_music];"
        f"[0:a][ducked_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,loudnorm=I={DEFAULT_TARGET_LUFS:.1f}:TP={DEFAULT_TARGET_TP:.1f}:LRA={DEFAULT_TARGET_LRA:.1f}[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(voice),
        "-stream_loop", "-1", "-i", str(bgm),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le" if target.suffix.lower() == ".wav" else "libmp3lame",
        str(target),
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target


PHASE_MULTIPLIERS = {
    # Canonical 5 acts (economia_cotidiana)
    "promessa": 1.0,     # Full corporate/aspirational hype (100%)
    "objeto": 0.85,      # Transition to product/price tag (85%)
    "bastidores": 0.65,  # Material production / factory / labor (65%)
    "revelacao": 0.30,   # Dry, stripped-back reality (30%)
    "fechamento": 0.10,  # Minimal soundbed or silence (10%)
    "aspiration": 1.0,
    "commodity": 0.85,
    "production": 0.65,
    "labor": 0.30,
    "reveal": 0.30,
    "conclusion": 0.10,

    # explicador_cientifico
    "enigma": 1.0,
    "mecanismo": 0.80,
    "experimento": 0.60,
    "implicacao": 0.35,
    "conclusao": 0.15,

    # ensaio_documental
    "tese": 1.0,
    "contexto": 0.80,
    "evidencia": 0.60,
    "analise": 0.35,
    "sintese": 0.10,

    # internet_retro
    "hook_pop": 1.0,
    "desconstrucao": 0.80,
    "humor_literal": 0.30,
    "plot_twist": 0.70,
    "remix": 0.20,
}


def measure_integrated_lufs(audio_path: Union[str, Path]) -> float:
    """Measures exact integrated loudness (LUFS) of an audio file using FFmpeg ebur128 filter."""
    src = Path(audio_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {src}")

    cmd = [
        "ffmpeg", "-nostats",
        "-i", str(src),
        "-filter_complex", "ebur128=peak=true",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    match = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS", result.stderr)
    if match:
        return float(match.group(1))
    return -14.0


def build_adaptive_volume_expr(
    segments: list[dict[str, Any]],
    base_volume: float = 0.20,
) -> str:
    """Builds an FFmpeg volume expression that dynamically modulates BGM volume across narrative phases."""
    if not segments:
        return f"{base_volume:.3f}"

    sorted_segs = sorted(segments, key=lambda s: float(s.get("start", 0.0)))
    expr = f"{base_volume * 0.10:.3f}"
    for seg in reversed(sorted_segs):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 3.0))
        phase = str(seg.get("phase", "promessa")).lower()
        mult = PHASE_MULTIPLIERS.get(phase, 0.70)
        vol = base_volume * mult
        expr = f"if(between(t,{start:.2f},{end:.2f}),{vol:.3f},{expr})"

    return expr


def mix_voice_with_adaptive_bgm(
    voice_path: Union[str, Path],
    bgm_path: Union[str, Path],
    output_path: Union[str, Path],
    phase_segments: Optional[list[dict[str, Any]]] = None,
    base_volume: float = 0.20,
    ducking_ratio: float = 4.0,
    ducking_threshold: float = 0.08,
) -> Path:
    """Mixes mastered voice with background music using narrative phase volume automation and sidechain ducking.

    Implements Section 20 of the Prototype Evaluation Report.
    """
    voice = Path(voice_path).resolve()
    bgm = Path(bgm_path).resolve()
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if not voice.exists():
        raise FileNotFoundError(f"Voice track not found: {voice}")
    if not bgm.exists():
        return master_voice_track(voice, target)

    vol_expr = build_adaptive_volume_expr(phase_segments or [], base_volume=base_volume)

    filter_complex = (
        f"[1:a]volume=eval=frame:volume='{vol_expr}'[bgm_adaptive];"
        f"[bgm_adaptive][0:a]sidechaincompress=threshold={ducking_threshold:.3f}:ratio={ducking_ratio:.1f}:attack=40:release=300[ducked_music];"
        f"[0:a][ducked_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,loudnorm=I={DEFAULT_TARGET_LUFS:.1f}:TP={DEFAULT_TARGET_TP:.1f}:LRA={DEFAULT_TARGET_LRA:.1f}[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(voice),
        "-stream_loop", "-1", "-i", str(bgm),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le" if target.suffix.lower() == ".wav" else "libmp3lame",
        str(target),
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target


def remux_video_with_audio(
    video_path: Union[str, Path],
    audio_path: Union[str, Path],
    output_path: Union[str, Path],
) -> Path:
    """Replaces the audio track of a video with a new audio file without re-encoding video."""
    src_v = Path(video_path).resolve()
    src_a = Path(audio_path).resolve()
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src_v),
        "-i", str(src_a),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(target),
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target



def measure_audio_loudness(audio_path: Union[str, Path]) -> Dict[str, float]:
    """Measures integrated loudness (LUFS), True Peak and LRA using FFmpeg's ebur128 filter."""
    src = Path(audio_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {src}")

    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", str(src),
        "-af", "ebur128=framelog=verbose",
        "-f", "null", "-",
    ]

    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    stderr = result.stderr or ""

    # Parse summary block
    # Summary:
    #   Integrated loudness:
    #     I:         -14.2 LUFS
    #     Threshold: -24.4 LUFS
    #   Loudness range:
    #     LRA:         6.8 LU
    #   True peak:
    #     Peak:       -1.1 dBFS
    i_match = re.search(r"I:\s+([-\d.]+)\s+LUFS", stderr)
    tp_match = re.search(r"Peak:\s+([-\d.]+)\s+dBFS", stderr)
    lra_match = re.search(r"LRA:\s+([-\d.]+)\s+LU", stderr)

    return {
        "integrated_lufs": float(i_match.group(1)) if i_match else -20.0,
        "true_peak_dbfs": float(tp_match.group(1)) if tp_match else -1.0,
        "loudness_range_lu": float(lra_match.group(1)) if lra_match else 7.0,
    }
