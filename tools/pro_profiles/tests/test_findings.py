import os
from pathlib import Path

import pytest

from pro_profiles.findings import (
    Finding,
    order_findings,
    pick_clips,
    render,
    select_findings,
    summary,
)
from pro_profiles.load import Match, Rally, Shot, load_content, load_dataset
from pro_profiles.stats import BANDS, SHOWN_GROUPS, PlayerStats, Ranked, player_stats, rank_band

BAND_KEYS = [b[0] for b in BANDS]
TOURNAMENTS = {"e": {"name": "Test Open", "season": 2022}}


def make_stats(n=11, target=5, target_groups=None, target_wins=None):
    """n pros, spread evenly so player `target` sits mid-table everywhere.

    Player i plays Lift 100 + 10i times and every other shown group 100 times,
    and wins 10 + 2i of 40 rallies in every band.
    """
    allst = {}
    for i in range(n):
        pid = f"p{i}"
        groups = {g: 100 for g in SHOWN_GROUPS}
        groups["Lift"] = 100 + 10 * i
        wins = {b: 10 + 2 * i for b in BAND_KEYS}
        if i == target:
            groups = target_groups or groups
            wins = {**wins, **(target_wins or {})}
        allst[pid] = PlayerStats(
            pid, groups, sum(groups.values()), {b: 40 for b in BAND_KEYS}, wins
        )
    return allst


def players_for(allst, event="MS"):
    return {p: {"name": p.upper(), "event": event} for p in allst}


def extreme_lifter():
    # Plays far more Lift and fewer of everything else than any other pro.
    groups = {g: 50 for g in SHOWN_GROUPS}
    groups["Lift"] = 1000
    return groups


def test_no_findings_player():
    allst = make_stats()
    found = select_findings("p5", allst, [], {}, players=players_for(allst))
    assert found == []
    assert summary("p5", found, players=players_for(allst)) is None


def test_weakness_comparison_uses_typical():
    # Mid-band wins 15/40 = 37.5%; the median pro wins 18/40 = 45%. Rank 8 of 11:
    # not bottom 4, but still the weakness: lowest band, 3+ points below typical.
    allst = make_stats(target_wins={"mid": 15})
    found = select_findings("p5", allst, [], {}, players=players_for(allst))
    assert [f.key for f in found] == ["band.mid.weakness"]
    w = found[0]
    assert w.kind == "weakness"
    assert w.claim == "Medium-length rallies are where he loses"
    assert w.figure == "38%"
    assert w.comparison == "won in 5 to 8 shots. A typical pro: 45%."
    assert summary("p5", found, players=players_for(allst)) == (
        "Keep the rally to 5 to 8 shots and he's beatable."
    )


def test_womens_pronouns():
    allst = make_stats(target=10)
    players = players_for(allst, event="WS")
    found = select_findings("p10", allst, [], {}, players=players)
    lift = next(f for f in found if f.key == "shot.Lift.top")
    assert lift.claim == "She lifts more than any other pro"
    assert lift.comparison.startswith("of her shots.")
    s = summary("p10", found, players=players)
    assert s.startswith("She ")
    assert " he " not in f" {s} " and " his " not in f" {s} "


def test_weakness_kept_when_more_than_four_candidates():
    # 7 style findings at the extremes (distance 50) plus a mild weakness.
    allst = make_stats(target_groups=extreme_lifter(), target_wins={"mid": 15})
    found = select_findings("p5", allst, [], {}, players=players_for(allst))
    assert len(found) == 4
    assert [f.kind for f in found] == ["style", "style", "style", "weakness"]
    assert found[-1].key == "band.mid.weakness"
    # Equal distances fall back to key order.
    assert [f.key for f in found[:3]] == ["shot.Clear.bottom", "shot.Drive.bottom", "shot.Drop.bottom"]


def fake(key, kind, dist, phrase=""):
    return Finding(key, kind, "", "", "", None, [], dist, phrase)


def test_order_ties_go_style_strength_weakness_then_key():
    fs = [
        fake("band.long.strength", "strength", 47.4),
        fake("shot.Drop.bottom", "style", 47.4),
        fake("band.short.weakness", "weakness", 47.4),
        fake("shot.Clear.bottom", "style", 47.4),
        fake("shot.Lift.top", "style", 50.0),
    ]
    assert [f.key for f in order_findings(fs)] == [
        "shot.Lift.top", "shot.Clear.bottom", "shot.Drop.bottom", "band.short.weakness"
    ]


