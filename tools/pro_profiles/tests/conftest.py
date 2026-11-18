import copy
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

MINI_PLAYERS = {
    "alpha-one": {"name": "Alpha One", "event": "MS", "aliases": ["Alpha ONE"]},
    "beta-two": {"name": "Beta Two", "event": "MS", "aliases": ["Beta TWO"]},
}
MINI_TOURNAMENTS = {
    "test-open-2022": {
        "name": "Test Open",
        "season": 2022,
        "aliases": [["Test Open 2022", "2022"]],
    }
}


@pytest.fixture
def mini_source() -> Path:
    return FIXTURES / "mini"


@pytest.fixture
def mini_players() -> dict:
    return copy.deepcopy(MINI_PLAYERS)


@pytest.fixture
def mini_tournaments() -> dict:
    return copy.deepcopy(MINI_TOURNAMENTS)
