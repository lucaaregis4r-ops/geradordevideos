"""Library of Congress moving image discovery with item-level rights review."""
import requests
from .base import MediaSourceProvider, ProviderCapabilities
from app.services.media_ranker.schemas import MediaCandidate


class LibraryOfCongressProvider(MediaSourceProvider):
    capabilities = ProviderCapabilities(("video",))
    name = "loc"

    def is_available(self):
        return True

    def search(self, query, media_type="video", aspect="portrait", limit=5):
        response = requests.get("https://www.loc.gov/film-and-videos/", params={"q":query, "fo":"json", "c":min(limit, 5)}, timeout=10)
        response.raise_for_status()
        candidates = []
        for item in response.json().get("results", []):
            source = item.get("id", "")
            files = [f for r in item.get("resources", []) for group in r.get("files", []) for f in group if isinstance(f, dict)]
            videos = [f for f in files if f.get("url", "").lower().endswith(".mp4")]
            if not videos:
                continue
            file = videos[0]
            candidates.append(MediaCandidate(provider=self.name, provider_asset_id=source,
                asset_id=f"loc_{source.rstrip('/').split('/')[-1]}", query=query,
                description=" ".join(item.get("description", [])), url=file["url"], source_page=source,
                width=int(file.get("width") or 0), height=int(file.get("height") or 0),
                license_id="; ".join(item.get("rights", [])), rights_status="rights_unknown"))
        return candidates