def test_order_weakness_always_last_even_when_most_extreme():
    fs = [fake("band.mid.weakness", "weakness", 50.0), fake("shot.Net.top", "style", 10.0)]
    assert [f.kind for f in order_findings(fs)] == ["style", "weakness"]


def test_summary_parts():
    style = fake("shot.Lift.top", "style", 50, "lifts more than anyone else in the data")
    strong = fake("band.long.strength", "strength", 47,
                  "lets rallies run long, where he wins far more than most")
    weak = fake("band.short.weakness", "weakness", 20, "Keep the rally short and he's beatable.")
    p = {"x": {"event": "MS"}}
    assert summary("x", [style, strong, weak], players=p) == (
        "He lifts more than anyone else in the data and lets rallies run long, where he "
        "wins far more than most. Keep the rally short and he's beatable."
    )
    assert summary("x", [strong], players=p) == (
        "He lets rallies run long, where he wins far more than most."
    )
    assert summary("x", [weak], players=p) == "Keep the rally short and he's beatable."
    # Only the first style and first strength finding are used.
    style2 = fake("shot.Drop.bottom", "style", 47, "rarely drops")
    assert summary("x", [style, style2], players=p) == (
        "He lifts more than anyone else in the data."
    )


# --- clips -----------------------------------------------------------------

def shot(player, group, t, order):
    return Shot(0, order, t, player, group, group is None)


def rally(mid, set_no, n, groups_by_player, winner):
    shots = tuple(
        shot(p, g, 10.0 * n + i, i + 1) for i, (p, g) in enumerate(groups_by_player)
    )
    return Rally(mid, set_no, n, shots, winner, 0, 0)


def match(mid, date, rallies):
    return Match(mid, "ShuttleSet", "e", "Finals", date, "p", "q", None, tuple(rallies))


def lift_rally(mid, set_no, n, winner="p"):
    return rally(mid, set_no, n, [("p", None), ("q", "Net"), ("p", "Lift")], winner)


def test_pick_clips_prefers_distinct_matches_then_date():
    m_late = match("late", "2022-05-01", [lift_rally("late", 1, 1), lift_rally("late", 1, 2)])
    m_early = match("early", "2021-01-01", [
        lift_rally("early", 2, 1),
        lift_rally("early", 1, 3),
        lift_rally("early", 1, 2, winner="q"),  # lost: not an example
        rally("early", 1, 4, [("p", None), ("q", "Lift")], "p"),  # q lifted, not p
        lift_rally("early", 1, 5),
        lift_rally("early", 1, 6),
    ])
    m_none = match("nosrc", "2020-01-01", [lift_rally("nosrc", 1, 1)])
    sources = {
        "late": {"url": "https://youtu.be/LATE", "offsetSec": 0},
        "early": {"url": "https://youtu.be/EARLY", "offsetSec": 0},
    }
    clips = pick_clips(
        "p", "shot.Lift.top", [m_late, m_early, m_none], sources,
        players={"p": {"name": "P"}, "q": {"name": "Q"}}, tournaments=TOURNAMENTS,
    )
    order = [(c.match_id, c.score_label) for c in clips]
    assert order == [
        ("early", "game 1 at 0–0"),  # early set 1 rally 3
        ("late", "game 1 at 0–0"),
        ("early", "game 1 at 0–0"),  # early set 1 rally 5
        ("late", "game 1 at 0–0"),
        ("early", "game 1 at 0–0"),  # early set 1 rally 6
    ]
    starts = [c.start_sec for c in clips]
    assert starts == [28, 8, 48, 18, 58]


def test_pick_clips_band_weakness_uses_lost_rallies():
    short_lost = rally("m", 1, 1, [("p", None), ("q", "Smash")], "q")
    short_won = rally("m", 1, 2, [("p", None), ("q", "Smash")], "p")
    no_winner = rally("m", 1, 3, [("p", None)], None)
    m = match("m", "2022-01-01", [short_lost, short_won, no_winner])
    sources = {"m": {"url": "https://youtu.be/M", "offsetSec": 0}}
    kw = dict(players={"p": {"name": "P"}, "q": {"name": "Q"}}, tournaments=TOURNAMENTS)
    lost = pick_clips("p", "band.short.weakness", [m], sources, **kw)
    won = pick_clips("p", "band.short.strength", [m], sources, **kw)
    assert [c.start_sec for c in lost] == [8]
    assert [c.start_sec for c in won] == [18]


