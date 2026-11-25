"""BST-0 input building (fullmatch/bst_inputs.py), ported from COURTSIDE's
bst_eval.py. bst_inputs is numpy-only, so it is imported directly."""
import numpy as np

from fullmatch.bst_inputs import (
    CLASSES, SEQ_LEN, assign_slots, build_window, class_label, normalize_joints,
    shuttle_input, window_frames,
)


def test_normalize_joints_matches_courtside_scheme():
    j = np.array([[[110., 220.], [0., 0.]]])            # one joint visible, one missing
    bb = np.array([[100., 200., 130., 240.]])            # x1,y1,x2,y2 -> diag 50
    out = normalize_joints(j, bb)
    assert np.allclose(out[0, 0], [10 / 50, 20 / 50])
    assert np.allclose(out[0, 1], [0, 0])                # missing stays zero


def test_normalize_joints_zero_bbox_does_not_divide_by_zero():
    out = normalize_joints(np.zeros((1, 17, 2)), np.zeros((1, 4)))
    assert np.all(out == 0)


def test_window_is_centred_and_30_long():
    assert window_frames(100) == list(range(85, 115))


def test_shuttle_scaled_from_pipeline_space():
    assert np.allclose(shuttle_input([(256, 144)], (512, 288), (1280, 720)), [[0.5, 0.5]])


def test_shuttle_missing_is_zero():
    assert np.allclose(shuttle_input([None, (512, 288)], (512, 288), (1280, 720)),
                       [[0, 0], [1, 1]])


def test_class_order_is_bst_merged():
    assert len(CLASSES) == 25
    assert CLASSES[0] == "未知球種"
    assert CLASSES[1] == "Top_放小球" and CLASSES[13] == "Bottom_放小球"
    assert CLASSES[12] == "Top_發長球" and CLASSES[24] == "Bottom_發長球"


def test_class_label_maps_to_side_and_ten_class():
    assert class_label(0) == (None, None, None)
    assert class_label(3) == ("Top", "殺球", "smash")
    assert class_label(13 + 7) == ("Bottom", "推球", "push/rush")
    assert class_label(2) == ("Top", "擋小球", "defensive shot")


def _player(cx, cy):
    return {"box": [cx - 10, cy - 20, cx + 10, cy + 20],
            "skeleton": [[cx, cy]] * 17}


def test_two_players_keep_pipeline_top_first_order():
    top, bottom = _player(250, 60), _player(260, 230)
    assert assign_slots([[top, bottom]]) == [[top, bottom]]


def test_single_player_goes_to_nearest_slot_from_two_player_frame():
    top, bottom = _player(250, 60), _player(260, 230)
    lone_bottom = _player(262, 228)
    slots = assign_slots([[top, bottom], [lone_bottom], []])
    assert slots[1] == [None, lone_bottom]
    assert slots[2] == [None, None]


def test_single_player_without_reference_is_dropped():
    assert assign_slots([[_player(250, 60)]]) == [[None, None]]


def test_build_window_shapes_and_contents():
    # Top and Bottom differ (joint 0 position and box size), so a slot swap fails.
    top = {"box": [240, 40, 260, 80], "skeleton": [[250, 60]] * 17}       # diag hypot(20, 40)
    bottom = {"box": [240, 200, 300, 280], "skeleton": [[300, 280]] * 17}  # diag 100
    players = {f: [top, bottom] for f in range(85, 115)}
    shuttle = {100: (256, 144)}
    jnb, sh = build_window(100, shuttle, players, src_size=(512, 288), dst_size=(1280, 720))
    assert jnb.shape == (SEQ_LEN, 2, 72)
    assert sh.shape == (SEQ_LEN, 2)
    assert np.allclose(sh[15], [0.5, 0.5])               # hit frame is index 15
    assert np.allclose(sh[0], [0, 0])
    diag = np.hypot(20, 40)
    assert np.allclose(jnb[15, 0, :2], [10 / diag, 20 / diag])   # Top in slot 0
    assert np.allclose(jnb[15, 1, :2], [60 / 100, 80 / 100])     # Bottom in slot 1
    # all joints identical -> every bone is zero
    assert np.allclose(jnb[15, :, 34:], 0)


def test_merged_to_ten_matches_eval_scoring():
    from train.eval_scoring import ZH_TO_TEN
    from fullmatch.bst_inputs import MERGED_TO_TEN, MERGED_TYPES_ZH
    assert set(MERGED_TO_TEN) == set(MERGED_TYPES_ZH)
    assert all(MERGED_TO_TEN[k] == ZH_TO_TEN[k] for k in MERGED_TO_TEN)


def test_build_window_missing_frames_are_zero():
    jnb, sh = build_window(100, {}, {}, src_size=(512, 288), dst_size=(1280, 720))
    assert np.all(jnb == 0) and np.all(sh == 0)
