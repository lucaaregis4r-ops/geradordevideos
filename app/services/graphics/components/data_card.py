"""Data Card / Statistical Visualization Component.

Renders high-impact numbers, ratios, and comparative progress bars:
- Big number / metric headline
- Comparative ratio bar
- Source attribution footnote
- Clean dark UI tailored for 9:16 safe area
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


class DataCardComponent(BaseEditorialComponent):
    """Renders statistical comparison and progress bars in safe area."""

    def _render_canvas(self, params: dict) -> Image.Image:
        headline_metric = params.get("headline_metric", params.get("value", "72%"))
        title = params.get("title", params.get("label", "PROPORÇÃO DO VALOR"))
        description = params.get("description", params.get("context", "Parcela retida na etapa final de distribuição"))
        percentage = params.get("percentage", 0.72)
        source_note = params.get("source_note", "FONTE: DADOS DO ROTEIRO")
        accent_color = params.get("accent_color", "#38BDF8")
        bg_color = params.get("bg_color", "#080C14")

        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        card_w = 880
        card_h = 720
        card_x = (CANVAS_WIDTH - card_w) // 2
        card_y = SAFE_TOP + (SAFE_BOTTOM - SAFE_TOP - card_h) // 2

        # Card body
        draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=20,
            fill="#0F172A",
            outline="#1E293B",
            width=2,
        )

        # Title / Label
        label_font = get_default_font(28)
        draw.text((card_x + 50, card_y + 50), title.upper(), font=label_font, fill="#94A3B8")

        # Huge Metric Number
        metric_font = get_default_font(110)
        draw.text((card_x + 50, card_y + 110), headline_metric.strip(), font=metric_font, fill="#F8FAFC")

        # Description text
        desc_font = get_default_font(32)
        draw.text((card_x + 50, card_y + 260), description[:55], font=desc_font, fill="#CBD5E1")

        # Comparative Progress Bar
        bar_x = card_x + 50
        bar_y = card_y + 360
        bar_w = card_w - 100
        bar_h = 36

        # Bar background
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=18, fill="#1E293B")
        # Bar fill
        fill_w = max(36, int(bar_w * min(1.0, max(0.0, percentage))))
        draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=18, fill=accent_color)

        # Percentage label under bar
        pct_label = f"{int(percentage * 100)}% CONCLUÍDO"
        draw.text((bar_x, bar_y + 55), pct_label, font=get_default_font(24), fill=accent_color)

        # Divider
        draw.line([(card_x + 50, card_y + 540), (card_x + card_w - 50, card_y + 540)], fill="#1E293B", width=2)

        # Footnote
        draw.text((card_x + 50, card_y + 580), source_note.upper(), font=get_default_font(22), fill="#64748B")

        return canvas
