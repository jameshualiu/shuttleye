"""Stacked shot classifier inputs (fullmatch.shot_features, fullmatch.contact).
Synthetic events only; no sklearn model is trained here except the tiny
fallback round trip, which is skipped when sklearn is missing."""
import numpy as np
import pytest

from fullmatch.bst_inputs import TEN_CLASSES
from fullmatch.contact import BIN_PX, BODY_M, RULER_Q, contact_height
from fullmatch.shot_features import (
    COURT_L, COURT_W, FEATURES, apply_shot_stack, attach_geometry, build_features, homography_from_kp6,
    to_court,
)
from train.eval_scoring import label_matched_events

KP6 = [[180, 123], [330, 123], [164, 175], [344, 175], [138, 262], [372, 262]]


def test_features_have_fixed_width_and_nan_for_missing():
    ev = [{"probs": [0.04] * 25, "side": "Top", "frame": 10}]
    X = build_features(ev, [{"startFrame": 0, "endFrame": 50, "eventIndices": [0]}])
    assert X.shape == (1, len(FEATURES)) and np.isnan(X).any()


def test_neighbour_context_columns():
    ev = [{"probs": [0.04] * 25, "side": "Top", "frame": f, "detailId": i} for i, f in enumerate([10, 40, 70])]
    X = build_features(ev, [{"startFrame": 0, "endFrame": 90, "eventIndices": [0, 1, 2]}])
    prev, nxt = FEATURES.index("prev_type"), FEATURES.index("next_type")
    assert X[0, prev] == -1 and X[1, prev] == 0 and X[1, nxt] == 2 and X[2, nxt] == -1


def test_neighbour_context_stops_at_rally_boundaries():
    ev = [{"probs": [0.04] * 25, "frame": f, "detailId": 3} for f in (10, 40, 200, 230)]
    rallies = [{"eventIndices": [0, 1]}, {"eventIndices": [2, 3]}]
    X = build_features(ev, rallies)
    prev, nxt = FEATURES.index("prev_type"), FEATURES.index("next_type")
    assert X[1, nxt] == -1 and X[2, prev] == -1


def test_probs_and_time_columns():
    probs = np.linspace(0, 1, 25)
    ev = [{"probs": probs.tolist(), "frame": 0, "timeSec": 1.0},
          {"probs": None, "frame": 30, "timeSec": 2.0}]
    X = build_features(ev, [{"eventIndices": [0, 1]}])
    assert np.allclose(X[0, :25], probs)
    assert np.isnan(X[1, :25]).all()
    dt_prev = FEATURES.index("dt_prev")
    assert np.isnan(X[0, dt_prev]) and X[1, dt_prev] == pytest.approx(1.0)


def test_homography_maps_court_corners():
    h = homography_from_kp6(KP6)
    assert np.allclose(to_court(h, 180, 123), [0, 0], atol=1e-6)
    assert np.allclose(to_court(h, 372, 262), [COURT_W, COURT_L], atol=1e-6)
    assert np.allclose(to_court(h, 138, 262), [0, COURT_L], atol=1e-6)


def _player(foot_x, foot_y, height=40.0):
    sk = [[0.0, 0.0]] * 17
    sk = [list(p) for p in sk]
    sk[15] = [foot_x - 2, foot_y]
    sk[16] = [foot_x + 2, foot_y]
    return {"box": [foot_x - 10, foot_y - height, foot_x + 10, foot_y], "skeleton": sk}


def test_attach_geometry_mirrors_every_hitter_to_one_end():
    # Top player near the far baseline middle, Bottom player near the near baseline middle.
    far, near = _player(255, 125, 30), _player(255, 260, 60)
    tracking = [{"frame": f, "players": [far, near]} for f in range(40)]
    res = {"fps": 30.0, "court": KP6, "court_outliers": [], "chunks": [],
           "tracking": tracking, "shuttle": [{"frame": f, "pos": None} for f in range(40)],
           "events": [{"frame": 10, "side": "Top", "location_px": [255, 100], "probs": [0.04] * 25},
                      {"frame": 30, "side": "Bottom", "location_px": [255, 200], "probs": [0.04] * 25}],
           "rallies": [{"eventIndices": [0, 1]}]}
    attach_geometry(res)
    X = build_features(res["events"], res["rallies"])
    hy, ry = FEATURES.index("hitter_ny"), FEATURES.index("recv_ny")
    ly = FEATURES.index("land_ny")
    # COURTSIDE convention: every hitter is mirrored to the y = 0 end, so the
    # hitter sits near 0 and the receiver near 1 whichever side hit
    assert X[0, hy] < 0.1 and X[1, hy] < 0.1
    assert X[0, ry] > 0.9 and X[1, ry] > 0.9
    # landing of hit 0 = next hitter's feet (the other end, seen from hit 0's hitter)
    assert X[0, ly] > 0.9
    assert np.isnan(X[1, ly])            # rally's last hit: no next hitter
    h = FEATURES.index("contact_h")
    assert np.isfinite(X[0, h]) and np.isfinite(X[1, h])


