"""Asset Catalog — Persistent transactional registry for all media assets.

Maintains an SQLite database of all downloaded and cached assets with:
- Measured technical metadata (width, height, duration via ffprobe / PIL)
- Content hash (SHA-256) for cross-provider deduplication
- Provenance and rights (author, public source page, license)
- Production usage history
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PIL import Image

from .schemas import MediaCandidate


def _compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _measure_media(file_path: Path) -> Tuple[int, int, float]:
    """Measures actual width, height, and duration of an image or video file.

    Never guesses or defaults blindly to 1080x1920.
    """
    ext = file_path.suffix.lower()

    # Image measurement using PIL
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        try:
            with Image.open(file_path) as img:
                w, h = img.size
                return w, h, 0.0
        except Exception as e:
            logger.warning("PIL measurement failed for {}: {}", file_path, e)

    # Video or fallback measurement using ffprobe
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration:format=duration",
        "-of", "json",
        str(file_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        w, h, dur = 0, 0, 0.0
        if streams:
            st = streams[0]
            w = int(st.get("width") or 0)
            h = int(st.get("height") or 0)
            dur = float(st.get("duration") or 0.0) if st.get("duration") != "N/A" else 0.0
        if dur == 0.0 and "format" in data:
            dur = float(data["format"].get("duration") or 0.0)
        return w, h, dur
    except Exception as e:
        logger.warning("ffprobe measurement failed for {}: {}", file_path, e)
        return 0, 0, 0.0


class AssetCatalog:
    """SQLite-backed persistent registry for all media files."""

    def __init__(self, db_path: str | Path = "storage/asset_catalog.db"):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrent access
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    provider TEXT,
                    provider_asset_id TEXT,
                    media_type TEXT,
                    width INTEGER,
                    height INTEGER,
                    duration REAL,
                    content_hash TEXT,
                    perceptual_hash TEXT,
                    local_path TEXT,
                    source_page TEXT,
                    creator_name TEXT,
                    creator_url TEXT,
                    license_id TEXT,
                    license_url TEXT,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    use_count INTEGER DEFAULT 1
                );
                """
            )
            conn.execute("CREATE TABLE IF NOT EXISTS asset_editorial (asset_id TEXT PRIMARY KEY, metadata TEXT NOT NULL)")
            try:
                conn.execute("ALTER TABLE assets ADD COLUMN perceptual_hash TEXT;")
            except Exception:
                pass  # Column already exists
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assets_hash ON assets(content_hash);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assets_phash ON assets(perceptual_hash);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assets_provider ON assets(provider, provider_asset_id);"
            )

    def register_downloaded_asset(
        self,
        candidate: MediaCandidate,
        local_file: Path,
    ) -> MediaCandidate:
        """Registers a downloaded local media file into the catalog.

        Inspects actual dimensions and duration, computes content_hash,
        and saves complete provenance.
        """
        if not local_file.exists():
            return candidate

        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO asset_editorial VALUES (?, ?)",
                         (candidate.asset_id, json.dumps({"description": candidate.description,
                          "tags": candidate.tags, "rights_status": candidate.rights_status,
                          "semantic_status": candidate.semantic_status,
                          "evaluation_context": candidate.evaluation_context})))
        content_hash = _compute_sha256(local_file)
        w, h, dur = _measure_media(local_file)

        # Check if asset with identical content hash is already registered
        existing = self.get_by_hash(content_hash)
        if existing:
            self.record_usage(existing["asset_id"])
            candidate.asset_id = existing["asset_id"]
            candidate.content_hash = content_hash
            candidate.perceptual_hash = existing.get("perceptual_hash") or candidate.perceptual_hash
            candidate.width = existing["width"]
            candidate.height = existing["height"]
            candidate.duration = existing["duration"]
            candidate.local_path = existing["local_path"]
            return candidate

        # Extract perceptual hash and visual metrics if not already present
        if not candidate.perceptual_hash:
            try:
                from .visual_evaluator import VisualEvaluator
                evaluator = VisualEvaluator()
                metrics = evaluator.evaluate_media(
                    local_file,
                    media_type=candidate.media_type,
                    duration=dur,
                )
                if metrics.perceptual_hash:
                    candidate.perceptual_hash = metrics.perceptual_hash
                candidate.visual_quality_score = metrics.quality_score
            except Exception as e:
                logger.debug("Visual evaluation during registration skipped: {}", e)

        candidate.content_hash = content_hash
        candidate.width = w
        candidate.height = h
        if dur > 0.0:
            candidate.duration = dur
        candidate.local_path = str(local_file.resolve())

        asset_id = candidate.asset_id or f"{candidate.provider}_{content_hash[:12]}"
        candidate.asset_id = asset_id

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assets (
                    asset_id, provider, provider_asset_id, media_type,
                    width, height, duration, content_hash, perceptual_hash, local_path,
                    source_page, creator_name, creator_url, license_id, license_url,
                    last_used_at, use_count
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    CURRENT_TIMESTAMP,
                    COALESCE((SELECT use_count + 1 FROM assets WHERE asset_id = ?), 1)
                );
                """,
                (
                    asset_id,
                    candidate.provider,
                    candidate.provider_asset_id or candidate.asset_id,
                    candidate.media_type,
                    w,
                    h,
                    candidate.duration,
                    content_hash,
                    candidate.perceptual_hash,
                    candidate.local_path,
                    candidate.source_page,
                    candidate.creator_name,
                    candidate.creator_url,
                    candidate.license_id,
                    candidate.license_url,
                    asset_id,
                ),
            )
            conn.commit()

        logger.info(
            "Registered asset {} into catalog: {}x{} dur={:.1f}s hash={} phash={}",
            asset_id, w, h, candidate.duration, content_hash[:8], candidate.perceptual_hash[:8]
        )
        return candidate

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,))
            row = cur.fetchone()
            if not row:
                return None
            editorial = conn.execute("SELECT metadata FROM asset_editorial WHERE asset_id = ?", (asset_id,)).fetchone()
            return {**dict(row), **(json.loads(editorial[0]) if editorial else {})}

    def get_by_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM assets WHERE content_hash = ?", (content_hash,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_by_perceptual_hash(
        self, perceptual_hash: str, max_distance: int = 8
    ) -> Optional[Dict[str, Any]]:
        """Finds an existing asset in the catalog whose perceptual hash is within max_distance."""
        if not perceptual_hash:
            return None
        from .perceptual_hash import hamming_distance
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM assets WHERE perceptual_hash IS NOT NULL AND perceptual_hash != '';"
            )
            for row in cur.fetchall():
                row_dict = dict(row)
                row_phash = row_dict.get("perceptual_hash") or ""
                if row_phash and hamming_distance(perceptual_hash, row_phash) <= max_distance:
                    return row_dict
        return None

    def record_usage(self, asset_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE assets
                SET use_count = use_count + 1, last_used_at = CURRENT_TIMESTAMP
                WHERE asset_id = ?;
                """,
                (asset_id,),
            )
            conn.commit()

    def list_assets(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM assets ORDER BY last_used_at DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]
