"""Independent channel presets. UUID identifiers avoid collisions and path traversal."""
from pathlib import Path
import re
import uuid

from .kit import BrandKit, load_kit, save_kit


def list_presets(root: Path = Path('storage/brand_presets')) -> dict[str, BrandKit]:
    return {p.stem: load_kit(p) for p in sorted(root.glob('*.json'))
            if re.fullmatch(r'[0-9a-f]{32}', p.stem)}


def save_preset(kit: BrandKit, preset_id: str | None = None,
                root: Path = Path('storage/brand_presets')) -> str:
    preset_id = preset_id or uuid.uuid4().hex
    if not re.fullmatch(r'[0-9a-f]{32}', preset_id):
        raise ValueError('Identificador de preset inválido.')
    save_kit(kit, root / f'{preset_id}.json')
    return preset_id


def preset_label(kit: BrandKit) -> str:
    return f'{kit.channel} · {kit.name}' if kit.channel else kit.name
