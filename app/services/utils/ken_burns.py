"""Ken Burns Motion Generator for Static Images, Photos, Prints and Cards.

Converts static photos and graphics into dynamic 9:16 vertical MP4 video clips
with smooth cinematic camera movement (zoom-in, zoom-out, pan, tilt, static cover).
Ensures zero black borders on vertical screens and adds a silent audio track
so clips are 100% compliant with video concatenators and players.
"""

from __future__ import annotations
import hashlib
import logging
from pathlib import Path
import subprocess
from typing import Optional, Union

from PIL import Image

logger = logging.getLogger(__name__)


def create_ken_burns_clip(
    image_path: Union[str, Path],
    output_path: Union[str, Path],
    duration: float = 4.0,
    motion: str = "zoom_in",
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    max_scale: float = 1.15,
) -> Path:
    """Renders a static image as an animated vertical MP4 video clip.

    Args:
        image_path: Path to the source image (JPG, PNG, WEBP, GIF frame, etc.).
        output_path: Target .mp4 output file path.
        duration: Clip duration in seconds.
        motion: Camera motion type ('zoom_in', 'zoom_out', 'pan_up', 'pan_down', 'lateral', 'static').
        width: Output video width (default 1080).
        height: Output video height (default 1920).
        fps: Frames per second (default 30).
        max_scale: Maximum zoom multiplier for Ken Burns (default 1.15).

    Returns:
        Path to the generated MP4 file.
    """
    src = Path(image_path).resolve()
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists() or src.stat().st_size == 0:
        raise FileNotFoundError(f"Source image not found or empty: {src}")

    # Return cached render if already present and valid
    if target.exists() and target.stat().st_size > 1000:
        return target

    dur = max(0.5, float(duration))
    total_frames = max(1, int(dur * fps))
    motion_norm = motion.lower().strip() if motion else "zoom_in"

    # Pre-scale image to at least target resolution if needed to prevent pixelation
    # Compute filter chain for zoompan and aspect ratio adaptation
    # Ensure source covers the 9:16 frame without black bars
    base_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"

    # Calculate zoom step per frame
    zoom_step = (max_scale - 1.0) / float(total_frames)

    if motion_norm in ("zoom_in", "ken_burns"):
        motion_filter = (
            f"zoompan=z='min(zoom+{zoom_step:.6f},{max_scale:.3f})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps={fps}"
        )
    elif motion_norm == "zoom_out":
        motion_filter = (
            f"zoompan=z='if(lte(zoom,1.0),1.0,max(zoom-{zoom_step:.6f},1.0))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps={fps}"
        )
    elif motion_norm in ("pan_up", "tilt_up"):
        pan_step = 0.15 / float(total_frames)
        motion_filter = (
            f"zoompan=z='1.12':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='(ih-ih/zoom)*(1-on/{total_frames})':"
            f"d=1:s={width}x{height}:fps={fps}"
        )
    elif motion_norm in ("pan_down", "tilt_down"):
        motion_filter = (
            f"zoompan=z='1.12':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='(ih-ih/zoom)*(on/{total_frames})':"
            f"d=1:s={width}x{height}:fps={fps}"
        )
    elif motion_norm in ("lateral", "pan_right"):
        motion_filter = (
            f"zoompan=z='1.12':"
            f"x='(iw-iw/zoom)*(on/{total_frames})':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps={fps}"
        )
    else:
        # Static cover crop
        motion_filter = f"scale={width}:{height},setsar=1"

    vf = f"{base_filter},{motion_filter}"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", str(src),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{dur:.2f}",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        "-r", str(fps),
        str(target),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.warning(
            "Primary Ken Burns zoompan failed on %s (%s). Falling back to direct cover scale.",
            src.name, exc
        )
        # Fallback safe command without zoompan
        fallback_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", str(src),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{dur:.2f}",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            "-r", str(fps),
            str(target),
        ]
        subprocess.run(fallback_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return target


IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"})


def is_image_file(path: Union[str, Path]) -> bool:
    """Checks whether a given file path is an image based on its suffix."""
    try:
        return Path(path).suffix.lower() in IMAGE_EXTENSIONS
    except Exception:
        return False

