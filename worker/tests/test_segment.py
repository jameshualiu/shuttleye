"""Rally segmentation and serve onset (fullmatch.segment / fullmatch.serves).

Synthetic arrays only; no video, no models.
"""
import numpy as np

from fullmatch.segment import (
    both_tracked, camera_runs, filter_runs_by_bbox, keep_group, segment_rallies, split_at_restarts,
)
from fullmatch.serves import serve_onset
from fullmatch.units import SCALE_TO_HD, frames_at, speed_at


# --- brief tests -------------------------------------------------------------

def test_camera_runs_bridge_short_dropouts_and_drop_short_runs():
    t = np.zeros(400, bool); t[10:200] = True; t[220:300] = True; t[350:370] = True
    assert camera_runs(t, merge_gap=45, min_run=45) == [(10, 299)]


def test_bbox_filter_drops_closeup_run():
    runs = [(0, 99), (200, 299), (400, 499)]
    h = np.r_[np.full(100, 80.), np.full(100, 0.), np.full(100, 82.), np.full(100, 0.), np.full(100, 200.)]
    assert filter_runs_by_bbox(runs, h, tol=0.25) == [(0, 99), (200, 299)]


def test_serve_onset_from_rest():
    xy = np.r_[np.full((20, 2), 100.), np.cumsum(np.full((10, 2), 8.), axis=0) + 100]
    assert serve_onset(xy, np.arange(30), hit_frames=[])["frame"] == 19


def test_one_hit_group_needs_solo_score():
    weak = [{"frame": 100, "score": 1.5, "side": "Top"}]
    strong = [{"frame": 100, "score": 4.0, "side": "Top"}]
    assert keep_group(weak) is False and keep_group(strong) is True


def test_restart_tap_is_split_off():
    g = [{"frame": 100, "v_in": 9.0}, {"frame": 160, "v_in": 1.0}, {"frame": 190, "v_in": 12.0}]
    assert [[h["frame"] for h in s] for s in split_at_restarts(g, restart_speed=2.5)] == [[100], [160, 190]]


# --- more ---------------------------------------------------------------------

def test_units():
    assert SCALE_TO_HD == 2.5
    assert frames_at(45, 30.0) == 45 and frames_at(45, 60.0) == 90 and frames_at(45, 25.0) == 38
    assert speed_at(3.0, 30.0) == 3.0 and speed_at(3.0, 60.0) == 1.5


def _player(top, h=40.0):
    return {"box": [100.0, top, 130.0, top + h], "skeleton": [[0.0, 0.0]] * 17}


def test_both_tracked_needs_two_players():
    tracking = [{"frame": 0, "players": [_player(50), _player(150)]},
                {"frame": 1, "players": [_player(50)]},
                {"frame": 3, "players": [_player(50), _player(150)]}]
    assert both_tracked(tracking, 5).tolist() == [True, False, False, True, False]


def test_serve_onset_skips_when_a_hit_is_close():
    xy = np.r_[np.full((20, 2), 100.), np.cumsum(np.full((10, 2), 8.), axis=0) + 100]
    assert serve_onset(xy, np.arange(30), hit_frames=[25]) is None
    assert serve_onset(xy, np.arange(30), hit_frames=[40])["isServe"] is True


def test_serve_onset_ignores_slow_motion_and_gaps():
    xy = np.r_[np.cumsum(np.full((20, 2), 1.), axis=0), np.full((5, 2), np.nan)]
    assert serve_onset(xy, np.arange(25), hit_frames=[]) is None


