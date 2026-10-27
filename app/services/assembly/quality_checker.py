"""Quality Checker — validates an AssemblyPlan before rendering.

Computes metrics and enforces pass/fail gates to prevent rendering
videos with known quality issues (duplicates, missing assets, etc.).
"""

from __future__ import annotations
from collections import Counter
import logging
from pathlib import Path
import math
from typing import List

from .schemas import AssemblyPlan, QualityScore

logger = logging.getLogger(__name__)


# Default thresholds — can be overridden via config
DEFAULT_THRESHOLDS = {
    "max_duplicate_assets": 0,
    "min_visual_diversity": 0.3,
    "max_segments_without_visual": 0,
    "max_text_safe_area_errors": 0,
    "max_low_resolution": 0,
    "min_semantic_match_avg": 0.6,
    "max_synthetic_assets": 0,
    "max_consecutive_same_treatment": 3,
}


class QualityChecker:
    """Computes quality metrics for an AssemblyPlan and gates rendering."""

    def __init__(self, thresholds: dict | None = None):
        self.thresholds = {**DEFAULT_THRESHOLDS}
        if thresholds:
            self.thresholds.update(thresholds)

    def evaluate(self, plan: AssemblyPlan) -> QualityScore:
        """Computes all quality metrics and determines pass/fail.

        Returns a QualityScore attached to the plan.
        """
        score = QualityScore(
            asset_count=len(plan.segments),
            duplicate_assets=self._count_duplicates(plan),
            semantic_match_avg=self._compute_semantic_avg(plan),
            visual_diversity=self._compute_diversity(plan),
            text_safe_area_errors=self._validate_text_safe_area(plan),
            low_resolution_count=self._count_low_resolution(plan),
            segments_without_visual=self._count_missing_visuals(plan),
            synthetic_assets=self._count_synthetic_assets(plan),
            consecutive_treatment_violations=self._check_consecutive_treatments(plan),
        )

        # Determine pass/fail
        alerts = self._check_alerts(score)
        creator_counts = Counter(
            str(segment.provenance.get("creator_name", "")).strip().casefold()
            for segment in plan.segments
            if not segment.is_callback and segment.provenance.get("creator_name")
        )
        for creator, count in creator_counts.items():
            if creator and count > 2:
                alerts.append(f"creator_limit:{creator}={count} (max=2)")
        if not plan.segments:
            alerts.append("empty_timeline")
        previous_end = 0.0
        for segment in plan.segments:
            if not math.isfinite(segment.semantic_score) or segment.semantic_score < 0.6 or segment.semantic_status not in {"reviewed", "visual_verified", "planned_graphic"}:
                alerts.append(f"pending_review:{segment.segment_id}")
            if (not math.isfinite(segment.start) or not math.isfinite(segment.end)
                    or segment.end <= segment.start or abs(segment.start - previous_end) > 1 / 30):
                alerts.append(f"invalid_timeline:{segment.segment_id}")
            if not math.isfinite(segment.source_in) or segment.source_in < 0 or (segment.source_out is not None and
                    (not math.isfinite(segment.source_out) or segment.source_out <= segment.source_in)):
                alerts.append(f"invalid_source_interval:{segment.segment_id}")
            previous_end = segment.end
        if abs(previous_end - plan.total_duration) > 1 / 30:
            alerts.append("invalid_total_duration")
        score.alerts = alerts
        score.passed = len(alerts) == 0

        # Log results
        if alerts:
            for alert in alerts:
                logger.warning("Quality alert: %s", alert)
            logger.info("Quality check FAILED with %d alert(s)", len(alerts))
        else:
            logger.info(
                "Quality check PASSED: %d assets, %.0f%% diversity, %.0f%% semantic match",
                score.asset_count,
                score.visual_diversity * 100,
                score.semantic_match_avg * 100,
            )

        plan.quality_score = score
        return score

    def _count_duplicates(self, plan: AssemblyPlan) -> int:
        """Counts involuntary asset duplicates (excludes callbacks)."""
        non_callback_ids = [
            s.asset_id for s in plan.segments if not s.is_callback
        ]
        counts = Counter(non_callback_ids)
        return sum(c - 1 for c in counts.values() if c > 1)

    def _compute_semantic_avg(self, plan: AssemblyPlan) -> float:
        """Average semantic match score across segments.

        Reads from segment.semantic_score if populated.
        """
        if not plan.segments:
            return 0.0
        scores = [
            getattr(s, "semantic_score", 0.0)
            for s in plan.segments
        ]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 3)

    def _check_consecutive_treatments(self, plan: AssemblyPlan) -> int:
        """Counts instances where more than max_consecutive segments share the same non-video treatment.

        Deliberate callbacks and dynamic stock video clips are exempted from being penalized as monotony.
        """
        max_consecutive = self.thresholds.get("max_consecutive_same_treatment", 3)
        if not plan.segments or len(plan.segments) <= max_consecutive:
            return 0

        monotonous_types = {"synthetic", "fallback", "component", "data_card", "split_screen", "price_tag", "quote"}
        violations = 0
        current_type = plan.segments[0].asset_type
        run_len = 1
        for s in plan.segments[1:]:
            if s.is_callback:
                current_type = s.asset_type
                run_len = 1
                continue
            if s.asset_type == current_type and current_type in monotonous_types:
                run_len += 1
                if run_len > max_consecutive:
                    violations += 1
            else:
                current_type = s.asset_type
                run_len = 1
        return violations

    def _compute_diversity(self, plan: AssemblyPlan) -> float:
        """Visual diversity score using temporal sliding windows and treatment variety.

        Prevents longer videos from being unfairly penalized: calculates local variety
        across temporal sliding windows of size 4.
        """
        if not plan.segments:
            return 0.0

        types = [s.asset_type for s in plan.segments]
        purposes = [s.purpose for s in plan.segments]

        # 1. Overall variety relative to expected mix
        type_variety = min(1.0, len(set(types)) / 3.0)
        purpose_variety = min(1.0, len(set(purposes)) / 3.0)

        # 2. Temporal sliding window variety
        window_size = min(4, len(types))
        if window_size > 1:
            window_scores = []
            for i in range(len(types) - window_size + 1):
                win = types[i : i + window_size]
                window_scores.append(len(set(win)) / window_size)
            temporal_score = sum(window_scores) / len(window_scores)
        else:
            temporal_score = 1.0

        score = 0.50 * temporal_score + 0.30 * type_variety + 0.20 * purpose_variety
        return round(min(1.0, max(0.0, score)), 3)

    def _count_missing_visuals(self, plan: AssemblyPlan) -> int:
        """Counts segments with no valid asset path."""
        return sum(
            1 for s in plan.segments
            if not s.asset_path or not Path(s.asset_path).is_file() or s.asset_id.startswith("missing_")
        )

    def _count_low_resolution(self, plan: AssemblyPlan) -> int:
        from app.services.media_ranker.asset_catalog import _measure_media
        errors = 0
        for segment in plan.segments:
            if not segment.asset_path or not Path(segment.asset_path).is_file():
                continue
            width, height, duration = _measure_media(Path(segment.asset_path))
            # Effective central 9:16 crop, with a minimum 720p portrait delivery.
            from app.services.media_ranker.crop_planner import useful_resolution
            useful_width, useful_height = useful_resolution(width, height, segment.crop_mode)
            if useful_width < 720 or useful_height < (720 if segment.crop_mode == "fit" else 1280):
                errors += 1
            if segment.asset_type == "video" and (
                segment.source_in < 0 or duration + 1 / 30 < segment.source_in + segment.end - segment.start
                or (segment.source_out is not None and (segment.source_out > duration + 1 / 30
                    or segment.source_out < segment.source_in + segment.end - segment.start - 1 / 30))
            ):
                errors += 1
        return errors

    def _count_synthetic_assets(self, plan: AssemblyPlan) -> int:
        """Counts segments using synthetic placeholder clips."""
        return sum(
            1 for s in plan.segments
            if (s.asset_id and s.asset_id.startswith("syn_"))
            or "fallback_" in (s.asset_path or "")
            or "synthetic_" in (s.asset_path or "")
            or getattr(s, "is_synthetic", False)
        )

    def _check_alerts(self, score: QualityScore) -> List[str]:
        """Returns list of threshold violations."""
        alerts: List[str] = []

        if score.duplicate_assets > self.thresholds["max_duplicate_assets"]:
            alerts.append(
                f"duplicate_assets={score.duplicate_assets} "
                f"(max={self.thresholds['max_duplicate_assets']})"
            )

        if score.visual_diversity < self.thresholds["min_visual_diversity"]:
            alerts.append(
                f"visual_diversity={score.visual_diversity:.2f} "
                f"(min={self.thresholds['min_visual_diversity']})"
            )

        if score.consecutive_treatment_violations > self.thresholds.get("max_consecutive_treatment_violations", 0):
            alerts.append(
                f"consecutive_treatment_violations={score.consecutive_treatment_violations} "
                f"(max={self.thresholds.get('max_consecutive_treatment_violations', 0)})"
            )

        if score.segments_without_visual > self.thresholds["max_segments_without_visual"]:
            alerts.append(
                f"segments_without_visual={score.segments_without_visual} "
                f"(max={self.thresholds['max_segments_without_visual']})"
            )

        if "max_synthetic_assets" in self.thresholds and score.synthetic_assets > self.thresholds["max_synthetic_assets"]:
            alerts.append(
                f"synthetic_assets={score.synthetic_assets} "
                f"(max={self.thresholds['max_synthetic_assets']})"
            )

        if score.text_safe_area_errors > self.thresholds["max_text_safe_area_errors"]:
            alerts.append(
                f"text_safe_area_errors={score.text_safe_area_errors} "
                f"(max={self.thresholds['max_text_safe_area_errors']})"
            )

        if score.low_resolution_count > self.thresholds["max_low_resolution"]:
            alerts.append(
                f"low_resolution={score.low_resolution_count} "
                f"(max={self.thresholds['max_low_resolution']})"
            )

        if score.semantic_match_avg < self.thresholds["min_semantic_match_avg"]:
            alerts.append(
                f"semantic_match_avg={score.semantic_match_avg:.2f} "
                f"(min={self.thresholds['min_semantic_match_avg']})"
            )

        return alerts

    def _validate_text_safe_area(self, plan: AssemblyPlan) -> int:
        """Validates that text overlays in all segments respect safe area boundaries.

        Returns the number of safe area violation errors.
        """
        errors = 0
        for s in plan.segments:
            if not s.overlay_text or not s.overlay_text.strip():
                continue

            text = s.overlay_text.strip()
            level = (s.text_level or "caption").lower()
            from app.services.graphics.typography_engine import TypographyEngine, validate_box_in_safe_area
            try:
                overlay = TypographyEngine().render_overlay(text, level=level)
                box = overlay.getchannel("A").getbbox()
                if box is None or not validate_box_in_safe_area(box)[0]:
                    errors += 1
                    continue
            except Exception:
                errors += 1
                continue


            # Level 1 (TITLE): should not exceed 6 words; if > 6 words at title font size, it overflows
            if level == "title" and len(text.split()) > 6:
                errors += 1
                logger.warning(
                    "Segment %s has title overlay with %d words, exceeding single-screen safe boundaries",
                    s.segment_id, len(text.split())
                )
            # Level 2 (EMPHASIS): should not exceed 120 characters to prevent vertical safe area overflow
            elif level == "emphasis" and len(text) > 120:
                errors += 1
                logger.warning(
                    "Segment %s has emphasis overlay exceeding 120 characters",
                    s.segment_id
                )

        return errors
