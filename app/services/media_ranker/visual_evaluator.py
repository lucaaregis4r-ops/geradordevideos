"""Visual Evaluator: Multi-frame visual quality assessment and perceptual feature extraction.

Implements Stage 3 of the Editorial Studio:
- Extracts 3-5 representative keyframes per video (or 1 for photo)
- Analyzes luminance, contrast, and sharpness
- Rejects pitch-black, blank, or corrupted clips
- Computes perceptual hashes (pHash/dHash) across keyframes
"""

from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import subprocess
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image
from loguru import logger

from .perceptual_hash import compute_dhash, compute_phash


@dataclass
class FrameMetrics:
    timestamp: float
    luminance: float
    contrast: float
    sharpness: float
    phash: str
    dhash: str
    is_black: bool = False
    is_blank: bool = False


@dataclass
class VisualMetrics:
    is_valid: bool
    quality_score: float  # 0.0 to 1.0
    mean_luminance: float
    mean_contrast: float
    mean_sharpness: float
    perceptual_hash: str
    frame_hashes: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    frames: List[FrameMetrics] = field(default_factory=list)


def _compute_frame_stats(img: Image.Image, timestamp: float = 0.0) -> FrameMetrics:
    """Computes technical visual stats on a single PIL frame."""
    gray = img.convert("L")
    pixels = np.array(gray, dtype=np.float32)

    lum = float(np.mean(pixels))
    contrast = float(np.std(pixels))

    # Sharpness via gradient variance (Laplacian proxy)
    dx = np.diff(pixels, axis=1)
    dy = np.diff(pixels, axis=0)
    sharpness = float(np.var(dx) + np.var(dy))

    ph = compute_phash(img)
    dh = compute_dhash(img)

    is_black = lum < 15.0
    is_blank = contrast < 6.0 or sharpness < 1.0

    return FrameMetrics(
        timestamp=timestamp,
        luminance=round(lum, 2),
        contrast=round(contrast, 2),
        sharpness=round(sharpness, 2),
        phash=ph,
        dhash=dh,
        is_black=is_black,
        is_blank=is_blank,
    )


