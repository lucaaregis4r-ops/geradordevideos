"""Credits and License Manifest Generator.

Generates:
1. credits.md: Clean attribution markdown for video descriptions and publication records.
2. manifest.json: Machine-readable rights and provenance audit trail.
"""

from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.assembly.schemas import AssemblyPlan
from app.services.director.schemas import ScenePlan
from app.services.media_ranker.asset_catalog import AssetCatalog


class CreditsGenerator:
    """Generates credits and legal manifests for video productions."""

    def __init__(self, catalog: Optional[AssetCatalog] = None):
        self.catalog = catalog or AssetCatalog()

    def generate_manifest(
        self,
        plan: AssemblyPlan | ScenePlan,
        project_title: str = "",
    ) -> Dict[str, Any]:
        """Collects asset provenance and builds a structured manifest."""
        project_id = getattr(plan, "project_id", getattr(plan, "script_id", "project"))
        assets_used: List[Dict[str, Any]] = []
        seen_assets = set()

        # Extract segments or scenes
        items = getattr(plan, "segments", getattr(plan, "scenes", []))

        for item in items:
            asset_id = getattr(item, "asset_id", None)
            if not asset_id:
                sel = getattr(item, "selected_media", None) or {}
                asset_id = sel.get("asset_id")

            if not asset_id or asset_id in seen_assets:
                continue
            seen_assets.add(asset_id)

            # Query catalog or metadata from item
            info = self.catalog.get_asset(asset_id) or {}
            provider = info.get("provider") or getattr(item, "asset_type", "unknown")
            creator = info.get("creator_name") or "Unknown Creator"
            creator_url = info.get("creator_url") or ""
            source_page = info.get("source_page") or ""
            license_id = info.get("license_id") or "Standard Rights"
            license_url = info.get("license_url") or ""
            content_hash = info.get("content_hash") or ""

            assets_used.append(
                {
                    "asset_id": asset_id,
                    "provider": provider,
                    "creator_name": creator,
                    "creator_url": creator_url,
                    "source_page": source_page,
                    "license_id": license_id,
                    "license_url": license_url,
                    "content_hash": content_hash,
                }
            )

        return {
            "project_id": project_id,
            "project_title": project_title,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_assets": len(assets_used),
            "assets": assets_used,
        }

    def generate_markdown(self, manifest: Dict[str, Any]) -> str:
        """Formats the manifest into clean, user-facing markdown."""
        title = manifest.get("project_title") or manifest.get("project_id", "Shorts Project")
        lines = [
            f"# 📜 Créditos e Manifesto de Direitos — {title}",
            "",
            f"> Gerado em: `{manifest.get('generated_at')}`  ",
            f"> Total de mídias únicas: **{manifest.get('total_assets', 0)}**",
            "",
            "## 🎥 Mídias e Autoria",
            "",
            "| Asset ID | Origem / Provedor | Criador / Autor | Licença | Link |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for a in manifest.get("assets", []):
            creator = a.get("creator_name", "Desconhecido")
            if a.get("creator_url"):
                creator = f"[{creator}]({a['creator_url']})"
            provider = a.get("provider", "local")
            lic = a.get("license_id", "Uso livre")
            if a.get("license_url"):
                lic = f"[{lic}]({a['license_url']})"
            link = f"[Página Original]({a['source_page']})" if a.get("source_page") else "Arquivo Local"

            lines.append(f"| `{a.get('asset_id')}` | {provider} | {creator} | {lic} | {link} |")

        lines.extend(
            [
                "",
                "## 📝 Texto de Atribuição Sugerido (YouTube / Redes Sociais)",
                "```text",
                f"Imagens e mídias utilizadas sob licença de seus respectivos autores:",
            ]
        )

        for a in manifest.get("assets", []):
            if a.get("creator_name") and a.get("creator_name") != "Unknown Creator":
                prov = a.get("provider", "")
                lines.append(f"- {a['creator_name']} ({prov} / {a.get('license_id', '')})")

        lines.extend(
            [
                "```",
                "",
            ]
        )
        return "\n".join(lines)

    def save_credits(
        self,
        plan: AssemblyPlan | ScenePlan,
        output_dir: Path,
        project_title: str = "",
    ) -> Dict[str, Path]:
        """Saves both credits.md and manifest.json to output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.generate_manifest(plan, project_title=project_title)
        md_text = self.generate_markdown(manifest)

        manifest_file = output_dir / "manifest.json"
        credits_file = output_dir / "credits.md"

        manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        credits_file.write_text(md_text, encoding="utf-8")

        return {
            "manifest_json": manifest_file,
            "credits_md": credits_file,
        }
