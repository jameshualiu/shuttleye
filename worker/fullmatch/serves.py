# Ported from COURTSIDE src/badminton/hits.py (the serve-onset pass of detect_hits),
# jayclim/BadmintonAI at commit 5c356f05cde0ed90c75316c133e0aba495e5232b.
# MIT License, Copyright (c) 2026 Jayden Lim
"""Serve detection as shuttle motion onset.

A serve starts from a shuttle at rest, so it never shows as a velocity kink and
hit detectors trained on kinks miss it. It is the first sustained fast motion
instead: three consecutive frame steps at >= 2 * MIN_SPEED (the pre-serve toss
and hand creep sit below that).

Pure numpy, no DuckDB. Coordinates are 1280x720 px and speeds px/frame at
30 fps (fullmatch.units); callers convert pipeline 512x288 tracks first.
"""
import numpy as np

MIN_SPEED = 3.0     # px/frame (1280x720, 30 fps); the onset needs 2x this
MIN_GAP = 8         # frames (30 fps); an existing hit within 2x this is the serve already


def serve_onset(xy: np.ndarray, frames: np.ndarray, hit_frames: list[int],
                min_speed: float = MIN_SPEED, min_gap: int = MIN_GAP) -> dict | None:
    """The first 3-step stretch of the raw (not interpolated) track `xy` with
    every step >= 2 * min_speed. Returns {"frame", "isServe": True, "score"} at
    the stretch's first frame (the last frame at rest), or None when there is
    no such stretch or a hit already sits within 2 * min_gap of it (as
    upstream, only the first fast stretch is considered).
    """
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 4:
        return None
    sp = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    for i in range(len(sp) - 2):
        seg = sp[i:i + 3]
        if not np.isnan(seg).any() and (seg >= 2 * min_speed).all():
            f = int(frames[i])
            if any(abs(f - h) <= 2 * min_gap for h in hit_frames):
                return None
            return {"frame": f, "isServe": True, "score": float(seg.sum())}
    return None
