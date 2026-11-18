import os
from pathlib import Path

import pytest

from pro_profiles.load import Match, Rally, Shot, load_content, load_dataset
from pro_profiles.stats import (
    BANDS,
    PlayerStats,
    SHOWN_GROUPS,
    player_stats,
    rank_band,
    rank_shot_share,
    share,
    win_rate,
)


def shot(player, group, order=1, is_serve=False):
    return Shot(1, order, 0.0, player, group, is_serve)


def rally(shots, winner, n=1):
    return Rally("m", 1, n, tuple(shots), winner, 0, 0)


def match(rallies, winner="a", loser="b"):
    return Match("m", "ShuttleSet", "e", "Final", "2022-01-01", winner, loser, None, tuple(rallies))


def ps(player="p", groups=None, rallies=None, wins=None):
    groups = groups or {}
    return PlayerStats(
        player,
        groups,
        sum(groups.values()),
        rallies or {"short": 0, "mid": 0, "long": 0},
        wins or {"short": 0, "mid": 0, "long": 0},
    )


def test_share_denominator_includes_net_kill_excludes_serves():
    shots = [
        shot("a", None, 1, True),
        shot("b", "Net", 2),
        shot("a", "Lift", 3),
        shot("b", "Net kill", 4),
        shot("a", "Smash", 5),
        shot("b", None, 6),  # unknown
        shot("a", "Net", 7),
        shot("a", "Net", 8),
    ]
    s = player_stats([match([rally(shots, "a")])], "a")
    assert s.grouped_shots == 4
    assert s.shots_by_group == {"Lift": 1, "Smash": 1, "Net": 2}
    assert share(s, "Net") == pytest.approx(0.5)
    b = player_stats([match([rally(shots, "a")])], "b")
    assert b.grouped_shots == 2  # Net + Net kill
    assert share(b, "Net") == pytest.approx(0.5)
    assert "Net kill" not in SHOWN_GROUPS


def test_band_boundaries_and_wins():
    def r(n, w):
        return rally([shot("a", "Net", i) for i in range(n)], w)

    m = match([r(4, "a"), r(5, "b"), r(8, "a"), r(9, "a"), r(12, "b")])
    s = player_stats([m], "a")
    assert s.rallies_by_band == {"short": 1, "mid": 2, "long": 2}
    assert s.wins_by_band == {"short": 1, "mid": 1, "long": 1}
    assert [b[0] for b in BANDS] == ["short", "mid", "long"]


def test_rally_without_winner_excluded_from_bands():
    m = match([rally([shot("a", "Net")], None), rally([shot("a", "Net")], "a")])
    s = player_stats([m], "a")
    assert s.rallies_by_band["short"] == 1
    assert s.wins_by_band["short"] == 1
    assert s.shots_by_group == {"Net": 2}
    assert s.grouped_shots == 2


def test_player_not_in_match_ignored():
    m = match([rally([shot("a", "Net")], "a")])
    s = player_stats([m], "zzz")
    assert s.grouped_shots == 0
    assert s.rallies_by_band == {"short": 0, "mid": 0, "long": 0}


def test_rank_ties_use_competition_ranking():
    allst = {k: ps(k, {"Lift": v, "Net": 300 - v}) for k, v in zip("xyz", [150, 150, 90])}
    # shares of Lift: .5 .5 .3
    r = [rank_shot_share(allst, k, "Lift") for k in "xyz"]
    assert [x.rank for x in r] == [1, 1, 3]
    assert [x.below for x in r] == [1, 1, 0]
    assert r[0].of == 3
    assert r[0].percentile == pytest.approx(50.0)
    assert r[2].percentile == 0.0


def test_typical_is_median_including_player():
    allst = {k: ps(k, {"Lift": v, "Net": 300 - v}) for k, v in zip("abcd", [30, 60, 90, 270])}
    r = rank_shot_share(allst, "a", "Lift")
    # shares .1 .2 .3 .9 -> median .25
    assert r.typical == pytest.approx(0.25)
    assert r.value == pytest.approx(0.1)
    assert r.rank == 4


def test_shot_rank_needs_300_grouped_shots():
    allst = {"a": ps("a", {"Lift": 10, "Net": 289}), "b": ps("b", {"Lift": 100, "Net": 200})}
    assert rank_shot_share(allst, "a", "Lift") is None
    r = rank_shot_share(allst, "b", "Lift")
    assert r.of == 1


def test_band_needs_30_rallies():
    s = ps("a", rallies={"short": 29, "mid": 0, "long": 0}, wins={"short": 20, "mid": 0, "long": 0})
    assert win_rate(s, "short") is None
    assert rank_band({"a": s}, "a", "short") is None
    s30 = ps("a", rallies={"short": 30, "mid": 0, "long": 0}, wins={"short": 15, "mid": 0, "long": 0})
    assert win_rate(s30, "short") == pytest.approx(0.5)
    assert rank_band({"a": s30}, "a", "short").rank == 1


def test_band_group_excludes_small_samples():
    big = lambda k, w: ps(k, rallies={"short": 40, "mid": 0, "long": 0}, wins={"short": w, "mid": 0, "long": 0})
    small = ps("s", rallies={"short": 5, "mid": 0, "long": 0}, wins={"short": 5, "mid": 0, "long": 0})
    allst = {"a": big("a", 20), "b": big("b", 30), "s": small}
    r = rank_band(allst, "a", "short")
    assert r.of == 2 and r.rank == 2 and r.typical == pytest.approx(0.625)


@pytest.mark.skipif(not os.environ.get("SHUTTLESET_DIR"), reason="needs SHUTTLESET_DIR")
def test_axelsen_snapshot():
    matches = load_dataset(
        Path(os.environ["SHUTTLESET_DIR"]), load_content("players"), load_content("tournaments")
    )
    pids = {s for m in matches for s in (m.winner, m.loser)}
    allst = {p: player_stats(matches, p) for p in pids}
    pid = next(p for p in pids if "axelsen" in p)
    a = allst[pid]
    assert a.grouped_shots == 7080
    expect = {"Net": 35.6, "Lift": 27.7, "Smash": 15.6, "Push": 6.4, "Drop": 5.0, "Drive": 4.7, "Clear": 3.8}
    for g, v in expect.items():
        assert round(share(a, g) * 100, 1) == v, g
    for g, rk in {"Lift": 1, "Smash": 5, "Drop": 38, "Clear": 36}.items():
        r = rank_shot_share(allst, pid, g)
        assert (r.rank, r.of) == (rk, 39), g
    assert a.rallies_by_band == {"short": 349, "mid": 344, "long": 695}
    for band, win, typ in [("short", 56, 50), ("mid", 60, 51), ("long", 58, 49)]:
        assert round(win_rate(a, band) * 100) == win, band
        assert round(rank_band(allst, pid, band).typical * 100) == typ, band
