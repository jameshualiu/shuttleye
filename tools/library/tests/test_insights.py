import pytest
from pro_profiles.load import Match, Rally, Shot
from pro_profiles.stats import Ranked
from library.insights import SHOWN_GROUPS

from library import insights
from library.insights import player_insights, rank_insight

P, O = "p", "o"


def shot(order, player, group=None, t=None, detail=None, zone=None, serve=False):
    return Shot(rally=1, order=order, time_sec=float(order if t is None else t), player=player,
                group=group, is_serve=serve, detail=detail, zone=zone)


def rally(shots, winner=None, n=1):
    return Rally(match_id="m", set_no=1, number=n, shots=tuple(shots), winner=winner, score_a=0, score_b=0)


def match(rallies):
    return Match(id="m", source="Analyzer", edition_id="e", round="F", date="2022-01-01",
                 winner=P, loser=O, youtube_url=None, rallies=tuple(rallies))


@pytest.fixture
def low(monkeypatch):
    monkeypatch.setattr(insights, "MIN_SHARE_SHOTS", 1)
    monkeypatch.setattr(insights, "MIN_BAND_RALLIES", 1)
    monkeypatch.setattr(insights, "MIN_SERVES", 1)
    monkeypatch.setattr(insights, "MIN_GAPS", 1)
    monkeypatch.setattr(insights, "MIN_RALLIES", 1)


def test_phase_mix_split(low):
    # P hits odd orders 1..13 (7 shots), O hits even
    groups = {1: None, 3: "Net", 5: "Smash", 7: "Smash", 9: "Lift", 11: "Net", 13: "Clear"}
    shots = [shot(i, P if i % 2 else O, groups.get(i, "Drop") if i % 2 else "Net") for i in range(1, 15)]
    shots[0] = shot(1, P, None, serve=True)
    r = player_insights([match([rally(shots)])], P)["phaseMix"]
    assert r["start"]["shots"] == 1 and r["start"]["Net"] == 100.0  # order 3 only; serve excluded
    assert r["mid"]["shots"] == 4
    assert r["mid"]["Smash"] == 50.0 and r["mid"]["Lift"] == 25.0 and r["mid"]["Net"] == 25.0
    assert r["late"] == {**{g: 0.0 for g in SHOWN_GROUPS}, "Clear": 100.0, "shots": 1}


def test_replies_after_smash(low):
    shots = [shot(1, O, "Smash"), shot(2, P, "Lift"), shot(3, O, "Smash"), shot(4, P, "Net"),
             shot(5, O, "Drop"), shot(6, P, "Net")]
    r = player_insights([match([rally(shots)])], P)["replies"]
    assert r["Smash"]["shots"] == 2 and r["Smash"]["Lift"] == 50.0 and r["Smash"]["Net"] == 50.0
    assert r["Drop"]["shots"] == 1 and r["Drop"]["Net"] == 100.0
    assert r["Lift"]["shots"] == 0 and r["Lift"]["Net"] is None


def test_zones_share(low):
    shots = [shot(1, P, "Net", zone="rear-left"), shot(2, O, "Net", zone="front-left"),
             shot(3, P, "Net", zone="rear-left"), shot(4, P, "Net", zone="mid-right"),
             shot(5, P, "Net", zone=None)]
    z = player_insights([match([rally(shots)])], P)["zones"]
    assert z["shots"] == 3
    assert z["rear-left"] == 66.7 and z["mid-right"] == 33.3 and z["front-left"] == 0.0
    assert len(z) == 7


def test_tempo_gap(low):
    shots = [shot(1, O, t=0.0), shot(2, P, t=1.5), shot(3, "?", t=2.0), shot(4, P, t=4.0)]
    t = player_insights([match([rally(shots)])], P)["tempo"]
    assert t["secPerShot"] == 1.75  # (1.5 + 2.0) / 2
    assert t["rallyShots"] == 4.0


def test_bands_only_read_rallies(low):
    rs = [rally([shot(i, P, "Net") for i in range(1, 4)], winner=P, n=1),
          rally([shot(i, P, "Net") for i in range(1, 4)], winner=O, n=2),
          rally([shot(i, P, "Net") for i in range(1, 4)], winner=None, n=3)]
    b = player_insights([match(rs)], P)["bands"]
    assert b[0] == {"band": "short", "label": "4 shots or fewer", "rallies": 2, "winRate": 50.0}
    assert b[1]["rallies"] == 0 and b[1]["winRate"] is None


def test_serve_short_share(low):
    def serve_rally(n, server, d, winner):
        return rally([shot(1, server, None, detail=d, serve=True), shot(2, O if server == P else P, "Net")],
                     winner=winner, n=n)
    rs = [serve_rally(1, P, "short service", P), serve_rally(2, P, "short service", O),
          serve_rally(3, P, "long service", P), serve_rally(4, O, "short service", P)]
    s = player_insights([match(rs)], P)["serve"]
    assert s == {"serves": 3, "shortShare": 66.7, "pointsWonShort": 50.0, "pointsWonLong": 100.0}


