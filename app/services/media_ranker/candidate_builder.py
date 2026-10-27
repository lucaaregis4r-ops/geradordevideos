"""Candidate builder connecting queries to providers and local media acervo.

Coordinates:
1. Pexels (if API key available)
2. Pixabay (if API key available)
3. Open photo and archive providers
4. Local Smart Library (storage/media_cache/)
5. Synthetic Video Generator fallback (ensures pipeline never fails for tests/prototypes)
"""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, List, Optional

from app.config import config
from app.models.schema import VideoAspect
from app.services import material
from loguru import logger
from .schemas import MediaCandidate


def _generate_synthetic_clip(
    query: str,
    output_path: Path,
    duration: float = 5.0,
    color: str = "random",
) -> None:
    """Generates a clean 1080x1920 9:16 test video using FFmpeg lavfi."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 0:
        return

    # Derive deterministic color from query hash
    colors = ["#1a2a6c", "#b21f1f", "#fdbb2d", "#11998e", "#38ef7d", "#0f2027", "#203a43", "#2c5364", "#4b6cb7", "#182848"]
    color_idx = int(hashlib.md5(query.encode()).hexdigest(), 16) % len(colors)
    chosen_color = colors[color_idx]

    clean_label = query[:25].replace("'", "").replace(":", "")

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c={chosen_color}:s=1080x1920:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(duration),
        "-vf", f"drawtext=text='{clean_label}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        # Fallback without text overlay if drawtext font issue occurs
        cmd_plain = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"color=c={chosen_color}:s=1080x1920:r=30",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(output_path),
        ]
        subprocess.run(cmd_plain, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _generate_synthetic_photo_clip(
    query: str,
    output_path: Path,
    duration: float = 5.0,
    motion: str = "zoom_in",
) -> None:
    """Generates an aesthetic photographic synthetic plate with Ken Burns motion."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 1000:
        return

    from PIL import Image, ImageDraw
    from app.services.utils.ken_burns import create_ken_burns_clip

    # Create an elegant textured plate (1440x2560 for crisp Ken Burns zoom)
    w, h = 1440, 2560
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)

    colors = [
        ((26, 42, 108), (178, 31, 31)),
        ((17, 153, 142), (56, 239, 125)),
        ((15, 32, 39), (44, 83, 100)),
        ((75, 108, 183), (24, 40, 72)),
        ((35, 37, 38), (65, 67, 69)),
    ]
    idx = int(hashlib.md5(query.encode()).hexdigest(), 16) % len(colors)
    c1, c2 = colors[idx]

    for y in range(h):
        ratio = y / float(h)
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    tmp_plate = output_path.parent / f"_tmp_{output_path.stem}.png"
    img.save(tmp_plate)

    try:
        create_ken_burns_clip(
            image_path=tmp_plate,
            output_path=output_path,
            duration=duration,
            motion=motion,
            width=1080,
            height=1920,
        )
    finally:
        tmp_plate.unlink(missing_ok=True)


