import os
from pathlib import Path

import pytest

from pro_profiles.doubles_load import DMatch, DPlayer, DRally, DShot, Pair, load_doubles
from pro_profiles.doubles_stats import (
    MEASURES,
    MIN_MATCHES,
    MIN_SAMPLE,
    PairStats,
    pair_stats,
    placement_zone,
    rank_measure,
    ranked_pairs,
)
from pro_profiles.load import load_content
from pro_profiles.stats import _rank, rank_value

GROUNDED = "Opp Grounded within Boundaries"
AB = Pair(id="ab", event="XD", players=("1", "2"))
CD = Pair(id="cd", event="XD", players=("3", "4"))
PAIRS = {"ab": AB, "cd": CD}
PLAYERS = {
    "1": DPlayer("1", "Al A", "A", "Male", "X"),
    "2": DPlayer("2", "Bea B", "B", "Female", "X"),
    "3": DPlayer("3", "Cy C", "C", "Male", "X"),
    "4": DPlayer("4", "Di D", "D", "Female", "X"),
}
SERVE = {"short": "short serve", "long": "long serve", None: None}


def make_rally(serve_type, met_at, shots, winner, reason=None, fault=None, n=1):
    """`shots` is the server's id, then (player, type, formation) for shots 2
    onward. Returns `n` copies of the rally."""
    server, *rest = shots
    seq = [DShot(1, server, SERVE[serve_type], None, met_at)]
    seq += [DShot(i, p, t, f, None) for i, (p, t, f) in enumerate(rest, start=2)]
    return [
        DRally(
            match_id="m1", set_no=1, number=0, server=server,
            receiver=rest[0][0] if rest else None, winner=winner,
            serve_type=serve_type, shots=tuple(seq), lose_reason=reason,
            fault_player=fault, before=(0, 0),
        )
    ] * n


def fixture_match() -> DMatch:
    rallies = (
        # S1 x20: ab serve short to the centre; 3rd shot a push (attack); ab win by a winner.
        make_rally("short", (30, 20), ["1", ("3", "net shot", None), ("2", "push", "Attack")],
                   "ab", GROUNDED, n=20)
        # S2 x10: ab serve short and wide; 3rd shot a drive; cd win by a winner.
        + make_rally("short", (5, 20), ["2", ("4", "lift", None), ("1", "drive", None),
                                        ("3", "lift", "Defense"), ("2", "smash", "Attack"),
                                        ("4", "smash", None)], "cd", GROUNDED, n=10)
        # S3 x10: ab serve long and wide (x 50); cd win, ab failed return.
        + make_rally("long", (50, 120), ["1", ("4", "smash", None)], "cd", "Failed Return", "1", n=10)
        # S4 x2: serve with no type, no winner.
        + make_rally(None, None, ["1", ("3", "drive", None)], None, n=2)
        # R1 x20: cd serve short to the middle; ab push return; ab win on a cd net fault.
        + make_rally("short", (40, 20), ["3", ("1", "push", "Attack"), ("4", "lift", None)],
                     "ab", "Net Fault", "3", n=20)
        # R2 x15: met_at out of range; ab net-shot return; cd win on an ab net fault.
        + make_rally("short", (-1199, 20), ["4", ("2", "net shot", "Defense")], "cd", "Net Fault", "2", n=15)
        # R3 x5: return with no type (but a formation); no winner.
        + make_rally("short", (30, 20), ["3", ("2", None, "Attack"), ("3", "smash", None)], None, n=5)
        # R4 x6: ab smash return; cd win, ab hit out.
        + make_rally("short", (30, 20), ["3", ("1", "smash", None)], "cd", "Out of Bounds", "1", n=6)
    )
    return DMatch(id="m1", edition_id="e", round="R1", date="2023-01-01", event="XD",
                  winner="ab", loser="cd", rallies=rallies, set_scores=((21, 19),))


