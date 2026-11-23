import copy
import hashlib
import os
import shutil
from collections import Counter
from pathlib import Path

import pytest

from pro_profiles.doubles_load import (
    ATTACK_TYPES,
    EVENTS,
    ChecksumError,
    load_doubles,
    verify_checksums,
)
from pro_profiles.load import MappingError, load_content

FIXTURE = Path(__file__).parent / "fixtures" / "doubles_mini"
CSV_FILES = (
    "match.csv", "player.csv", "rally.csv", "set.csv",
    "shot.csv", "shot_merge_all.csv", "tournament.csv",
)
MINI_TOURNAMENTS = {
    "ids": {"10": "indonesia-open-2023", "12": "indonesia-open-2023"},
    "editions": {"indonesia-open-2023": {"name": "Indonesia Open", "season": 2023}},
}


@pytest.fixture
def mini():
    matches, pairs, players = load_doubles(FIXTURE, copy.deepcopy(MINI_TOURNAMENTS), {})
    return {m.id: m for m in matches}, pairs, players


def rally(matches, match_id, set_no, number):
    return next(
        r for r in matches[match_id].rallies if (r.set_no, r.number) == (set_no, number)
    )


def test_constants():
    assert EVENTS == {"1": "MD", "2": "WD", "3": "XD"}
    assert ATTACK_TYPES == frozenset({"smash", "drop", "push"})


def test_pairs_and_slugs(mini):
    matches, pairs, _ = mini
    # "Kim"/"LEE" clash across MD and WD, so both get the event suffix; the
    # others don't. Slugs are lowercase ASCII, in player-id order.
    assert sorted(pairs) == ["kim-lee-md", "kim-lee-wd", "park-choi", "pearly-tan-boje"]
    assert pairs["kim-lee-wd"].players == ("5", "6")  # win_A=6, win_B=5: sorted
    assert pairs["kim-lee-wd"].event == "WD"
    assert pairs["park-choi"].event == "MD"
    m1 = matches["1"]
    assert (m1.winner, m1.loser, m1.event) == ("kim-lee-md", "park-choi", "MD")


def test_players(mini):
    _, _, players = mini
    assert players["8"].last_name == "BØJE"
    assert (players["1"].name, players["1"].gender, players["1"].nationality) == (
        "KIM Alpha", "Male", "Korea",
    )


def test_match_fields(mini):
    matches, _, _ = mini
    m = matches["2"]
    assert (m.round, m.date, m.event) == ("Semi-finals", "2023-06-14", "WD")


def test_rallies_ordered_by_set_and_number(mini):
    matches, _, _ = mini
    assert [(r.set_no, r.number) for r in matches["1"].rallies] == [
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (2, 1), (2, 2),
    ]


def test_winner_from_score_change_when_score_team_blank(mini):
    matches, _, _ = mini
    assert rally(matches, "1", 1, 1).winner == "kim-lee-md"
    assert rally(matches, "1", 1, 2).winner == "park-choi"  # score_team blank
    assert rally(matches, "1", 1, 4).winner is None  # no score went up
    assert rally(matches, "1", 2, 1).winner == "park-choi"  # new set restarts at 0-0


def test_before_score_match_winner_first(mini):
    matches, _, _ = mini
    assert [r.before for r in matches["1"].rallies] == [
        (0, 0), (1, 0), (1, 1), (2, 1), (2, 1), (0, 0), (0, 1),
    ]


def test_receiver_is_shot_two_hitter(mini):
    matches, _, _ = mini
    r = rally(matches, "1", 1, 1)
    assert (r.server, r.receiver) == ("1", "3")
    assert rally(matches, "1", 1, 4).receiver is None  # single-shot rally


def test_shots(mini):
    matches, _, _ = mini
    shots = rally(matches, "1", 1, 1).shots
    assert [s.num for s in shots] == [1, 2, 3]  # file order was 2, 1, 3
    assert [s.player for s in shots] == ["1", "3", ""]  # shot 3's player is blank
    assert [s.type for s in shots] == ["short serve", "push", "smash"]
    assert [s.formation for s in shots] == ["Attack", "Defense", "Attack"]
    assert shots[1].met_at == (40.5, 100.25)
    r2 = rally(matches, "1", 1, 2).shots
    assert r2[1].met_at is None  # blank return_x/return_y
    assert r2[1].formation is None  # shot missing from shot_merge_all
    assert rally(matches, "1", 1, 3).shots[1].formation is None  # blank formation


