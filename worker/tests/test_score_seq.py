"""fullmatch.score_seq (vendored COURTSIDE score_seq.py): the expectations are
pinned to upstream's output on the same reads."""
from fullmatch.score_seq import is_final, point_log, set_finals, sets_won


def _reads(set_no, pairs):
    return [(set_no, x, y, i) for i, (x, y) in enumerate(pairs)]


def test_point_log_repairs_spike_and_expands_jump():
    # (0, 8) is the 0/8 template confusion; upstream keeps the opening 0-0 read
    # as an entry and splits 0-0 -> 2-0 -> 4-0 into single points
    reads = _reads(1, [(0, 0), (1, 0), (0, 8), (2, 0), (4, 0)])
    assert [p[1:3] for p in point_log(reads)] == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
    assert [p[5] for p in point_log(reads)] == [False, True, False, True, False]


def test_point_log_completes_cut_away_set_point_and_drops_spike():
    reads = [(1, 18, 15, 0), (1, 19, 15, 1), (1, 20, 15, 2),
             (2, 3, 1, 3), (2, 0, 8, 4), (2, 4, 1, 5)]
    pl = point_log(reads)
    assert set_finals(pl) == {1: (21, 15), 2: (4, 1)}
    assert pl[-1][1:4] == (4, 1, "x")
    assert sets_won(pl) == (1, 0)     # set 2 is not legally finished


def test_complete_leaves_truncated_set_alone():
    pl = point_log(_reads(1, [(5, 3)]))
    assert set_finals(pl) == {1: (5, 3)}


def test_is_final_rules():
    assert is_final(21, 19) and is_final(30, 29) and is_final(22, 20)
    assert not is_final(21, 20) and not is_final(29, 29)
