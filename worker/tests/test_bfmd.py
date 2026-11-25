"""BFMD annotation loader (train/bfmd.py) on a tiny synthetic match.

The fixture mirrors BFMD's metadata/<match>.json and hit_inferred/<match>.json
layout (README of github.com/Ning-D/BFMD); no BFMD data is used.
"""
import json

import pytest

from train.bfmd import BFMD_TO_PRODUCT, BFMD_TO_TEN, load_match
from train.eval_scoring import PRODUCT_TYPES, ZH_TO_TEN, score_set_sides

MATCH = "Some-Open-2025-Player-One-vs.-Player-Two-SF"


def _write(tmp_path, metadata, hits):
    ann = tmp_path / "annotations"
    (ann / "metadata").mkdir(parents=True)
    (ann / "hit_inferred").mkdir()
    (ann / "metadata" / f"{MATCH}.json").write_text(json.dumps(metadata))
    (ann / "hit_inferred" / f"{MATCH}.json").write_text(
        json.dumps({"match_name": MATCH, "n_hits": len(hits), "hits": hits}))
    return ann / "metadata" / f"{MATCH}.json"


def _hit(frame, shot, side, player, game, rally):
    return {"frame": frame, "shot_type": shot, "side": side, "player": player,
            "game": game, "rally": rally}


@pytest.fixture
def match(tmp_path):
    metadata = {
        "match_name": MATCH, "player1_name": "Player One", "player2_name": "Player Two",
        "game1_top_player": "player2",
        "games": {
            "game1": {"rallies": [{"start": 100, "end": 300}, {"start": 500, "end": 700},
                                  {"start": 900, "end": 950}],
                      "score_events": [
                          {"rally_start": 100, "rally_end": 300, "winner": None,
                           "score_after_rally": {"player1": 1, "player2": 0}},
                          {"rally_start": 500, "rally_end": 700, "winner": None,
                           "score_after_rally": {"player1": 1, "player2": 1}},
                          {"rally_start": 900, "rally_end": 950, "winner": None,
                           "score_after_rally": {"player1": 2, "player2": 1}}],
                      "final_score": {"player1": 2, "player2": 1}},
            "game2": {"rallies": [{"start": 2000, "end": 2200}],
                      "score_events": [{"rally_start": 2000, "rally_end": 2200, "winner": None,
                                        "score_after_rally": {"player1": 0, "player2": 1}}],
                      "final_score": {"player1": 0, "player2": 1}},
        },
    }
    hits = [
        # game 1: player2 (Top) serves rally 0; rally 1 opens on a stroke type
        _hit(110, "serve", "top", "Player Two", 1, 0),
        _hit(130, "lift", "bottom", "Player One", 1, 0),
        _hit(170, "press", "top", "Player Two", 1, 0),
        _hit(510, "net_shot", "bottom", "Player One", 1, 1),
        _hit(540, "flick_serve", "top", "Player Two", 1, 1),     # mislabelled, not first
        _hit(560, "bounce", "bottom", "Player One", 1, 1),       # not a stroke: dropped
        # rally 2 of game 1 has no hits at all
        # game 2: ends changed
        _hit(2010, "serve", "bottom", "Player Two", 2, 0),
        _hit(2040, "smash", "top", "Player One", 2, 0),
    ]
    return _write(tmp_path, metadata, hits)


def test_load_match_shape(match):
    m = load_match(match)
    assert m["video_id"] == MATCH and m["fps"] == 30.0
    assert m["players"] == ("Player One", "Player Two")
    assert m["rallies"] == [(100, 300), (500, 700), (900, 950), (2000, 2200)]
    assert [s["frame"] for s in m["shots"]] == [110, 130, 170, 510, 540, 2010, 2040]
    # same keys as eval_scoring.parse_rallies' shots (plus provenance)
    for s in m["shots"]:
        assert {"frame", "serve", "type", "ten", "side"} <= set(s)


def test_load_match_maps_types_sides_and_serves(match):
    shots = {s["frame"]: s for s in load_match(match)["shots"]}
    assert shots[110] == {**shots[110], "serve": True, "type": None, "ten": "short service", "side": "Top"}
    assert shots[130] == {**shots[130], "serve": False, "type": "Lob", "ten": "lob", "side": "Bottom"}
    # press is ambiguous between push/rush and a drop: excluded from both taxonomies
    assert shots[170]["type"] is None and shots[170]["ten"] is None and shots[170]["label"] == "press"
    # the rally's first stroke is its serve whatever it is typed (ball_round-1 rule)
    assert shots[510]["serve"] is True and shots[510]["ten"] == "net shot"
    assert shots[540]["serve"] is True and shots[540]["ten"] == "long service"
    assert shots[2040] == {**shots[2040], "type": "Smash", "ten": "smash", "side": "Top"}


def test_load_match_sets_scores_and_exclusions(match):
    m = load_match(match)
    assert sorted(m["sets"]) == [1, 2]
    assert sorted(m["sets"][1]) == [0, 1]                  # the hitless rally has no shots
    assert [s["frame"] for s in m["sets"][2][0]] == [2010, 2040]
    s1 = m["scores"][1]
    assert [r["scoreAfter"] for r in s1] == [(1, 0), (1, 1), (2, 1)]
    assert [r["winner"] for r in s1] == ["A", "B", "A"]    # A = player1
    assert (s1[0]["first"], s1[0]["last"]) == (110, 170)
    assert (s1[2]["first"], s1[2]["last"]) == (900, 950)   # no hits: the rally interval
    assert (s1[0]["start"], s1[0]["end"]) == (100, 300)
    assert [r["aSide"] for r in s1] == ["near", "near", None]   # player1 hits from the bottom
    assert m["scores"][2][0]["aSide"] == "far"
    assert m["excluded"] == {"press": 1, "bounce": 1}


def test_mapping_targets_are_our_taxonomies():
    assert set(BFMD_TO_TEN.values()) <= set(ZH_TO_TEN.values())
    assert set(BFMD_TO_PRODUCT.values()) <= set(PRODUCT_TYPES)


def test_score_set_sides():
    pred = [{"set": 1, "fromScore": (0, 0), "near": "B"}, {"set": 2, "fromScore": (0, 0), "near": "B"}]
    gt = {1: [{"aSide": None}, {"aSide": "far"}], 2: [{"aSide": "near"}], 3: [{"aSide": "far"}]}
    s = score_set_sides(pred, gt)
    assert s["per_set"] == {1: {"pred": "B", "gt": "B"}, 2: {"pred": "B", "gt": "A"},
                            3: {"pred": None, "gt": "B"}}
    assert (s["correct"], s["total"]) == (1, 3)
