"""Write the test fixture as one unpublished match, for working on the match page.

    python -m library.seed_dev [match_id]      # from tools/

Needs GOOGLE_APPLICATION_CREDENTIALS (a service-account key outside the repo). The
match is only readable by an admin (`python -m library.set_admin <uid>`), and never
appears in the library until published. Delete it from the Firestore console when done.
"""
import json
import sys
from pathlib import Path

from .match_doc import match_doc
from .store import FirestoreStore

FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "product_result.json"


def seed(store, match_id: str = "dev-fixture-match") -> dict:
    result = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc = match_doc(result, {
        "id": match_id, "youtubeId": "M7lc1UVf-VE", "editionId": "test-open-2022",
        "round": "Final", "date": "2022-08-01",
        "playerA": {"id": "viktor-axelsen", "name": "Viktor AXELSEN", "event": "MS"},
        "playerB": {"id": "some-opponent", "name": "Some OPPONENT", "event": "MS"},
        "nearFirst": "B",
    })
    doc["status"] = "unpublished"
    store.set(f"matches/{match_id}", doc)
    return doc


if __name__ == "__main__":
    mid = sys.argv[1] if len(sys.argv) > 1 else "dev-fixture-match"
    seed(FirestoreStore(), mid)
    print(f"wrote matches/{mid} (unpublished): open /matches/{mid} signed in as an admin")