def test_contact_height_person_ruler():
    # Standing box = 100 HD px at this depth -> 1 px = BODY_M / 100 m.
    heights = np.array([60.0] * 20 + [100.0] * 80)
    bottoms = np.full(100, 500.0)
    h = contact_height(heights, bottoms, ground_y=500.0, bottom_y=500.0, shuttle_y=400.0)
    ruler = np.quantile(heights, RULER_Q)
    assert h == pytest.approx(round(100 * BODY_M / ruler, 3))
    # no boxes in this depth bin -> no estimate
    assert np.isnan(contact_height(heights, bottoms, 500.0, 500.0 + 3 * BIN_PX, 400.0))
    # implausible (track glitch) -> NaN
    assert np.isnan(contact_height(heights, bottoms, 500.0, 500.0, -1000.0))


def test_label_matched_events_drops_serves_and_unmatched():
    preds = [{"frame": 100}, {"frame": 131}, {"frame": 170}, {"frame": 300}]
    gt = [{"frame": 100, "serve": True, "ten": "short service", "type": None},
          {"frame": 130, "serve": False, "ten": "lob", "type": "Lob"},
          {"frame": 171, "serve": False, "ten": "clear", "type": "Clear"}]
    labels = label_matched_events(preds, gt, tolerance=3)
    assert labels == {1: gt[1], 2: gt[2]}


def test_apply_shot_stack_falls_back_without_a_model(tmp_path):
    res = {"events": [{"frame": 1, "detailType": "lob", "type": "Lob"}], "rallies": []}
    out = apply_shot_stack(res, tmp_path / "missing.joblib", log=lambda *_: None)
    assert out["events"][0]["detailType"] == "lob" and not out.get("shotStack")


def test_apply_shot_stack_overwrites_non_serves(tmp_path):
    sklearn = pytest.importorskip("sklearn")
    import joblib
    from sklearn.dummy import DummyClassifier

    X = np.zeros((4, len(FEATURES)))
    ten = DummyClassifier(strategy="constant", constant="smash").fit(X, ["smash", "lob", "smash", "drop"])
    six = DummyClassifier(strategy="constant", constant="Smash").fit(X, ["Smash", "Lob", "Smash", "Drop"])
    path = tmp_path / "shot_stack.joblib"
    joblib.dump({"features": FEATURES, "ten": ten, "six": six, "sklearn": sklearn.__version__}, path)

    res = {"fps": 30.0, "court": KP6, "court_outliers": [], "chunks": [], "tracking": [], "shuttle": [],
           "events": [{"frame": 1, "probs": [0.04] * 25, "detailType": "lob", "type": "Lob", "side": "Top"},
                      {"frame": 9, "isServe": True, "detailType": "short service", "type": None}],
           "rallies": [{"eventIndices": [0, 1]}]}
    apply_shot_stack(res, path, log=lambda *_: None)
    e0, e1 = res["events"]
    assert (e0["detailType"], e0["type"], e0["detailId"]) == ("smash", "Smash", TEN_CLASSES.index("smash"))
    assert e1["detailType"] == "short service"
    assert res["shotStack"]["applied"] == 1


# --- fix round 1: guarded stack, degenerate courts, type/detailType consistency

class _Raises:
    classes_ = np.array(["smash"])

    def predict_proba(self, X):
        raise ValueError("sklearn drift at predict time")


