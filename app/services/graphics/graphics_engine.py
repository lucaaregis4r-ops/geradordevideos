"""Graphics Engine orchestrator for programmatic visual cards.

Routes abstract scenes (formulas, statistics, quotes, titles, concepts)
to dedicated programmatic renderers and generates smooth 9:16 vertical MP4 clips.
"""

from __future__ import annotations
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

from app.services.director.schemas import Scene, VisualType
from .base_card import BaseCardRenderer
from .components import (
    DataCardComponent,
    EditorialCropComponent,
    HistoricalArchiveComponent,
    PriceTagComponent,
    SplitScreenComponent,
)
from .formula_card import FormulaCardRenderer
from .number_card import NumberCardRenderer
from .quote_card import QuoteCardRenderer
from .text_card import TextCardRenderer
from .theme import get_theme

if TYPE_CHECKING:
    from app.services.media_ranker.schemas import MediaCandidate


class GraphicsEngine:
    """Central engine for rendering programmatic motion graphic cards."""

    GRAPHIC_TYPES = {
        VisualType.FORMULA.value,
        VisualType.NUMBER.value,
        VisualType.QUOTE.value,
        VisualType.GRAPHIC.value,
        VisualType.TITLE.value,
    }

    EDITORIAL_COMPONENTS = {
        "price_tag": PriceTagComponent,
        "split_screen": SplitScreenComponent,
        "historical_archive": HistoricalArchiveComponent,
        "data_card": DataCardComponent,
        "editorial_crop": EditorialCropComponent,
    }

    def __init__(self, cache_dir: Optional[Path | str] = None):
        self.cache_dir = Path(cache_dir or "storage/media_cache/graphics").resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_graphic_type(cls, visual_type: Union[VisualType, str, None]) -> bool:
        """Determines if a visual type is handled by the Graphics Engine."""
        if not visual_type:
            return False
        val = visual_type.value if hasattr(visual_type, "value") else str(visual_type).lower()
        return val in cls.GRAPHIC_TYPES

    @classmethod
    def is_graphic_scene(cls, scene: Scene) -> bool:
        """Checks if a scene should be rendered via the graphics engine."""
        if cls.is_graphic_type(scene.visual_type):
            return True
        if getattr(scene, "component_type", None) in cls.EDITORIAL_COMPONENTS:
            return True
        if getattr(scene, "visual_type", "") in cls.EDITORIAL_COMPONENTS:
            return True
        text = (scene.narration or "").lower()
        if any(marker in text for marker in ["[formula", "[graphic", "[quote", "[number", "[card", "[split", "[recibo", "[arquivo"]):
            return True
        return False

    def render_editorial_component(
        self,
        component_type: str,
        output_path: Optional[Path | str] = None,
        duration: float = 3.0,
        motion: str = "zoom_in",
        **kwargs,
    ) -> Path:
        """Renders an editorial visual component clip (price_tag, split_screen, archive, etc.)."""
        comp_cls = self.EDITORIAL_COMPONENTS.get(component_type, EditorialCropComponent)
        renderer = comp_cls()
        if output_path is None:
            token = f"{component_type}_{duration}_{kwargs}"
            safe_id = hashlib.md5(token.encode()).hexdigest()[:12]
            output_path = self.cache_dir / f"comp_{component_type}_{safe_id}.mp4"

        target_file = Path(output_path).resolve()
        if target_file.exists() and target_file.stat().st_size > 1000:
            return target_file

        return renderer.render_video(
            output_path=target_file,
            duration=duration,
            motion=motion,
            **kwargs,
        )

    def render_scene_card(
        self,
        scene: Scene,
        output_path: Optional[Path | str] = None,
        duration: float = 4.0,
        theme_name: Optional[str] = None,
        motion: str = "zoom_in",
    ) -> Path:
        """Renders an appropriate graphic card video for the given scene."""
        if output_path is None:
            safe_id = hashlib.md5(f"{scene.scene_id}_{scene.narration}_{duration}".encode()).hexdigest()[:12]
            output_path = self.cache_dir / f"card_{scene.scene_id}_{safe_id}.mp4"

        target_file = Path(output_path).resolve()
        if target_file.exists() and target_file.stat().st_size > 1000:
            return target_file

        vtype = scene.visual_type.value if hasattr(scene.visual_type, "value") else str(scene.visual_type)
        comp_type = getattr(scene, "component_type", None) or vtype

        # Route to editorial component if matched
        if comp_type in self.EDITORIAL_COMPONENTS:
            if comp_type == "price_tag":
                return self.render_editorial_component(
                    "price_tag",
                    output_path=target_file,
                    duration=duration,
                    price_text=scene.text_overlay or "R$ 79,90",
                    item_title=scene.intent or "PRODUTO",
                    subtitle=scene.narration[:60] if len(scene.narration) > 10 else None,
                )
            elif comp_type == "historical_archive":
                return self.render_editorial_component(
                    "historical_archive",
                    output_path=target_file,
                    duration=duration,
                    date_badge=scene.text_overlay or "DOCUMENTO HISTÓRICO",
                    caption=scene.intent or scene.narration[:60],
                )
            elif comp_type == "data_card":
                return self.render_editorial_component(
                    "data_card",
                    output_path=target_file,
                    duration=duration,
                    headline_metric=scene.text_overlay or "DADOS",
                    title=scene.intent or "ANÁLISE DE DADOS",
                    description=scene.narration[:60],
                )
            elif comp_type == "split_screen":
                return self.render_editorial_component(
                    "split_screen",
                    output_path=target_file,
                    duration=duration,
                    top_label=scene.intent or "PARTE 1",
                    bottom_label=scene.narration[:30],
                )
            elif comp_type == "editorial_crop":
                return self.render_editorial_component(
                    "editorial_crop",
                    output_path=target_file,
                    duration=duration,
                    title=scene.intent or "DETALHE",
                    caption=scene.text_overlay,
                )

        theme = get_theme(theme_name) if theme_name else None

        # Route by visual type
        if vtype == VisualType.FORMULA.value:
            renderer = FormulaCardRenderer(theme=theme or get_theme("chalkboard"))
            img = renderer.render_card_image(
                formula=scene.narration,
                title=scene.intent if scene.intent else "FÓRMULA FUNDAMENTAL",
                explanation=scene.narration,
            )
        elif vtype == VisualType.NUMBER.value:
            renderer = NumberCardRenderer(theme=theme or get_theme("neon_sports"))
            img = renderer.render_card_image(
                text=scene.narration,
                context_label=scene.intent if scene.intent else "MÉTRICA CHAVE",
                explanation=scene.narration,
            )
        elif vtype == VisualType.QUOTE.value:
            renderer = QuoteCardRenderer(theme=theme or get_theme("editorial"))
            img = renderer.render_card_image(text=scene.narration)
        elif vtype == VisualType.TITLE.value:
            renderer = TextCardRenderer(theme=theme or get_theme("sunset_burst"))
            img = renderer.render_card_image(
                title=scene.intent or scene.narration[:40],
                subtitle=scene.narration if len(scene.narration) > 40 else None,
                badge_label="🎬 CAPÍTULO",
            )
        else:
            # Default / Graphic / Concept card
            renderer = TextCardRenderer(theme=theme or get_theme("dark_modern"))
            img = renderer.render_card_image(
                title=scene.intent or "CONCEITO CHAVE",
                subtitle=scene.narration,
                badge_label="📌 INFOGRÁFICO",
            )

        # Convert image to video clip
        return renderer.image_to_video(
            image=img,
            output_path=target_file,
            duration=duration,
            motion=motion,
            fps=30,
        )

    def create_card_candidate(
        self,
        scene: Scene,
        duration: float = 4.0,
        theme_name: Optional[str] = None,
    ) -> MediaCandidate:
        """Renders the scene card and packages it into a top-priority MediaCandidate."""
        from app.services.media_ranker.schemas import MediaCandidate

        card_path = self.render_scene_card(
            scene=scene,
            duration=duration,
            theme_name=theme_name,
            motion="zoom_in",
        )

        return MediaCandidate(
            provider="graphics_engine",
            asset_id=f"card_{scene.scene_id}",
            query=scene.intent or scene.narration[:30],
            width=1080,
            height=1920,
            duration=duration,
            url=str(card_path),
            local_path=str(card_path),
            technical_score=1.0,
            semantic_score=0.98,
            final_score=0.99,
            source_page="Graphics Engine Programmatic Card",
        )
