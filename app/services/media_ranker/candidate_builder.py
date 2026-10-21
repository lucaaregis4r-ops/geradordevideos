"""Candidate builder connecting queries to providers and local media acervo.

Coordinates:
1. Pexels (if API key available)
2. Pixabay (if API key available)
3. Coverr (if API key available)
4. Local Smart Library (storage/media_cache/)
5. Synthetic Video Generator fallback (ensures pipeline never fails for tests/prototypes)
"""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import List, Optional

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

        # 1. Look for local mp4 files
        for mp4 in self.media_cache_dir.glob("*.mp4"):
            name = mp4.stem.lower()
            if any(tok in name for tok in tokens):
                asset_id = mp4.stem
                results.append(
                    MediaCandidate(
                        provider="local",
                        asset_id=asset_id,
                        query=query,
                        width=1080,
                        height=1920,
                        duration=5.0,
                        url=str(mp4),
                        local_path=str(mp4),
                        technical_score=0.95,
                        final_score=0.95,
                    )
                )

        # 2. Look for local image files (jpg, jpeg, png, webp) and convert with Ken Burns
        photo_dir = self.media_cache_dir / "rendered_photos"
        photo_dir.mkdir(parents=True, exist_ok=True)
        from app.services.utils.ken_burns import create_ken_burns_clip

        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            for img_file in self.media_cache_dir.glob(ext):
                name = img_file.stem.lower()
                if any(tok in name for tok in tokens):
                    asset_id = f"photo_{img_file.stem}"
                    clip_path = photo_dir / f"{asset_id}.mp4"
                    try:
                        create_ken_burns_clip(
                            image_path=img_file,
                            output_path=clip_path,
                            duration=target_duration,
                            motion=preferred_motion,
                        )
                        results.append(
                            MediaCandidate(
                                provider="local_photo",
                                asset_id=asset_id,
                                query=query,
                                width=1080,
                                height=1920,
                                duration=target_duration,
                                url=str(clip_path),
                                local_path=str(clip_path),
                                technical_score=0.97,
                                final_score=0.97,
                            )
                        )
                    except Exception as e:
                        logger.warning("Failed to render Ken Burns clip for {}: {}", img_file, e)

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
        is_photo_intent = visual_type.lower() in ("stock_image", "photo", "archive", "generated_image")

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
            except Exception as e:
                logger.warning("Sources manager photo search failed for query='{}': {}", query, e)

        # 3. Check Pexels Video (if video intent and keys present)
        pexels_keys = config.app.get("pexels_api_keys", [])
        if pexels_keys and not is_photo_intent:
            try:
                min_dur = max(3, int(target_duration))
                raw_pexels = material.search_videos_pexels(
                    search_term=query,
                    minimum_duration=min_dur,
                    video_aspect=VideoAspect.portrait,
                )
                for item in raw_pexels:
                    s_info = item.source_info if isinstance(item.source_info, dict) else {}
                    creator = s_info.get("creator") or {}
                    rendition = s_info.get("rendition") or {}
                    w = int(rendition.get("width") or 1080)
                    h = int(rendition.get("height") or 1920)
                    orig_id = str(s_info.get("asset_id") or "")
                    asset_id = f"pexels_vid_{orig_id}" if orig_id else hashlib.md5(item.url.encode()).hexdigest()[:12]

                    candidates.append(
                        MediaCandidate(
                            provider="pexels",
                            provider_asset_id=orig_id,
                            asset_id=asset_id,
                            query=query,
                            width=w,
                            height=h,
                            duration=float(item.duration),
                            url=item.url,
                            source_page=s_info.get("source_page", ""),
                            media_type="video",
                            creator_name=creator.get("name", "") if isinstance(creator, dict) else "",
                            creator_url=creator.get("url", "") if isinstance(creator, dict) else "",
                            license_id="Pexels License",
                            license_url="https://www.pexels.com/license/",
                        )
                    )
            except Exception as e:
                logger.warning("Pexels video search failed for query='{}': {}", query, e)

        # 4. Check Pixabay Video
        pixabay_keys = config.app.get("pixabay_api_keys", [])
        if pixabay_keys and not is_photo_intent:
            try:
                min_dur = max(3, int(target_duration))
                raw_pixabay = material.search_videos_pixabay(
                    search_term=query,
                    minimum_duration=min_dur,
                    video_aspect=VideoAspect.portrait,
                )
                for item in raw_pixabay:
                    s_info = item.source_info if isinstance(item.source_info, dict) else {}
                    creator = s_info.get("creator") or {}
                    rendition = s_info.get("rendition") or {}
                    w = int(rendition.get("width") or 1080)
                    h = int(rendition.get("height") or 1920)
                    orig_id = str(s_info.get("asset_id") or "")
                    asset_id = f"pixabay_vid_{orig_id}" if orig_id else hashlib.md5(item.url.encode()).hexdigest()[:12]

                    candidates.append(
                        MediaCandidate(
                            provider="pixabay",
                            provider_asset_id=orig_id,
                            asset_id=asset_id,
                            query=query,
                            width=w,
                            height=h,
                            duration=float(item.duration),
                            url=item.url,
                            source_page=s_info.get("source_page", ""),
                            media_type="video",
                            creator_name=creator.get("name", "") if isinstance(creator, dict) else "",
                            creator_url=creator.get("url", "") if isinstance(creator, dict) else "",
                            license_id="Pixabay License",
                            license_url="https://pixabay.com/service/license-summary/",
                        )
                    )
            except Exception as e:
                logger.warning("Pixabay video search failed for query='{}': {}", query, e)

        # 5. If few candidates found for video intent, supplement with high-res photos for Ken Burns
        if not is_photo_intent and len(candidates) < 3:
            try:
                supplements = self.sources_manager.search_photos(
                    query=query,
                    aspect="portrait",
                    limit_per_provider=2,
                )
                candidates.extend(supplements)
            except Exception as e:
                logger.warning("Supplementary photo search failed for query='{}': {}", query, e)

        # 4. Fallback generator only if explicitly enabled
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
