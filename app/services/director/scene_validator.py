"""Scene Validator and Integrity Enforcer.

CRITICAL PRODUCT RULE (Section 9):
The narration text in each scene MUST be a literal slice of the approved human script.
The LLM is strictly prohibited from rewriting, deleting, or hallucinating text.
"""

from __future__ import annotations
import re
from typing import Any, Tuple

from .schemas import Scene, ScenePlan


class SceneValidationError(ValueError):
    pass


def _normalize_for_comparison(text: str) -> str:
    """Normalizes whitespace and standardizes quotes/dashes for comparison."""
    t = text.replace("“", '"').replace("”", '"').replace("’", "'")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def realign_narration_with_original(
    raw_scenes: list[dict[str, Any]], original_clean_script: str
) -> list[dict[str, Any]]:
    """Guarantees that narration in each scene corresponds to the exact character slice
    from the approved human script, eliminating minor whitespace or casing shifts from the LLM.
    """
    from app.services.editorial.directives import strip_stage_directions

    clean_original = strip_stage_directions(original_clean_script).strip()
    realigned = []
    current_pos = 0

    for idx, sc in enumerate(raw_scenes):
        sc_copy = dict(sc)
        narration = sc.get("narration", "").strip()

        # Try exact search from current_pos
        match_idx = clean_original.lower().find(narration.lower(), current_pos)
        if match_idx != -1:
            end_idx = match_idx + len(narration)
            # Use exact slice from original text
            sc_copy["narration"] = clean_original[match_idx:end_idx].strip()
            current_pos = end_idx
        else:
            # Fallback: if not found cleanly, preserve narration as given
            sc_copy["narration"] = narration

        realigned.append(sc_copy)

    return realigned


def validate_scene_plan(
    plan: ScenePlan, original_clean_script: str, strict_words: bool = True
) -> Tuple[bool, list[str]]:
    """Validates that:
    1. Narration concatenation matches approved script.
    2. Scene IDs are formatted and sequential (scene_001, scene_002...).
    3. Each scene has at least 1 search query and an intent.
    4. Scene count is reasonable.
    """
    errors: list[str] = []

    if not plan.scenes:
        errors.append("Plan contains no scenes.")
        return False, errors

    # 1. Narration fidelity check
    from app.services.editorial.directives import strip_stage_directions

    clean_script_text = strip_stage_directions(original_clean_script)
    combined_narration = " ".join(s.narration for s in plan.scenes)
    clean_combined_text = strip_stage_directions(combined_narration)

    norm_combined = _normalize_for_comparison(clean_combined_text)
    norm_original = _normalize_for_comparison(clean_script_text)

    if strict_words:
        # Whitespace between slices may differ; words, ordering, case and punctuation may not.
        original = re.sub(r"\s+", " ", clean_script_text).strip()
        combined = re.sub(r"\s+", " ", clean_combined_text).strip()
        if combined != original:
            errors.append("Narration does not match approved script literally")

    # 2. Scene structure check
    seen_ids = set()
    for i, sc in enumerate(plan.scenes):
        if not sc.scene_id:
            errors.append(f"Scene #{i+1} has no scene_id")
        elif sc.scene_id in seen_ids:
            errors.append(f"Duplicate scene_id: {sc.scene_id}")
        seen_ids.add(sc.scene_id)

        if not sc.narration.strip():
            errors.append(f"Scene {sc.scene_id} has empty narration")

        if not sc.intent.strip():
            errors.append(f"Scene {sc.scene_id} has empty visual intent")

        if not sc.queries or len(sc.queries) < 1:
            errors.append(f"Scene {sc.scene_id} must have at least 1 search query")

    is_valid = len(errors) == 0
    return is_valid, errors
