import json

import pytest

from pro_profiles.clips import Clip, clip_for_rally, default_labels, make_labels, youtube_id
from pro_profiles.load import Match, Rally, Shot

PLAYERS = {"a": {"name": "Anthony Ginting"}, "b": {"name": "Kento Momota"}}
TOURNAMENTS = {"mm-2020": {"name": "Malaysia Masters", "season": 2020}}


def make_match(url="https://www.youtube.com/watch?v=abc123XYZ_-", round_="Finals"):
    shots = (Shot(1, 1, 100.0, "a", None, True), Shot(1, 2, 120.0, "b", "Net", False))
    rally = Rally("m1", 2, 1, shots, "a", 11, 7)
    return Match("m1", "ShuttleSet", "mm-2020", round_, "2020-01-01", "a", "b", url, (rally,))


def labels(match, rally):
    return ("M", "S")


def test_youtube_id_variants():
    assert youtube_id("https://www.youtube.com/watch?v=abc123XYZ_-") == "abc123XYZ_-"
    assert youtube_id("https://www.youtube.com/watch?v=abc123&t=30s&list=x") == "abc123"
    assert youtube_id("https://www.youtube.com/watch?feature=share&v=abc123") == "abc123"
    assert youtube_id("https://youtu.be/abc123") == "abc123"
    assert youtube_id("https://youtu.be/abc123?t=5") == "abc123"
    with pytest.raises(ValueError):
        youtube_id("https://example.com/nothing")


def test_clip_window_applies_offset_and_padding():
    m = make_match()
    sources = {"m1": {"url": m.youtube_url, "offsetSec": 5, "checked": False}}
    clip = clip_for_rally(m, m.rallies[0], sources, labels)
    assert clip == Clip("m1", "abc123XYZ_-", 103, 128, "M", "S")


def test_clip_window_floors_start_and_ceils_end():
    m = make_match()
    r = m.rallies[0]
    r = Rally(r.match_id, r.set_no, r.number, (
        Shot(1, 1, 100.4, "a", None, True), Shot(1, 2, 120.2, "b", "Net", False)), "a", 0, 0)
    sources = {"m1": {"url": m.youtube_url, "offsetSec": 0, "checked": False}}
    clip = clip_for_rally(m, r, sources, labels)
    assert (clip.start_sec, clip.end_sec) == (98, 124)  # floor(98.4), ceil(123.2)


def test_clip_start_never_negative():
    m = make_match()
    r = Rally("m1", 1, 1, (Shot(1, 1, 1.0, "a", None, True),), "a", 0, 0)
    sources = {"m1": {"url": m.youtube_url, "offsetSec": 0, "checked": False}}
    assert clip_for_rally(m, r, sources, labels).start_sec == 0


def test_no_source_no_clip():
    m = make_match(url=None)
    assert clip_for_rally(m, m.rallies[0], {}, labels) is None


def test_score_label_from_player_perspective():
    m = make_match()
    r = m.rallies[0]  # winner "a" leads 11-7
    assert default_labels(m, r, "a", PLAYERS, TOURNAMENTS) == (
        "Malaysia Masters 2020 final against Kento Momota",
        "game 2 at 11–7",
    )
    assert default_labels(m, r, "b", PLAYERS, TOURNAMENTS) == (
        "Malaysia Masters 2020 final against Anthony Ginting",
        "game 2 at 7–11",
    )


@pytest.mark.parametrize("raw,word", [
    ("Finals", "final"), ("Semi-finals", "semi-final"),
    ("Quarter-finals", "quarter-final"), ("Group-Stage", "group stage")])
def test_round_wording(raw, word):
    m = make_match(round_=raw)
    label, _ = default_labels(m, m.rallies[0], "a", PLAYERS, TOURNAMENTS)
    assert label == f"Malaysia Masters 2020 {word} against Kento Momota"


def test_make_labels_binds_player():
    m = make_match()
    fn = make_labels("b", PLAYERS, TOURNAMENTS)
    assert fn(m, m.rallies[0])[1] == "game 2 at 7–11"
