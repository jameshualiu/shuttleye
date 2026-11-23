import os
from pathlib import Path

import pytest

from pro_profiles.doubles_findings import (
    EDGE,
    EDGE_SMALL,
    MIN_GAP,
    RARELY_MAX,
    SMALL_GROUP,
    WEAKNESS_GAP,
    all_keys,
    display_last_name,
    full_name,
    given_name,
    pair_name,
    pair_summary,
    select_pair_findings,
)
from pro_profiles.doubles_load import DPlayer, Pair, load_doubles
from pro_profiles.doubles_stats import MEASURES, PairStats, pair_stats, ranked_pairs
from pro_profiles.load import load_content

WIN_RATES = ("serve.win_rate", "receive.win_rate", "first4.win_rate")


def group(event: str, columns: dict[str, list[float | None]], matches: int = 3):
    """Pairs p0..pN-1 in one event. `columns` maps a measure to one value per
    pair; measures left out are None for every pair."""
    n = len(next(iter(columns.values())))
    pairs, players, all_stats = {}, {}, {}
    for i in range(n):
        pid = f"p{i}"
        a, b = f"{pid}a", f"{pid}b"
        players[a] = DPlayer(a, f"Ann Alpha{i}", f"Alpha{i}", "Female", "X")
        players[b] = DPlayer(b, f"Bo Beta{i}", f"Beta{i}", "Female", "X")
        pairs[pid] = Pair(pid, event, (a, b))
        values = {k: columns.get(k, [None] * n)[i] for k in MEASURES}
        all_stats[pid] = PairStats(pid, matches, values, {k: 100 for k in MEASURES}, {})
    return all_stats, pairs, players


def keys(pair_id, all_stats, pairs):
    return [f.key for f in select_pair_findings(pair_id, all_stats, pairs)]


def test_constants():
    assert (EDGE, EDGE_SMALL, SMALL_GROUP, MIN_GAP, WEAKNESS_GAP, RARELY_MAX) == (
        2, 1, 8, 0.05, 0.03, 0.15)


def test_needs_rank_and_gap():
    # 10 pairs; p0 is 2nd. The typical pair (median) is 0.50.
    base = [None, 0.99] + [0.50] * 8
    st, pairs, _ = group("MD", {"serve.short_share": [0.54] + base[1:]})
    assert keys("p0", st, pairs) == []  # 4 points from typical
    st, pairs, _ = group("MD", {"serve.short_share": [0.56] + base[1:]})
    assert keys("p0", st, pairs) == ["serve.short_share.top"]  # 6 points
    st, pairs, _ = group("MD", {"serve.short_share": [0.55] + base[1:]})
    assert keys("p0", st, pairs) == ["serve.short_share.top"]  # exactly 5 points
    # 3rd place is never a finding in a group of 8 or more, whatever the gap.
    st, pairs, _ = group("MD", {"serve.short_share": [0.90, 0.99, 0.95] + [0.50] * 7})
    assert keys("p0", st, pairs) == []
    # Bottom 2 with the gap.
    st, pairs, _ = group("MD", {"serve.short_share": [0.40, 0.30] + [0.50] * 8})
    assert keys("p0", st, pairs) == ["serve.short_share.bottom"]


def test_small_group_uses_edge_one():
    st, pairs, _ = group("XD", {"rally.attack_share": [0.40, 0.45, 0.30, 0.30, 0.30]})
    assert keys("p0", st, pairs) == []  # 2nd of 5
    assert keys("p1", st, pairs) == ["rally.attack_share.top"]
    st, pairs, _ = group("XD", {"rally.attack_share": [0.20, 0.10, 0.30, 0.30, 0.30]})
    assert keys("p0", st, pairs) == []  # 2nd from bottom of 5
    assert keys("p1", st, pairs) == ["rally.attack_share.bottom"]


