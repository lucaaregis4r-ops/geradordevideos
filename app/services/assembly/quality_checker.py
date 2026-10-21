"""Quality Checker — validates an AssemblyPlan before rendering.

Computes metrics and enforces pass/fail gates to prevent rendering
videos with known quality issues (duplicates, missing assets, etc.).
"""

from __future__ import annotations
from collections import Counter
import logging
from typing import List

from .schemas import AssemblyPlan, QualityScore

logger = logging.getLogger(__name__)


# Default thresholds — can be overridden via config
DEFAULT_THRESHOLDS = {
    "max_duplicate_assets": 0,
    "min_visual_diversity": 0.3,
    "max_segments_without_visual": 0,
    "max_text_safe_area_errors": 0,
    "max_low_resolution": 2,
    "min_semantic_match_avg": 0.4,
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
            low_resolution_count=0,    # Placeholder — needs asset metadata
            segments_without_visual=self._count_missing_visuals(plan),
        )

        # Determine pass/fail
        alerts = self._check_alerts(score)
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
            if getattr(s, "semantic_score", 0.0) > 0
        ]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 3)

    def _compute_diversity(self, plan: AssemblyPlan) -> float:
        """Visual diversity score: ratio of unique asset types and categories.

        A video with all stock_video segments scores low; mixing video,
        photo, graphic, text_card, etc. scores high.
        """
        if not plan.segments:
            return 0.0

        types = [s.asset_type for s in plan.segments]
        purposes = [s.purpose for s in plan.segments]

        type_diversity = len(set(types)) / max(len(types), 1)
        purpose_diversity = len(set(purposes)) / max(len(purposes), 1)

        # Weighted: type variety matters more
        return round(0.6 * type_diversity + 0.4 * purpose_diversity, 3)

    def _count_missing_visuals(self, plan: AssemblyPlan) -> int:
        """Counts segments with no valid asset path."""
        return sum(
            1 for s in plan.segments
            if not s.asset_path or s.asset_id.startswith("missing_")
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

        if score.segments_without_visual > self.thresholds["max_segments_without_visual"]:
            alerts.append(
                f"segments_without_visual={score.segments_without_visual} "
                f"(max={self.thresholds['max_segments_without_visual']})"
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

        if score.semantic_match_avg > 0 and score.semantic_match_avg < self.thresholds["min_semantic_match_avg"]:
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
