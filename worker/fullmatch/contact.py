# Ported from COURTSIDE src/badminton/contact.py, jayclim/BadmintonAI at commit
# 5c356f05cde0ed90c75316c133e0aba495e5232b.
# MIT License, Copyright (c) 2026 Jayden Lim
"""Contact height (metres): how high the shuttle was when it was hit.

No 3D reconstruction: the hitter is the ruler. With the shuttle at image y
`shuttle_y` and the hitter's ground point at image y `ground_y`, the contact is
(ground_y - shuttle_y) px above the floor at the hitter's depth; a standing
player of BODY_M metres spans `ruler` px at that same depth, so

    height_m = (ground_y - shuttle_y) * BODY_M / ruler

`ruler` is the RULER_Q quantile of that player's box heights whose box bottom
falls in the same BIN_PX-wide bin of image y (lunges and crouches shrink the
box; a high quantile is about standing upright). Upstream measured 81.9%
above/below-net agreement with ShuttleSet's hit_height and by-shot medians in
the expected order (lob < net shot < drive < drop < clear < smash).

Pixel values are 1280x720 (COURTSIDE's frame size; BIN_PX is in those
pixels): callers multiply our 512x288 coordinates by units.SCALE_TO_HD first.
Upstream reads players and strokes from DuckDB; here the caller passes arrays.
Pure numpy.
"""
import numpy as np

BODY_M = 1.78     # generic standing height for the person-ruler
HIGH_M = 1.55     # net-tape height (upstream's above/below-net band)
RULER_Q = 0.80    # box-height quantile ~ standing
BIN_PX = 30       # box-bottom y bin width (1280x720 px) for the depth-dependent ruler
VALID_M = (-0.5, 5.0)   # outside -> ruler/track glitch -> NaN


def contact_height(box_heights: np.ndarray, box_bottoms: np.ndarray, ground_y: float,
                   bottom_y: float, shuttle_y: float) -> float:
    """Contact height in metres for one hit, NaN when there is no estimate.

    box_heights / box_bottoms: this player's (one court side's) box heights
    and box-bottom y over the match, HD pixels. ground_y: the hitter's ground
    point (feet) at the hit, bottom_y: the hitter's box bottom at the hit (picks
    the depth bin), shuttle_y: the shuttle's image y at the hit.
    """
    if any(v is None or not np.isfinite(v) for v in (ground_y, bottom_y, shuttle_y)):
        return float("nan")
    heights = np.asarray(box_heights, dtype=float)
    bins = np.floor(np.asarray(box_bottoms, dtype=float) / BIN_PX)
    sel = heights[bins == np.floor(bottom_y / BIN_PX)]
    if sel.size == 0:
        return float("nan")
    ruler = float(np.quantile(sel, RULER_Q))
    if ruler <= 0:
        return float("nan")
    h = (ground_y - shuttle_y) * BODY_M / ruler
    return round(h, 3) if VALID_M[0] <= h <= VALID_M[1] else float("nan")