def test_keep_group_rules():
    # 3+ hits must alternate
    same = [{"frame": f, "score": 5.0, "side": "Top"} for f in (0, 30, 60)]
    alt = [{"frame": f, "score": 5.0, "side": s} for f, s in ((0, "Top"), (30, "Bottom"), (60, "Top"))]
    assert keep_group(same) is False and keep_group(alt) is True
    # 2 hits need MIN_PAIR_DT between them
    assert keep_group([{"frame": 0, "score": 5.0, "side": "Top"}, {"frame": 5, "score": 5.0, "side": "Bottom"}]) is False
    assert keep_group([{"frame": 0, "score": 5.0, "side": "Top"}, {"frame": 30, "score": 5.0, "side": "Bottom"}]) is True
    # a serve keeps a short group only with a hit after it (Ruling 12)
    serve = {"frame": 0, "score": 25.0, "side": "Top", "isServe": True}
    assert keep_group([serve]) is False
    assert keep_group([serve, {"frame": 30, "score": 0.5, "side": "Bottom"}]) is True
    # mostly unattributed -> ghost kinks
    assert keep_group([{"frame": 0, "score": 9.0}]) is False


def test_split_at_restarts_ignores_unknown_speed():
    g = [{"frame": 100, "v_in": 9.0}, {"frame": 160, "v_in": None}]
    assert len(split_at_restarts(g)) == 1


def _scene(total=900):
    """Two players tracked on frames 100-500 (a rally) and 700-760 (a second run);
    a shuttle at rest then served at frame 149, with a reversal every 40 frames."""
    tracking = [{"frame": f, "players": []} for f in range(total)]
    for f in list(range(100, 501)) + list(range(700, 761)):
        tracking[f] = {"frame": f, "players": [_player(40), _player(150)]}
    shuttle = [{"frame": f, "pos": None, "confidence": 0.0} for f in range(total)]
    # boxes centre at y=60 (Top) and y=170 (Bottom); the shuttle flies between them
    x, y, vy = 115.0, 170.0, 0.0
    for f in range(130, 420):
        if f == 150:
            vy = -2.75                   # served from rest: 6.9 HD px/frame
        elif f > 150 and (f - 150) % 40 == 0:
            vy = -vy                     # a hit: hard reversal
        y += vy
        shuttle[f] = {"frame": f, "pos": [x, y], "confidence": 0.9}
    hits = [150 + 40 * k for k in range(1, 6)]
    sides = ["Top", "Bottom", "Top", "Bottom", "Top"]
    events = [{"frame": f, "side": s, "type": "Clear"} for f, s in zip(hits, sides)]
    events.append({"frame": 820, "side": "Top", "type": "Smash"})   # dead time, no run
    return events, tracking, shuttle, total


def test_segment_rallies_inserts_serve_and_drops_dead_time():
    events, tracking, shuttle, total = _scene()
    rallies = segment_rallies(events, tracking, shuttle, total)
    assert len(rallies) == 1
    r = rallies[0]
    serve = [e for e in events if e.get("isServe")]
    assert len(serve) == 1 and serve[0]["type"] == "Serve" and serve[0]["detailType"] is None
    assert abs(serve[0]["frame"] - 149) <= 1
    assert [e["frame"] for e in events] == sorted(e["frame"] for e in events)
    kept = [events[i]["frame"] for i in r["eventIndices"]]
    assert kept[0] == serve[0]["frame"] and 820 not in kept and len(kept) == 6
    assert r["startFrame"] == serve[0]["frame"] and r["lastHitFrame"] == 350
    assert r["endFrame"] == 389     # landing: lowest screen point of the last flight


def test_serve_before_a_quick_return_is_kept():
    # serve at 149, return 14 frames later: upstream's 16-frame guard would
    # swallow it, SERVE_HIT_GAP (8) doesn't
    events, tracking, shuttle, total = _scene()
    events.insert(0, {"frame": 163, "side": "Top", "type": "Net"})
    segment_rallies(events, tracking, shuttle, total)
    assert [e["frame"] for e in events if e.get("isServe")] == [149]


