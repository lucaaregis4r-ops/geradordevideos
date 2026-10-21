"""Tests for Sprint 3 (v0.5) of the Mercadoria Editorial Pipeline.

Validates:
1. Safe area boundary math (250px top header, 350px bottom controls, 60px side margins).
2. Typographic hierarchy generation:
   - Level 1: TITLE (huge uppercase keywords, gold/badge styling).
   - Level 2: EMPHASIS (medium phrase badge).
   - Level 3: CAPTION (subtitle-style lower third).
3. Pixel placement inside safe boundaries for vertical 9:16 (1080x1920).
4. QualityChecker enforcement of safe area gates.
"""

from pathlib import Path
import pytest
from PIL import Image

from app.services.assembly.quality_checker import QualityChecker
from app.services.assembly.schemas import AssemblyPlan, AssemblySegment
from app.services.graphics.typography_engine import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
    SAFE_TOP,
    TypographyEngine,
    validate_box_in_safe_area,
)


def test_safe_area_constants_and_boundary_math():
    """Validates safe area definitions and boundary checking function."""
    assert SAFE_TOP == 250
    assert SAFE_BOTTOM == 1570
    assert SAFE_LEFT == 60
    assert SAFE_RIGHT == 1020
    assert CANVAS_WIDTH == 1080
    assert CANVAS_HEIGHT == 1920

    # Inside safe area
    valid_box = (100, 300, 900, 600)
    ok, err = validate_box_in_safe_area(valid_box)
    assert ok is True
    assert err == ""

    # Violate top
    top_violating = (100, 150, 900, 400)
    ok, err = validate_box_in_safe_area(top_violating)
    assert ok is False
    assert "Top header violation" in err

    # Violate bottom
    bottom_violating = (100, 1500, 900, 1650)
    ok, err = validate_box_in_safe_area(bottom_violating)
    assert ok is False
    assert "Bottom controls violation" in err

    # Violate left
    left_violating = (30, 400, 900, 600)
    ok, err = validate_box_in_safe_area(left_violating)
    assert ok is False
    assert "Left margin violation" in err

    # Violate right
    right_violating = (100, 400, 1050, 600)
    ok, err = validate_box_in_safe_area(right_violating)
    assert ok is False
    assert "Right margin violation" in err


def test_render_title_overlay_inside_safe_area():
    """Validates that Level 1 TITLE renders within safe area bounds."""
    engine = TypographyEngine()
    overlay = engine.render_overlay("R$ 79,90", level="title")

    assert overlay.size == (1080, 1920)
    assert overlay.mode == "RGBA"

    # Get bounding box of all non-transparent pixels
    bbox = overlay.getbbox()
    assert bbox is not None
    x1, y1, x2, y2 = bbox

    ok, reason = validate_box_in_safe_area(bbox)
    assert ok is True, reason


def test_render_emphasis_overlay_inside_safe_area():
    """Validates that Level 2 EMPHASIS renders within safe area bounds."""
    engine = TypographyEngine()
    overlay = engine.render_overlay("TRANSFORME TRABALHO EM VALOR", level="emphasis")

    assert overlay.size == (1080, 1920)
    bbox = overlay.getbbox()
    assert bbox is not None

    ok, reason = validate_box_in_safe_area(bbox)
    assert ok is True, reason


def test_render_caption_overlay_inside_safe_area():
    """Validates that Level 3 CAPTION renders within safe area bounds."""
    engine = TypographyEngine()
    overlay = engine.render_overlay(
        "Milhares de pessoas trabalham juntas sem nunca terem se conhecido.",
        level="caption",
    )

    assert overlay.size == (1080, 1920)
    bbox = overlay.getbbox()
    assert bbox is not None

    ok, reason = validate_box_in_safe_area(bbox)
    assert ok is True, reason


def test_render_overlay_to_file(tmp_path):
    """Validates direct file export of typography PNG."""
    engine = TypographyEngine()
    out_file = tmp_path / "typography_title.png"

    saved = engine.render_overlay_to_file("QUEM FEZ ISSO?", output_path=out_file, level="title")
    assert saved.exists()
    assert saved.stat().st_size > 1000

    loaded = Image.open(saved)
    assert loaded.size == (1080, 1920)
    assert loaded.mode == "RGBA"


def test_quality_checker_enforces_safe_area_limits():
    """Validates that QualityChecker catches safe area overflow and passes clean plans."""
    checker = QualityChecker()

    # 1. Clean plan
    clean_segments = [
        AssemblySegment(
            segment_id="seg_1",
            start=0.0,
            end=3.0,
            asset_id="asset_1",
            asset_type="video",
            asset_path="/tmp/1.mp4",
            overlay_text="R$ 79,90",
            text_level="title",
        ),
        AssemblySegment(
            segment_id="seg_2",
            start=3.0,
            end=6.0,
            asset_id="asset_2",
            asset_type="photo",
            asset_path="/tmp/2.mp4",
            overlay_text="TRANSFORME TRABALHO EM VALOR",
            text_level="emphasis",
        ),
    ]
    clean_plan = AssemblyPlan(
        project_id="clean_typography",
        segments=clean_segments,
        total_duration=6.0,
    )

    clean_score = checker.evaluate(clean_plan)
    assert clean_score.text_safe_area_errors == 0
    assert clean_score.passed is True

    # 2. Bad plan with excessive title words that overflow single-screen safe limits
    bad_segments = [
        AssemblySegment(
            segment_id="seg_bad",
            start=0.0,
            end=3.0,
            asset_id="asset_1",
            asset_type="video",
            asset_path="/tmp/1.mp4",
            overlay_text="ESTE É UM TÍTULO ABSURDAMENTE LONGO QUE NUNCA DEVERIA SER USADO COMO TITULO PRINCIPAL EM UMA TELA VERTICAL",
            text_level="title",
        )
    ]
    bad_plan = AssemblyPlan(
        project_id="bad_typography",
        segments=bad_segments,
        total_duration=3.0,
    )

    bad_score = checker.evaluate(bad_plan)
    assert bad_score.text_safe_area_errors >= 1
    assert bad_score.passed is False
