"""Base class and Safe Area constants for Editorial Visual Components.

Enforces Hard Constraint 4 from AGENTS.md:
- Top Forbidden Zone: < 250px (status bars, app headers)
- Bottom Forbidden Zone: > 1570px (subtitles, like/share buttons, profile)
- Side Margins: >= 60px (useful width: 960px, from x=60 to x=1020)
- Canvas: 1080 x 1920 (9:16 vertical portrait)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

SAFE_TOP = 250
SAFE_BOTTOM = 1570
SAFE_LEFT = 60
SAFE_RIGHT = 1020

SAFE_WIDTH = SAFE_RIGHT - SAFE_LEFT    # 960px
SAFE_HEIGHT = SAFE_BOTTOM - SAFE_TOP  # 1320px


def get_default_font(size: int = 40) -> ImageFont.ImageFont:
    """Attempts to load a clean sans-serif TrueType font, falling back to default."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in font_candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


class BaseEditorialComponent(ABC):
    """Abstract base class for high-impact 9:16 editorial visual components."""

    def render_image(
        self,
        output_path: Optional[Path | str] = None,
        metadata: Optional[dict] = None,
        **kwargs,
    ) -> Image.Image | Path:
        """Renders the component onto a 1080x1920 PIL Image, optionally saving to output_path."""
        meta = {}
        if metadata:
            meta.update(metadata)
        meta.update(kwargs)
        img = self._render_canvas(meta)
        if output_path is not None:
            out = Path(output_path).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            img.save(out)
            return out
        return img

    @abstractmethod
    def _render_canvas(self, params: dict) -> Image.Image:
        """Internal canvas rendering method to be implemented by components."""
        pass

    def render_video(
        self,
        output_path: Path | str,
        duration: float = 3.0,
        fps: int = 30,
        motion: str = "zoom_in",
        metadata: Optional[dict] = None,
        **kwargs,
    ) -> Path:
        """Renders the component image and animates it into a 9:16 MP4 video clip."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        meta = {}
        if metadata:
            meta.update(metadata)
        meta.update(kwargs)

        img = self._render_canvas(meta)
        temp_img = out.parent / f"temp_{out.stem}.png"
        img.save(temp_img)

        # Generate smooth zoom using ffmpeg zoompan filter within safe area
        zoom_expr = "min(zoom+0.0015,1.08)" if motion == "zoom_in" else "max(1.08-0.0015*on,1.0)"
        frames_count = int(duration * fps)

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(temp_img),
            "-vf", f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames_count}:s=1080x1920:fps={fps}",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=30)
        finally:
            if temp_img.exists():
                temp_img.unlink()

        return out
