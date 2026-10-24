"""Typography and On-Screen Graphic Text Hierarchy Engine.

Implements the 3-level typographic hierarchy for 9:16 vertical videos:
- Level 1 (TITLE): High-impact keywords (64pt–88pt) in uppercase, high-contrast badge (e.g. "R$ 79,90", "QUEM FEZ ISSO?").
- Level 2 (EMPHASIS): Short emphasis phrases (40pt–52pt) on dark pill cards.
- Level 3 (CAPTION): Lower-third subtitle-style text (28pt–36pt).

Strictly enforces vertical Safe Area (1080x1920):
- Prohibited top zone: < 250px (covered by status bars, search, profile tabs).
- Prohibited bottom zone: > 1570px (covered by like/comment buttons, caption, audio pill).
- Side margins: >= 60px on each side (maximum width: 960px).
"""

from __future__ import annotations
import logging
from pathlib import Path
import subprocess
from typing import Optional, Tuple, Union

from PIL import Image, ImageColor, ImageDraw, ImageFont

from app.services.director.schemas import TextLevel
from .base_card import resolve_font_path

logger = logging.getLogger(__name__)

# Vertical 9:16 (1080x1920) Safe Area Boundaries
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

SAFE_TOP = 250
SAFE_BOTTOM = 1570
SAFE_LEFT = 60
SAFE_RIGHT = 1020
MAX_TEXT_WIDTH = SAFE_RIGHT - SAFE_LEFT  # 960px


def validate_box_in_safe_area(
    box: Tuple[int, int, int, int],
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
) -> Tuple[bool, str]:
    """Checks whether a bounding box (x1, y1, x2, y2) falls completely within safe area boundaries."""
    x1, y1, x2, y2 = box

    if x1 < SAFE_LEFT:
        return False, f"Left margin violation: x1={x1} < {SAFE_LEFT}"
    if x2 > SAFE_RIGHT:
        return False, f"Right margin violation: x2={x2} > {SAFE_RIGHT}"
    if y1 < SAFE_TOP:
        return False, f"Top header violation: y1={y1} < {SAFE_TOP}"
    if y2 > SAFE_BOTTOM:
        return False, f"Bottom controls violation: y2={y2} > {SAFE_BOTTOM}"

    return True, ""