def test_serve_length_from_receiver_zone(low):
    # Analyzer serves carry no detail: length comes from where the receiver hit shot 2.
    def serve_rally(n, server, zone, winner, receiver=None, serve=True):
        recv = receiver or (O if server == P else P)
        return rally([shot(1, server, None, serve=serve), shot(2, recv, "Net", zone=zone)],
                     winner=winner, n=n)
    rs = [serve_rally(1, P, "front-left", P), serve_rally(2, P, "mid-right", O),
          serve_rally(3, P, "rear-left", P), serve_rally(4, P, "rear-right", O),
          serve_rally(5, P, None, P),                       # zone unknown: excluded
          serve_rally(6, P, "rear-left", P, receiver="?"),  # receiver unknown: excluded
          serve_rally(7, P, "rear-left", P, serve=False),   # first shot not a serve: not counted
          serve_rally(8, O, "front-left", P)]               # opponent's serve
    s = player_insights([match(rs)], P)["serve"]
    assert s == {"serves": 6, "shortShare": 50.0, "pointsWonShort": 50.0, "pointsWonLong": 50.0}


def test_serve_detail_overrides_zone(low):
    rs = [rally([shot(1, P, None, detail="long service", serve=True), shot(2, O, "Net", zone="front-left")],
                winner=P)]
    s = player_insights([match(rs)], P)["serve"]
    assert s["serves"] == 1 and s["shortShare"] == 0.0 and s["pointsWonLong"] == 100.0


def test_serve_without_any_length(low):
    rs = [rally([shot(1, P, None, serve=True)], winner=P)]
    s = player_insights([match(rs)], P)["serve"]
    assert s == {"serves": 1, "shortShare": None, "pointsWonShort": None, "pointsWonLong": None}


def test_smash_wins(low):
    rs = [rally([shot(1, O, "Net"), shot(2, P, "Smash"), shot(3, O, "Lift")], winner=P, n=1),
          rally([shot(1, O, "Net"), shot(2, P, "Smash"), shot(3, O, "Lift"), shot(4, P, "Net"),
                 shot(5, O, "Net")], winner=P, n=2),
          rally([shot(1, P, "Smash"), shot(2, O, "Net")], winner=None, n=3)]
    s = player_insights([match(rs)], P)["smashWins"]
    assert s == {"smashes": 2, "winShare": 50.0}


def test_under_minimum_is_null():
    shots = [shot(i, P, "Net", zone="rear-left") for i in range(1, 50)]
    out = player_insights([match([rally(shots, winner=P)])], P)
    assert out["phaseMix"]["mid"]["Net"] is None and out["phaseMix"]["mid"]["shots"] == 8
    assert out["zones"]["rear-left"] is None and out["zones"]["shots"] == 49
    assert out["tempo"] == {"secPerShot": None, "rallyShots": None}
    assert out["serve"]["shortShare"] is None and out["serve"]["serves"] == 0  # first shot is not a serve
    assert out["smashWins"] == {"smashes": 0, "winShare": None}
    assert all(b["winRate"] is None for b in out["bands"])
    empty = player_insights([], P)
    assert empty["zones"]["shots"] == 0


def test_rank_needs_ten_players():
    def ins(v):
        return {"tempo": {"secPerShot": v}}
    nine = {f"p{i}": ins(float(i)) for i in range(9)}
    assert rank_insight(nine, "p3", ("tempo", "secPerShot")) is None
    ten = {f"p{i}": ins(float(i)) for i in range(10)}
    r = rank_insight(ten, "p3", ("tempo", "secPerShot"))
    assert isinstance(r, Ranked) and r.of == 10 and r.rank == 7
    ten["p3"] = ins(None)
    assert rank_insight(ten, "p3", ("tempo", "secPerShot")) is None


def test_unrelated_match_ignored(low):
    mine = match([rally([shot(1, P, "Net"), shot(2, O, "Net")], winner=P)])
    other = Match(id="x", source="Analyzer", edition_id="e", round="F", date="2022-01-01",
                  winner="a", loser="b", youtube_url=None,
                  rallies=(rally([shot(1, "a", "Net"), shot(2, "b", "Net")], winner="b"),))
    out = player_insights([mine, other], P)
    assert out["bands"][0]["rallies"] == 1 and out["bands"][0]["winRate"] == 100.0


def test_unknown_player_excluded_from_shares_but_counts_length(low):
    shots = [shot(1, P, "Net"), shot(2, "?", "Smash"), shot(3, "?", None), shot(4, P, "Lift")]
    out = player_insights([match([rally(shots, winner=P)])], P)
    assert out["phaseMix"]["start"]["shots"] == 2
    assert out["phaseMix"]["start"]["Smash"] == 0.0
    assert out["tempo"]["rallyShots"] == 4.0
    assert out["bands"][0]["rallies"] == 1


def test_block_is_its_own_group(low):
    shots = [shot(1, O, "Smash"), shot(2, P, "Block"), shot(3, O, "Smash"), shot(4, P, "Lift")]
    r = player_insights([match([rally(shots)])], P)
    assert r["replies"]["Smash"]["Block"] == 50.0 and r["replies"]["Smash"]["Lift"] == 50.0
    assert r["phaseMix"]["start"]["Block"] == 50.0