def test_blank_serve_type_is_none_but_rally_kept(mini):
    matches, _, _ = mini
    assert rally(matches, "1", 1, 1).serve_type == "short"
    assert rally(matches, "1", 1, 2).serve_type == "long"
    r = rally(matches, "1", 1, 3)
    assert r.serve_type is None
    assert r.shots[0].type is None
    assert r.winner == "kim-lee-md"


def test_set_scores_use_max_scores_winner_first(mini):
    matches, _, _ = mini
    assert matches["1"].set_scores == ((3, 1), (1, 1))
    # The match winner lost set 1; set.csv says 21-19 for set 3, but the
    # rally scores win.
    assert matches["2"].set_scores == ((0, 2), (1, 0), (2, 0))


def test_lose_reason_trimmed(mini):
    matches, _, _ = mini
    assert rally(matches, "1", 1, 1).lose_reason == "Net Fault"
    assert rally(matches, "1", 1, 4).lose_reason is None  # blank


def test_fault_player_only_if_on_losing_pair(mini):
    matches, _, _ = mini
    assert rally(matches, "1", 1, 1).fault_player == "3"  # losing pair
    assert rally(matches, "1", 1, 2).fault_player == "2"  # losing pair (B won)
    assert rally(matches, "1", 1, 3).fault_player is None  # on the winning pair
    assert rally(matches, "1", 1, 4).fault_player is None  # no winner, blank
    assert rally(matches, "1", 2, 2).fault_player is None  # blank


def test_indonesia_open_ids_merge(mini):
    matches, _, _ = mini
    assert matches["1"].edition_id == matches["2"].edition_id == "indonesia-open-2023"


def test_unknown_tournament_raises():
    tournaments = copy.deepcopy(MINI_TOURNAMENTS)
    del tournaments["ids"]["12"]
    with pytest.raises(MappingError, match="12"):
        load_doubles(FIXTURE, tournaments, {})


def _edit(src: Path, name: str, old: str, new: str) -> None:
    text = (src / name).read_text(encoding="utf-8")
    assert old in text, (name, old)
    (src / name).write_text(text.replace(old, new), encoding="utf-8")


@pytest.fixture
def same_event_clash(tmp_path) -> Path:
    """Match 2 becomes MD with winners 1 + 6, so (1, 2) and (1, 6) are both
    "kim-lee" in MD and differ only in the partner: 2 "Beta Lee" vs 6 "LEE Zeta"."""
    src = tmp_path / "src"
    shutil.copytree(FIXTURE, src)
    _edit(src, "match.csv", ".mp4,2,12,Semi-finals,2023-06-14,3,45,6,5",
          ".mp4,1,12,Semi-finals,2023-06-14,3,45,1,6")
    return src


def test_same_event_slug_clash_uses_partner_initials(same_event_clash):
    matches, pairs, _ = load_doubles(same_event_clash, copy.deepcopy(MINI_TOURNAMENTS), {})
    assert sorted(pairs) == ["kim-lee-b", "kim-lee-z", "park-choi", "pearly-tan-boje"]
    assert pairs["kim-lee-b"].players == ("1", "2")
    assert pairs["kim-lee-z"].players == ("1", "6")
    assert {m.id: m.winner for m in matches} == {"1": "kim-lee-b", "2": "kim-lee-z"}


def test_same_event_initials_clash_raises(same_event_clash):
    _edit(same_event_clash, "player.csv", "6,LEE Zeta,LEE", "6,LEE Bo,LEE")
    with pytest.raises(MappingError, match="kim-lee"):
        load_doubles(same_event_clash, copy.deepcopy(MINI_TOURNAMENTS), {})


