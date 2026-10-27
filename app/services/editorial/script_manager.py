"""Script Manager for Fábrica de Shorts.

Enforces human-in-the-loop script immutability:
- Human script mode (human_script = true): LLM is strictly prohibited from altering words.
- Version tracking: script_v001, script_v002, etc. Never overwrite.
- Cryptographic SHA-256 integrity verification.
- Metadata persistence in JSON storage.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Optional

from .directives import parse_directives, strip_directives


@dataclass(frozen=True)
class ScriptVersion:
    script_id: str
    version: int
    version_tag: str  # e.g., "script_v001"
    sha256: str
    raw_text: str
    clean_narration: str
    approved_at: str
    channel: str = "default"
    title: str = ""
    human_script: bool = True
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ScriptVersion:
        return cls(**data)


class ScriptManager:
    """Manages immutable script versions in local storage."""

    def __init__(self, storage_dir: str | Path = "storage/scripts"):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def _script_folder(self, script_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", script_id)
        folder = self.storage_dir / safe_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def get_latest_version_number(self, script_id: str) -> int:
        folder = self._script_folder(script_id)
        existing = list(folder.glob("v*.json"))
        if not existing:
            return 0
        versions = []
        for p in existing:
            m = re.match(r"^v(\d+)\.json$", p.name)
            if m:
                versions.append(int(m.group(1)))
        return max(versions) if versions else 0

    def save_script(
        self,
        script_id: str,
        raw_text: str,
        *,
        title: str = "",
        channel: str = "default",
        force_new_version: bool = False,
        metadata: Optional[dict] = None,
    ) -> ScriptVersion:
        """Stores a new script version if text changed, or returns existing if identical."""
        raw_clean = raw_text.strip()
        clean_narration, _ = parse_directives(raw_clean)
        text_hash = self._hash(clean_narration)

        latest_num = self.get_latest_version_number(script_id)
        if latest_num > 0 and not force_new_version:
            latest = self.get_version(script_id, latest_num)
            if latest and latest.sha256 == text_hash and latest.raw_text == raw_clean:
                # Text is identical to current version; preserve without duplicating
                return latest

        new_version_num = latest_num + 1
        version_tag = f"script_v{new_version_num:03d}"
        now_iso = datetime.now(timezone.utc).isoformat()

        script_version = ScriptVersion(
            script_id=script_id,
            version=new_version_num,
            version_tag=version_tag,
            sha256=text_hash,
            raw_text=raw_clean,
            clean_narration=clean_narration,
            approved_at=now_iso,
            channel=channel,
            title=title or script_id,
            human_script=True,
            metadata=metadata or {},
        )

        folder = self._script_folder(script_id)
        target_path = folder / f"v{new_version_num:03d}.json"
        with target_path.open("w", encoding="utf-8") as f:
            json.dump(script_version.to_dict(), f, ensure_ascii=False, indent=2)

        return script_version

    def get_version(self, script_id: str, version: int) -> Optional[ScriptVersion]:
        folder = self._script_folder(script_id)
        target_path = folder / f"v{version:03d}.json"
        if not target_path.exists():
            return None
        with target_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return ScriptVersion.from_dict(data)

    def get_latest(self, script_id: str) -> Optional[ScriptVersion]:
        latest_num = self.get_latest_version_number(script_id)
        if latest_num == 0:
            return None
        return self.get_version(script_id, latest_num)

    def list_versions(self, script_id: str) -> list[ScriptVersion]:
        folder = self._script_folder(script_id)
        files = sorted(folder.glob("v*.json"))
        results = []
        for f in files:
            with f.open("r", encoding="utf-8") as handle:
                results.append(ScriptVersion.from_dict(json.load(handle)))
        return results
