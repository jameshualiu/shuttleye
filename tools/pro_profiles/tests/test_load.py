import os
import shutil
from pathlib import Path

import pytest

from pro_profiles.load import MappingError, load_content, load_dataset

SS = Path("ShuttleSet/set")
SS22 = Path("CoachAI-Challenge-IJCAI2023/ShuttleSet22/set")


@pytest.fixture
def mini(mini_source, mini_players, mini_tournaments):
    matches = load_dataset(mini_source, mini_players, mini_tournaments)
    return {m.id: m for m in matches}


def test_duplicate_folder_keeps_shuttleset_copy(mini):
    assert sorted(mini) == ["M1", "M2", "M3"]
    assert mini["M1"].source == "ShuttleSet"
    assert mini["M1"].youtube_url == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    assert mini["M2"].source == "ShuttleSet22"


def test_missing_folders_are_skipped(mini):
    assert "GONE" not in mini and "GONE_Trim" not in mini


def test_match_fields(mini):
    m = mini["M1"]
    assert (m.edition_id, m.round, m.date) == ("test-open-2022", "Finals", "2022-03-05")
    assert (m.winner, m.loser) == ("alpha-one", "beta-two")
    assert mini["M2"].date == "2022-03-03"  # year given as "2022.0"
    assert mini["M2"].youtube_url is None
    assert mini["M3"].youtube_url is None  # blank url


def test_passive_drop_typo_maps_to_drop(mini):
    shots = [s for r in mini["M1"].rallies for s in r.shots]
    typo = [s for s in shots if s.group == "Drop"]
    assert len(typo) == 2  # 過度切球 and 過渡切球


def test_serves_and_unknown_have_no_group(mini):
    rally = mini["M1"].rallies[0]
    serve, _, unknown = rally.shots
    assert serve.group is None and serve.is_serve
    assert unknown.group is None and not unknown.is_serve


def test_groups(mini):
    rally = mini["M1"].rallies[1]
    assert [s.group for s in rally.shots] == [None, "Smash", "Net", "Net kill"]


def test_shot_players_and_order(mini):
    rally = mini["M1"].rallies[0]
    assert [s.player for s in rally.shots] == ["alpha-one", "beta-two", "alpha-one"]
    assert [s.order for s in rally.shots] == [1, 2, 3]
    assert all(s.rally == 1 for s in rally.shots)


def test_rally_winner_from_last_row(mini):
    assert mini["M1"].rallies[0].winner == "alpha-one"
    assert mini["M1"].rallies[3].winner == "beta-two"  # set 2, getpoint B


def test_rally_without_winner_is_kept_with_none(mini):
    rallies = mini["M1"].rallies
    assert [(r.set_no, r.number, r.winner) for r in rallies] == [
        (1, 1, "alpha-one"),
        (1, 2, "alpha-one"),
        (1, 3, None),
        (2, 1, "beta-two"),
    ]


def test_rally_scores_are_before_the_rally(mini):
    # roundscore is the score AFTER a rally; Rally carries the score before it.
    r = mini["M1"].rallies[1]
    assert (r.match_id, r.set_no, r.number) == ("M1", 1, 2)
    assert [(r.set_no, r.score_a, r.score_b) for r in mini["M1"].rallies] == [
        (1, 0, 0),  # first rally of a set starts at 0-0
        (1, 1, 0),  # rally 1 ended 1-0
        (1, 2, 0),
        (2, 0, 0),  # resets in set 2
    ]
    assert (mini["M2"].rallies[0].score_a, mini["M2"].rallies[0].score_b) == (0, 0)


def test_set_scores_are_max_roundscore(mini):
    # Set 1 rally 3 has no winner but still advanced the score to 2-1.
    assert mini["M1"].set_scores == ((2, 1), (0, 1))
    assert mini["M2"].set_scores == ((3, 4),)


def test_set_scores_use_max_not_last_row(mini_source, mini_players, mini_tournaments, tmp_path):
    root = tmp_path / "src"
    shutil.copytree(mini_source, root)
    csv_path = root / SS / "M1" / "set1.csv"
    # A stray trailing row repeating an earlier rally (as in the WTF 2020 final).
    csv_path.write_text(csv_path.read_text() + "1,4.0,00:13:00,1,0,A,未知球種,\n")
    m = {m.id: m for m in load_dataset(root, mini_players, mini_tournaments)}["M1"]
    assert m.set_scores[0] == (2, 1)


def test_time_parsing(mini):
    assert mini["M1"].rallies[0].shots[0].time_sec == 654.0


def test_unmapped_player_raises(mini_source, mini_players, mini_tournaments):
    del mini_players["beta-two"]
    with pytest.raises(MappingError, match="Beta TWO"):
        load_dataset(mini_source, mini_players, mini_tournaments)


def test_unmapped_tournament_raises(mini_source, mini_players, mini_tournaments):
    mini_tournaments["test-open-2022"]["aliases"] = [["Other Open 2022", "2022"]]
    with pytest.raises(MappingError, match="Test Open 2022"):
        load_dataset(mini_source, mini_players, mini_tournaments)


def test_unknown_shot_type_raises(mini_source, mini_players, mini_tournaments, tmp_path):
    root = tmp_path / "src"
    shutil.copytree(mini_source, root)
    csv_path = root / SS / "M3" / "set1.csv"
    csv_path.write_text(csv_path.read_text().replace("長球", "新球種"))
    with pytest.raises(MappingError, match="新球種"):
        load_dataset(root, mini_players, mini_tournaments)


def test_bad_getpoint_player_raises(mini_source, mini_players, mini_tournaments, tmp_path):
    root = tmp_path / "src"
    shutil.copytree(mini_source, root)
    csv_path = root / SS / "M3" / "set1.csv"
    csv_path.write_text(csv_path.read_text().replace("長球,B", "長球,C"))
    with pytest.raises(MappingError, match=r"'C'.*M3.*rally 1"):
        load_dataset(root, mini_players, mini_tournaments)


def test_duplicate_player_alias_raises(mini_source, mini_players, mini_tournaments):
    mini_players["beta-two"]["aliases"].append("Alpha ONE")
    with pytest.raises(MappingError, match="Alpha ONE"):
        load_dataset(mini_source, mini_players, mini_tournaments)


def test_duplicate_tournament_alias_raises(mini_source, mini_players, mini_tournaments):
    mini_tournaments["other-2022"] = {
        "name": "Other", "season": 2022, "aliases": [["Test Open 2022", "2022.0"]]
    }
    with pytest.raises(MappingError, match="Test Open 2022"):
        load_dataset(mini_source, mini_players, mini_tournaments)


def test_content_files_load():
    players = load_content("players")
    tournaments = load_content("tournaments")
    assert len(players) == 43
    assert len(tournaments) == 31
    assert {p["event"] for p in players.values()} == {"MS", "WS"}


@pytest.mark.skipif("SHUTTLESET_DIR" not in os.environ, reason="SHUTTLESET_DIR not set")
def test_real_dataset_counts():
    matches = load_dataset(
        Path(os.environ["SHUTTLESET_DIR"]), load_content("players"), load_content("tournaments")
    )
    assert len(matches) == 94
    assert len({m.edition_id for m in matches}) == 31
    assert len({p for m in matches for p in (m.winner, m.loser)}) == 43
    assert sum(m.youtube_url is not None for m in matches) == 43
