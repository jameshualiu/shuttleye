import copy
import dataclasses
import json
import os
from pathlib import Path

import pytest

from pro_profiles.doubles_build import LICENSE_TEXT, build, edition_names, write_doubles
from pro_profiles.doubles_load import ChecksumError, load_doubles
from pro_profiles.doubles_stats import MEASURES

FIXTURE = Path(__file__).parent / "fixtures" / "doubles_mini"
MINI_TOURNAMENTS = {
    "ids": {"10": "indonesia-open-2023", "12": "indonesia-open-2023"},
    "editions": {"indonesia-open-2023": {"name": "Indonesia Open", "season": 2023}},
}
EDITIONS = {"indonesia-open-2023": {"name": "Indonesia Open", "season": 2023}}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def loaded():
    return load_doubles(FIXTURE, copy.deepcopy(MINI_TOURNAMENTS), {})


@pytest.fixture
def mini_out(tmp_path, loaded):
    """The fixture as is: every pair has one match, so none is ranked."""
    out = tmp_path / "out"
    write_doubles(out, *loaded, EDITIONS)
    return out


@pytest.fixture
def ranked_out(tmp_path, loaded):
    """Each match twice with 12x the rallies, so every pair has 2 matches and
    enough samples for most measures."""
    matches, pairs, players = loaded
    big = [
        dataclasses.replace(m, id=f"{m.id}{k}", rallies=m.rallies * 12)
        for m in matches for k in range(2)
    ]
    out = tmp_path / "ranked"
    write_doubles(out, big, pairs, players, EDITIONS)
    return out


def test_unranked_pair_json(mini_out):
    d = read(mini_out / "pairs" / "kim-lee-md.json")
    assert d["id"] == "kim-lee-md" and d["event"] == "MD"
    assert d["ranked"] is False and d["summary"] is None
    assert d["context"] == {"matches": 1, "firstYear": 2023, "lastYear": 2023, "comparedWith": 0}
    assert [p["id"] for p in d["players"]] == ["1", "2"]
    assert d["players"][0] == {
        "id": "1", "name": "Kim Alpha", "nationality": "Korea", "gender": "Male",
    }
    view = d["views"]["all"]
    assert view["kind"] == "all" and view["ranks"] == {} and view["findings"] == []
    assert view["mixed"] is None
    assert set(view) == {"kind", "rallies", "serve", "receive", "first4", "mixed", "rest",
                         "ranks", "samples", "findings", "typical"}
    assert set(view["serve"]["placement"]) == {"centre", "middle", "wide", "backCentre", "backWide"}
    assert [r["playerId"] for r in view["rest"]["roles"]] == ["1", "2"]
    # Below 30 samples every value is null; only the counts show.
    assert view["serve"]["shortShare"] is None and view["serve"]["serves"] == 4
    # Each measure's own sample count, so the page can say "4 serves" beside it.
    assert set(MEASURES) <= set(view["samples"])
    assert view["samples"]["serve.short_share"] == view["serve"]["serves"]
    assert view["samples"]["receive.attack_share"] == view["receive"]["returns"]
    assert view["samples"]["first4.share"] == view["rallies"]
    assert view["samples"]["first4.win_rate"] <= view["samples"]["first4.share"]
    assert "mixed.serve_by" not in view["samples"]
    assert view["typical"] == {}
    assert [f["id"] for f in d["filters"]] == ["all", "t:indonesia-open-2023", "m:1"]
    assert d["filters"][0] == {"id": "all", "kind": "all", "label": "All 1 match", "matches": 1}
    assert d["filters"][1]["label"] == "Indonesia Open 2023"
    assert d["filters"][2]["label"] == "Indonesia Open 2023 final against Park / Choi"
    assert set(d["views"]) == {f["id"] for f in d["filters"]}


def test_mixed_block_only_for_xd(loaded, tmp_path):
    matches, pairs, players = loaded
    xd = dataclasses.replace(pairs["kim-lee-md"], id="kim-lee-md", event="XD")
    write_doubles(tmp_path, matches, {**pairs, "kim-lee-md": xd}, players, EDITIONS)
    mixed = read(tmp_path / "pairs" / "kim-lee-md.json")["views"]["all"]["mixed"]
    assert set(mixed) == {"serveBy", "receiveBy"} and set(mixed["serveBy"]) == {"man", "woman"}
    samples = read(tmp_path / "pairs" / "kim-lee-md.json")["views"]["all"]["samples"]
    assert {"mixed.serve_by", "mixed.receive_by"} <= set(samples)


