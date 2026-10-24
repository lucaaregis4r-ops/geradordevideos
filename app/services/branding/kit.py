"""Small versioned brand kit shared by editor and production."""
import json
from pathlib import Path
from pydantic import BaseModel, Field


class BrandKit(BaseModel):
    version: int = 1
    name: str = 'Minha identidade'
    accent: str = Field(default='#FFD700', pattern=r'^#[0-9a-fA-F]{6}$')
    voice: str = 'pt-BR-FranciscaNeural-Female'
    voice_rate: float = Field(default=1.0, ge=0.8, le=1.3)
    music_path: str = ''
    music_volume: float = Field(default=0.12, ge=0, le=0.3)


def load_kit(path: Path = Path('storage/brand_kit.json')) -> BrandKit:
    return BrandKit.model_validate_json(path.read_text()) if path.exists() else BrandKit()


def save_kit(kit: BrandKit, path: Path = Path('storage/brand_kit.json')) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(kit.model_dump(), ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