def _generate_synthetic_meme_clip(
    query: str,
    output_path: Path,
    duration: float = 1.2,
) -> None:
    """Generates a high-contrast comedic break card / ironic meme clip (Section 11).

    Features bold satirical framing, punchy colors, and hard cuts without Ken Burns zoom.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 1000:
        return

    from PIL import Image, ImageDraw
    w, h = 1080, 1920
    img = Image.new("RGB", (w, h), color=(14, 14, 16))
    draw = ImageDraw.Draw(img)

    # Accent warning border / frame
    border_margin = 80
    draw.rounded_rectangle(
        [(border_margin, 700), (w - border_margin, 1220)],
        radius=28,
        fill=(250, 180, 30),
    )
    # Inner dark contrast plate
    draw.rounded_rectangle(
        [(border_margin + 12, 712), (w - border_margin - 12, 1208)],
        radius=20,
        fill=(18, 18, 20),
    )

    clean_label = query.upper()[:40].replace("'", "")
    # Header tag
    draw.text((w // 2, 790), "⚠️  METÁFORA LITERAL  ⚠️", fill=(250, 180, 30), anchor="mm")
    # Punchline
    draw.text((w // 2, 960), clean_label, fill=(255, 255, 255), anchor="mm")

    tmp_png = output_path.parent / f"_tmp_meme_{output_path.stem}.png"
    img.save(tmp_png)

    # Hard cut, no Ken Burns zoom
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", str(tmp_png),
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", f"{duration:.2f}",
        "-vf", "scale=1080:1920,setsar=1,fps=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        tmp_png.unlink(missing_ok=True)


class CandidateBuilder:
    def __init__(
        self,
        media_cache_dir: str | Path = "storage/media_cache",
        sources_manager: Optional[Any] = None,
    ):
        self.media_cache_dir = Path(media_cache_dir).resolve()
        self.media_cache_dir.mkdir(parents=True, exist_ok=True)
        if sources_manager is None:
            from app.services.media_sources.manager import MediaSourcesManager
            self.sources_manager = MediaSourcesManager()
        else:
            self.sources_manager = sources_manager

    def search_local_library(
        self, query: str, target_duration: float = 5.0, preferred_motion: str = "zoom_in"
    ) -> List[MediaCandidate]:
        """Searches local media in storage/media_cache/ (videos and images)."""
        results: List[MediaCandidate] = []
        tokens = [t.lower() for t in query.split() if len(t) > 2]
        if not tokens:
            return results

        # Preserve physical media types. Ken Burns belongs to assembly, not retrieval.
        from .asset_catalog import _measure_media
        for asset in self.media_cache_dir.iterdir():
            if asset.suffix.lower() not in {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"}:
                continue
            if not any(token in asset.stem.lower() for token in tokens):
                continue
            width, height, duration = _measure_media(asset)
            if not width or not height:
                continue
            is_image = asset.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            results.append(MediaCandidate(
                provider="local", asset_id=asset.stem, query=query,
                width=width, height=height, duration=duration,
                media_type="image" if is_image else "video",
                url=str(asset), local_path=str(asset),
            ))

        return results

    def search_query(
        self,
        query: str,
        target_duration: float = 4.0,
        enable_synthetic_fallback: bool = False,
        visual_type: str = "stock_video",
        preferred_motion: str = "zoom_in",
    ) -> List[MediaCandidate]:
        """Searches providers and local library for a given query string."""
        candidates: List[MediaCandidate] = []
        self.search_attempts = []
        is_photo_intent = visual_type.lower() in ("stock_image", "photo", "generated_image")

        # 1. Search local library first (including photos with Ken Burns)
        local_matches = self.search_local_library(
            query=query,
            target_duration=target_duration,
            preferred_motion=preferred_motion,
        )
        candidates.extend(local_matches)

        # 2. If photo intent, query real photo providers (Pexels Photos, Commons, Openverse)
        if is_photo_intent:
            try:
                photo_candidates = self.sources_manager.search_photos(
                    query=query,
                    aspect="portrait",
                    limit_per_provider=4,
                )
                candidates.extend(photo_candidates)
                self.search_attempts.extend(getattr(self.sources_manager, "last_attempts", []))
            except Exception as e:
                logger.warning("Sources manager photo search failed for query='{}': {}", query, e)

        if not is_photo_intent:
            from app.services.media_sources.base import SearchRequest
            result = self.sources_manager.search(SearchRequest(query=query, duration=target_duration, include_archives=visual_type == "archive"))
            candidates.extend(result.candidates)
            self.search_attempts.extend(getattr(self.sources_manager, "last_attempts", []))
            # Search both orientations before considering a photo fallback.
            landscape = self.sources_manager.search(SearchRequest(query=query, orientations=("landscape",), duration=target_duration, include_archives=visual_type == "archive"))
            candidates.extend(landscape.candidates)
            self.search_attempts.extend(getattr(self.sources_manager, "last_attempts", []))

        # 5. If few candidates found for video intent, supplement with high-res photos for Ken Burns
        if not is_photo_intent and len([c for c in candidates if c.media_type == "video"]) < 3:
            try:
                supplements = self.sources_manager.search_photos(
                    query=query,
                    aspect="portrait",
                    limit_per_provider=2,
                )
                candidates.extend(supplements)
                self.search_attempts.extend(getattr(self.sources_manager, "last_attempts", []))
            except Exception as e:
                logger.warning("Supplementary photo search failed for query='{}': {}", query, e)

        # 7. Fallback generator only if explicitly enabled
        if not candidates and enable_synthetic_fallback:
            slug = hashlib.md5(f"{query}_{visual_type}".encode()).hexdigest()[:10]
            is_meme_intent = (
                visual_type.lower() in ("meme", "graphic")
                or any(w in query.lower() for w in ["literal", "falling", "joke", "ironic"])
            )
            if is_meme_intent:
                synthetic_path = self.media_cache_dir / f"meme_syn_{slug}.mp4"
                meme_dur = min(1.5, max(0.8, target_duration))
                _generate_synthetic_meme_clip(
                    query=query,
                    output_path=synthetic_path,
                    duration=meme_dur,
                )
                provider_tag = "synthetic_meme"
                syn_duration = meme_dur
                tech_score = 0.20
            elif is_photo_intent:
                synthetic_path = self.media_cache_dir / f"photo_syn_{slug}.mp4"
                syn_duration = max(5.0, target_duration + 1.0)
                _generate_synthetic_photo_clip(
                    query=query,
                    output_path=synthetic_path,
                    duration=syn_duration,
                    motion=preferred_motion,
                )
                provider_tag = "synthetic_photo"
                syn_duration = syn_duration
                tech_score = 0.15
            else:
                synthetic_path = self.media_cache_dir / f"synthetic_{slug}.mp4"
                syn_duration = max(5.0, target_duration + 1.0)
                _generate_synthetic_clip(
                    query=query,
                    output_path=synthetic_path,
                    duration=syn_duration,
                )
                provider_tag = "synthetic_local"
                tech_score = 0.10

            logger.warning(
                "No real media candidate found for query='{}' (type={}). Generated synthetic placeholder: {}",
                query, visual_type, synthetic_path
            )

            candidates.append(
                MediaCandidate(
                    provider=provider_tag,
                    asset_id=f"syn_{slug}",
                    query=query,
                    width=1080,
                    height=1920,
                    duration=syn_duration,
                    url=str(synthetic_path),
                    local_path=str(synthetic_path),
                    technical_score=tech_score,
                    final_score=tech_score,
                    is_synthetic=True,
                )
            )
        elif not candidates:
            logger.info("No media candidates found for query='{}' (type={})", query, visual_type)

        return candidates
