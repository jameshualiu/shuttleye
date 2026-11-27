from pro_profiles.clips import default_labels

from library.match_doc import match_doc
from library.tests.docs import TOURNAMENTS, make_doc, make_rally
from library.to_model import to_match


def test_to_match_players_and_rallies(product_result, meta):
    doc = match_doc(product_result, meta)
    m = to_match(doc)
    assert m.id == "test-match"
    assert m.source == "Analyzer"
    assert m.winner == "viktor-axelsen" and m.loser == "some-opponent"
    assert m.youtube_url == "https://www.youtube.com/watch?v=abc123"
    assert len(m.rallies) == len(doc["rallies"])
    for r, d in zip(m.rallies, doc["rallies"]):
        assert r.number == d["n"]
        assert r.set_no == (d["set"] or 1)
        expected = {"A": m.winner, "B": m.loser, None: None}[d["winner"]]
        assert r.winner == expected
        sb = d["scoreBefore"] or [None, None]
        assert (r.score_a, r.score_b) == tuple(sb)
    games = doc["games"]
    assert m.set_scores == (tuple((g["a"], g["b"]) for g in games) if games else ())


def test_shot_fields(product_result, meta):
    doc = match_doc(product_result, meta)
    m = to_match(doc)
    for r, d in zip(m.rallies, doc["rallies"]):
        assert len(r.shots) == len(d["shots"])
        for i, (s, ds) in enumerate(zip(r.shots, d["shots"]), 1):
            assert s.order == i and s.rally == d["n"]
            assert s.time_sec == ds["t"] and s.group == ds["g"]
            assert s.detail == ds["d"] and s.zone == ds["z"]
            assert s.is_serve == ds["s"]
            ids = {"A": "viktor-axelsen", "B": "some-opponent", None: "?"}
            assert s.player == ids[ds["p"]]
    assert any(s.player == "?" for r in m.rallies for s in r.shots)


def test_unread_score_label_not_zero_zero():
    r = {**make_rally(1, ["", "Net"]), "scoreBefore": None, "set": 2}
    m = to_match(make_doc("m1", "aa", "bb", [r]))
    rally = m.rallies[0]
    assert (rally.score_a, rally.score_b) == (None, None)
    players = {"aa": {"name": "A A"}, "bb": {"name": "B B"}}
    assert default_labels(m, rally, "aa", players, TOURNAMENTS)[1] == "game 2, score not read"
