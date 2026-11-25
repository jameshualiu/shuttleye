import pytest

from library import publish as pub
from library.publish import PublishError, publish, recompute, unpublish
from library.store import MemoryStore
from library.tests.docs import EDITION, TOURNAMENTS, late_rallies, make_doc


@pytest.fixture(autouse=True)
def content(monkeypatch):
    monkeypatch.setattr(pub, "load_context", lambda: {
        "players": {}, "tournaments": TOURNAMENTS, "photos": {}})


def seed(store, *docs):
    for d in docs:
        store.set(f"matches/{d['id']}", {**d, "status": "unpublished", "attributed": True, "insights": None})


def make_store(*docs):
    store = MemoryStore()
    seed(store, *docs)
    return store


def doc(mid, a, b, date="2022-08-01"):
    return make_doc(mid, a, b, late_rallies(30, 6), date=date)


def test_publish_unattributed_refused():
    store = make_store(doc("m1", "aa", "bb"))
    store.set("matches/m1", {**store.get("matches/m1"), "attributed": False})
    with pytest.raises(PublishError):
        publish(store, "m1")
    with pytest.raises(PublishError):
        publish(store, "nope")
    assert store.get("matches/m1")["status"] == "unpublished"
    assert store.get("library/index") is None


def test_publish_writes_profiles_and_insights():
    store = make_store(doc("m1", "aa", "bb"), doc("m2", "aa", "cc", date="2022-08-02"))
    changed = publish(store, "m1")
    assert "matches/m1" in changed and "players/aa" in changed and "library/index" in changed
    m = store.get("matches/m1")
    assert m["status"] == "published"
    assert set(m["insights"]) == {"A", "B"}
    assert m["insights"]["A"]["insights"]["phaseMix"]["late"]["Smash"] == 20.0
    assert store.get("players/aa/views/all")["kind"] == "all"
    assert store.get(f"tournaments/{EDITION}")["id"] == EDITION
    assert [p["id"] for p in store.get("library/index")["players"]] == ["aa", "bb"]
    assert store.get("matches/m2")["insights"] is None
    assert store.get("players/cc") is None

    publish(store, "m2")
    # aa's other published match (m1) is the "usual" for m2, so aa has history
    assert store.get("matches/m2")["status"] == "published"
    assert {p["id"] for p in store.get("library/index")["players"]} == {"aa", "bb", "cc"}


def test_unpublish_removes_from_profiles():
    store = make_store(doc("m1", "aa", "bb"), doc("m2", "aa", "cc", date="2022-08-02"))
    publish(store, "m1")
    publish(store, "m2")
    changed = unpublish(store, "m2")
    assert "players/cc" in changed and "players/cc/views/all" in changed
    assert store.get("players/cc") is None
    assert not [p for p in store.paths() if p.startswith("players/cc")]
    assert [p["id"] for p in store.get("library/index")["players"]] == ["aa", "bb"]
    assert store.get("matches/m2")["status"] == "unpublished"
    assert store.get("matches/m2")["insights"] is None
    assert store.get("players/aa/views/m:m2") is None

    unpublish(store, "m1")
    assert not [p for p in store.paths() if p.split("/")[0] in ("players", "tournaments")]
    assert store.get("library/index")["players"] == []


def test_recompute_idempotent():
    store = make_store(doc("m1", "aa", "bb"))
    publish(store, "m1")
    assert recompute(store) == []
    assert recompute(store) == []


def test_memory_store_rejects_nested_arrays():
    store = MemoryStore()
    with pytest.raises(ValueError):
        store.set("x/y", {"games": [[21, 15]]})
    store.set("x/y", {"games": [{"a": 21, "b": 15}], "scoreBefore": [0, 0]})
