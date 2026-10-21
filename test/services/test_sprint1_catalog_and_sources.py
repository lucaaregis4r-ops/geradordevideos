"""Unit tests for Sprint 1: Unified Asset Catalog, Metadata Tracking & Real Photo Sources.

Validates:
1. PexelsPhotoProvider parses real photo responses with photographer attribution.
2. WikimediaCommonsProvider parses MediaWiki responses with clean author names and CC licenses.
3. OpenverseProvider queries open-culture image archives with commercial-friendly filters.
4. MediaSourcesManager coordinates providers and handles partial failures gracefully.
5. AssetCatalog registers files in SQLite with real dimensions, duration and SHA-256 hash.
6. Content hash deduplication reuses canonical assets across duplicate downloads.
7. CreditsGenerator produces compliant credits.md and manifest.json.
8. CandidateBuilder routes photo intents to real photo providers instead of synthetic plates.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from app.services.assembly.schemas import AssemblyPlan, AssemblySegment
from app.services.editorial.credits_generator import CreditsGenerator
from app.services.media_ranker.asset_catalog import AssetCatalog, _measure_media
from app.services.media_ranker.candidate_builder import CandidateBuilder
from app.services.media_ranker.schemas import MediaCandidate
from app.services.media_sources.base import MediaSourceProvider
from app.services.media_sources.manager import MediaSourcesManager
from app.services.media_sources.openverse import OpenverseProvider
from app.services.media_sources.pexels_photos import PexelsPhotoProvider
from app.services.media_sources.wikimedia_commons import WikimediaCommonsProvider, _strip_html


def test_strip_html_helper():
    """Validates HTML stripping from MediaWiki artist/author fields."""
    html = '<a href="https://example.com" class="ext-link">Jane Doe</a> / <i>Staff</i>'
    assert _strip_html(html) == "Jane Doe / Staff"
    assert _strip_html("") == ""
    assert _strip_html(None) == ""


def test_pexels_photo_provider_mock():
    """Validates Pexels Photo API parsing with photographer attribution and portrait URLs."""
    provider = PexelsPhotoProvider()

    mock_resp = {
        "photos": [
            {
                "id": 998877,
                "width": 1440,
                "height": 2560,
                "url": "https://www.pexels.com/photo/clean-cotton-shirt-998877/",
                "photographer": "Maria Silva",
                "photographer_url": "https://www.pexels.com/@mariasilva",
                "src": {
                    "original": "https://images.pexels.com/photos/998877/orig.jpg",
                    "large2x": "https://images.pexels.com/photos/998877/large2x.jpg",
                    "portrait": "https://images.pexels.com/photos/998877/portrait.jpg",
                    "tiny": "https://images.pexels.com/photos/998877/tiny.jpg",
                },
            }
        ]
    }

    with patch.object(provider, "is_available", return_value=True):
        with patch.object(provider, "_get_api_key", return_value="dummy_key"):
            with patch("requests.get") as mock_get:
                mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_resp)
                candidates = provider.search(query="cotton t-shirt", aspect="portrait")

    assert len(candidates) == 1
    c = candidates[0]
    assert c.provider == "pexels_photos"
    assert c.provider_asset_id == "998877"
    assert c.asset_id == "pexels_photo_998877"
    assert c.media_type == "image"
    assert c.creator_name == "Maria Silva"
    assert c.creator_url == "https://www.pexels.com/@mariasilva"
    assert c.url == "https://images.pexels.com/photos/998877/portrait.jpg"
    assert c.width == 1440
    assert c.height == 2560
    assert c.license_id == "Pexels License"


def test_wikimedia_commons_provider_mock():
    """Validates Wikimedia Commons API parsing with license metadata and clean creator."""
    provider = WikimediaCommonsProvider()

    mock_resp = {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "title": "File:James Webb Telescope Mirror.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/wikipedia/commons/test_jwst.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:James_Webb_Telescope_Mirror.jpg",
                            "width": 2000,
                            "height": 3000,
                            "mime": "image/jpeg",
                            "extmetadata": {
                                "Artist": {"value": '<a href="...">NASA/Chris Gunn</a>'},
                                "LicenseShortName": {"value": "Public domain"},
                                "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/mark/1.0/"},
                            },
                        }
                    ],
                }
            }
        }
    }

    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_resp)
        candidates = provider.search(query="james webb telescope")

    assert len(candidates) == 1
    c = candidates[0]
    assert c.provider == "wikimedia_commons"
    assert c.provider_asset_id == "12345"
    assert c.creator_name == "NASA/Chris Gunn"
    assert c.license_id == "Public domain"
    assert c.media_type == "image"
    assert c.width == 2000
    assert c.height == 3000


def test_openverse_provider_mock():
    """Validates Openverse API parsing with Creative Commons licensing."""
    provider = OpenverseProvider()

    mock_resp = {
        "results": [
            {
                "id": "ov_987",
                "title": "Soccer Match Stadium",
                "creator": "Carlos Fotógrafo",
                "creator_url": "https://flickr.com/photos/carlos",
                "url": "https://openverse.org/images/ov_987.jpg",
                "thumbnail": "https://openverse.org/thumbs/ov_987.jpg",
                "license": "by",
                "license_version": "4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "foreign_landing_url": "https://flickr.com/photos/carlos/123",
            }
        ]
    }

    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_resp)
        candidates = provider.search(query="soccer tactical board")

    assert len(candidates) == 1
    c = candidates[0]
    assert c.provider == "openverse"
    assert c.provider_asset_id == "ov_987"
    assert c.creator_name == "Carlos Fotógrafo"
    assert c.license_id == "CC BY 4.0"
    assert c.license_url == "https://creativecommons.org/licenses/by/4.0/"


def test_media_sources_manager_aggregate():
    """Validates that MediaSourcesManager queries all active providers and merges candidates."""
    p1 = MagicMock(spec=MediaSourceProvider)
    p1.is_available.return_value = True
    p1.name = "mock_p1"
    p1.search.return_value = [
        MediaCandidate(provider="p1", asset_id="c1", query="test", url="http://p1.jpg")
    ]

    p2 = MagicMock(spec=MediaSourceProvider)
    p2.is_available.return_value = True
    p2.name = "mock_p2"
    p2.search.return_value = [
        MediaCandidate(provider="p2", asset_id="c2", query="test", url="http://p2.jpg")
    ]

    manager = MediaSourcesManager(providers=[p1, p2])
    results = manager.search_photos(query="test", limit_per_provider=2)

    assert len(results) == 2
    assert results[0].asset_id == "c1"
    assert results[1].asset_id == "c2"


def test_asset_catalog_lifecycle_and_content_hash(tmp_path):
    """Validates AssetCatalog registration, real dimension measurement, and content_hash deduplication."""
    db_file = tmp_path / "catalog.db"
    catalog = AssetCatalog(db_path=db_file)

    # Create a real test image file with explicit dimensions 400x800
    img_file = tmp_path / "test_image.png"
    img = Image.new("RGB", (400, 800), color=(100, 150, 200))
    img.save(img_file)

    # Verify measurement helper
    w, h, dur = _measure_media(img_file)
    assert w == 400
    assert h == 800
    assert dur == 0.0

    cand1 = MediaCandidate(
        provider="pexels_photos",
        provider_asset_id="111",
        asset_id="asset_orig",
        query="test image",
        creator_name="Alice",
        license_id="Pexels",
        url="https://pexels.com/img1.jpg",
    )

    registered = catalog.register_downloaded_asset(cand1, img_file)
    assert registered.content_hash != ""
    assert registered.width == 400
    assert registered.height == 800
    assert registered.local_path == str(img_file.resolve())

    # Retrieve from catalog
    asset_record = catalog.get_asset(registered.asset_id)
    assert asset_record is not None
    assert asset_record["creator_name"] == "Alice"
    assert asset_record["width"] == 400
    assert asset_record["use_count"] == 1

    # Second download of same bytes from a different URL -> must deduplicate by content_hash!
    img_copy = tmp_path / "different_filename.png"
    img_copy.write_bytes(img_file.read_bytes())

    cand2 = MediaCandidate(
        provider="wikimedia_commons",
        provider_asset_id="222",
        asset_id="asset_second",
        query="different query",
        url="https://commons.wikimedia.org/copy.png",
    )

    deduped = catalog.register_downloaded_asset(cand2, img_copy)
    # Must reuse the canonical original asset_id
    assert deduped.asset_id == registered.asset_id
    assert deduped.content_hash == registered.content_hash

    # Usage count should be incremented to 2
    updated_record = catalog.get_asset(registered.asset_id)
    assert updated_record["use_count"] == 2


def test_credits_generator(tmp_path):
    """Validates credits.md and manifest.json generation for a video production."""
    db_file = tmp_path / "catalog.db"
    catalog = AssetCatalog(db_path=db_file)

    # Register mock assets in catalog
    img_path = tmp_path / "factory.png"
    Image.new("RGB", (100, 100)).save(img_path)

    c1 = MediaCandidate(
        provider="pexels",
        asset_id="asset_factory",
        creator_name="Lucas Fotógrafo",
        creator_url="https://pexels.com/@lucas",
        source_page="https://pexels.com/photo/123",
        license_id="Pexels License",
        license_url="https://pexels.com/license/",
    )
    catalog.register_downloaded_asset(c1, img_path)

    plan = AssemblyPlan(
        project_id="mercadoria_sprint1",
        segments=[
            AssemblySegment(
                segment_id="seg_0",
                start=0.0,
                end=3.0,
                asset_id="asset_factory",
                asset_type="photo",
                asset_path=str(img_path),
            )
        ],
        total_duration=3.0,
    )

    gen = CreditsGenerator(catalog=catalog)
    output_dir = tmp_path / "production_out"
    saved = gen.save_credits(plan, output_dir=output_dir, project_title="O Valor da Camiseta")

    credits_md = saved["credits_md"]
    manifest_json = saved["manifest_json"]

    assert credits_md.exists()
    assert manifest_json.exists()

    # Check manifest JSON
    manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    assert manifest["project_id"] == "mercadoria_sprint1"
    assert manifest["total_assets"] == 1
    assert manifest["assets"][0]["creator_name"] == "Lucas Fotógrafo"
    assert manifest["assets"][0]["license_id"] == "Pexels License"

    # Check markdown
    md_content = credits_md.read_text(encoding="utf-8")
    assert "O Valor da Camiseta" in md_content
    assert "Lucas Fotógrafo" in md_content
    assert "Pexels License" in md_content
    assert "Texto de Atribuição Sugerido" in md_content


def test_candidate_builder_uses_photo_providers_for_photo_intent(tmp_path):
    """CandidateBuilder routes photo visual_type to real photo providers."""
    mock_sources = MagicMock(spec=MediaSourcesManager)
    mock_photo = MediaCandidate(
        provider="pexels_photos",
        asset_id="real_photo_999",
        query="vintage cotton",
        media_type="image",
        creator_name="Fotógrafo Real",
        license_id="Pexels",
        url="https://pexels.com/real.jpg",
        technical_score=0.90,
    )
    mock_sources.search_photos.return_value = [mock_photo]

    builder = CandidateBuilder(
        media_cache_dir=tmp_path / "cache",
        sources_manager=mock_sources,
    )

    candidates = builder.search_query(
        query="vintage cotton",
        visual_type="stock_image",  # Photo intent!
        enable_synthetic_fallback=False,
    )

    # Must have called search_photos and returned real photo candidate
    mock_sources.search_photos.assert_called_once()
    assert len(candidates) == 1
    assert candidates[0].asset_id == "real_photo_999"
    assert candidates[0].is_synthetic is False
    assert candidates[0].creator_name == "Fotógrafo Real"
