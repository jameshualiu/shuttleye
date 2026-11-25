"""Scoreboard events -> rallies (align_scores) and the per-set side map.
Pure: fullmatch.scoreboard imports cv2 lazily, so this runs without it."""
from fullmatch.scoreboard import align_scores, events, rally_serve_sides, side_map


def test_align_assigns_to_latest_ended_rally():
    rallies = [{"id": 1, "endFrame": 100}, {"id": 2, "endFrame": 300}]
    ev = [{"frame": 180, "score": (1, 0)}, {"frame": 420, "score": (1, 1)}]
    out = align_scores(rallies, ev)
    assert out[0]["scoreAfter"] == (1, 0) and out[1]["scoreAfter"] == (1, 1)
    assert out[0]["winner"] == "A" and out[1]["winner"] == "B"
    assert out[0]["set"] == 1 and out[1]["set"] == 1


def test_align_late_event_skips_rally_without_reading():
    # the overlay update for rally 1 was hidden by a replay: the 2-0 reading
    # lands after rally 2 ended, rally 1 inherits nothing from a later event
    rallies = [{"endFrame": 100}, {"endFrame": 300}, {"endFrame": 500}]
    ev = [{"frame": 350, "score": (2, 0)}, {"frame": 560, "score": (3, 0)}]
    out = align_scores(rallies, ev)
    assert out[0]["scoreAfter"] == (0, 0) and out[0]["winner"] is None
    assert out[1]["scoreAfter"] == (2, 0) and out[2]["scoreAfter"] == (3, 0)
    assert out[2]["winner"] == "A"


def test_align_orients_scores_to_match_winner_and_closes_sets():
    # bottom row wins both sets; set 1's 21st point was never shown
    rallies = [{"endFrame": f} for f in (100, 200, 300, 400)]
    ev = [{"frame": 150, "set": 1, "score": (17, 19)}, {"frame": 250, "set": 1, "score": (17, 20)},
          {"frame": 450, "set": 2, "score": (10, 21)}]
    out = align_scores(rallies, ev)
    assert out[1]["scoreAfter"] == (20, 17)          # (A, B), A = bottom row
    assert out[2]["set"] == 1 and out[2]["scoreAfter"] == (21, 17) and out[2]["winner"] == "A"
    assert out[3]["set"] == 2 and out[3]["scoreAfter"] == (21, 10)


def test_events_debounce_and_set_change():
    tl = [{"frame": f, "cells": c, "top": t, "bot": b}
          for f, c, t, b in [(0, 1, 0, 0), (30, 1, 0, 0), (60, 1, 1, 0), (90, 1, 1, 0),
                             (120, 1, 8, 0), (150, 1, 1, 0), (180, 1, 1, 1), (210, 1, 1, 1),
                             (240, 2, 0, 0), (270, 2, 0, 0)]]
    ev = events(tl)     # the one-sample 8-0 misread is dropped
    assert [(e["frame"], e["set"], e["score"]) for e in ev] == [
        (0, 1, (0, 0)), (60, 1, (1, 0)), (180, 1, (1, 1)), (240, 2, (0, 0))]
    assert ev[2]["winner"] == "bot" and ev[2]["jump"] == 1
    assert ev[3]["newSet"] and ev[3]["winner"] is None


def make_deciding_set_rallies(near_first="A", swap_after=(11, 7)):
    """Set-3 rallies: A and B trade points up to `swap_after` (a > b),
    the ends change (leader reached 11), then alternate to 21-x. Serve sides
    follow 'winner serves next', A serving first from `near_first`'s end."""
    other = {"A": "B", "B": "A"}
    a, b = swap_after
    pts = ["A", "B"] * b + ["A"] * (a - b)        # B reaches b before A reaches a
    while a < 21:
        w = "B" if len(pts) % 2 else "A"
        a, b = (a + 1, b) if w == "A" else (a, b + 1)
        pts.append(w)
    rallies, near, swapped, sa, sb, server = [], near_first, False, 0, 0, "A"
    for w in pts:
        if max(sa, sb) == 11 and not swapped:
            near, swapped = other[near], True
        serve_side = "near" if server == near else "far"
        sa, sb = (sa + 1, sb) if w == "A" else (sa, sb + 1)
        rallies.append({"set": 3, "scoreAfter": (sa, sb), "winner": w, "serveSide": serve_side})
        server = w
    return rallies


def test_deciding_set_ends_swap_at_11():
    rallies = make_deciding_set_rallies(near_first="A", swap_after=(11, 7))
    sm = side_map(rallies)
    before, after = sm[0], sm[-1]
    assert before["near"] == "A" and after["near"] == "B"
    assert after["set"] == 3 and after["fromScore"] == (11, 7)
    # each rally carries its near player
    assert rallies[0]["near"] == "A" and rallies[-1]["near"] == "B"


def test_side_map_alternates_ends_between_sets():
    rallies = []
    for sn, near in ((1, "B"), (2, "A")):
        a = b = 0
        server = "A"
        for k in range(12):
            w = "A" if k % 2 == 0 else "B"
            serve_side = "near" if server == near else "far"
            a, b = (a + 1, b) if w == "A" else (a, b + 1)
            rallies.append({"set": sn, "scoreAfter": (a, b), "winner": w, "serveSide": serve_side})
            server = w
    sm = side_map(rallies)
    assert [(s["set"], s["near"]) for s in sm] == [(1, "B"), (2, "A")]


def test_side_map_without_votes_is_empty():
    assert side_map([{"set": 1, "scoreAfter": None, "winner": None, "serveSide": None}]) == []


def test_serve_side_from_serve_or_opposite_of_first_hit():
    res = {"events": [{"frame": 0, "side": "Bottom", "isServe": True}, {"frame": 20, "side": "Top"},
                      {"frame": 500, "side": "Top"}, {"frame": 530, "side": "Bottom"}],
           "rallies": [{"eventIndices": [0, 1]}, {"eventIndices": [2, 3]}, {"eventIndices": []}]}
    rally_serve_sides(res)
    # rally 2 lost its serve: its first hit is the return, so the server is near
    assert [r["serveSide"] for r in res["rallies"]] == ["near", "near", None]