def test_measures_on_fixture():
    st = pair_stats([fixture_match()], AB, PLAYERS)
    assert st.pair == "ab" and st.matches == 1
    assert list(st.values) == list(MEASURES)
    expected = {
        "serve.short_share": (30 / 40, 40),
        "serve.win_rate": (20 / 40, 40),
        "serve.third_down": (20 / 30, 30),
        "receive.attack_share": (26 / 41, 41),
        "receive.win_rate": (20 / 41, 41),
        "first4.share": (71 / 81, 81),
        "first4.win_rate": (40 / 71, 71),
        "rally.attack_share": (56 / 81, 81),
        "rally.formation_attack": (55 / 70, 70),
    }
    for key, (value, n) in expected.items():
        assert st.samples[key] == n, key
        assert st.values[key] == pytest.approx(value), key

    d = st.dists
    assert st.samples["serve.placement"] == 40
    assert d["serve.placement"] == pytest.approx(
        {"centre": 0.5, "middle": 0.0, "wide": 0.25, "back_centre": 0.0, "back_wide": 0.25})
    assert d["receive.mix"] == pytest.approx({
        "net shot": 15 / 41, "push": 20 / 41, "smash": 6 / 41,
        "lift": 0.0, "drive": 0.0, "clear": 0.0, "drop": 0.0,
    })
    assert d["roles"].keys() == {"1", "2"}
    assert d["roles"]["1"] == pytest.approx({"smash": 6 / 16, "net shot": 0.0})
    assert d["roles"]["2"] == pytest.approx({"smash": 10 / 16, "net shot": 1.0})
    assert st.samples["points.lost"] == 41
    assert d["points.lost"] == pytest.approx({
        "opp_winner": 10 / 41, "net_fault": 15 / 41, "out": 6 / 41,
        "failed_return": 10 / 41, "judgment_error": 0.0, "fault": 0.0,
    })
    assert st.samples["points.won"] == 40
    assert d["points.won"] == pytest.approx({"winner": 0.5, "opp_error": 0.5})
    assert d["mixed.serve_by"] == pytest.approx({"man": 32 / 42, "woman": 10 / 42})
    assert d["mixed.receive_by"] == pytest.approx({"man": 26 / 46, "woman": 20 / 46})


def test_below_min_sample_is_none():
    m = fixture_match()
    short = DMatch(**{**m.__dict__, "rallies": m.rallies[:29]})  # 29 x S1
    st = pair_stats([short], AB, PLAYERS)
    assert MIN_SAMPLE == 30
    assert st.samples["serve.short_share"] == 29
    assert st.values["serve.short_share"] is None
    assert st.values["receive.win_rate"] is None and st.samples["receive.win_rate"] == 0
    # Exactly 30 is enough.
    st30 = pair_stats([DMatch(**{**m.__dict__, "rallies": m.rallies[:30]})], AB, PLAYERS)
    assert st30.values["serve.short_share"] == 1.0  # 20 x S1 + 10 x S2, all short
    assert st30.values["serve.win_rate"] == pytest.approx(20 / 30)


def test_one_match_pair_unranked():
    st = pair_stats([fixture_match()], AB, PLAYERS)
    assert MIN_MATCHES == 2 and st.matches == 1
    all_stats = {"ab": st, "cd": pair_stats([fixture_match()], CD, PLAYERS)}
    assert ranked_pairs(all_stats, PAIRS, "XD") == []
    assert rank_measure(all_stats, PAIRS, "ab", "serve.short_share") is None


def _ps(pair, matches, value):
    return PairStats(pair, matches, {k: value for k in MEASURES}, {k: 100 for k in MEASURES}, {})


def test_typical_includes_pair():
    pairs = {
        "p1": Pair("p1", "WD", ("1", "2")), "p2": Pair("p2", "WD", ("3", "4")),
        "p3": Pair("p3", "WD", ("5", "6")), "p4": Pair("p4", "WD", ("7", "8")),
        "one": Pair("one", "WD", ("9", "10")), "md": Pair("md", "MD", ("11", "12")),
    }
    all_stats = {
        "p1": _ps("p1", 2, 0.9), "p2": _ps("p2", 3, 0.5), "p3": _ps("p3", 5, 0.4),
        "p4": _ps("p4", 2, None), "one": _ps("one", 1, 0.0), "md": _ps("md", 9, 0.1),
    }
    assert ranked_pairs(all_stats, pairs, "WD") == ["p1", "p2", "p3", "p4"]
    r = rank_measure(all_stats, pairs, "p1", "serve.win_rate")
    # Median of p1, p2, p3 (p4's value is None; "one" and "md" are not in the group).
    assert (r.value, r.rank, r.of, r.below) == (0.9, 1, 3, 2)
    assert r.typical == pytest.approx(0.5)
    assert rank_measure(all_stats, pairs, "p3", "serve.win_rate").rank == 3
    assert rank_measure(all_stats, pairs, "p4", "serve.win_rate") is None
    assert rank_measure(all_stats, pairs, "one", "serve.win_rate") is None


