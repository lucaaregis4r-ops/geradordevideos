"""Editorial Crop / Focused Framing Component.

Takes an image and composes it with clean editorial framing:
- Centers on subject with 9:16 letterbox/pillarbox matte
- Elegant accent frame lines
- Caption badge in safe area
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from .base_component import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
    SAFE_TOP,
    BaseEditorialComponent,
    get_default_font,
)


class EditorialCropComponent(BaseEditorialComponent):
    """Frames and centers media within safe area with editorial letterboxing."""

    def _render_canvas(self, params: dict) -> Image.Image:
        image_source = params.get("image_source")
        title = params.get("title", "DETALHE DO OBJETO")
        caption = params.get("caption", params.get("aspect_ratio"))
        accent_color = params.get("accent_color", "#E63946")
        bg_color = params.get("bg_color", "#0D0E11")

        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        frame_w = SAFE_RIGHT - SAFE_LEFT  # 960px
        frame_h = SAFE_BOTTOM - SAFE_TOP  # 1320px
        frame_x = SAFE_LEFT
        frame_y = SAFE_TOP

        # Load image if provided
        im = None
        if image_source is not None:
            if isinstance(image_source, (str, Path)) and Path(image_source).exists():
                try:
                    with Image.open(image_source) as loaded:
                        im = loaded.convert("RGB")
                except Exception:
                    pass
            elif isinstance(image_source, Image.Image):
                im = image_source.convert("RGB")

        if im:
            # Scale maintaining aspect ratio inside frame_w x (frame_h - 100)
            target_h = frame_h - 100
            im_ratio = im.width / im.height
            frame_ratio = frame_w / target_h

            if im_ratio > frame_ratio:
                # Wider: scale by width
                new_w = frame_w
                new_h = int(frame_w / im_ratio)
            else:
                # Taller: scale by height
                new_h = target_h
                new_w = int(target_h * im_ratio)

            resized = im.resize((new_w, new_h), Image.Resampling.BILINEAR)
            pos_x = frame_x + (frame_w - new_w) // 2
            pos_y = frame_y + 40 + (target_h - new_h) // 2
            canvas.paste(resized, (pos_x, pos_y))

            # Thin accent border around photo
            draw.rectangle([pos_x - 2, pos_y - 2, pos_x + new_w + 2, pos_y + new_h + 2], outline=accent_color, width=2)
        else:
            # Fallback frame placeholder
            draw.rectangle([frame_x, frame_y + 40, frame_x + frame_w, frame_y + frame_h - 60], fill="#1F2937")

        # Top Title Badge
        badge_font = get_default_font(24)
        draw.rounded_rectangle([frame_x, frame_y, frame_x + len(title) * 16 + 30, frame_y + 42], radius=6, fill=accent_color)
        draw.text((frame_x + 16, frame_y + 8), title.upper(), font=badge_font, fill="#FFFFFF")

        # Bottom Caption if provided
        if caption:
            draw.text((frame_x, frame_y + frame_h - 40), caption[:60].upper(), font=get_default_font(28), fill="#E5E7EB")

        return canvas
