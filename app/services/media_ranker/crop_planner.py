"""Geometry of usable portrait pixels; never equate source width with crop quality."""
def useful_resolution(width: int, height: int, crop_mode: str = "center") -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return 0, 0
    if crop_mode == "fit":
        return width, height
    return int(min(width, height * 9 / 16)), int(min(height, width * 16 / 9))