def test_landing_frame_stops_at_a_cut():
    from fullmatch.segment import landing_frame
    xy = np.full((40, 2), np.nan)
    xy[2:12] = np.c_[np.full(10, 100.), np.arange(10) * 5 + 100]   # falling to y=145
    xy[12:20] = np.c_[np.full(8, 900.), np.full(8, 700.)]           # jump: a cut
    assert landing_frame(xy, 0) == 11


def test_segment_rallies_empty():
    assert segment_rallies([], [{"frame": 0, "players": []}], [{"frame": 0, "pos": None}], 1) == []


def _restart_scene(total=700):
    """A pickup tap at 150 (Bottom pushes the resting shuttle along slowly), the
    shuttle at rest again, then a detected serve at 200 from rest (v_in ~ 0, a
    restart) and a rally with reversals every 40 frames up to 400."""
    tracking = [{"frame": f, "players": [_player(40), _player(150)]} for f in range(100, 600)]
    tracking = [{"frame": f, "players": []} for f in range(100)] + tracking + \
        [{"frame": f, "players": []} for f in range(600, total)]
    shuttle = [{"frame": f, "pos": None, "confidence": 0.0} for f in range(total)]
    x, y, vy = 115.0, 170.0, 0.0
    for f in range(120, 450):
        if f == 150:
            vy = -0.6                    # tap: 1.5 HD px/frame, no motion onset
        elif f == 160:
            vy = 0.0                     # at rest again
        elif f == 200:
            vy = -2.75                   # serve from rest
        elif f > 200 and (f - 200) % 40 == 0:
            vy = -vy
        y += vy
        shuttle[f] = {"frame": f, "pos": [x, y], "confidence": 0.9}
    events = [{"frame": 150, "side": "Bottom", "type": "Net"}]
    sides = ["Bottom", "Top", "Bottom", "Top", "Bottom", "Top"]
    events += [{"frame": 200 + 40 * k, "side": s, "type": "Clear"} for k, s in enumerate(sides)]
    return events, tracking, shuttle, total


def test_pickup_tap_before_a_restart_serve_is_not_the_rally_start():
    events, tracking, shuttle, total = _restart_scene()
    rallies = segment_rallies(events, tracking, shuttle, total)
    assert len(rallies) == 1
    r = rallies[0]
    kept = [events[i]["frame"] for i in r["eventIndices"]]
    assert r["startFrame"] == 200 and 150 not in kept          # starts at the serve
    assert kept == [200, 240, 280, 320, 360, 400]


def test_surviving_tap_is_not_merged_back_into_the_rally(monkeypatch):
    from fullmatch import segment
    monkeypatch.setattr(segment, "MIN_SOLO_SCORE", 0.0)       # let the tap survive
    events, tracking, shuttle, total = _restart_scene()
    rallies = segment_rallies(events, tracking, shuttle, total)
    starts = [r["startFrame"] for r in rallies]
    assert 200 in starts                                       # restart boundary kept
    rally = next(r for r in rallies if r["startFrame"] == 200)
    assert 150 not in [events[i]["frame"] for i in rally["eventIndices"]]
    assert len(rallies) == 1      # the surviving 1-hit tap part is pre-serve handling: dropped


def test_false_restart_inside_a_long_rally_is_merged_back():
    # serve + 3 hits, then a hit with a noise-zero v_in: split there, re-merged
    from fullmatch import segment
    events, tracking, shuttle, total = _scene()
    for f in range(306, 311):            # shuttle "stalls" just before the hit at 310
        shuttle[f] = {**shuttle[305], "frame": f}
    parts = []
    orig = segment.split_at_restarts
    segment.split_at_restarts = lambda g, *a: parts.append(orig(g, *a)) or parts[-1]
    try:
        rallies = segment.segment_rallies(events, tracking, shuttle, total)
    finally:
        segment.split_at_restarts = orig
    assert any(len(p) == 2 for p in parts)                     # it was split...
    assert len(rallies) == 1                                   # ...and merged back
    assert rallies[0]["startFrame"] == 149 and rallies[0]["lastHitFrame"] == 350
