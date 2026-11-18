import filecmp
import json
import os
from pathlib import Path

import pytest

from pro_profiles.build import PINNED_SHA, build
from pro_profiles.load import load_content, load_dataset

SOURCES = {"M1": {"url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "offsetSec": 0}}


def run_build(out, mini_source, mini_players, mini_tournaments, photos=None):
    build(
        mini_source, out,
        players=mini_players, tournaments=mini_tournaments,
        sources=SOURCES, photos=photos or {},
    )


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture
def mini_out(tmp_path, mini_source, mini_players, mini_tournaments):
    run_build(tmp_path, mini_source, mini_players, mini_tournaments)
    return tmp_path


def test_match_view_has_no_ranks_or_findings(mini_out):
    seen = 0
    for p in (mini_out / "players").glob("*.json"):
        if p.name == "index.json":
            continue
        for fid, view in read(p)["views"].items():
            if fid == "all":
                continue
            seen += 1
            assert view["findings"] == []
            assert all(r["rank"] is None and r["of"] is None for r in view["shotChoice"])
    assert seen >= 4


def test_filtered_views_have_rally_browser_and_all_does_not(mini_out):
    data = read(mini_out / "players" / "alpha-one.json")
    assert data["views"]["all"]["rallyBrowser"] == []
    clips = data["views"]["m:M1"]["rallyBrowser"]
    assert [c["startSec"] for c in clips] == [652, 688, 1798]  # (set, rally) order
    assert clips[0]["youtubeId"] == "AAAAAAAAAAA"
    assert data["views"]["m:M2"]["rallyBrowser"] == []  # no clip source


def test_unranked_player_all_view(mini_out):
    data = read(mini_out / "players" / "alpha-one.json")
    assert data["summary"] is None
    assert data["views"]["all"]["findings"] == []
    assert all(r["rank"] is None for r in data["views"]["all"]["shotChoice"])
    assert data["context"]["comparedWith"] == 0
    assert data["photo"] is None


def test_tournament_games_from_rally_winners(mini_out):
    t = read(mini_out / "tournaments" / "test-open-2022.json")
    m1 = next(m for m in t["matches"] if m["id"] == "M1")
    # Set 1: A won rallies 1 and 2 (rally 3 has no winner); set 2: B won.
    assert m1["games"] == [[2, 0], [0, 1]]
    assert m1["winner"] == {"id": "alpha-one", "name": "Alpha One"}
    assert m1["loser"] == {"id": "beta-two", "name": "Beta Two"}
    assert [m["id"] for m in t["matches"]] == sorted(
        (m["id"] for m in t["matches"]), key=lambda i: ({"M2": "2022-03-03", "M3": "2022-03-04", "M1": "2022-03-05"}[i], i)
    )
    assert {p["id"] for p in t["players"]} == {"alpha-one", "beta-two"}


def test_output_is_deterministic(tmp_path, mini_source, mini_players, mini_tournaments):
    a, b = tmp_path / "a", tmp_path / "b"
    run_build(a, mini_source, mini_players, mini_tournaments)
    run_build(b, mini_source, mini_players, mini_tournaments)
    files_a = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    assert files_a == files_b and files_a
    for f in files_a:
        assert (a / f).read_bytes() == (b / f).read_bytes()


def test_index_sorted(mini_out, tmp_path, mini_source, mini_players, mini_tournaments):
    idx = read(mini_out / "players" / "index.json")
    assert idx["generatedFrom"] == PINNED_SHA
    assert [p["id"] for p in idx["players"]] == ["alpha-one", "beta-two"]
    assert idx["players"][0]["matches"] == 3 and idx["players"][0]["ranked"] is False

    mini_tournaments["early-2020"] = {"name": "Early", "season": 2020, "aliases": []}
    mini_tournaments["alpha-2022"] = {"name": "Alpha Cup", "season": 2022, "aliases": []}
    mini_players["zed"] = {"name": "Zed", "event": "WS", "aliases": []}
    mini_players["amy"] = {"name": "Amy", "event": "WS", "aliases": []}
    out = tmp_path / "x"
    run_build(out, mini_source, mini_players, mini_tournaments)
    idx = read(out / "players" / "index.json")
    assert [(p["event"], p["name"]) for p in idx["players"]] == [("MS", "Alpha One"), ("MS", "Beta Two")]
    # Players with no matches are left out.
    ed = read(out / "tournaments" / "index.json")["editions"]
    assert [e["id"] for e in ed] == ["test-open-2022"]


def test_photo_from_photos_json(tmp_path, mini_source, mini_players, mini_tournaments):
    photos = {"alpha-one": {"sourceUrl": "https://x/y", "author": "Ann", "licence": "CC BY 2.0",
                            "focusX": 40, "focusY": 25}}
    run_build(tmp_path, mini_source, mini_players, mini_tournaments, photos)
    photo = read(tmp_path / "players" / "alpha-one.json")["photo"]
    assert photo == {"src": "/pro-data/photos/alpha-one.jpg", "credit": "Photo: Ann, CC BY 2.0",
                     "sourceUrl": "https://x/y", "focusX": 40, "focusY": 25}
    idx = read(tmp_path / "players" / "index.json")["players"]
    assert idx[0]["photo"] == photo and idx[1]["photo"] is None


def test_rally_browser_skips_rallies_without_winner(mini_out):
    # M1 set 1 rally 3 has no winner: 3 real rallies with clips, not 4.
    view = read(mini_out / "players" / "alpha-one.json")["views"]["m:M1"]
    assert view["rallies"] == 3
    assert [c["startSec"] for c in view["rallyBrowser"]] == [652, 688, 1798]


def test_all_filter_label_singular(mini_out):
    from pro_profiles.build import _all_label

    assert _all_label(1) == "All 1 match"
    assert _all_label(2) == "All 2 matches"
    labels = [f["label"] for f in read(mini_out / "players" / "alpha-one.json")["filters"]]
    assert labels[0] == "All 3 matches"


needs_data = pytest.mark.skipif(
    not os.environ.get("SHUTTLESET_DIR"), reason="needs SHUTTLESET_DIR"
)


@needs_data
def test_axelsen_file_shape(tmp_path):
    build(Path(os.environ["SHUTTLESET_DIR"]), tmp_path)
    data = read(tmp_path / "players" / "viktor-axelsen.json")
    assert len(data["views"]["all"]["findings"]) == 4
    assert data["context"] == {"matches": 20, "firstYear": 2020, "lastYear": 2022, "comparedWith": 38}
    assert data["summary"]
    lift = next(r for r in data["views"]["all"]["shotChoice"] if r["group"] == "Lift")
    assert (lift["share"], lift["rank"], lift["of"]) == (27.7, 1, 39)
    assert len(list((tmp_path / "players").glob("*.json"))) == 44
    assert len(list((tmp_path / "tournaments").glob("*.json"))) == 32


@needs_data
def test_rally_browser_matches_independent_count(tmp_path):
    """Browser length == the subset's real rallies (winner set) in matches with a clip source."""
    players, tournaments = load_content("players"), load_content("tournaments")
    sources = load_content("clip_sources")
    matches = load_dataset(Path(os.environ["SHUTTLESET_DIR"]), players, tournaments)
    by_id = {m.id: m for m in matches}

    def expected(pid, fid):
        if fid.startswith("m:"):
            subset = [by_id[fid[2:]]]
        else:
            subset = [m for m in matches
                      if m.edition_id == fid[2:] and pid in (m.winner, m.loser)]
        return sum(
            1 for m in subset if m.id in sources for r in m.rallies
            if r.winner is not None and r.shots
        )

    build(Path(os.environ["SHUTTLESET_DIR"]), tmp_path)
    checked = 0
    for p in (tmp_path / "players").glob("*.json"):
        if p.name == "index.json":
            continue
        data = read(p)
        for fid, view in data["views"].items():
            if fid == "all":
                continue
            checked += 1
            assert len(view["rallyBrowser"]) == expected(data["id"], fid), (p.name, fid)
            assert len(view["rallyBrowser"]) <= view["rallies"], (p.name, fid)
        label = data["filters"][0]["label"]
        n = data["context"]["matches"]
        assert label == ("All 1 match" if n == 1 else f"All {n} matches")
    assert checked > 300
