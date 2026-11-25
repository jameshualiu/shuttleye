"""Consensus court from many court_keypoints_6 detections. Pure Python.

A broadcast's play camera is fixed, so detections of the real court agree to a
few pixels while close-ups and replays give scattered, wrong "courts". Taking
the first detection (setup_homography's default) can lock onto one of those;
taking the largest cluster can't, as long as play dominates the samples.
"""
import math

# Max per-keypoint distance (512x288 pipeline pixels) for two kp6 detections to
# count as the same court. On the Axelsen v Christie broadcast the correct
# per-chunk courts sat within 4.1 px of the match median; the wrong ones were
# 60-280 px off. 10 px is ~2.5x the observed jitter and 6x under the nearest
# wrong court.
COURT_TOL_PX = 10.0


def court_distance(a, b) -> float:
    """Largest Euclidean distance between corresponding keypoints."""
    return max(math.dist(p, q) for p, q in zip(a, b))


def consensus_court(kps: list, tol: float = COURT_TOL_PX) -> tuple[int, list[int]] | None:
    """Pick the detection with the most others within `tol` (ties: earliest).

    Returns (index of that detection, indices of its cluster), or None for no
    detections. A real detection is returned (not an average) so callers can
    keep its matching court/net/35-point geometry.
    """
    if not kps:
        return None
    best, best_members = 0, []
    for i, a in enumerate(kps):
        members = [j for j, b in enumerate(kps) if court_distance(a, b) <= tol]
        if len(members) > len(best_members):
            best, best_members = i, members
    return best, best_members


def court_outliers(chunks: list[dict], tol: float = COURT_TOL_PX) -> tuple[list | None, list[int]]:
    """Match-wide mode court over merge_chunks()' chunk list, and the ids of
    chunks with a court that deviates from it by more than `tol`."""
    found = [(i, c["geometry"]["court_keypoints_6"]) for i, c in enumerate(chunks)
             if c.get("court_found") and (c.get("geometry") or {}).get("court_keypoints_6")]
    pick = consensus_court([kp for _, kp in found], tol)
    if pick is None:
        return None, []
    mode = found[pick[0]][1]
    return mode, [i for i, kp in found if court_distance(kp, mode) > tol]