def test_filtered_view_has_no_ranks_or_findings(ranked_out):
    d = read(ranked_out / "pairs" / "kim-lee-md.json")
    assert d["ranked"] is True and d["context"]["comparedWith"] == 1
    allv = d["views"]["all"]
    assert allv["ranks"] and set(allv["ranks"]) <= set(MEASURES)
    assert set(allv["ranks"]["serve.short_share"]) == {"rank", "of", "typical"}
    assert allv["ranks"]["serve.short_share"]["of"] == 2
    seen = 0
    for fid, view in d["views"].items():
        if fid == "all":
            continue
        seen += 1
        assert view["ranks"] == {} and view["findings"] == []
    assert seen == 3  # one tournament, two matches


def test_typical_from_all_matches(ranked_out):
    d = read(ranked_out / "pairs" / "kim-lee-md.json")
    allv = d["views"]["all"]
    assert allv["typical"] and set(allv["typical"]) <= set(MEASURES)
    # The median of the two MD pairs (0.75 and 1.0 short share).
    assert allv["typical"]["serve.short_share"] == 87.5
    for key, rank in allv["ranks"].items():
        assert rank["typical"] == allv["typical"][key]
    for fid, view in d["views"].items():
        assert view["typical"] == allv["typical"], fid
    # An unranked pair's page has typical values too.
    assert read(ranked_out / "pairs" / "kim-lee-md.json")["views"]["m:10"]["typical"]


def test_typical_for_unranked_pair_comes_from_the_group(loaded, tmp_path):
    matches, pairs, players = loaded
    big = [
        dataclasses.replace(m, id=f"{m.id}{k}", rallies=m.rallies * 12)
        for m in matches for k in range(2)
    ]
    # Give one of the two matches a different losing pair: park-choi keeps one
    # match, so it is unranked while kim-lee-md (2 matches) is ranked.
    big = [dataclasses.replace(m, loser="x-y") if m.id == "11" else m for m in big]
    pairs = {**pairs, "x-y": dataclasses.replace(pairs["park-choi"], id="x-y")}
    write_doubles(tmp_path, big, pairs, players, EDITIONS)
    d = read(tmp_path / "pairs" / "park-choi.json")
    assert d["ranked"] is False and d["views"]["all"]["ranks"] == {}
    # The group is the one ranked MD pair, so typical is that pair's own value.
    assert d["views"]["all"]["typical"]["serve.short_share"] == 75.0


def test_findings_use_singles_shape(ranked_out):
    for p in (ranked_out / "pairs").glob("*.json"):
        if p.name == "index.json":
            continue
        for f in read(p)["views"]["all"]["findings"]:
            assert set(f) == {"key", "kind", "claim", "figure", "comparison", "tip", "clips"}
            assert f["clips"] == []


def test_pair_index(ranked_out):
    idx = read(ranked_out / "pairs" / "index.json")["pairs"]
    assert [(r["event"], r["id"]) for r in idx] == [
        ("MD", "kim-lee-md"), ("MD", "park-choi"), ("WD", "kim-lee-wd"), ("WD", "pearly-tan-boje"),
    ]
    assert idx[0] == {
        "id": "kim-lee-md", "event": "MD", "matches": 2, "ranked": True,
        "players": [
            {"id": "1", "name": "Kim Alpha", "nationality": "Korea"},
            {"id": "2", "name": "Beta Lee", "nationality": "Korea"},
        ],
    }


def test_doubles_tournament_games_and_incomplete(mini_out):
    idx = read(mini_out / "tournaments" / "index.json")
    assert idx == {"editions": [
        {"id": "indonesia-open-2023", "name": "Indonesia Open", "season": 2023, "doublesMatches": 2},
    ]}
    t = read(mini_out / "tournaments" / "indonesia-open-2023.json")
    assert (t["id"], t["name"], t["season"]) == ("indonesia-open-2023", "Indonesia Open", 2023)
    m1, m2 = t["matches"]  # by date: match 2 (June 14) is first
    assert (m1["id"], m2["id"]) == ("2", "1")
    assert m2 == {
        "id": "1", "event": "MD", "round": "Finals", "date": "2023-06-18",
        "winner": {"id": "kim-lee-md", "names": "Kim / Lee"},
        "loser": {"id": "park-choi", "names": "Park / Choi"},
        "games": [[3, 1], [1, 1]], "incomplete": [0, 1],
    }
    assert m1["games"] == [[0, 2], [1, 0], [2, 0]] and m1["incomplete"] == [0, 1, 2]
    assert {p["id"] for p in t["pairs"]} == {"kim-lee-md", "park-choi", "kim-lee-wd", "pearly-tan-boje"}
    assert [p["event"] for p in t["pairs"]] == ["MD", "MD", "WD", "WD"]


