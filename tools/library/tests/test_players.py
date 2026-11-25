import json
from pathlib import Path

from library.players import resolve_player, slugify

PLAYERS = json.loads(
    (Path(__file__).parents[2] / "pro_profiles" / "content" / "players.json").read_text()
)


def test_alias_match():
    assert resolve_player("Viktor AXELSEN", PLAYERS) == ("viktor-axelsen", False)


def test_alias_case_insensitive():
    assert resolve_player("viktor axelsen", PLAYERS) == ("viktor-axelsen", False)


def test_unknown_name_slug():
    assert resolve_player("Some New-Player", PLAYERS) == ("some-new-player", True)


def test_slugify_strips_accents():
    assert slugify("Anders Antonsen") == "anders-antonsen"
    assert slugify("Ng Ka Long, Angus") == "ng-ka-long-angus"