def test_player_aliases_merge_duplicate_ids(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(FIXTURE, src)
    with open(src / "player.csv", "a", encoding="utf-8") as f:
        f.write("9,Alpha KIM,KIM,Male,Right,1995-01-01,180,Korea\n")
    _edit(src, "match.csv", "2,30,1,2,3,4", "2,30,9,2,3,4")
    _edit(src, "rally.csv", "1,1,1,0,0,1,0,1,0.0", "1,1,1,0,0,1,0,9,0.0")
    _edit(src, "shot.csv", "1,1,1,00:00:00,0,0,1.0", "1,1,1,00:00:00,0,0,9.0")
    matches, pairs, players = load_doubles(src, copy.deepcopy(MINI_TOURNAMENTS), {"9": "1"})
    assert "9" not in players
    assert pairs["kim-lee-md"].players == ("1", "2")
    r = rally({m.id: m for m in matches}, "1", 1, 1)
    assert r.server == r.shots[0].player == "1"


def test_match_override_replaces_tournament_id():
    tournaments = copy.deepcopy(MINI_TOURNAMENTS)
    tournaments["ids"] = {"10": "indonesia-open-2023", "99": "other-open-2023"}
    tournaments["match_overrides"] = {"2": "99"}
    matches, _, _ = load_doubles(FIXTURE, tournaments, {})
    assert {m.id: m.edition_id for m in matches} == {
        "1": "indonesia-open-2023", "2": "other-open-2023",
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_checksums_pass(tmp_path):
    verify_checksums(FIXTURE, {f: _sha(FIXTURE / f) for f in CSV_FILES})


def test_checksum_mismatch_names_file(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(FIXTURE, src)
    expected = {f: _sha(src / f) for f in CSV_FILES}
    with open(src / "rally.csv", "a", encoding="utf-8") as f:
        f.write("99,1,99,0,0,0,0,1,,x,,,0,0,0,0,\n")
    with pytest.raises(ChecksumError, match="rally.csv"):
        verify_checksums(src, expected)


def test_checksum_missing_file_names_file(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(FIXTURE, src)
    expected = {f: _sha(src / f) for f in CSV_FILES}
    (src / "set.csv").unlink()
    with pytest.raises(ChecksumError, match="set.csv"):
        verify_checksums(src, expected)


def test_content_files():
    checksums = load_content("doubles_checksums")
    assert sorted(checksums) == sorted(CSV_FILES)
    assert all(len(v) == 64 for v in checksums.values())
    doubles = load_content("doubles_tournaments")
    singles = load_content("tournaments")
    assert doubles["ids"]["10"] == doubles["ids"]["12"] == "indonesia-open-2023"
    assert doubles["ids"]["2"] == "korea-masters-2022"
    assert doubles["ids"]["3"] == "indonesia-masters-2022"
    assert set(doubles["match_overrides"].values()) <= set(doubles["ids"])
    assert load_content("doubles_player_aliases") == {"81": "3", "82": "4"}
    for edition in doubles["ids"].values():
        assert edition in singles or edition in doubles["editions"], edition
    for eid, e in doubles["editions"].items():
        assert eid not in singles, eid  # shared editions come from singles
        assert isinstance(e["name"], str) and isinstance(e["season"], int)
        assert eid.endswith(f"-{e['season']}")


@pytest.mark.skipif("DSHUTTLENET_DIR" not in os.environ, reason="DSHUTTLENET_DIR not set")
def test_real_checksums():
    verify_checksums(Path(os.environ["DSHUTTLENET_DIR"]), load_content("doubles_checksums"))


@pytest.mark.skipif("DSHUTTLENET_DIR" not in os.environ, reason="DSHUTTLENET_DIR not set")
def test_real_counts():
    matches, pairs, _ = load_doubles(
        Path(os.environ["DSHUTTLENET_DIR"]), load_content("doubles_tournaments")
    )
    assert len(matches) == 58
    assert len(pairs) == 46
    assert Counter(p.event for p in pairs.values()) == {"MD": 19, "WD": 16, "XD": 11}
    assert sum(len(m.rallies) for m in matches) == 4846
    assert "hoki-kobayashi" in pairs and "baek-lee-yl" in pairs and "baek-lee-sh" in pairs
    assert pairs["baek-lee-sh"].players == ("14", "33")


@pytest.mark.skipif("DSHUTTLENET_DIR" not in os.environ, reason="DSHUTTLENET_DIR not set")
def test_real_edition_season_matches_date_year():
    editions = {**load_content("tournaments"), **load_content("doubles_tournaments")["editions"]}
    matches, _, _ = load_doubles(
        Path(os.environ["DSHUTTLENET_DIR"]), load_content("doubles_tournaments")
    )
    wrong = [
        (m.id, m.edition_id, m.date) for m in matches
        if editions[m.edition_id]["season"] != int(m.date[:4])
    ]
    assert wrong == []
