"""Editorial Components Package for Fábrica de Shorts.

Exports the 5 canonical editorial visual components:
1. PriceTagComponent: Physical price tag / retail receipt
2. SplitScreenComponent: Dual vertical split screen comparison
3. HistoricalArchiveComponent: Archival photo with date/location badge
4. DataCardComponent: Big metric and comparative progress bar
5. EditorialCropComponent: Letterboxed focal point crop with accent frame
"""

from .base_component import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
    SAFE_TOP,
    BaseEditorialComponent,
)
from .data_card import DataCardComponent
from .editorial_crop import EditorialCropComponent
from .historical_archive import HistoricalArchiveComponent
from .price_tag import PriceTagComponent
from .split_screen import SplitScreenComponent

__all__ = [
    "CANVAS_WIDTH",
    "CANVAS_HEIGHT",
    "SAFE_TOP",
    "SAFE_BOTTOM",
    "SAFE_LEFT",
    "SAFE_RIGHT",
    "BaseEditorialComponent",
    "PriceTagComponent",
    "SplitScreenComponent",
    "HistoricalArchiveComponent",
    "DataCardComponent",
    "EditorialCropComponent",
]