def test_finding_without_clip_sources():
    allst = make_stats(target=10)
    m = Match("m", "ShuttleSet", "e", "Finals", "2022-01-01", "p10", "p0", None, (
        rally("m", 1, 1, [("p10", None), ("p0", "Net"), ("p10", "Lift")], "p10"),))
    found = select_findings(
        "p10", allst, [m], {}, players=players_for(allst), tournaments=TOURNAMENTS
    )
    assert found and all(f.clips == [] for f in found)


# --- content completeness ----------------------------------------------------

def all_keys():
    keys = [f"shot.{g}.{side}" for g in SHOWN_GROUPS for side in ("top", "bottom")]
    keys += [f"band.{b}.{kind}" for b in BAND_KEYS for kind in ("strength", "weakness")]
    return keys


def test_every_key_has_template_and_tip():
    templates = load_content("templates")
    tips = load_content("tips")
    for key in ("claim.shot.top1", "claim.shot.top", "claim.shot.bottom", "claim.shot.bottom_mild",
                "comparison.shot.top", "comparison.shot.bottom"):
        assert key in templates, key
    for g in SHOWN_GROUPS:
        assert g in templates["verbs"], g
        for side in ("top1", "top", "bottom", "bottom_mild"):
            assert f"phrase.shot.{g}.{side}" in templates, (g, side)
    for b in BAND_KEYS:
        for kind in ("strength", "weakness"):
            assert f"claim.band.{b}.{kind}" in templates
            assert f"comparison.band.{b}.{kind}" in templates
        assert f"phrase.band.{b}.strength" in templates
        assert f"sentence.band.{b}.weakness" in templates
    for key in all_keys():
        assert isinstance(tips.get(key), str) and tips[key].strip(), key
    tip_keys = [k for k in tips if not k.startswith("_")]
    assert len(tip_keys) == 22  # 8 groups x top/bottom + 3 bands x strength/weakness
    assert tips["_status"] == "draft — James to review"
    assert tips["shot.Lift.top"] == (
        "When you're under pressure, lift high to the back corners instead of forcing a "
        "drop. It buys you time to get back to the middle."
    )


@pytest.mark.parametrize("event,he,his", [("MS", "He", "his"), ("WS", "She", "her")])
def test_every_key_renders(event, he, his):
    for key in all_keys():
        kind = "style" if key.startswith("shot.") else key.split(".")[2]
        for rank, below in ((1, 38), (2, 37), (39, 0), (38, 1), (37, 2)):
            r = Ranked(value=0.2, rank=rank, of=39, below=below, typical=0.189,
                       percentile=below / 38 * 100)
            claim, figure, comparison, phrase = render(key, kind, r, event)
            for text in (claim, comparison, phrase):
                assert text and "{" not in text and "}" not in text, (key, text)
            assert claim.startswith((he, "Long", "Medium", "Short")), claim
            if kind == "weakness":
                assert phrase.endswith("."), phrase
            else:
                assert not phrase[0].isupper(), phrase


def test_bottom_comparison_agrees_with_count():
    r = lambda below: Ranked(0.04, 39 - below, 39, below, 0.1, below / 38 * 100)
    assert render("shot.Drop.bottom", "style", r(1), "MS")[2] == "Only one of 38 pros drops less."
    assert render("shot.Drop.bottom", "style", r(3), "MS")[2] == "Only 3 of 38 pros drop less."
    assert render("shot.Drop.bottom", "style", r(0), "MS")[2] == "No other pro drops less."
    assert render("shot.Net.bottom", "style", r(1), "WS")[0] == "She almost never plays net shots"
    # The comparison's plural agreement must not leak into the claim.
    assert render("shot.Lift.bottom", "style", r(2), "MS")[:3:2] == (
        "He almost never lifts", "Only 2 of 38 pros lift less.")