def test_weakness_largest_gap_3_points():
    others = [0.50] * 9
    cols = lambda s, r, f: {  # noqa: E731
        "serve.win_rate": [s] + others, "receive.win_rate": [r] + others,
        "first4.win_rate": [f] + others,
    }
    st, pairs, _ = group("MD", cols(0.49, 0.47, 0.48))
    found = select_pair_findings("p0", st, pairs)
    assert [(f.key, f.kind) for f in found] == [("receive.win_rate.weakness", "weakness")]
    assert found[0].figure == "47%"
    assert found[0].comparison == "won when receiving. A typical pair: 50%."
    st, pairs, _ = group("MD", cols(0.49, 0.48, 0.485))
    assert keys("p0", st, pairs) == []  # lowest is only 2 points below
    # Lowest win rate also bottom 2 with the gap: listed once, as the weakness.
    st, pairs, _ = group("MD", cols(0.49, 0.40, 0.48))
    found = select_pair_findings("p0", st, pairs)
    assert [(f.key, f.kind) for f in found] == [("receive.win_rate.weakness", "weakness")]
    assert found[0].claim == "They win fewer of the rallies they receive than any other pair"


def test_weakness_is_largest_gap_not_lowest_value():
    # Serve is the lowest value (40%) but only 5 points under its typical 45%;
    # receive is 48%, 7 points under its typical 55%.
    st, pairs, _ = group("MD", {
        "serve.win_rate": [0.40] + [0.45] * 9,
        "receive.win_rate": [0.48] + [0.55] * 9,
        "first4.win_rate": [0.50] * 10,
    })
    found = select_pair_findings("p0", st, pairs)
    assert [f.key for f in found] == ["receive.win_rate.weakness"]
    # Equal gaps: serve before receive before first4.
    st, pairs, _ = group("MD", {
        "serve.win_rate": [0.40] + [0.45] * 9,
        "receive.win_rate": [0.50] + [0.55] * 9,
        "first4.win_rate": [0.45] + [0.50] * 9,
    })
    assert keys("p0", st, pairs) == ["serve.win_rate.weakness"]
    st, pairs, _ = group("MD", {
        "receive.win_rate": [0.50] + [0.55] * 9,
        "first4.win_rate": [0.45] + [0.50] * 9,
    })
    assert keys("p0", st, pairs) == ["receive.win_rate.weakness"]


