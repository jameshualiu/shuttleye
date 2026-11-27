import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
WORKER = HERE.parents[2] / "worker"
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))


@pytest.fixture
def product_result():
    return json.loads((HERE / "fixtures" / "product_result.json").read_text())


@pytest.fixture
def meta():
    return {
        "id": "test-match", "youtubeId": "abc123", "editionId": "test-open-2022",
        "round": "Final", "date": "2022-08-01",
        "playerA": {"id": "viktor-axelsen", "name": "Viktor AXELSEN"},
        "playerB": {"id": "some-opponent", "name": "Some Opponent"}, "nearFirst": "B",
    }
