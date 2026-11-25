from library import profiles
from library.profiles import build_library
from library.tests.docs import EDITION, TOURNAMENTS, late_rallies, make_doc, make_rally

PLAYERS = {"xx": {"name": "Xavier X", "event": "MS"}, "zz": {"name": "Zoe Z", "event": "WS"}}


def small_docs():
    rallies = [make_rally(1, ["", "Net", "Lift", "Smash"]), make_rally(2, ["", "Drop"], winner="B")]
    return [make_doc("m1", "xx", "yy", rallies), make_doc("m2", "zz", "xx", rallies, date="2022-08-02")]


def test_paths():
    out = build_library(small_docs(), PLAYERS, TOURNAMENTS, {})
    views = {
        "xx": ["all", f"t:{EDITION}", "m:m1", "m:m2"],
        "yy": ["all", f"t:{EDITION}", "m:m1"],
        "zz": ["all", f"t:{EDITION}", "m:m2"],
    }
    expected = {f"players/{p}" for p in views} | {
        f"players/{p}/views/{v}" for p, vs in views.items() for v in vs
    } | {f"tournaments/{EDITION}", "library/index"}
    assert set(out) == expected
    assert [f["id"] for f in out["players/xx"]["filters"]] == views["xx"]
    view = out["players/xx/views/m:m1"]
    assert set(view) == {"kind", "shots", "rallies", "insights", "findings", "rallyBrowser"}
    assert view["kind"] == "match" and len(view["rallyBrowser"]) == 2
    assert view["rallyBrowser"][0]["youtubeId"] == "yt-m1"


def test_no_comparison_under_ten():
    out = build_library(small_docs(), PLAYERS, TOURNAMENTS, {})
    doc = out["players/xx"]
    assert set(doc) == {"id", "name", "event", "context", "summary", "photo", "filters"}
    assert doc["summary"] is None
    assert doc["context"] == {"matches": 2, "firstYear": 2022, "lastYear": 2022, "comparedWith": 0}
    assert out["players/xx/views/all"]["findings"] == []
    assert out["players/xx/views/all"]["rallyBrowser"]  # example rallies instead


def test_new_player_falls_back_to_doc_name():
    out = build_library(small_docs(), PLAYERS, TOURNAMENTS, {})
    assert out["players/yy"]["name"] == "YY" and out["players/yy"]["event"] == "MS"
    assert out["players/zz"]["name"] == "Zoe Z" and out["players/zz"]["event"] == "WS"


def test_index_only_published_input():
    docs = small_docs()
    out = build_library(docs[:1], PLAYERS, TOURNAMENTS, {})
    index = out["library/index"]
    assert index["matches"] == [{
        "id": "m1", "editionId": EDITION, "round": "Final", "date": "2022-08-01",
        "players": docs[0]["players"], "games": [[21, 15], [21, 18]], "youtubeId": "yt-m1",
    }]
    assert {p["id"] for p in index["players"]} == {"xx", "yy"}
    assert index["editions"] == [{"id": EDITION, "name": "Test Open", "season": 2022, "matches": 1}]
    assert "players/zz" not in out


def twelve_player_docs():
    # p00 smashes on every late shot; the others on fewer.
    docs = []
    for i in range(0, 12, 2):
        a, b = f"p{i:02d}", f"p{i + 1:02d}"
        smash_a = 45 if i == 0 else i * 3
        docs.append(make_doc(f"m{i}", a, b, late_rallies(45, smash_a, i * 3 + 1)))
    return docs


def test_findings_with_twelve_players():
    out = build_library(twelve_player_docs(), {}, TOURNAMENTS, {})
    star = out["players/p00"]
    assert star["context"]["comparedWith"] == 11
    findings = out["players/p00/views/all"]["findings"]
    smash = [f for f in findings if f["key"] == "phaseMix.late.Smash.top"]
    assert len(smash) == 1
    f = smash[0]
    assert f["kind"] == "style"
    assert f["claim"] == "He smashes more than most pros after the 12th shot of a rally"
    assert f["figure"] == "100.0%"
    assert f["comparison"].startswith("of his shots after the 12th shot of a rally. A typical pro: ")
    assert f["tip"] is None
    assert 1 <= len(f["clips"]) <= 5 and f["clips"][0]["youtubeId"] == "yt-m0"
    assert star["summary"] and star["summary"].startswith("He ")
    assert len(findings) <= 4
    # Filtered views never carry findings.
    assert out[f"players/p00/views/t:{EDITION}"]["findings"] == []


def test_findings_need_ranked_players(monkeypatch):
    monkeypatch.setattr(profiles, "MIN_GROUPED_SHOTS", 10_000)
    out = build_library(twelve_player_docs(), {}, TOURNAMENTS, {})
    assert out["players/p00"]["context"]["comparedWith"] == 0
    assert out["players/p00"]["summary"] is None


def _rally(n_shots, winner, smash_at=None):
    from pro_profiles.load import Rally, Shot
    shots = tuple(Shot(rally=1, order=i + 1, time_sec=float(i), player="p" if i % 2 == 0 else "o",
                       group="Smash" if i == smash_at else "Drive", is_serve=i == 0,
                       detail="short service" if i == 0 else None)
                  for i in range(n_shots))
    return Rally(match_id="m", set_no=1, number=1, shots=shots, winner=winner, score_a=0, score_b=0)


def test_shows_band_weakness_needs_lost_rally():
    path = ("bandWin", "long")
    assert profiles.shows(path, "weakness", "p", _rally(10, "o"))
    assert not profiles.shows(path, "weakness", "p", _rally(10, "p"))
    assert not profiles.shows(path, "weakness", "p", _rally(4, "o"))  # wrong band
    assert profiles.shows(path, "strength", "p", _rally(10, "p"))


def test_shows_rate_weakness_needs_lost_rally():
    smash = ("smashWins", "winShare")
    assert profiles.shows(smash, "strength", "p", _rally(9, "p", smash_at=8))
    assert not profiles.shows(smash, "weakness", "p", _rally(9, "p", smash_at=8))
    assert profiles.shows(smash, "weakness", "p", _rally(9, "o", smash_at=8))
    serve = ("serve", "pointsWonShort")
    assert profiles.shows(serve, "strength", "p", _rally(5, "p"))
    assert not profiles.shows(serve, "weakness", "p", _rally(5, "p"))
    assert profiles.shows(serve, "weakness", "p", _rally(5, "o"))
