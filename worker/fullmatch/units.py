"""Unit conversions for thresholds ported from COURTSIDE.

COURTSIDE's pixel thresholds (wrist distances, shuttle speeds in px/frame) were
tuned on 1280x720 frames at 30 fps. Our pipeline's shuttle and player
coordinates are in 512x288, so they are multiplied by SCALE_TO_HD before an
upstream pixel threshold is applied; the thresholds then keep their upstream
values.

Frame counts that stand for a time span (gaps, run lengths, windows) are
scaled by fps/30 with frames_at; a speed threshold in px/frame is scaled by
30/fps with speed_at. At 30 fps both are the identity.
"""
SCALE_TO_HD = 1280 / 512        # 512x288 pipeline pixels -> 1280x720 (also 720/288)
REF_FPS = 30.0                  # COURTSIDE's frame-based constants assume 30 fps


def frames_at(n: int, fps: float) -> int:
    """A 30-fps frame count expressed at `fps`."""
    return int(round(n * fps / REF_FPS))


def speed_at(v: float, fps: float) -> float:
    """A 30-fps px/frame speed expressed at `fps`."""
    return v * REF_FPS / fps
