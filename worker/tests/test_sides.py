"""Alternating side decode (fullmatch.sides). Synthetic arrays only."""
import ast
from pathlib import Path

import numpy as np

from fullmatch.bst_inputs import EN_TO_PRODUCT, MERGED_TO_EN, MERGED_TO_PRODUCT, MERGED_TO_TEN, MERGED_TYPES_ZH, TEN_CLASSES
from fullmatch.sides import apply_side_decode, best_type_within_side, decode_sides, side_probs
from train.eval_scoring import ZH_TO_TEN

WORKER = Path(__file__).resolve().parents[1]


def test_alternation_fixes_one_weak_flip():
    p = np.array([0.9, 0.2, 0.55, 0.1, 0.9])     # third hit weakly says Top
    sides, over = decode_sides(p)
    assert sides == ["Top", "Bottom", "Top", "Bottom", "Top"]
    assert not any(over)


def test_weak_bottom_flip_is_fixed_too():
    sides, _ = decode_sides(np.array([0.1, 0.8, 0.45, 0.9]))
    assert sides == ["Bottom", "Top", "Bottom", "Top"]


def test_strong_contrary_evidence_is_flagged():
    p = np.array([0.9, 0.05, 0.03, 0.1])          # hits 2 and 3 both strongly Bottom
    sides, over = decode_sides(p)
    assert over.count(True) >= 1
    assert all(a != b for a, b in zip(sides, sides[1:]))


def test_empty_and_single():
    assert decode_sides(np.array([])) == ([], [])
    assert decode_sides(np.array([0.7]))[0] == ["Top"]


def test_type_picked_within_decoded_side():
    probs = np.zeros(25); probs[3] = 0.6; probs[13 + 5] = 0.3   # Top class 3 wins overall
    assert best_type_within_side(probs, "Bottom") == 13 + 5
    assert best_type_within_side(probs, "Top") == 3


def test_side_probs():
    probs = np.zeros((3, 25))
    probs[0, 2] = 0.6; probs[0, 14] = 0.2        # Top 0.75
    probs[1, 0] = 1.0                            # unknown only -> 0.5
    probs[2, 20] = 1.0                           # Bottom -> 0
    assert np.allclose(side_probs(probs), [0.75, 0.5, 0.0])


def _ev(frame, side, cls=None, **kw):
    e = {"frame": frame, "side": side, **kw}
    if cls is not None:
        p = [0.0] * 25
        p[cls] = 0.9
        e.update(probs=p, type="x", detailType="x")
    return e


def test_apply_overrides_side_and_repicks_type_within_it():
    # middle hit's best class is Top smash (3) but alternation says Bottom;
    # its Bottom smash (15) is the runner-up
    mid = _ev(20, "Top", 3)
    mid["probs"][15] = 0.08
    mid["probs"][3] = 0.52   # Top 0.52 vs Bottom 0.08 -> p_top ~0.87, weak enough to flip
    res = {"events": [_ev(10, "Top", 3), mid, _ev(30, "Top", 3)],
           "rallies": [{"eventIndices": [0, 1, 2]}]}
    # make hits 0 and 2 clearly Top, 1 weakly Top -> decode T,B,T
    apply_side_decode(res, log=lambda *a: None)
    ev = res["events"]
    assert [e["side"] for e in ev] == ["Top", "Bottom", "Top"]
    assert ev[1]["detailType"] == "smash" and ev[1]["type"] == "Smash"
    assert ev[1]["detailId"] == TEN_CLASSES.index("smash")
    assert ev[1].get("sideOverridden") is False


def test_serve_participates_but_keeps_its_type():
    serve = {"frame": 5, "type": "Serve", "isServe": True, "side": "Top", "detailType": None}
    res = {"events": [serve, _ev(10, "Bottom", 13 + 2), _ev(20, "Top", 3)],
           "rallies": [{"eventIndices": [0, 1, 2]}]}
    apply_side_decode(res, log=lambda *a: None)
    assert res["events"][0]["type"] == "Serve" and res["events"][0]["side"] == "Top"
    assert "probs" not in res["events"][0]
    assert res["events"][0]["detailType"] is None
    assert [e["side"] for e in res["events"]] == ["Top", "Bottom", "Top"]


def test_unknown_hit_stays_unknown():
    e = {"frame": 20, "side": None, "type": "Unknown", "detailType": None,
         "probs": [1.0] + [0.0] * 24}
    res = {"events": [_ev(10, "Top", 3), e, _ev(30, "Top", 3)],
           "rallies": [{"eventIndices": [0, 1, 2]}]}
    apply_side_decode(res, log=lambda *a: None)
    got = res["events"][1]
    assert got["side"] == "Bottom"
    assert got["type"] == "Unknown" and got["detailType"] is None and got["detailId"] is None


def test_hit_whose_side_is_unchanged_keeps_its_original_choice():
    keep = _ev(20, "Bottom", 13 + 2)
    keep["type"], keep["detailType"] = "Clear", "clear"      # deliberately not the argmax's type
    res = {"events": [_ev(10, "Top", 3), keep, _ev(30, "Top", 3)],
           "rallies": [{"eventIndices": [0, 1, 2]}]}
    apply_side_decode(res, log=lambda *a: None)
    got = res["events"][1]
    assert got["type"] == "Clear" and got["detailType"] == "clear" and got["detailId"] == TEN_CLASSES.index("clear")


# --- contract guards ---------------------------------------------------------

def test_ten_classes_match_eval_scoring_order():
    ordered = list(dict.fromkeys(ZH_TO_TEN.values()))
    assert TEN_CLASSES == ordered and len(TEN_CLASSES) == 10
    assert set(MERGED_TO_TEN.values()) == set(TEN_CLASSES)


def test_stroke_classifier_derives_vocabularies_from_bst_inputs():
    tree = ast.parse((WORKER / "detectors" / "stroke_classifier.py").read_text())
    src = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in ("TYPE_EN", "PRODUCT_TYPE"):
            src[node.targets[0].id] = ast.unparse(node.value)
    assert src == {"TYPE_EN": "bst_inputs.MERGED_TO_EN", "PRODUCT_TYPE": "bst_inputs.EN_TO_PRODUCT"}
    assert set(MERGED_TO_EN) == set(MERGED_TYPES_ZH)
    assert MERGED_TO_PRODUCT == {zh: EN_TO_PRODUCT[en] for zh, en in MERGED_TO_EN.items()}
