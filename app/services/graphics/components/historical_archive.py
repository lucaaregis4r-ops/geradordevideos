"""Historical Archive / Archival Photo Component.

Treats historical photographs and evidence with document styling:
- Archival mount / matte inside safe area
- Date and location stamp badge (e.g. '1972 • BERLIM')
- Archival catalog index code
- Vintage tone / vignette contrast
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


class HistoricalArchiveComponent(BaseEditorialComponent):
    """Renders an archival document/photograph spotlight within safe area."""

    def _render_canvas(self, params: dict) -> Image.Image:
        image_source = params.get("image_source")
        year = params.get("year")
        date_badge = params.get("date_badge") or (f"{year} • DOCUMENTO HISTÓRICO" if year else "1968 • DOCUMENTO HISTÓRICO")
        caption = params.get("caption", "REGISTRO DE ARQUIVO")
        archive_id = params.get("archive_id", "ARQ-REF / 409-B")
        bg_color = params.get("bg_color", "#121214")

        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        # Archival matte inside Safe Area
        matte_w = SAFE_RIGHT - SAFE_LEFT  # 960px
        matte_h = SAFE_BOTTOM - SAFE_TOP  # 1320px
        matte_x = SAFE_LEFT
        matte_y = SAFE_TOP

        # Background archival paper border
        draw.rounded_rectangle(
            [matte_x, matte_y, matte_x + matte_w, matte_y + matte_h],
            radius=16,
            fill="#18181B",
            outline="#3F3F46",
            width=2,
        )

        # Top Header Bar: Archival Index
        header_font = get_default_font(24)
        draw.text((matte_x + 36, matte_y + 36), archive_id.upper(), font=header_font, fill="#A1A1AA")

        # Top Date Badge
        badge_font = get_default_font(24)
        badge_w = len(date_badge) * 16 + 30
        draw.rounded_rectangle(
            [matte_x + matte_w - badge_w - 36, matte_y + 30, matte_x + matte_w - 36, matte_y + 70],
            radius=6,
            fill="#C9A227",
        )
        draw.text(
            (matte_x + matte_w - badge_w - 20, matte_y + 38),
            date_badge.upper(),
            font=badge_font,
            fill="#121214",
        )

        # Photo Container inside matte
        photo_x = matte_x + 36
        photo_y = matte_y + 90
        photo_w = matte_w - 72  # 888px
        photo_h = matte_h - 220  # 1100px

        photo_img = None
        if image_source is not None:
            if isinstance(image_source, (str, Path)) and Path(image_source).exists():
                try:
                    with Image.open(image_source) as im:
                        photo_img = im.convert("RGB")
                except Exception:
                    pass
            elif isinstance(image_source, Image.Image):
                photo_img = image_source.convert("RGB")

        if photo_img:
            photo_resized = photo_img.resize((photo_w, photo_h), Image.Resampling.BILINEAR)
            canvas.paste(photo_resized, (photo_x, photo_y))
        else:
            # Vintage paper placeholder
            draw.rectangle([photo_x, photo_y, photo_x + photo_w, photo_y + photo_h], fill="#27272A")
            draw.text(
                (photo_x + photo_w // 2 - 120, photo_y + photo_h // 2),
                "[ FOTOGRAFIA DE ARQUIVO ]",
                font=get_default_font(28),
                fill="#71717A",
            )

        # Bottom Caption / Metadata Stamp
        caption_y = photo_y + photo_h + 30
        cap_font = get_default_font(32)
        draw.text((photo_x, caption_y), caption[:60].upper(), font=cap_font, fill="#F4F4F5")

        draw.line([(photo_x, caption_y + 45), (photo_x + 200, caption_y + 45)], fill="#C9A227", width=3)

        return canvas
