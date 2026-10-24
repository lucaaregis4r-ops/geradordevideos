"""Validate the actual encoded export, not just the planned timeline."""
import json
from pathlib import Path
import re
import subprocess


def validate_export(path: str | Path, duration: float, fps: int = 30) -> dict:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                           capture_output=True, text=True, check=True, timeout=20)
    data = json.loads(probe.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    actual = float(data.get("format", {}).get("duration", 0))
    errors = []
    if video.get("width") != 1080 or video.get("height") != 1920:
        errors.append("invalid_export_dimensions")
    if not audio:
        errors.append("missing_export_audio")
    # AAC/MP3 priming adds small encoder padding; never accept a repeated narration scene.
    if abs(actual - duration) > max(0.15, 2 / fps):
        errors.append("export_duration_mismatch")
    decoded = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vf",
        "blackdetect=d=0.3:pix_th=0.10", "-f", "null", "-"], capture_output=True, text=True, timeout=180)
    if decoded.returncode != 0:
        errors.append("export_decode_failed")
    if re.search(r"black_duration:[0-9.]+", decoded.stderr):
        errors.append("export_black_frames")
    return {"passed": not errors, "errors": errors, "duration": actual, "expected_duration": duration}
