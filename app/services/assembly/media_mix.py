"""Duration-weighted media mix; animated photographs are still photographs."""
from .schemas import AssemblyPlan


def summarize_media_mix(plan: AssemblyPlan) -> dict:
    seconds = {"video": 0.0, "photo": 0.0, "graphic": 0.0, "missing": 0.0}
    providers: set[str] = set()
    for segment in plan.segments:
        duration = max(0.0, segment.end - segment.start)
        kind = ("missing" if not segment.asset_path else "video" if segment.asset_type == "video"
                else "photo" if segment.asset_type in {"photo", "image"} else "graphic")
        seconds[kind] += duration
        provider = segment.provenance.get("provider")
        if provider:
            providers.add(provider)
    total = sum(seconds.values())
    ratio = seconds["video"] / total if total else 0.0
    return {"seconds": seconds, "video_ratio": round(ratio, 4),
            "target_video_ratio": 0.65, "below_target": ratio < 0.65,
            "providers": sorted(providers)}
