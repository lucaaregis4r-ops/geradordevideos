"""Archive/Prelinger discovery. Availability never implies clearance for reuse."""
from urllib.parse import quote
import requests
from .base import MediaSourceProvider, ProviderCapabilities
from app.services.media_ranker.schemas import MediaCandidate


class InternetArchiveProvider(MediaSourceProvider):
    capabilities = ProviderCapabilities(("video",))

    @property
    def name(self):
        return "internet_archive"

    def is_available(self):
        return True

    def resolve_asset(self, identifier):
        response = requests.get(f"https://archive.org/metadata/{quote(identifier, safe='')}", timeout=10)
        response.raise_for_status()
        item = response.json()
        files = [f for f in item.get("files", []) if str(f.get("name", "")).lower().endswith((".mp4", ".webm")) and not f.get("private")]
        if not files:
            raise ValueError("no_playable_derivative")
        # Prefer a download of practical size; technical validation follows locally.
        file = min(files, key=lambda f: int(f.get("size") or 2**63))
        return item.get("metadata", {}), file

    def search(self, query, media_type="video", aspect="portrait", limit=5):
        response = requests.get("https://archive.org/advancedsearch.php", params={
            "q": f'collection:prelinger AND mediatype:movies AND ({query})',
            "fl[]": "identifier", "rows": min(limit, 5), "output": "json"}, timeout=10)
        response.raise_for_status()
        candidates = []
        for result in response.json().get("response", {}).get("docs", []):
            identifier = result["identifier"]
            metadata, file = self.resolve_asset(identifier)
            license_url = metadata.get("licenseurl", "")
            if isinstance(license_url, list):
                license_url = license_url[0] if license_url else ""
            candidates.append(MediaCandidate(
                provider=self.name, provider_asset_id=identifier,
                asset_id=f"archive_{identifier}", query=query,
                description=str(metadata.get("description") or metadata.get("title") or ""),
                width=0, height=0, duration=0,
                url=f"https://archive.org/download/{quote(identifier, safe='')}/{quote(file['name'])}",
                source_page=f"https://archive.org/details/{quote(identifier, safe='')}",
                creator_name=str(metadata.get("creator", "")),
                license_url=license_url, license_id=license_url, rights_status="rights_unknown"))
        return candidates
