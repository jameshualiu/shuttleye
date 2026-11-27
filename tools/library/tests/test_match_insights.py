import copy

from library.insights import player_insights
from library.match_insights import match_insights
from library.tests.docs import TOURNAMENTS, late_rallies, make_doc
from library.to_model import to_match


def doc():
    # A: 60 late shots, 12 of them smashes -> 20.0%.
    return make_doc("m1", "aa", "bb", late_rallies(30, 6))


def usual_with_late_smash(value: float) -> dict:
    d = doc()
    ins = copy.deepcopy(player_insights([to_match(d)], "aa"))
    ins["phaseMix"]["late"]["Smash"] = value
    return {"aa": ins}


def test_match_insights_vs_usual():
    out = match_insights(doc(), usual_with_late_smash(14.0), players={}, tournaments=TOURNAMENTS)
    assert set(out) == {"A", "B"}
    assert out["A"]["insights"]["phaseMix"]["late"]["Smash"] == 20.0
    [f] = out["A"]["findings"]
    assert f["claim"] == ("Smashed on 20.0% of his shots after the 12th shot of a rally, "
                          "vs 14.0% in his other matches.")
    assert f["figure"] == "20.0%" and f["kind"] == "style" and f["tip"] is None
    assert set(f) == {"key", "kind", "claim", "figure", "comparison", "tip", "clips"}
    assert f["clips"] and all(c["youtubeId"] == "yt-m1" for c in f["clips"])
    assert out["B"]["findings"] == []  # no usual for bb

    out = match_insights(doc(), usual_with_late_smash(16.0), players={}, tournaments=TOURNAMENTS)
    assert out["A"]["findings"] == []


def test_match_insights_no_history():
    out = match_insights(doc(), {}, players={}, tournaments=TOURNAMENTS)
    assert out["A"]["findings"] == [] and out["B"]["findings"] == []
    assert out["B"]["insights"]["phaseMix"]["late"]["shots"] == 60


def test_match_insights_caps_at_four():
    usual = usual_with_late_smash(0.0)
    late = usual["aa"]["phaseMix"]["late"]
    late["Clear"], late["Drive"] = 30.0, 50.0  # Clear 80 -> gap 50; Drive is not a finding scalar
    for g in ("Net", "Lift", "Drop"):
        late[g] = 20.0  # actual 0 -> gap 20, like Smash (20 vs 0)
    out = match_insights(doc(), usual, players={}, tournaments=TOURNAMENTS)
    keys = [f["key"] for f in out["A"]["findings"]]
    assert len(keys) == 4
    assert keys[0] == "phaseMix.late.Clear.more"


def test_match_insights_small_samples_give_no_finding():
    # 30 rallies: A has only 30 start-phase shots (< MIN_SHARE_SHOTS), so start shares are null.
    usual = usual_with_late_smash(20.0)  # late phase level with the match
    assert usual["aa"]["phaseMix"]["start"]["Net"] is None
    usual["aa"]["phaseMix"]["start"]["Net"] = 50.0
    out = match_insights(doc(), usual, players={}, tournaments=TOURNAMENTS)
    assert out["A"]["findings"] == []

    # 2 long rallies, both won: band win rate null (< MIN_BAND_RALLIES) despite 100% vs 60%.
    small = make_doc("m2", "aa", "bb", late_rallies(2, 0))
    ins = copy.deepcopy(player_insights([to_match(small)], "aa"))
    long_band = next(b for b in ins["bands"] if b["band"] == "long")
    assert long_band["rallies"] == 2 and long_band["winRate"] is None
    long_band["winRate"] = 60.0
    out = match_insights(small, {"aa": ins}, players={}, tournaments=TOURNAMENTS)
    assert out["A"]["findings"] == []
