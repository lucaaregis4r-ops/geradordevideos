"""Import local clips with explicit curation and provenance (no scraping).

Usage: python -m app.services.media_ranker.import_curated manifest.json
The JSON is a list of {path, tags, description, creator_name, source_page,
license_id, license_url, rights_status}. Approval is scoped to this recorded use.
"""
import argparse
import json
from .smart_library import SmartLibrary


def import_manifest(path, library=None):
    library = library or SmartLibrary()
    records = json.loads(path.read_text(encoding="utf-8"))
    imported = []
    for record in records:
        for field in ("path", "tags", "description", "creator_name", "source_page", "license_id", "rights_status"):
            if not record.get(field):
                raise ValueError(f"missing_curated_metadata:{field}")
        if record["rights_status"] not in {"rights_unknown", "reviewed_allowed", "blocked_for_this_use"}:
            raise ValueError("invalid_rights_status")
        imported.append(library.register_approved_asset(record["path"], record["tags"],
            intent=record["description"], metadata=record).asset_id)
    return imported


if __name__ == "__main__":
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    print(json.dumps(import_manifest(parser.parse_args().manifest)))