def test_rank_value_wraps_rank():
    values = {"a": 0.2, "b": 0.5, "c": 0.5, "d": 0.9}
    for p in values:
        assert rank_value(values, p) == _rank(values, p)


def test_placement_zone_boundaries():
    z = placement_zone
    assert z((30.5, 20), "short") == "centre"
    assert z((20.5, 20), "short") == "centre"  # exactly 10 from the centre line
    assert z((40.5, 20), "short") == "centre"
    assert z((20.4, 20), "short") == "middle"
    assert z((40.6, 20), "short") == "middle"
    assert z((14.1, 20), "short") == "middle"
    assert z((14, 20), "short") == "wide"
    assert z((0, 20), "short") == "wide"
    assert z((46, 20), "short") == "wide"
    assert z((45.9, 20), "short") == "middle"
    assert z((61, 20), "short") == "wide"
    assert z((14, 120), "long") == "back_wide"
    assert z((46, 120), "long") == "back_wide"
    assert z((14.1, 120), "long") == "back_centre"
    assert z((45.9, 120), "long") == "back_centre"
    assert z((30.5, 120), "long") == "back_centre"


def test_mixed_serve_by_gender():
    st = pair_stats([fixture_match()], AB, PLAYERS)
    assert st.dists["mixed.serve_by"] == pytest.approx({"man": 32 / 42, "woman": 10 / 42})
    wd = Pair("ab", "WD", ("1", "2"))
    m = fixture_match()
    st_wd = pair_stats([DMatch(**{**m.__dict__, "event": "WD"})], wd, PLAYERS)
    assert "mixed.serve_by" not in st_wd.dists and "mixed.receive_by" not in st_wd.dists


# baek-lee-sh (WD, 10 matches): (value, sample, typical WD value). Match 10
# was hand-checked against the raw CSVs (see the task 2 report).
SNAPSHOT = {
    "serve.short_share": (0.9626, 401, 0.8795),
    "serve.win_rate": (0.5769, 442, 0.5028),
    "serve.third_down": (0.1465, 389, 0.2294),
    "receive.attack_share": (0.4106, 358, 0.4106),
    "receive.win_rate": (0.5486, 381, 0.5000),
    "first4.share": (0.1762, 823, 0.2172),
    "first4.win_rate": (0.5310, 145, 0.4891),
    "rally.attack_share": (0.3038, 7563, 0.3819),
    "rally.formation_attack": (0.4132, 6961, 0.4132),
}


@pytest.mark.skipif("DSHUTTLENET_DIR" not in os.environ, reason="DSHUTTLENET_DIR not set")
def test_real_snapshot():
    matches, pairs, players = load_doubles(
        Path(os.environ["DSHUTTLENET_DIR"]), load_content("doubles_tournaments")
    )
    all_stats = {pid: pair_stats(matches, p, players) for pid, p in pairs.items()}
    st = all_stats["baek-lee-sh"]
    assert st.matches == 10
    assert len(ranked_pairs(all_stats, pairs, "WD")) == 11
    assert len(ranked_pairs(all_stats, pairs, "MD")) == 10
    assert len(ranked_pairs(all_stats, pairs, "XD")) == 5
    assert set(SNAPSHOT) == set(MEASURES)
    for key, (value, n, typical) in SNAPSHOT.items():
        assert st.samples[key] == n, key
        assert st.values[key] == pytest.approx(value, abs=5e-5), key
        assert rank_measure(all_stats, pairs, "baek-lee-sh", key).typical == pytest.approx(
            typical, abs=5e-5), key
    assert st.samples["serve.placement"] == 401
    assert st.dists["serve.placement"] == pytest.approx({
        "centre": 0.9501, "middle": 0.0125, "wide": 0.0,
        "back_centre": 0.0150, "back_wide": 0.0224,
    }, abs=5e-5)
    assert st.samples["points.won"] == 451 and st.samples["points.lost"] == 349
