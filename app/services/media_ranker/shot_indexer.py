"""FFmpeg scene-cut indexing with content-sensitive on-disk cache."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess


@dataclass
class Shot:
    shot_id: str
    source_in: float
    source_out: float


def index_shots(path: str | Path, duration: float, cache_dir: str | Path) -> list[Shot]:
    source = Path(path)
    identity = f"cuts-v1:{source.resolve()}:{source.stat().st_size}:{source.stat().st_mtime_ns}"
    cache = Path(cache_dir) / (hashlib.sha256(identity.encode()).hexdigest() + ".json")
    if cache.exists():
        return [Shot(**row) for row in json.loads(cache.read_text())]
    result = subprocess.run(["ffmpeg", "-v", "info", "-i", str(source), "-an",
        "-vf", "scale=160:-2,select='gt(scene,0.35)',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, check=True, timeout=45)
    cuts = sorted({0.0, duration, *[float(v) for v in re.findall(r"pts_time:([0-9.]+)", result.stderr) if 0 < float(v) < duration]})
    shots = [Shot(f"shot_{i:04d}", a, b) for i, (a, b) in enumerate(zip(cuts, cuts[1:])) if b > a]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps([asdict(s) for s in shots]))
    return shots
