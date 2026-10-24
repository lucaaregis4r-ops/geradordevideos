"""Smart Library (Acervo Inteligente).

Manages reusable local assets with semantic tags and approval history.
In future productions, approved assets are matched first before querying external stock.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional

from .schemas import MediaCandidate


@dataclass
class LibraryAsset:
    asset_id: str
    filename: str
    local_path: str
    tags: List[str]
    intent: str = ""
    approved: bool = True
    use_count: int = 1
    last_used: str = ""
    width: int = 1080
    height: int = 1920
    duration: float = 5.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LibraryAsset:
        return cls(**data)


class SmartLibrary:
    def __init__(self, library_dir: str | Path = "storage/media_cache"):
        self.library_dir = Path(library_dir).resolve()
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.library_dir / "catalog.json"
        self._assets: Dict[str, LibraryAsset] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        if self.catalog_path.exists():
            try:
                with self.catalog_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("assets", []):
                        asset = LibraryAsset.from_dict(item)
                        if Path(asset.local_path).exists():
                            self._assets[asset.asset_id] = asset
            except Exception:
                self._assets = {}

    def _save_catalog(self) -> None:
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "assets": [a.to_dict() for a in self._assets.values()],
        }
        with self.catalog_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def register_approved_asset(
        self,
        media_path: str | Path,
        tags: List[str],
        intent: str = "",
        asset_id: Optional[str] = None,
        duration: float = 5.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LibraryAsset:
        """Indexes an approved media clip into the smart library."""
        src_file = Path(media_path).resolve()
        if not src_file.exists():
            raise FileNotFoundError(f"Source media '{media_path}' not found")

        aid = asset_id or src_file.stem
        dest_file = self.library_dir / f"{aid}{src_file.suffix}"

        # Copy to managed library folder if not already inside it
        if src_file != dest_file:
            shutil.copyfile(src_file, dest_file)

        now_iso = datetime.now(timezone.utc).isoformat()
        normalized_tags = [t.lower().strip() for t in tags if t.strip()]

        existing = self._assets.get(aid)
        if existing:
            existing.use_count += 1
            existing.last_used = now_iso
            for t in normalized_tags:
                if t not in existing.tags:
                    existing.tags.append(t)
            asset = existing
        else:
            asset = LibraryAsset(
                asset_id=aid,
                filename=dest_file.name,
                local_path=str(dest_file),
                tags=normalized_tags,
                intent=intent,
                approved=True,
                use_count=1,
                last_used=now_iso,
                duration=duration,
            )
            self._assets[aid] = asset

        from .asset_catalog import _measure_media
        asset.width, asset.height, measured = _measure_media(dest_file)
        asset.duration = measured or duration
        if metadata:
            asset.metadata.update(metadata)
        self._save_catalog()
        return asset

    def search_library(
        self,
        query: str,
        target_duration: float = 4.0,
        min_match_ratio: float = 0.3,
    ) -> List[MediaCandidate]:
        """Searches the approved library for matching assets."""
        tokens = set(re.findall(r"\w+", query.lower()))
        if not tokens:
            return []

        matched: List[MediaCandidate] = []
        for asset in self._assets.values():
            if not asset.approved or asset.metadata.get("rights_status") == "blocked_for_this_use" or not Path(asset.local_path).exists():
                continue

            asset_tokens = set(asset.tags) | set(re.findall(r"\w+", asset.intent.lower()))
            overlap = tokens.intersection(asset_tokens)
            if overlap:
                ratio = len(overlap) / len(tokens)
                if ratio >= min_match_ratio or len(overlap) >= 2:
                    matched.append(
                        MediaCandidate(
                            provider="smart_library",
                            asset_id=asset.asset_id,
                            query=query,
                            description=asset.intent, tags=list(asset.tags),
                            source_page=asset.metadata.get("source_page", ""),
                            creator_name=asset.metadata.get("creator_name", ""),
                            license_id=asset.metadata.get("license_id", ""),
                            license_url=asset.metadata.get("license_url", ""),
                            rights_status=asset.metadata.get("rights_status", "rights_unknown"),
                            media_type="image" if Path(asset.local_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else "video",
                            width=asset.width,
                            height=asset.height,
                            duration=asset.duration,
                            url=f"file://{asset.local_path}",
                            local_path=asset.local_path,
                            technical_score=0.95,
                            semantic_score=round(min(1.0, 0.7 + (ratio * 0.3)), 2),
                            final_score=0.95,
                        )
                    )

        # Sort by final score descending
        return sorted(matched, key=lambda c: c.final_score, reverse=True)
