import json
from pathlib import Path

import pytest

from pro_profiles.build import build
from pro_profiles.photos import (
    add_approval,
    credit,
    licence_allowed,
    parse_candidate,
    parse_focus,
    render_contact_sheet,
    commons_filename,
    is_jpeg,
    validate_approval,
)

from .test_build import SOURCES


@pytest.mark.parametrize("name", ["CC BY 4.0", "CC BY-SA 2.0", "CC BY 2.5", "CC BY-SA 4.0", "CC0",
                                  "CC0 1.0", "Public domain"])
def test_licence_allowed(name):
    assert licence_allowed(name)


@pytest.mark.parametrize("name", ["CC BY-NC 2.0", "CC BY-ND 2.0", "CC BY-NC-SA 3.0", "Fair use",
                                  "All rights reserved", "", "CC BY NC 2.0", "CC BY-ND",
                                  "CC BY 2.0 NC", "CC BY-SA 4.0 (ND)", "cc by nc-sa 3.0"])
def test_licence_rejected(name):
    assert not licence_allowed(name)


def test_credit_strips_html():
    html = '<a href="//commons.wikimedia.org/wiki/User:F">Fauziananta</a> &amp; <b>co</b>\n'
    assert credit(html, "CC BY 4.0") == "Photo: Fauziananta & co, CC BY 4.0"


def test_parse_candidate_keeps_allowed_only():
    page = {"title": "File:A.jpg", "imageinfo": [{
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:A.jpg",
        "thumburl": "https://upload/thumb.jpg",
        "extmetadata": {"LicenseShortName": {"value": "CC BY 4.0"},
                        "Artist": {"value": "<a>Ann</a>"}}}]}
    c = parse_candidate(page)
    assert c == {"sourceUrl": "https://commons.wikimedia.org/wiki/File:A.jpg",
                 "thumbUrl": "https://upload/thumb.jpg", "author": "Ann", "licence": "CC BY 4.0"}
    page["imageinfo"][0]["extmetadata"]["LicenseShortName"]["value"] = "CC BY-NC 2.0"
    assert parse_candidate(page) is None
    assert parse_candidate({}) is None


def test_parse_focus():
    assert parse_focus("50,30") == (50, 30)
    for bad in ("50", "a,b", "150,30", "50,-1"):
        with pytest.raises(ValueError):
            parse_focus(bad)


def test_contact_sheet_lists_candidates_and_commands():
    html = render_contact_sheet({
        "alpha-one": {"name": "Alpha One", "sourceUrl": "https://c/File:A.jpg",
                      "thumbUrl": "https://u/t.jpg", "author": "Ann <x>", "licence": "CC BY 4.0"},
    })
    assert "Alpha One" in html and "https://u/t.jpg" in html and "CC BY 4.0" in html
    assert "approve alpha-one --focus 50,30" in html
    assert "Ann <x>" not in html  # escaped


def test_build_uses_approved_photo(tmp_path, mini_source, mini_players, mini_tournaments):
    photos = add_approval({}, "alpha-one", {
        "sourceUrl": "https://c/File:A.jpg", "author": "Ann", "licence": "CC BY 4.0"}, (40, 25))
    assert photos["alpha-one"]["focusX"] == 40
    build(mini_source, tmp_path, players=mini_players, tournaments=mini_tournaments,
          sources=SOURCES, photos=photos)
    photo = json.loads((Path(tmp_path) / "players" / "alpha-one.json").read_text())["photo"]
    assert photo["src"] == "/pro-data/photos/alpha-one.jpg"
    assert photo["credit"] == "Photo: Ann, CC BY 4.0"
    assert (photo["focusX"], photo["focusY"]) == (40, 25)


def test_validate_approval():
    players = {"a": {}, "b": {}}
    good = {"licence": "CC BY 4.0"}
    assert validate_approval("a", players, {"a": good}) is good
    with pytest.raises(ValueError, match="unknown player"):
        validate_approval("z", players, {"z": good})
    with pytest.raises(ValueError, match="no candidate"):
        validate_approval("b", players, {"a": good})
    with pytest.raises(ValueError, match="licence"):
        validate_approval("a", players, {"a": {"licence": "CC BY-NC 2.0"}})


def test_commons_filename_and_jpeg():
    assert commons_filename("https://commons.wikimedia.org/wiki/File:A%20b.jpg") == "A b.jpg"
    with pytest.raises(ValueError):
        commons_filename("https://example.com/x")
    assert is_jpeg(b"\xff\xd8\xff") and not is_jpeg(b"\x89PNG")
