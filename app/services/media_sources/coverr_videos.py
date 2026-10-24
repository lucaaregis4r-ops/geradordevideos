"""Coverr video API adapter; uses configured credentials and download URLs."""
from .stock_videos import StockVideoProvider


class CoverrVideoProvider(StockVideoProvider):
    provider_name = "coverr"