def test_win_rate_strength():
    st, pairs, _ = group("MD", {"serve.win_rate": [0.60, 0.58] + [0.50] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert (f.key, f.kind) == ("serve.win_rate.top", "strength")
    assert f.claim == "They win more of the rallies they serve than any other pair"
    assert (f.figure, f.comparison) == ("60%", "won when serving. Better than every other pair.")
    [f] = select_pair_findings("p1", st, pairs)
    assert f.claim == "They win more of the rallies they serve than most pairs"
    assert f.comparison == "won when serving. Better than 8 of 9 pairs."


def test_serve_receive_first_on_ties():
    # p0 is strictly first on both: same percentile distance (50).
    st, pairs, _ = group("MD", {
        "rally.attack_share": [0.60] + [0.30] * 9,
        "serve.third_down": [0.60] + [0.20] * 9,
        "receive.attack_share": [0.90] + [0.40] * 9,
    })
    assert keys("p0", st, pairs) == [
        "receive.attack_share.top", "serve.third_down.top", "rally.attack_share.top"
    ]
    # More extreme comes first, whatever the section: p0 is 1st of 10 on the
    # rally measure but only 2nd on the serve one.
    st, pairs, _ = group("MD", {
        "rally.attack_share": [0.60] + [0.30] * 9,
        "serve.third_down": [0.60, 0.70] + [0.20] * 8,
    })
    assert keys("p0", st, pairs) == ["rally.attack_share.top", "serve.third_down.top"]


def test_at_most_four_weakness_last_and_serve_receive_kept():
    top = lambda v, rest: [v] + [rest] * 9  # noqa: E731
    st, pairs, _ = group("MD", {
        "serve.short_share": top(0.99, 0.80),
        "serve.third_down": top(0.60, 0.20),
        "receive.attack_share": top(0.90, 0.40),
        "first4.share": top(0.60, 0.30),
        "rally.attack_share": top(0.60, 0.30),
        "rally.formation_attack": top(0.80, 0.50),
        "serve.win_rate": top(0.40, 0.50),
        "receive.win_rate": top(0.50, 0.50),
        "first4.win_rate": top(0.50, 0.50),
    })
    found = select_pair_findings("p0", st, pairs)
    assert len(found) == 4
    assert found[-1].key == "serve.win_rate.weakness"
    assert [f.kind for f in found[:3]] == ["style"] * 3
    assert all(not f.key.startswith("rally.") for f in found)  # ties go serve/receive first
    assert all(f.clips == [] for f in found)


def test_wording_rules():
    templates = load_content("doubles_templates")
    for text in templates.values():
        assert " far " not in f" {text} ".lower(), text
        assert "almost never" not in text.lower(), text  # doubles says "rarely"
    # Tied first: not "more than any other pair".
    st, pairs, _ = group("MD", {"serve.third_down": [0.40, 0.40] + [0.20] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They attack with their third shot more than most pairs"
    assert "any other" not in f.phrase
    # Strictly first.
    st, pairs, _ = group("MD", {"serve.third_down": [0.40, 0.35] + [0.20] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They attack with their third shot more than any other pair"
    assert (f.figure, f.comparison) == (
        "40%", "of their third shots were a smash, drop or push. A typical pair: 20%."
    )
    # "Almost never" only under half the typical value.
    st, pairs, _ = group("MD", {"serve.third_down": [0.09, 0.15] + [0.20] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They rarely attack with their third shot"  # under half of 20%
    # "Rarely" also needs the value itself at 15% or less: 40% against a
    # typical 88% is under half, but not rare.
    st, pairs, _ = group("MD", {"serve.short_share": [0.40, 0.70] + [0.88] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They serve short less than any other pair"
    st, pairs, _ = group("MD", {"serve.short_share": [0.40, 0.40] + [0.88] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They serve short less than most pairs"
    st, pairs, _ = group("MD", {"serve.third_down": [0.15, 0.25] + [0.40] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They rarely attack with their third shot"  # 15% exactly
    st, pairs, _ = group("MD", {"serve.third_down": [0.10, 0.15] + [0.20] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They attack with their third shot less than any other pair"
    st, pairs, _ = group("MD", {"serve.third_down": [0.10, 0.10] + [0.20] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.claim == "They attack with their third shot less than most pairs"  # tied last
    # Better than every other pair only when beating the whole group.
    st, pairs, _ = group("MD", {"first4.win_rate": [0.60, 0.60] + [0.50] * 8})
    [f] = select_pair_findings("p0", st, pairs)
    assert f.comparison == "won in rallies of 4 shots or fewer. Better than 8 of 9 pairs."
    assert f.claim == "They win more of their rallies of 4 shots or fewer than most pairs"


def test_every_key_has_template_and_tip():
    templates = load_content("doubles_templates")
    tips = load_content("doubles_tips")
    assert tips["_status"] == "draft — James to review"
    assert len(all_keys()) == 2 * len(MEASURES)
    assert sorted(k for k in tips if not k.startswith("_")) == sorted(all_keys())
    for key in all_keys():
        assert isinstance(tips[key], str) and tips[key].strip(), key
    # Every reachable rendering works for every key.
    for key in all_keys():
        measure, side = key.rsplit(".", 1)
        for value in (0.9, 0.3, 0.1):
            for column in ([value] + [0.5] * 9, [value, value] + [0.5] * 8):
                if side == "weakness":
                    cols = {m: [0.5] * 10 for m in WIN_RATES}
                    cols[measure] = [min(x, 0.45) for x in column]
                else:
                    cols = {measure: column}
                st, pairs, players = group("MD", cols)
                found = select_pair_findings("p0", st, pairs)
                for f in found:
                    for text in (f.claim, f.comparison, f.phrase):
                        assert "{" not in text and "}" not in text, (f.key, text)
                assert "{" not in (pair_summary("p0", found, pairs, players) or "")


def test_unranked_pair_no_findings():
    st, pairs, players = group("MD", {"serve.short_share": [0.99] + [0.50] * 9})
    st["p0"].matches = 1
    assert select_pair_findings("p0", st, pairs) == []
    assert pair_summary("p0", [], pairs, players) is None


def test_summary_parts():
    top = lambda v, rest: [v] + [rest] * 9  # noqa: E731
    cols = {
        "rally.attack_share": top(0.60, 0.30),
        "serve.short_share": [0.95, 0.99] + [0.80] * 8,
        "receive.win_rate": top(0.40, 0.50),
    }
    st, pairs, players = group("MD", cols)
    found = select_pair_findings("p0", st, pairs)
    assert [f.key for f in found] == [
        "rally.attack_share.top", "serve.short_share.top", "receive.win_rate.weakness"
    ]
    # Leads with the serve/receive finding even though the rally one ranks higher.
    assert pair_summary("p0", found, pairs, players) == (
        "Alpha0 and Beta0 serve short more than most pairs and attack more than any "
        "other pair. They are easier to beat when they receive."
    )
    # Only a weakness: the pair is named in the weakness sentence.
    st, pairs, players = group("MD", {"receive.win_rate": top(0.40, 0.50)})
    found = select_pair_findings("p0", st, pairs)
    assert pair_summary("p0", found, pairs, players) == (
        "Alpha0 and Beta0 are easier to beat when they receive."
    )
    # No serve/receive finding: lead with what there is.
    st, pairs, players = group("MD", {"rally.attack_share": top(0.60, 0.30)})
    found = select_pair_findings("p0", st, pairs)
    assert pair_summary("p0", found, pairs, players) == (
        "Alpha0 and Beta0 attack more than any other pair."
    )


def test_display_last_name():
    names = [display_last_name(DPlayer("1", "x", n, "Male", "X"), {})
             for n in ("BAEK", "Lee", "Pearly Tan", "VAN DER BERG", "JEAN-LUC")]
    assert names == ["Baek", "Lee", "Pearly Tan", "Van Der Berg", "Jean-Luc"]
    # The content override, by player id.
    pearly = DPlayer("44", "Pearly Tan Koong Le", "Pearly Tan", "Female", "Malaysia")
    assert display_last_name(pearly) == "Tan"
    assert load_content("doubles_display_names")["44"] == "Tan"


def test_given_name():
    assert given_name(DPlayer("50", "Benyapa Aimsaard", "Aimsaard", "Female", "X")) == "Benyapa"
    assert given_name(DPlayer("5", "KIM Gi Jung", "KIM", "Male", "X")) == "Gi Jung"
    assert given_name(DPlayer("9", "Thom GICQUEL", "GICQUEL", "Male", "X")) == "Thom"
    # Nothing left: the full name.
    assert given_name(DPlayer("7", "Tan", "Tan", "Female", "X"), {}) == "Tan"
    # The display override's last name is the one removed, wherever it is.
    pearly = DPlayer("44", "Pearly Tan Koong Le", "Pearly Tan", "Female", "Malaysia")
    assert given_name(pearly) == "Pearly Koong Le"
    assert given_name(pearly, {}) == "Koong Le"


def test_pair_name_shared_last_name_uses_given_names():
    players = {
        "50": DPlayer("50", "Benyapa Aimsaard", "Aimsaard", "Female", "X"),
        "51": DPlayer("51", "Nuntakarn Aimsaard", "Aimsaard", "Female", "X"),
        "5": DPlayer("5", "KIM Gi Jung", "KIM", "Male", "X"),
        "6": DPlayer("6", "KIM Sa Rang", "Kim", "Male", "X"),
        "44": DPlayer("44", "Pearly Tan Koong Le", "Pearly Tan", "Female", "X"),
        "45": DPlayer("45", "Thinaah Muralitharan", "Muralitharan", "Female", "X"),
    }
    pairs = {
        "aa": Pair("aa", "WD", ("50", "51")),
        "kk": Pair("kk", "MD", ("5", "6")),
        "tm": Pair("tm", "WD", ("44", "45")),
    }
    assert pair_name("aa", pairs, players) == "Benyapa and Nuntakarn Aimsaard"
    assert pair_name("kk", pairs, players) == "Gi Jung and Sa Rang Kim"
    assert pair_name("tm", pairs, players) == "Tan and Muralitharan"
    # The summary uses the same name.
    st, _, _ = group("WD", {"rally.attack_share": [0.60] + [0.30] * 9})
    st["aa"] = st.pop("p0")
    st["aa"].pair = "aa"
    gpairs = {**{k: Pair(k, "WD", (f"{k}a", f"{k}b")) for k in st if k != "aa"}, "aa": pairs["aa"]}
    gplayers = {**players, **{f"{k}{s}": DPlayer(f"{k}{s}", "A B", f"B{k}{s}", "Female", "X")
                              for k in st if k != "aa" for s in "ab"}}
    found = select_pair_findings("aa", st, gpairs)
    assert pair_summary("aa", found, gpairs, gplayers) == (
        "Benyapa and Nuntakarn Aimsaard attack more than any other pair."
    )


def test_pair_name_clash_uses_full_name_of_varying_partner():
    players = {
        "14": DPlayer("14", "BAEK Ha Na", "BAEK", "Female", "Korea"),
        "15": DPlayer("15", "LEE Yu Lim", "LEE", "Female", "Korea"),
        "33": DPlayer("33", "Lee So Hee", "Lee", "Female", "Korea"),
        "62": DPlayer("62", "LEE Yang", "LEE", "Male", "X"),
        "1": DPlayer("1", "BAEK Other", "BAEK", "Male", "X"),
    }
    pairs = {
        "sh": Pair("sh", "WD", ("14", "33")),
        "yl": Pair("yl", "WD", ("14", "15")),
        "md": Pair("md", "MD", ("1", "62")),  # same short name, other event
    }
    assert pair_name("sh", pairs, players, {}, " / ", {}) == "Baek / Lee So Hee"
    assert pair_name("yl", pairs, players, {}, " / ", {}) == "Baek / Lee Yu Lim"
    assert pair_name("md", pairs, players, {}, " / ", {}) == "Baek / Lee"
    # Without the clash, the short name.
    assert pair_name("sh", {"sh": pairs["sh"]}, players, {}, " / ", {}) == "Baek / Lee"


def test_full_name():
    kim = DPlayer("85", "ASTRUP Kim", "ASTRUP", "Male", "Denmark")
    assert full_name(kim) == "Kim Astrup"  # the content override
    assert full_name(kim, {}) == "Astrup Kim"
    assert full_name(DPlayer("5", "KIM Gi Jung", "KIM", "Male", "Korea"), {}) == "Kim Gi Jung"
    assert display_last_name(kim) == "Astrup"
    full = load_content("doubles_full_names")
    assert {k: v for k, v in full.items() if not k.startswith("_")} == {
        "28": "Shevon Jemie Lai", "85": "Kim Astrup", "86": "Anders Skaarup Rasmussen",
        "87": "Vinson Chiu", "88": "Joshua Yuan",
    }


def test_summary_never_pairs_first4_share_with_first4_win_rate():
    top = lambda v, rest: [v] + [rest] * 9  # noqa: E731
    # first4.share and first4.win_rate tie at the top; the rally finding is
    # less extreme (2nd), but it is the one paired with the lead.
    st, pairs, players = group("MD", {
        "first4.share": top(0.60, 0.30),
        "first4.win_rate": top(0.70, 0.50),
        "rally.attack_share": [0.50, 0.60] + [0.30] * 8,
    })
    found = select_pair_findings("p0", st, pairs)
    assert [f.key for f in found] == [
        "first4.share.top", "first4.win_rate.top", "rally.attack_share.top"
    ]
    assert pair_summary("p0", found, pairs, players) == (
        "Alpha0 and Beta0 see more of their rallies end within 4 shots than any other "
        "pair and attack more than most pairs."
    )
    # Only the two first4 findings: no second phrase.
    st, pairs, players = group("MD", {
        "first4.share": top(0.60, 0.30), "first4.win_rate": top(0.70, 0.50),
    })
    found = select_pair_findings("p0", st, pairs)
    assert pair_summary("p0", found, pairs, players) == (
        "Alpha0 and Beta0 see more of their rallies end within 4 shots than any other pair."
    )
    # Any other combination is allowed, including two serve findings.
    st, pairs, players = group("MD", {
        "serve.short_share": top(0.99, 0.80), "serve.win_rate": top(0.60, 0.50),
        "rally.attack_share": top(0.60, 0.30),
    })
    found = select_pair_findings("p0", st, pairs)
    assert pair_summary("p0", found, pairs, players) == (
        "Alpha0 and Beta0 serve short more than any other pair and win more of the "
        "rallies they serve than any other pair."
    )


needs_data = pytest.mark.skipif(
    "DSHUTTLENET_DIR" not in os.environ, reason="DSHUTTLENET_DIR not set"
)


@needs_data
def test_real_pairs():
    matches, pairs, players = load_doubles(
        Path(os.environ["DSHUTTLENET_DIR"]), load_content("doubles_tournaments")
    )
    all_stats = {pid: pair_stats(matches, p, players) for pid, p in pairs.items()}
    for event in ("MD", "WD", "XD"):
        for pid in ranked_pairs(all_stats, pairs, event):
            found = select_pair_findings(pid, all_stats, pairs)
            assert len(found) <= 4
            assert len({f.key.rsplit(".", 1)[0] for f in found}) == len(found)
            if found:
                text = pair_summary(pid, found, pairs, players)
                assert text and "{" not in text and " far " not in text
    found = select_pair_findings("baek-lee-sh", all_stats, pairs)
    assert pair_summary("baek-lee-sh", found, pairs, players) == (
        "Baek and Lee So Hee serve short more than any other pair and win more of the "
        "rallies they serve than any other pair."
    )
    # Weakness = largest gap below typical (unrounded, >= 3 points).
    weak = {
        pid: next((f.key for f in select_pair_findings(pid, all_stats, pairs)
                   if f.kind == "weakness"), None)
        for pid in ("tang-tse", "gicquel-delrue", "liu-ou", "alfian-ardianto",
                    "pearly-tan-muralitharan", "iwanaga-nakanishi", "lee-wang")
    }
    assert weak == {
        "tang-tse": "receive.win_rate.weakness",  # serve is above typical
        "gicquel-delrue": "serve.win_rate.weakness",  # 12.1 points vs first4 10.3
        "liu-ou": "first4.win_rate.weakness",  # 9.6 points vs serve 9.2
        "alfian-ardianto": "first4.win_rate.weakness",
        "pearly-tan-muralitharan": "serve.win_rate.weakness",
        "iwanaga-nakanishi": "serve.win_rate.weakness",  # 9.6 vs receive 8.8
        "lee-wang": None,  # receive is 2.999 points under: not 3
    }
    assert pair_name("aimsaard-aimsaard", pairs, players) == "Benyapa and Nuntakarn Aimsaard"
    assert pair_name("pearly-tan-muralitharan", pairs, players) == "Tan and Muralitharan"
    assert pair_name("baek-lee-sh", pairs, players, sep=" / ") == "Baek / Lee So Hee"
    assert pair_name("baek-lee-yl", pairs, players, sep=" / ") == "Baek / Lee Yu Lim"
    assert players["44"].last_name == "Pearly Tan"  # the id the display override targets
