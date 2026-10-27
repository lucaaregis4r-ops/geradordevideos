"""NASA public image/video catalogue. Rights remain item-specific review metadata."""
from urllib.parse import quote
import requests
from .base import MediaSourceProvider, ProviderCapabilities
from app.services.media_ranker.schemas import MediaCandidate


class NASAProvider(MediaSourceProvider):
    capabilities = ProviderCapabilities(("image", "video"))
    name = "nasa"

    def is_available(self):
        return True

    def search(self, query, media_type="video", aspect="portrait", limit=5):
        response = requests.get("https://images-api.nasa.gov/search", params={"q":query, "media_type":media_type, "page_size": min(limit, 5)}, timeout=10)
        response.raise_for_status()
        candidates = []
        for item in response.json().get("collection", {}).get("items", []):
            data = item.get("data", [{}])[0]
            asset_id = data.get("nasa_id")
            if not asset_id:
                continue
            assets = requests.get(f"https://images-api.nasa.gov/asset/{quote(asset_id, safe='')}", timeout=10)
            assets.raise_for_status()
            suffix = (".mp4",) if media_type == "video" else (".jpg", ".png")
            urls = [v["href"] for v in assets.json().get("collection", {}).get("items", []) if v.get("href", "").lower().endswith(suffix)]
            if not urls:
                continue
            candidates.append(MediaCandidate(provider=self.name, provider_asset_id=asset_id,
                asset_id=f"nasa_{asset_id}", query=query, description=data.get("description", ""),
                url=urls[0], width=0, height=0, media_type=media_type,
                creator_name=data.get("photographer") or data.get("center", "NASA"),
                source_page=f"https://images.nasa.gov/details/{quote(asset_id, safe='')}",
                license_url="https://www.nasa.gov/nasa-brand-center/images-and-media/"))
        return candidates
