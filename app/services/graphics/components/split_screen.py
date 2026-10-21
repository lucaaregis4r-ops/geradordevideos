"""Split Screen / Dual Parallel Comparison Component.

Composes two visual planes vertically in 9:16 portrait:
- Top Plane (y: 250 to 910)
- Bottom Plane (y: 910 to 1570)
- Accent divider bar with optional comparison badges
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


class SplitScreenComponent(BaseEditorialComponent):
    """Renders dual vertical split screen comparison within safe area."""

    def _render_canvas(self, params: dict) -> Image.Image:
        top_image = params.get("top_image")
        bottom_image = params.get("bottom_image")
        top_label = params.get("top_label", params.get("label_top", "PLANO A"))
        bottom_label = params.get("bottom_label", params.get("label_bottom", "PLANO B"))
        accent_color = params.get("accent_color", "#E63946")
        bg_color = params.get("bg_color", "#0D0E11")

        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        mid_y = SAFE_TOP + (SAFE_BOTTOM - SAFE_TOP) // 2  # ~910px
        top_rect = (SAFE_LEFT, SAFE_TOP, SAFE_RIGHT, mid_y - 6)
        bot_rect = (SAFE_LEFT, mid_y + 6, SAFE_RIGHT, SAFE_BOTTOM)

        pane_w = SAFE_RIGHT - SAFE_LEFT  # 960px
        pane_h = (SAFE_BOTTOM - SAFE_TOP) // 2 - 6  # 654px

        def _load_and_fit(src, target_w, target_h, default_color):
            if src is not None:
                if isinstance(src, (str, Path)) and Path(src).exists():
                    try:
                        with Image.open(src) as im:
                            return im.convert("RGB").resize((target_w, target_h), Image.Resampling.BILINEAR)
                    except Exception:
                        pass
                elif isinstance(src, Image.Image):
                    return src.convert("RGB").resize((target_w, target_h), Image.Resampling.BILINEAR)
            # Fallback color pane
            fallback = Image.new("RGB", (target_w, target_h), color=default_color)
            return fallback

        top_im = _load_and_fit(top_image, pane_w, pane_h, "#1E293B")
        bot_im = _load_and_fit(bottom_image, pane_w, pane_h, "#0F172A")

        canvas.paste(top_im, (SAFE_LEFT, SAFE_TOP))
        canvas.paste(bot_im, (SAFE_LEFT, mid_y + 6))

        # Sharp Accent Divider Bar
        draw.rectangle([SAFE_LEFT, mid_y - 4, SAFE_RIGHT, mid_y + 4], fill=accent_color)

        # Top Badge
        if top_label:
            font = get_default_font(28)
            draw.rounded_rectangle([SAFE_LEFT + 24, SAFE_TOP + 24, SAFE_LEFT + 24 + len(top_label) * 20 + 30, SAFE_TOP + 74], radius=8, fill="#000000CC")
            draw.text((SAFE_LEFT + 40, SAFE_TOP + 34), top_label.upper(), font=font, fill="#FFFFFF")

        # Bottom Badge
        if bottom_label:
            font = get_default_font(28)
            draw.rounded_rectangle([SAFE_LEFT + 24, mid_y + 24, SAFE_LEFT + 24 + len(bottom_label) * 20 + 30, mid_y + 74], radius=8, fill="#000000CC")
            draw.text((SAFE_LEFT + 40, mid_y + 34), bottom_label.upper(), font=font, fill="#FFFFFF")

        return canvas