def _stack_res():
    return {"fps": 30.0, "court": KP6, "court_outliers": [], "chunks": [], "tracking": [], "shuttle": [],
            "events": [{"frame": 1, "probs": [0.04] * 25, "detailType": "lob", "type": "Lob", "side": "Top",
                        "detailId": TEN_CLASSES.index("lob")},
                       {"frame": 9, "isServe": True, "detailType": "short service", "type": None}],
            "rallies": [{"eventIndices": [0, 1]}]}


def test_apply_shot_stack_keeps_task6_types_when_predict_fails(tmp_path):
    pytest.importorskip("sklearn")
    import joblib

    path = tmp_path / "broken.joblib"
    joblib.dump({"features": FEATURES, "ten": _Raises(), "six": None}, path)
    res = _stack_res()
    before = [dict(e) for e in res["events"]]
    logs = []
    apply_shot_stack(res, path, log=logs.append)
    assert res["events"] == before          # untouched, not even geometry fields
    assert "shotStack" not in res
    assert any("stack failed" in m for m in logs)


def test_degenerate_chunk_court_only_blanks_that_chunk():
    bad = [[100, 100]] * 6                     # all corners identical -> singular DLT
    far, near = _player(255, 125, 30), _player(255, 260, 60)
    tracking = [{"frame": f, "players": [far, near]} for f in range(200)]
    res = {"fps": 30.0, "court": KP6, "court_outliers": [],
           "chunks": [{"start": 0, "end": 99, "court_found": True, "geometry": {"court_keypoints_6": bad}},
                      {"start": 100, "end": 199, "court_found": True, "geometry": {"court_keypoints_6": KP6}}],
           "tracking": tracking, "shuttle": [],
           "events": [{"frame": 10, "side": "Top", "location_px": [255, 100]},
                      {"frame": 150, "side": "Top", "location_px": [255, 100]}],
           "rallies": []}
    attach_geometry(res)
    X = build_features(res["events"], [])
    hy = FEATURES.index("hitter_ny")
    assert np.isnan(X[0, hy]) and np.isfinite(X[1, hy])


def test_ten_to_products_is_derived_and_only_push_rush_is_ambiguous():
    from fullmatch.bst_inputs import MERGED_TO_PRODUCT, MERGED_TO_TEN, TEN_TO_PRODUCTS

    for ten, opts in TEN_TO_PRODUCTS.items():
        assert set(opts) == {MERGED_TO_PRODUCT[zh] for zh, t in MERGED_TO_TEN.items() if t == ten} - {None}
    assert {t for t, o in TEN_TO_PRODUCTS.items() if len(o) > 1} == {"push/rush"}
    assert TEN_TO_PRODUCTS["push/rush"] == ["Drive", "Net"]


def test_product_type_follows_detail_type():
    from fullmatch.shot_features import product_type

    assert product_type("smash", {"Lob": 0.9, "Smash": 0.1}) == "Smash"     # six can't override
    assert product_type("push/rush", {"Drive": 0.2, "Net": 0.7, "Lob": 0.1}) == "Net"
    assert product_type("push/rush", {"Drive": 0.6, "Net": 0.3}) == "Drive"
    assert product_type("push/rush", None, current="Net") == "Net"
    assert product_type("short service") is None


@pytest.mark.parametrize("ten_label,six_label", [("smash", "Lob"), ("push/rush", "Net"), ("push/rush", "Smash")])
def test_stacked_type_is_consistent_with_detail_type(tmp_path, ten_label, six_label):
    pytest.importorskip("sklearn")
    import joblib
    from sklearn.dummy import DummyClassifier

    from fullmatch.bst_inputs import TEN_TO_PRODUCTS

    X = np.zeros((3, len(FEATURES)))
    ten = DummyClassifier(strategy="constant", constant=ten_label).fit(X, [ten_label, "lob", "drop"])
    six = DummyClassifier(strategy="constant", constant=six_label).fit(X, [six_label, "Drive", "Clear"])
    path = tmp_path / f"stack_{ten_label.replace('/', '_')}_{six_label}.joblib"
    joblib.dump({"features": FEATURES, "ten": ten, "six": six}, path)
    res = _stack_res()
    apply_shot_stack(res, path, log=lambda *_: None)
    e = res["events"][0]
    assert e["detailType"] == ten_label
    assert e["type"] in TEN_TO_PRODUCTS[ten_label]
    if ten_label == "push/rush" and six_label == "Net":
        assert e["type"] == "Net"