class TypographyEngine:
    """Renders transparent PNG overlays with strict typographic hierarchy and safe area validation."""

    def __init__(
        self,
        font_bold: Optional[str] = None,
        font_medium: Optional[str] = None,
    ):
        self.font_bold_path = font_bold or resolve_font_path(prefer_bold=True)
        self.font_medium_path = font_medium or resolve_font_path(prefer_bold=False)

    def load_font(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        """Loads TrueType font at specified point size with fallback."""
        path = self.font_bold_path if bold else self.font_medium_path
        if path and Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
        return ImageFont.load_default()

    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
        """Wraps text so no line exceeds max_w."""
        words = text.split()
        if not words:
            return []

        lines: list[str] = []
        current: list[str] = []
        dummy = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy)

        for w in words:
            candidate = " ".join(current + [w])
            bbox = draw.textbbox((0, 0), candidate, font=font)
            line_w = bbox[2] - bbox[0]
            if line_w <= max_w or not current:
                current.append(w)
            else:
                lines.append(" ".join(current))
                current = [w]
        if current:
            lines.append(" ".join(current))
        return lines

    def render_overlay(
        self,
        text: str,
        level: Union[TextLevel, str] = TextLevel.TITLE,
        width: int = CANVAS_WIDTH,
        height: int = CANVAS_HEIGHT,
        position_y: Optional[int] = None,
    ) -> Image.Image:
        """Renders an RGBA transparent overlay containing the hierarchical text element."""
        if not text or not text.strip():
            return Image.new("RGBA", (width, height), (0, 0, 0, 0))

        raw_level = level.value if hasattr(level, "value") else str(level).lower()
        clean_text = text.strip()

        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        if raw_level == "title":
            font_size = 76
            font = self.load_font(font_size, bold=True)
            display_text = clean_text.upper()
            lines = self.wrap_text(display_text, font, max_w=MAX_TEXT_WIDTH - 80)
            if len(lines) > 2:
                # Shrink slightly if 3 lines
                font_size = 64
                font = self.load_font(font_size, bold=True)
                lines = self.wrap_text(display_text, font, max_w=MAX_TEXT_WIDTH - 80)

            # Colors: Warm Gold / Yellow with dark background badge
            text_color = (255, 215, 0, 255)  # Gold
            badge_bg = (15, 17, 23, 220)      # Deep dark
            border_color = (255, 215, 0, 200)

            pad_x = 40
            pad_y = 24
            line_spacing = 16

            # Compute multiline dimensions
            line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
            max_line_w = max((b[2] - b[0]) for b in line_bboxes)
            total_text_h = sum((b[3] - b[1]) for b in line_bboxes) + line_spacing * (len(lines) - 1)

            box_w = max_line_w + pad_x * 2
            box_h = total_text_h + pad_y * 2

            # Position vertically: Upper-middle (default y = 480)
            target_y = position_y if position_y is not None else 520
            # Clamp strictly to Safe Area
            target_y = max(SAFE_TOP + 20, min(SAFE_BOTTOM - box_h - 20, target_y))
            target_x = (width - box_w) // 2

            # Draw rounded badge
            draw.rounded_rectangle(
                [(target_x, target_y), (target_x + box_w, target_y + box_h)],
                radius=24,
                fill=badge_bg,
                outline=border_color,
                width=3,
            )

            # Draw lines centered
            curr_y = target_y + pad_y
            for line, bbox in zip(lines, line_bboxes):
                lw = bbox[2] - bbox[0]
                lx = (width - lw) // 2
                draw.text((lx, curr_y), line, font=font, fill=text_color)
                curr_y += (bbox[3] - bbox[1]) + line_spacing

        elif raw_level == "emphasis":
            font_size = 46
            font = self.load_font(font_size, bold=True)
            display_text = clean_text.upper()
            lines = self.wrap_text(display_text, font, max_w=MAX_TEXT_WIDTH - 60)

            text_color = (255, 255, 255, 255)
            badge_bg = (24, 28, 36, 210)
            border_color = (56, 189, 248, 180)  # Electric blue

            pad_x = 32
            pad_y = 20
            line_spacing = 12

            line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
            max_line_w = max((b[2] - b[0]) for b in line_bboxes)
            total_text_h = sum((b[3] - b[1]) for b in line_bboxes) + line_spacing * (len(lines) - 1)

            box_w = max_line_w + pad_x * 2
            box_h = total_text_h + pad_y * 2

            target_y = position_y if position_y is not None else 920
            target_y = max(SAFE_TOP + 20, min(SAFE_BOTTOM - box_h - 20, target_y))
            target_x = (width - box_w) // 2

            draw.rounded_rectangle(
                [(target_x, target_y), (target_x + box_w, target_y + box_h)],
                radius=18,
                fill=badge_bg,
                outline=border_color,
                width=2,
            )

            curr_y = target_y + pad_y
            for line, bbox in zip(lines, line_bboxes):
                lw = bbox[2] - bbox[0]
                lx = (width - lw) // 2
                draw.text((lx, curr_y), line, font=font, fill=text_color)
                curr_y += (bbox[3] - bbox[1]) + line_spacing

        else:
            # Caption (subtitle style in lower third of safe area)
            font_size = 34
            font = self.load_font(font_size, bold=False)
            lines = self.wrap_text(clean_text, font, max_w=MAX_TEXT_WIDTH - 40)

            text_color = (255, 255, 255, 255)
            badge_bg = (0, 0, 0, 180)

            pad_x = 24
            pad_y = 14
            line_spacing = 8

            line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
            max_line_w = max((b[2] - b[0]) for b in line_bboxes) if line_bboxes else 100
            total_text_h = sum((b[3] - b[1]) for b in line_bboxes) + line_spacing * (len(lines) - 1)

            box_w = max_line_w + pad_x * 2
            box_h = total_text_h + pad_y * 2

            target_y = position_y if position_y is not None else (SAFE_BOTTOM - box_h - 40)
            target_y = max(SAFE_TOP + 20, min(SAFE_BOTTOM - box_h - 10, target_y))
            target_x = (width - box_w) // 2

            draw.rounded_rectangle(
                [(target_x, target_y), (target_x + box_w, target_y + box_h)],
                radius=14,
                fill=badge_bg,
            )

            curr_y = target_y + pad_y
            for line, bbox in zip(lines, line_bboxes):
                lw = bbox[2] - bbox[0]
                lx = (width - lw) // 2
                draw.text((lx, curr_y), line, font=font, fill=text_color)
                curr_y += (bbox[3] - bbox[1]) + line_spacing

        return canvas

    def render_overlay_to_file(
        self,
        text: str,
        output_path: Union[str, Path],
        level: Union[TextLevel, str] = TextLevel.TITLE,
        width: int = CANVAS_WIDTH,
        height: int = CANVAS_HEIGHT,
        position_y: Optional[int] = None,
    ) -> Path:
        """Renders overlay and writes it directly to disk as PNG."""
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        img = self.render_overlay(
            text=text,
            level=level,
            width=width,
            height=height,
            position_y=position_y,
        )
        img.save(target, format="PNG")
        return target


def composite_overlay_to_clip(
    video_path: Union[str, Path],
    overlay_png_path: Union[str, Path],
    output_path: Union[str, Path],
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
    fps: int = 30,
    crop_mode: str = "center",
    source_in: float = 0.0,
    duration: float | None = None,
) -> Path:
    """Composites a transparent PNG overlay onto a video clip using FFmpeg."""
    src = Path(video_path).resolve()
    overlay = Path(overlay_png_path).resolve()
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise FileNotFoundError(f"Source video not found: {src}")
    if not overlay.exists():
        raise FileNotFoundError(f"Overlay PNG not found: {overlay}")

    from .framing import portrait_filter
    filter_complex = (
        f"[0:v]{portrait_filter(width, height, fps, crop_mode)}[bg];"
        f"[bg][1:v]overlay=0:0:eof_action=repeat:shortest=0[outv]"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(source_in), "-i", str(src),
        "-i", str(overlay),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        *(["-t", str(duration)] if duration is not None else []),
        str(target),
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target

