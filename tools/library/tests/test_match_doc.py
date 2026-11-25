import copy
import json

from fullmatch.bst_inputs import TEN_CLASSES
from library.match_doc import GROUP_OF_DETAIL, match_doc, zone_of, NEAR_FIRST_WARNING, WINNER_WARNING


def test_hitter_from_side_and_near(product_result, meta):
    doc = match_doc(product_result, meta)
    shots = doc["rallies"][0]["shots"]
    assert shots[0]["p"] == "B"   # Bottom, near player B
    assert shots[1]["p"] == "A"   # Top


def test_unattributed_rally_sets_flag(product_result, meta):
    doc = match_doc(product_result, meta)
    assert all(s["p"] is None for s in doc["rallies"][1]["shots"])
    assert doc["attributed"] is False


def test_unknown_and_null_side_kept(product_result, meta):
    doc = match_doc(product_result, meta)
    for r, src in zip(doc["rallies"], product_result["rallies"]):
        assert len(r["shots"]) == len(src["eventIndices"])
    assert doc["rallies"][1]["shots"][1]["g"] is None
    assert doc["rallies"][1]["shots"][2]["p"] is None


def test_score_before(product_result, meta):
    doc = match_doc(product_result, meta)
    assert [r["scoreBefore"] for r in doc["rallies"]] == [[0, 0], [1, 0], [1, 1]]


def test_score_before_unread(product_result, meta):
    res = copy.deepcopy(product_result)
    res["rallies"][1]["scoreRead"] = False
    res["rallies"][1]["scoreAfter"] = None
    doc = match_doc(res, meta)
    assert doc["rallies"][1]["scoreBefore"] == [1, 0]
    assert doc["rallies"][2]["scoreBefore"] is None


def test_doc_fields(product_result, meta):
    doc = match_doc(product_result, meta)
    assert doc["games"] == [{"a": 21, "b": 15}]
    assert doc["status"] == "unpublished"
    assert doc["players"]["A"] == {"id": "viktor-axelsen", "name": "Viktor AXELSEN"}
    assert doc["winner"] == "A" and doc["accuracy"] is None and doc["insights"] is None
    assert doc["summary"]["rallies"] == 3
    assert doc["summary"]["avgShots"] == round(8 / 3, 1)
    assert doc["summary"]["durationSec"] == 30.0
    assert doc["rallies"][0]["shots"][0] == {"t": 1.0, "p": "B", "g": None, "d": "short service", "z": None, "s": True}


def test_near_first_warning(product_result, meta):
    doc = match_doc(product_result, {**meta, "nearFirst": "A"})
    assert "near side at rally 1 disagrees with --near-first" in doc["analyzer"]["warnings"]
    assert not product_result["warnings"]
    ok = match_doc(product_result, meta)
    assert ok["analyzer"]["warnings"] == []


def test_zone_of():
    assert zone_of([1.0, 12.0], True) == "rear-left"
    assert zone_of([1.0, 1.0], False) == "rear-right"
    assert zone_of([5.0, 7.5], True) == "front-right"
    assert zone_of([3.5, 3.5], False) == "mid-left"
    assert zone_of(None, True) is None


def test_group_map():
    for name in TEN_CLASSES:
        assert name in GROUP_OF_DETAIL
    assert GROUP_OF_DETAIL["lob"] == "Lift" and GROUP_OF_DETAIL["short service"] is None


def test_doc_size_under_limit(product_result, meta):
    events, rallies = [], []
    for r in range(120):
        idx = []
        for k in range(20):
            idx.append(len(events))
            events.append({"timeSec": r * 30.0 + k, "type": "Smash", "detailType": "smash",
                           "side": "Top" if k % 2 else "Bottom", "isServe": k == 0,
                           "location_m": [3.123456, 4.123456]})
        rallies.append({"id": r + 1, "set": 1, "startSec": r * 30.0, "endSec": r * 30.0 + 20,
                        "eventIndices": idx, "scoreAfter": [r, 0], "winner": "A",
                        "nearPlayer": "A", "scoreRead": True})
    res = {**product_result, "events": events, "rallies": rallies}
    assert len(json.dumps(match_doc(res, meta))) < 900_000


def test_player_ids_carried_unchanged(product_result, meta):
    doc = match_doc(product_result, meta)
    assert doc["players"]["A"]["id"] == "viktor-axelsen"
    assert doc["players"]["A"]["name"] == "Viktor AXELSEN"
    assert doc["players"]["B"]["id"] == "some-opponent"


def test_player_event_recorded_when_given(product_result, meta):
    meta = {**meta, "playerA": {**meta["playerA"], "event": "MS"}}
    doc = match_doc(product_result, meta)
    assert doc["players"]["A"] == {"id": "viktor-axelsen", "name": "Viktor AXELSEN", "event": "MS"}
    assert "event" not in doc["players"]["B"]


def _attributed(product_result):
    import copy
    res = copy.deepcopy(product_result)
    for r in res["rallies"]:
        r["nearPlayer"] = r.get("nearPlayer") or "B"
    return res


def test_near_first_disagreement_unattributes(product_result, meta):
    res = _attributed(product_result)
    assert match_doc(res, meta)["attributed"] is True
    doc = match_doc(res, {**meta, "nearFirst": "A"})
    assert doc["attributed"] is False
    assert NEAR_FIRST_WARNING in doc["analyzer"]["warnings"]


def test_games_winner_disagreement_unattributes(product_result, meta):
    res = _attributed(product_result)
    res["sets"] = [{"set": 1, "finalScore": [15, 21]}, {"set": 2, "finalScore": [21, 19]},
                   {"set": 3, "finalScore": [10, 21]}]
    doc = match_doc(res, meta)
    assert doc["attributed"] is False
    assert WINNER_WARNING in doc["analyzer"]["warnings"]
    assert NEAR_FIRST_WARNING not in doc["analyzer"]["warnings"]
    res["sets"] = [{"set": 1, "finalScore": [21, 15]}, {"set": 2, "finalScore": None}]   # partial, A ahead
    ok = match_doc(res, meta)
    assert ok["attributed"] is True and WINNER_WARNING not in ok["analyzer"]["warnings"]