class VisualEvaluator:
    """Evaluates media assets visually and extracts keyframe perceptual hashes."""

    def __init__(self, temp_dir: str | Path = "storage/thumbnails"):
        self.temp_dir = Path(temp_dir).resolve()
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def extract_image_frame(self, file_path: Path) -> Optional[Image.Image]:
        """Loads a static image via PIL."""
        try:
            with Image.open(file_path) as img:
                return img.convert("RGB")
        except Exception as e:
            logger.warning("Failed to open image {}: {}", file_path, e)
            return None

    def extract_video_frame(
        self, video_path: Path, timestamp: float, width: int = 540, height: int = 960
    ) -> Optional[Image.Image]:
        """Extracts a single frame from video at a given timestamp via FFmpeg."""
        token = f"{video_path}_{timestamp}_{width}x{height}"
        slug = hashlib.md5(token.encode("utf-8")).hexdigest()
        out_path = self.temp_dir / f"eval_{slug}.jpg"

        if not out_path.exists() or out_path.stat().st_size == 0:
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(max(0.0, timestamp)),
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                "-q:v", "2",
                str(out_path),
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except Exception as e:
                logger.debug("FFmpeg frame extraction failed for {} at {}: {}", video_path, timestamp, e)
                return None

        if out_path.exists() and out_path.stat().st_size > 0:
            try:
                with Image.open(out_path) as img:
                    return img.convert("RGB")
            except Exception:
                return None
        return None

    def evaluate_media(
        self,
        media_path: str | Path,
        media_type: str = "video",
        duration: float = 0.0,
        sample_count: int = 3,
        source_in: float = 0.0,
    ) -> VisualMetrics:
        """Performs multi-frame visual evaluation on a media asset.

        Args:
            media_path: Path to the media file on disk.
            media_type: 'video' or 'photo'.
            duration: Total duration in seconds (for video sampling).
            sample_count: Number of frames to sample (3 to 5 for video, 1 for photo).
        """
        path = Path(media_path).resolve()
        if not path.exists() or path.stat().st_size == 0:
            return VisualMetrics(
                is_valid=False,
                quality_score=0.0,
                mean_luminance=0.0,
                mean_contrast=0.0,
                mean_sharpness=0.0,
                perceptual_hash="",
                rejection_reason="file_not_found_or_empty",
            )

        if path.stat().st_size < 1024:
            return VisualMetrics(
                is_valid=False,
                quality_score=0.50,
                mean_luminance=0.0,
                mean_contrast=0.0,
                mean_sharpness=0.0,
                perceptual_hash="",
                rejection_reason="file_too_small_or_mock",
            )

        frames: List[FrameMetrics] = []

        if media_type == "photo" or path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
            img = self.extract_image_frame(path)
            if img is None:
                return VisualMetrics(
                    is_valid=False,
                    quality_score=0.0,
                    mean_luminance=0.0,
                    mean_contrast=0.0,
                    mean_sharpness=0.0,
                    perceptual_hash="",
                    rejection_reason="corrupted_image",
                )
            frames.append(_compute_frame_stats(img, timestamp=0.0))
        else:
            # Video: determine 3-5 sample timestamps
            count = max(1, min(sample_count, 5))
            if duration > 1.0:
                # Distribute points at 15%, 50%, 85% (or evenly across duration)
                fractions = np.linspace(0.15, 0.85, count)
                timestamps = [round(float(duration * frac), 2) for frac in fractions]
            else:
                timestamps = [round(0.2 * (i + 1), 2) for i in range(count)]

            for ts in timestamps:
                img = self.extract_video_frame(path, source_in + ts)
                if img is not None:
                    frames.append(_compute_frame_stats(img, timestamp=ts))

        if not frames:
            return VisualMetrics(
                is_valid=False,
                quality_score=0.0,
                mean_luminance=0.0,
                mean_contrast=0.0,
                mean_sharpness=0.0,
                perceptual_hash="",
                rejection_reason="frame_extraction_failed",
            )

        # Aggregate metrics
        mean_lum = float(np.mean([f.luminance for f in frames]))
        mean_contrast = float(np.mean([f.contrast for f in frames]))
        mean_sharpness = float(np.mean([f.sharpness for f in frames]))
        all_black = all(f.is_black for f in frames)
        all_blank = all(f.is_blank for f in frames)
        frame_hashes = [f.phash for f in frames]

        # Representative perceptual hash: central frame
        central_idx = len(frames) // 2
        primary_phash = frames[central_idx].phash

        if all_black:
            return VisualMetrics(
                is_valid=False,
                quality_score=0.05,
                mean_luminance=round(mean_lum, 2),
                mean_contrast=round(mean_contrast, 2),
                mean_sharpness=round(mean_sharpness, 2),
                perceptual_hash=primary_phash,
                frame_hashes=frame_hashes,
                rejection_reason="excessive_black_frames",
                frames=frames,
            )

        if all_blank:
            return VisualMetrics(
                is_valid=False,
                quality_score=0.10,
                mean_luminance=round(mean_lum, 2),
                mean_contrast=round(mean_contrast, 2),
                mean_sharpness=round(mean_sharpness, 2),
                perceptual_hash=primary_phash,
                frame_hashes=frame_hashes,
                rejection_reason="low_contrast_flat_media",
                frames=frames,
            )

        # Compute quality score (0.2 to 1.0)
        # Luminance score: ideal is 60 - 180
        lum_score = 1.0 - (min(abs(mean_lum - 120), 100) / 100.0) * 0.4
        # Contrast score: ideal > 35
        contrast_score = min(1.0, mean_contrast / 45.0)
        # Sharpness score: ideal > 20
        sharp_score = min(1.0, mean_sharpness / 30.0)

        quality = 0.4 * lum_score + 0.35 * contrast_score + 0.25 * sharp_score
        quality = round(min(1.0, max(0.2, quality)), 3)

        return VisualMetrics(
            is_valid=True,
            quality_score=quality,
            mean_luminance=round(mean_lum, 2),
            mean_contrast=round(mean_contrast, 2),
            mean_sharpness=round(mean_sharpness, 2),
            perceptual_hash=primary_phash,
            frame_hashes=frame_hashes,
            frames=frames,
        )
