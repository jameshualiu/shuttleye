"""Unit tests for worker/train/eval_scoring.py (offline ShuttleSet eval).

eval_scoring is pure Python, so it's imported directly rather than mirrored.
"""
from train.eval_scoring import (
    ZH_TO_PRODUCT,
    PRODUCT_TYPES,
    match_hits,
    parse_rallies,
    score_rally,
    side_from_location,
    summarize,
)

# Identity homography: court plane == pixel plane. Far baseline at y=100,
# near baseline at y=500, so the net is at y=300.
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
FAR, NEAR = (0, 100), (0, 500)


def test_side_from_location_splits_at_the_net():
    assert side_from_location(IDENTITY, FAR, NEAR, 50, 150) == "Top"
    assert side_from_location(IDENTITY, FAR, NEAR, 50, 450) == "Bottom"
    assert side_from_location(IDENTITY, FAR, NEAR, None, 450) is None


def test_side_from_location_with_real_shuttleset_homography():
    # Axelsen vs Christie, YONEX Thailand Open 2021 QF (ShuttleSet homography.csv)
    h = [[1.2281615994201802, 0.5007529112054755, -608.0146919698522],
         [-0.004669709313989736, 5.717743425891395, -1447.3340488904664],
         [-1.546309742847567e-05, 0.002835614670238587, 1.0]]
    far, near = (413.2, 302.0), (290.2, 659.2)
    # set1.csv rally 1: player A stands far, player B stands near
    assert side_from_location(h, far, near, 543.0, 389.0) == "Top"
    assert side_from_location(h, far, near, 653.0, 526.0) == "Bottom"


def test_shuttleset_labels_map_onto_product_types():
    assert set(ZH_TO_PRODUCT.values()) <= set(PRODUCT_TYPES)
    assert ZH_TO_PRODUCT["點扣"] == "Smash"
    assert ZH_TO_PRODUCT["過度切球"] == "Drop"
    assert "發短球" not in ZH_TO_PRODUCT  # serves are excluded, not mapped


def test_parse_rallies_groups_sorts_and_labels_shots():
    rows = [
        {"rally": "1", "frame_num": "130.0", "type": "長球", "player_location_x": "5", "player_location_y": "450"},
        {"rally": "1", "frame_num": "100.0", "type": "發短球", "player_location_x": "5", "player_location_y": "150"},
        {"rally": "2", "frame_num": "400.0", "type": "未知球種", "player_location_x": "", "player_location_y": ""},
        {"rally": "2", "frame_num": "", "type": "長球"},
    ]
    rallies = parse_rallies(rows, IDENTITY, FAR, NEAR)
    assert [s["frame"] for s in rallies[1]] == [100, 130]
    assert rallies[1][0] == {"frame": 100, "serve": True, "type": None, "side": "Top"}
    assert rallies[1][1] == {"frame": 130, "serve": False, "type": "Clear", "side": "Bottom"}
    assert rallies[2] == [{"frame": 400, "serve": False, "type": None, "side": None}]


def test_match_hits_is_one_to_one_and_closest_first():
    # pred 11 is closer to gt 12 than pred 9 is, so 9 pairs with nothing
    assert match_hits([9, 11], [12], tolerance=3) == [(1, 0)]
    assert match_hits([10, 50], [12, 49], tolerance=3) == [(0, 0), (1, 1)]
    assert match_hits([10], [20], tolerance=3) == []


def _shot(frame, side, type_, serve=False):
    return {"frame": frame, "serve": serve, "type": type_, "side": side}


def test_score_rally_counts_hits_side_and_type():
    gt = [
        _shot(100, "Bottom", None, serve=True),
        _shot(130, "Top", "Clear"),
        _shot(160, "Bottom", "Smash"),
        _shot(190, "Top", "Net"),
    ]
    preds = [
        {"frame": 101, "side": "Bottom", "type": "Drive"},  # on the serve: ignored
        {"frame": 131, "side": "Top", "type": "Clear"},     # right
        {"frame": 158, "side": "Top", "type": "Smash"},     # wrong side, right type
        {"frame": 250, "side": "Bottom", "type": "Net"},    # false positive
    ]
    s = score_rally(preds, gt, tolerance=3)
    assert (s["tp"], s["fp"], s["fn"]) == (2, 1, 1)
    assert (s["side_correct"], s["side_total"], s["side_missing"]) == (1, 2, 0)
    assert (s["type_correct"], s["type_total"]) == (2, 2)
    assert s["frame_offsets"] == [1, -2]


def test_score_rally_counts_missing_side_and_unknown_type_as_wrong():
    gt = [_shot(130, "Top", "Clear")]
    preds = [{"frame": 130, "side": None, "type": None}]
    s = score_rally(preds, gt)
    assert (s["side_correct"], s["side_total"], s["side_missing"]) == (0, 1, 1)
    assert s["type_correct"] == 0
    assert s["confusion"] == {("Clear", "Unknown"): 1}


def test_summarize_aggregates_across_rallies():
    a = score_rally([{"frame": 10, "side": "Top", "type": "Clear"}], [_shot(10, "Top", "Clear")])
    b = score_rally([], [_shot(50, "Bottom", "Lob")])
    out = summarize([a, b])
    assert out["hits"]["precision"] == 1.0
    assert out["hits"]["recall"] == 0.5
    assert out["side"]["accuracy"] == 1.0
    assert out["confusion"] == {"Clear->Clear": 1}


def test_summarize_handles_no_predictions():
    out = summarize([score_rally([], [_shot(50, "Bottom", "Lob")])])
    assert out["hits"]["precision"] is None
    assert out["hits"]["f1"] is None
    assert out["side"]["accuracy"] is None