def test_bottom_claim_almost_never_only_under_half_typical():
    # Axelsen-like: 5.0% vs typical 10.2% -> under half -> "almost never".
    strong = Ranked(0.050, 38, 39, 1, 0.102, 1 / 38 * 100)
    claim, _, _, phrase = render("shot.Drop.bottom", "style", strong, "MS")
    assert (claim, phrase) == ("He almost never drops", "rarely drops")
    # Chou-like: 14.3% vs typical 18.9% -> not under half -> mild wording, same key.
    mild = Ranked(0.143, 37, 39, 2, 0.189, 2 / 38 * 100)
    claim, _, comparison, phrase = render("shot.Lift.bottom", "style", mild, "WS")
    assert claim == "She lifts less than most pros"
    assert phrase == "lifts less than most"
    assert comparison == "Only 2 of 38 pros lift less."
    # Exactly half is not "under half".
    half = Ranked(0.05, 38, 39, 1, 0.10, 1 / 38 * 100)
    assert render("shot.Drop.bottom", "style", half, "MS")[0] == "He drops less than most pros"


def band_stats(target_mid_wins):
    """11 pros, 100 rallies per band, mid-band typical (median) = 51%."""
    others = [40, 45, 48, 50, 51, 51, 52, 55, 58, 60]
    allst = {}
    for i, mid in enumerate(others + [target_mid_wins]):
        pid = "t" if i == len(others) else f"o{i}"
        allst[pid] = PlayerStats(
            pid, {}, 0, {b: 100 for b in BAND_KEYS}, {"short": 60, "mid": mid, "long": 60}
        )
    return allst


@pytest.mark.parametrize("mid,weak", [(50, False), (49, False), (48, True), (45, True)])
def test_weakness_needs_three_point_gap(mid, weak):
    allst = band_stats(mid)
    assert rank_band(allst, "t", "mid").typical == pytest.approx(0.51)
    found = select_findings("t", allst, [], {}, players=players_for(allst))
    assert ("band.mid.weakness" in [f.key for f in found]) is weak


def test_top_claim_uses_top1_only_for_rank_one():
    r1 = Ranked(0.277, 1, 39, 38, 0.189, 100.0)
    r3 = Ranked(0.25, 3, 39, 36, 0.189, 36 / 38 * 100)
    assert render("shot.Lift.top", "style", r1, "MS")[0] == "He lifts more than any other pro"
    assert render("shot.Lift.top", "style", r3, "MS")[0] == "He lifts more than most pros"
    assert render("shot.Lift.top", "style", r1, "MS")[1] == "27.7%"
    assert render("shot.Lift.top", "style", r1, "MS")[3] == "lifts more than anyone else in the data"


# --- real data ---------------------------------------------------------------

needs_data = pytest.mark.skipif(
    not os.environ.get("SHUTTLESET_DIR"), reason="needs SHUTTLESET_DIR"
)


@pytest.fixture(scope="module")
def real():
    matches = load_dataset(
        Path(os.environ["SHUTTLESET_DIR"]), load_content("players"), load_content("tournaments")
    )
    pids = {s for m in matches for s in (m.winner, m.loser)}
    allst = {p: player_stats(matches, p) for p in pids}
    return matches, allst


@needs_data
def test_axelsen_findings(real):
    matches, allst = real
    found = select_findings("viktor-axelsen", allst, matches, load_content("clip_sources"))
    assert [f.key for f in found] == [
        "shot.Lift.top", "shot.Drop.bottom", "band.long.strength", "band.mid.strength"
    ]
    assert [f.kind for f in found] == ["style", "style", "strength", "strength"]
    assert [f.claim for f in found] == [
        "He lifts more than any other pro",
        "He almost never drops",
        "Long rallies go his way",
        "Medium-length rallies go his way",
    ]
    assert [f.figure for f in found] == ["27.7%", "5.0%", "58%", "60%"]
    assert [f.comparison for f in found] == [
        "of his shots. A typical pro: 18.9%.",
        "Only one of 38 pros drops less.",
        "won past 8 shots. Better than 37 of 38 pros.",
        "won in 5 to 8 shots. Better than 34 of 35 pros.",
    ]
    assert found[0].tip.startswith("When you're under pressure, lift high")
    for f in found:
        assert 1 <= len(f.clips) <= 5
        ids = [c.match_id for c in f.clips]
        distinct = len(set(ids))
        assert len(set(ids[:distinct])) == distinct  # different matches come first


@needs_data
def test_axelsen_summary(real):
    matches, allst = real
    found = select_findings("viktor-axelsen", allst, matches, load_content("clip_sources"))
    assert summary("viktor-axelsen", found) == (
        "He lifts more than anyone else in the data and lets rallies run long, "
        "where he wins far more than most."
    )