def test_finished_game_not_marked_incomplete(loaded, tmp_path):
    matches, pairs, players = loaded
    m = dataclasses.replace(matches[1], set_scores=((21, 19), (21, 20), (30, 29)))
    write_doubles(tmp_path, [matches[0], m], pairs, players, EDITIONS)
    t = read(tmp_path / "tournaments" / "indonesia-open-2023.json")
    row = next(r for r in t["matches"] if r["id"] == "2")
    assert row["incomplete"] == [1]  # 21-20 isn't a finished game; 21-19 and 30-29 are


def test_shared_edition_takes_singles_name(loaded, tmp_path):
    matches, pairs, players = loaded
    # build() resolves names: a singles edition wins over the doubles-only entry.
    singles = {"indonesia-open-2023": {"name": "Singles Name", "season": 2022},
               "korea-masters-2022": {"name": "Korea Masters", "season": 2022}}
    doubles = {"ids": {"1": "indonesia-open-2023", "2": "korea-masters-2022"},
               "editions": {"indonesia-open-2023": {"name": "D", "season": 2023},
                            "x-2024": {"name": "X", "season": 2024}}}
    assert edition_names(doubles, singles) == {
        "indonesia-open-2023": {"name": "Singles Name", "season": 2022},
        "korea-masters-2022": {"name": "Korea Masters", "season": 2022},
        "x-2024": {"name": "X", "season": 2024},
    }


def test_output_deterministic(tmp_path, loaded):
    a, b = tmp_path / "a", tmp_path / "b"
    write_doubles(a, *loaded, EDITIONS)
    write_doubles(b, *loaded, EDITIONS)
    assert tree(a) == tree(b)


def test_license_file_written(mini_out):
    text = (mini_out / "LICENSE").read_text(encoding="utf-8")
    assert text == LICENSE_TEXT
    assert "CC BY-NC-SA 4.0" in text and "DShuttleNet" in text and "kaggle.com" in text
    assert "non-commercial" in text.lower()


def test_no_singles_paths_written(tmp_path):
    out = tmp_path / "pro-data" / "doubles"
    build(FIXTURE, out, tournaments=copy.deepcopy(MINI_TOURNAMENTS), checksums={}, aliases={},
          singles_tournaments={})
    top = {p.name for p in out.parent.iterdir()}
    assert top == {"doubles"}
    assert {p.name for p in out.iterdir()} == {"LICENSE", "pairs", "tournaments"}
    assert not any("players" in str(p.relative_to(out)).split(os.sep) for p in out.rglob("*"))


def test_build_verifies_checksums_first(tmp_path):
    # The recorded checksums are for the real dataset, not the fixture.
    with pytest.raises(ChecksumError):
        build(FIXTURE, tmp_path / "out", tournaments=copy.deepcopy(MINI_TOURNAMENTS), aliases={})
    assert not (tmp_path / "out").exists()


needs_data = pytest.mark.skipif("DSHUTTLENET_DIR" not in os.environ, reason="DSHUTTLENET_DIR not set")


@needs_data
def test_real_build(tmp_path):
    out = tmp_path / "doubles"
    build(Path(os.environ["DSHUTTLENET_DIR"]), out)
    idx = read(out / "pairs" / "index.json")["pairs"]
    assert len(idx) == len(list((out / "pairs").glob("*.json"))) - 1
    d = read(out / "pairs" / "baek-lee-sh.json")
    assert d["ranked"] is True and d["context"]["matches"] == 10
    assert d["context"]["comparedWith"] == 10  # 11 ranked women's pairs
    assert d["summary"].startswith("Baek and Lee So Hee ")
    # Two WD pairs would both be "Baek / Lee": the varying partner gets a full name.
    shown = {(p["id"], p["names"]) for f in (out / "tournaments").glob("*.json")
             if f.name != "index.json" for p in read(f)["pairs"]}
    baek = {n for pid, n in shown if pid.startswith("baek-lee")}
    assert baek == {"Baek / Lee So Hee", "Baek / Lee Yu Lim"}
    labels = [f["label"] for f in read(out / "pairs" / "baek-lee-yl.json")["filters"]]
    assert not any(label.endswith("against Baek / Lee") for label in labels)
    # Western players stored surname-first display given name first.
    ast = read(out / "pairs" / "astrup-rasmussen.json")
    assert [p["name"] for p in ast["players"]] == ["Kim Astrup", "Anders Skaarup Rasmussen"]
    v = d["views"]["all"]
    assert v["samples"]["first4.win_rate"] < v["samples"]["first4.share"] == v["rallies"]
    ids = {e["id"] for e in read(out / "tournaments" / "index.json")["editions"]}
    assert "indonesia-open-2023" in ids
    assert len(list((out / "tournaments").glob("*.json"))) == len(ids) + 1
