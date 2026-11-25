from library.match_doc import match_doc
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
        sb = d["scoreBefore"] or [0, 0]
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
