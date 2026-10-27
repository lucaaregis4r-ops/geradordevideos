"""Shared portrait framing for plain clips and clips with typography."""

FRAMING_VERSION = 2


def portrait_filter(width: int, height: int, fps: int, mode: str = "center") -> str:
    if mode == "fit":
        return (
            f"split[fill][content];[fill]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},gblur=sigma=20[blur];"
            f"[content]scale={width}:{height}:force_original_aspect_ratio=decrease[fit];"
            f"[blur][fit]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps}"
        )
    if mode != "center":
        raise ValueError("unsupported_crop_mode")
    return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps}")
