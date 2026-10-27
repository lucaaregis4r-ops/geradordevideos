"""Original restrained looks built from native FFmpeg filters, before typography."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import uuid

from pydantic import BaseModel, Field
from typing import Literal

LOOK_LABELS = {
    'neutral': 'Original — sem tratamento',
    'documentary': 'Documental — contraste suave',
    'warm': 'Quente — tons acolhedores',
    'cool': 'Frio — tons industriais',
    'archive': 'Arquivo — cores reduzidas',
}


class VisualLook(BaseModel):
    preset: Literal['neutral', 'documentary', 'warm', 'cool', 'archive'] = 'neutral'
    intensity: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    grain: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    vignette: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)

    def filters(self) -> str:
        parts = []
        i = self.intensity
        # Values interpolate from identity; intensity zero is a true bypass.
        if self.preset != 'neutral' and i > 0:
            contrast, saturation, warmth = {
                'documentary': (0.10, -0.12, 0.01),
                'warm': (0.06, 0.06, 0.05),
                'cool': (0.08, -0.14, -0.04),
                'archive': (0.06, -0.70, 0.03),
            }[self.preset]
            parts.extend([
                f'eq=contrast={1+contrast*i:.5f}:saturation={1+saturation*i:.5f}',
                f'colorbalance=rm={warmth*i:.5f}:bm={-warmth*i:.5f}:pl=0',
            ])
        if self.grain > 0:
            parts.append(f'noise=alls={self.grain*8:.3f}:allf=t+u:all_seed=42')
        if self.vignette > 0:
            parts.append(f'vignette=angle={self.vignette*0.5:.5f}:eval=init')
        return ','.join(parts)


def render_look(source: str | Path, look: VisualLook, cache_dir: Path, *,
                source_in: float = 0, duration: float, preview: bool = False) -> Path:
    """Trim and filter a bounded interval; atomic, versioned cache; never alter source."""
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(source_in) or source_in < 0:
        raise ValueError('Intervalo de vídeo inválido.')
    if not look.filters() and not preview:
        return source
    stamp = source.stat()
    key = hashlib.sha256(json.dumps(['look-v3', str(source), stamp.st_size, stamp.st_mtime_ns,
        look.model_dump(), source_in, duration, preview], sort_keys=True).encode()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = cache_dir / f'{key}.mp4'
    if output.is_file() and output.stat().st_size:
        return output
    temporary = cache_dir / f'{key}.{uuid.uuid4().hex}.tmp.mp4'
    filters = []
    if preview:
        filters.append('scale=540:960:force_original_aspect_ratio=decrease:force_divisible_by=2')
    if look.filters():
        filters.append(look.filters())
    filters.extend(['setsar=1', 'format=yuv420p'])
    command = ['ffmpeg', '-y', '-v', 'error', '-ss', str(source_in), '-i', str(source),
               '-t', str(duration), '-map', '0:v:0', '-an', '-filter_threads', '2', '-vf', ','.join(filters),
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-movflags', '+faststart', str(temporary)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=max(120, duration*30))
        # Reject truncated results instead of caching a successful but empty/short clip.
        measured = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
            'format=duration', '-of', 'default=nw=1:nk=1', str(temporary)], timeout=15))
        if measured < duration - 0.15:
            raise ValueError('O trecho escolhido ultrapassa o fim do vídeo.')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
