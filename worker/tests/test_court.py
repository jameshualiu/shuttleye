"""Consensus court clustering (fullmatch/court.py)."""
from fullmatch.court import COURT_TOL_PX, consensus_court, court_distance, court_outliers

REAL = [[178, 123], [329, 123], [165, 176], [345, 176], [137, 263], [371, 263]]
REPLAY = [[429, 226], [484, 226], [420, 240], [490, 240], [400, 280], [500, 280]]


def shift(kp, dx, dy=0):
    return [[x + dx, y + dy] for x, y in kp]


def test_distance_is_worst_keypoint():
    kp = [list(p) for p in REAL]
    kp[4] = [137 + 3, 263 + 4]
    assert court_distance(REAL, kp) == 5.0


def test_largest_cluster_beats_first_detection():
    kps = [REPLAY, shift(REPLAY, 2), shift(REAL, 1), shift(REAL, -2, 1), REAL]
    idx, members = consensus_court(kps)
    assert idx in (2, 3, 4) and sorted(members) == [2, 3, 4]


def test_tie_goes_to_earliest_and_empty_is_none():
    assert consensus_court([REPLAY, REAL]) == (0, [0])
    assert consensus_court([]) is None


def test_jitter_within_tolerance_clusters_but_wrong_court_does_not():
    assert court_distance(REAL, shift(REAL, 4, 1)) <= COURT_TOL_PX
    assert court_distance(REAL, shift(REAL, 60)) > COURT_TOL_PX


def test_court_outliers_reports_deviating_chunks():
    def chunk(kp):
        return {"court_found": kp is not None,
                "geometry": None if kp is None else {"court_keypoints_6": kp}}
    chunks = [chunk(None), chunk(REAL), chunk(shift(REAL, 2)), chunk(REPLAY), chunk(shift(REAL, -1, 2))]
    mode, outliers = court_outliers(chunks)
    assert court_distance(mode, REAL) <= COURT_TOL_PX
    assert outliers == [3]
    assert court_outliers([chunk(None)]) == (None, [])
