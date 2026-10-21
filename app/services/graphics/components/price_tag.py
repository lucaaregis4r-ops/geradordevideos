"""Price Tag / Tangible Receipt Component.

Renders a physical sticker or retail price tag within the 9:16 vertical safe area:
- Item name
- Large price typography
- Tangible barcode and batch metadata
- High contrast and physical card drop shadow
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


class PriceTagComponent(BaseEditorialComponent):
    """Renders a tangible price tag card centered in vertical safe area."""

    def _render_canvas(self, params: dict) -> Image.Image:
        price_text = params.get("price_text", params.get("price", "R$ 79,90"))
        item_title = params.get("item_title", params.get("item", "PRODUTO"))
        subtitle = params.get("subtitle", params.get("store"))
        badge_label = params.get("badge_label", "PREÇO DE VENDA")
        bg_color = params.get("bg_color", "#0D0E11")
        card_color = params.get("card_color", "#FAFAF9")
        accent_color = params.get("accent_color", "#E63946")

        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        # Card dimensions centered in safe area
        card_w = 840
        card_h = 760
        card_x = (CANVAS_WIDTH - card_w) // 2
        card_y = SAFE_TOP + (SAFE_BOTTOM - SAFE_TOP - card_h) // 2

        # 1. Subtle drop shadow
        shadow_offset = 18
        draw.rounded_rectangle(
            [
                card_x + shadow_offset,
                card_y + shadow_offset,
                card_x + card_w + shadow_offset,
                card_y + card_h + shadow_offset,
            ],
            radius=24,
            fill="#000000",
        )

        # 2. Main card body
        draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=24,
            fill=card_color,
            outline="#E5E7EB",
            width=3,
        )

        # 3. Top Accent Badge
        badge_font = get_default_font(26)
        badge_w = 280
        badge_h = 44
        badge_x = card_x + 50
        badge_y = card_y + 50
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=8,
            fill=accent_color,
        )
        draw.text(
            (badge_x + 18, badge_y + 8),
            badge_label.upper(),
            font=badge_font,
            fill="#FFFFFF",
        )

        # 4. Item Name
        title_font = get_default_font(38)
        draw.text(
            (card_x + 50, card_y + 120),
            item_title[:32].upper(),
            font=title_font,
            fill="#111827",
        )

        # 5. Huge Price
        price_font = get_default_font(90)
        draw.text(
            (card_x + 50, card_y + 200),
            price_text.strip(),
            font=price_font,
            fill="#0F172A",
        )

        # Divider line
        draw.line(
            [(card_x + 50, card_y + 350), (card_x + card_w - 50, card_y + 350)],
            fill="#D1D5DB",
            width=2,
        )

        # 6. Subtitle / Details if present
        if subtitle:
            sub_font = get_default_font(30)
            draw.text(
                (card_x + 50, card_y + 380),
                subtitle[:60],
                font=sub_font,
                fill="#4B5563",
            )

        # 7. Tangible Barcode Simulation
        barcode_y = card_y + 520
        barcode_x = card_x + 50
        draw.text((barcode_x, barcode_y - 30), "CÓDIGO DE BARRAS / SKU 0982-BR", font=get_default_font(20), fill="#9CA3AF")

        bar_pattern = [3, 1, 4, 2, 1, 3, 2, 4, 1, 2, 3, 1, 4, 2, 2, 1, 3, 4, 1, 2, 4, 2, 1, 3, 2, 1, 4, 3, 1, 2, 3, 1]
        cx = barcode_x
        for w in bar_pattern:
            draw.rectangle([cx, barcode_y, cx + w * 4, barcode_y + 90], fill="#1F2937")
            cx += (w * 4) + 6

        return canvas
