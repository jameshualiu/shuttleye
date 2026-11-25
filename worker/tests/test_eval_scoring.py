"""Unit tests for worker/train/eval_scoring.py (offline ShuttleSet eval).

eval_scoring is pure Python, so it's imported directly rather than mirrored.
"""
from train.eval_scoring import (
    ZH_TO_PRODUCT,
    ZH_TO_TEN,
    PRODUCT_TYPES,
    fit_frame_offset,
    match_hits,
    parse_rallies,
    parse_rally_scores,
    score_rally,
    score_scoreboard,
    score_segments,
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
    assert rallies[1][0] == {"frame": 100, "serve": True, "type": None, "ten": "short service", "side": "Top"}
    assert rallies[1][1] == {"frame": 130, "serve": False, "type": "Clear", "ten": "clear", "side": "Bottom"}
    assert rallies[2] == [{"frame": 400, "serve": False, "type": None, "ten": None, "side": None}]


def test_parse_rallies_ball_round_one_is_the_serve():
    # ShuttleSet types many serves 未知球種; ball_round 1 is the serve whatever the type
    rows = [
        {"rally": "3", "ball_round": "1", "frame_num": "500", "type": "未知球種",
         "player_location_x": "5", "player_location_y": "150"},
        {"rally": "3", "ball_round": "2", "frame_num": "530", "type": "未知球種",
         "player_location_x": "5", "player_location_y": "450"},
        {"rally": "3", "ball_round": "3.0", "frame_num": "560", "type": "長球",
         "player_location_x": "5", "player_location_y": "150"},
        {"rally": "4", "ball_round": "", "frame_num": "800", "type": "發長球"},   # type check kept
    ]
    rallies = parse_rallies(rows, IDENTITY, FAR, NEAR)
    assert [s["serve"] for s in rallies[3]] == [True, False, False]
    assert rallies[3][0]["type"] is None and rallies[3][0]["ten"] is None
    assert rallies[4][0]["serve"] is True


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


def test_zh_to_ten_covers_the_ten_classes():
    assert set(ZH_TO_TEN.values()) == {
        "short service", "long service", "clear", "drive", "drop", "lob",
        "net shot", "smash", "push/rush", "defensive shot"}
    assert ZH_TO_TEN["點扣"] == "smash"
    assert "未知球種" not in ZH_TO_TEN


def test_score_segments_exact_and_split():
    gt = [(100, 400), (600, 900)]
    pred = [(90, 410), (600, 740), (745, 905)]
    s = score_segments(pred, gt)
    assert (s["tp"], s["fn"], s["split"]) == (2, 0, 1)
    assert s["fp"] == 0  # the second half of a split rally is not a false positive


def test_score_segments_merged():
    s = score_segments([(100, 900)], [(100, 400), (600, 900)])
    assert s["merged"] == 1 and s["tp"] == 1 and s["fn"] == 1


def test_score_segments_spurious_prediction_is_fp():
    s = score_segments([(100, 400), (1000, 1100)], [(100, 400)])
    assert (s["tp"], s["fp"], s["fn"], s["precision"], s["recall"]) == (1, 1, 0, 0.5, 1.0)


def test_fit_frame_offset_finds_shift():
    gt = [10, 50, 90, 130]
    pred = [f - 3 for f in gt]
    assert fit_frame_offset(pred, gt) == -3


def test_score_rally_counts_serve_when_included():
    gt = [{"frame": 10, "serve": True, "type": None, "ten": "short service", "side": "Bottom"},
          {"frame": 40, "serve": False, "type": "Net", "ten": "net shot", "side": "Top"}]
    pred = [{"frame": 11, "isServe": True, "type": "Serve", "detailType": "short service", "side": "Bottom"},
            {"frame": 40, "type": "Net", "detailType": "net shot", "side": "Top"}]
    s = score_rally(pred, gt, include_serves=True)
    assert s["tp"] == 2 and s["ten_correct"] == 2
    assert score_rally(pred, gt)["tp"] == 1  # default unchanged: serves excluded


def test_score_labelled_hits_counts_ten_type_and_side():
    from train.eval_scoring import score_labelled_hits
    gt = [
        {"frame": 10, "serve": True, "type": None, "ten": "short service", "side": "Bottom"},
        {"frame": 40, "serve": False, "type": "Net", "ten": "net shot", "side": "Top"},
        {"frame": 70, "serve": False, "type": "Drive", "ten": "push/rush", "side": "Bottom"},
        {"frame": 99, "serve": False, "type": "Smash", "ten": "smash", "side": "Top"},
    ]
    preds = [("Bottom", "發短球"), ("Top", "勾球"), ("Top", "平球"), (None, None)]
    s = score_labelled_hits(gt, preds)
    assert (s["ten_total"], s["ten_correct"]) == (4, 2)          # serve + cross-court net
    assert (s["ten_known"], s["ten_known_correct"]) == (3, 2)    # unknown pred excluded
    assert (s["type_total"], s["type_correct"]) == (3, 2)        # serves excluded; push -> Drive
    assert (s["side_total"], s["side_correct"]) == (4, 2)
    assert (s["side_known"], s["side_known_correct"]) == (3, 2)


def test_parse_rally_scores_reads_score_after_and_a_side():
    rows = [
        {"rally": "1", "frame_num": "100", "roundscore_A": "0", "roundscore_B": "1", "player": "B",
         "player_location_x": "5", "player_location_y": "450"},
        {"rally": "1", "frame_num": "130", "roundscore_A": "0", "roundscore_B": "1", "player": "A",
         "player_location_x": "5", "player_location_y": "150"},
        {"rally": "2", "frame_num": "300", "roundscore_A": "1", "roundscore_B": "1", "player": "A",
         "player_location_x": "", "player_location_y": ""},
    ]
    r = parse_rally_scores(rows, IDENTITY, FAR, NEAR)
    assert r[0] == {"rally": 1, "first": 100, "last": 130, "scoreAfter": (0, 1), "winner": "B", "aSide": "far"}
    assert r[1]["winner"] == "A" and r[1]["aSide"] is None


def test_score_scoreboard_rallies_finals_and_sides():
    gt = {1: [{"rally": 1, "first": 100, "last": 200, "scoreAfter": (1, 0), "winner": "A", "aSide": "near"},
              {"rally": 2, "first": 400, "last": 500, "scoreAfter": (1, 1), "winner": "B", "aSide": "near"},
              {"rally": 3, "first": 700, "last": 800, "scoreAfter": (21, 1), "winner": "A", "aSide": "near"}]}
    pred = [{"startFrame": 95, "endFrame": 210, "set": 1, "scoreAfter": (1, 0), "winner": "A", "near": "A"},
            {"startFrame": 410, "endFrame": 520, "set": 1, "scoreAfter": (0, 1), "winner": "B", "near": "B"},
            {"startFrame": 690, "endFrame": 790, "set": 1, "scoreAfter": (21, 1), "winner": "A", "near": "A"}]
    s = score_scoreboard(pred, gt)
    assert s["rallies"] == 3 and s["matched"] == 3
    assert s["score_correct"] == 2 and s["winner_correct"] == 3 and s["side_correct"] == 2
    assert s["finals"] == {1: {"pred": (21, 1), "gt": (21, 1), "exact": True}}
    assert s["finals_exact"] is True
