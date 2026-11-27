import copy
import json

import pytest

from library import ingest as ing
from library import publish as pub
from library import runners
from library.ingest import IngestError, build_meta, ingest, main, run_batch
from library.runners import Analyzer, accuracy_from_report, make_analyzer
from library.store import MemoryStore
from library.tests.docs import TOURNAMENTS

PLAYERS = {"viktor-axelsen": {"name": "Viktor Axelsen", "event": "MS", "aliases": ["Viktor AXELSEN"]},
           "jonatan-christie": {"name": "Jonatan Christie", "event": "MS", "aliases": []}}
URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture(autouse=True)
def content(monkeypatch):
    monkeypatch.setattr(pub, "load_context", lambda: {
        "players": PLAYERS, "tournaments": TOURNAMENTS, "photos": {}})


@pytest.fixture
def attributed(product_result):
    res = copy.deepcopy(product_result)
    for r in res["rallies"]:
        r["nearPlayer"] = r.get("nearPlayer") or "B"
    return res


class FakeAnalyzer(Analyzer):
    name = "fake"

    def __init__(self, product, fail=False):
        self._product, self.fail, self.videos = product, fail, []

    def analyse(self, video):
        self.videos.append(video)
        assert video.exists()
        if self.fail:
            raise RuntimeError("boom")
        return {"internal": True}

    def segment(self, res):
        res["segmented"] = True

    def scoreboard(self, res, video):
        res["scored"] = True

    def product(self, res):
        assert res == {"internal": True, "segmented": True, "scored": True}
        return copy.deepcopy(self._product)


class FakeDownloader:
    def __init__(self):
        self.paths = []

    def __call__(self, url, out_dir):
        p = out_dir / "match.mp4"
        p.write_bytes(b"not really a video")
        self.paths.append(p)
        return p


def meta():
    m, _ = build_meta(URL, ["Viktor AXELSEN", "Jonatan Christie"], "loser", "test-open-2022",
                      "Final", "2022-08-01", None, PLAYERS, TOURNAMENTS)
    return m


def test_build_meta_resolves_players():
    m, created = build_meta(URL, ["Viktor AXELSEN", "Jonatan Christie"], "loser", "test-open-2022",
                            "Final", "2022-08-01", None, PLAYERS, TOURNAMENTS)
    assert created == []
    assert m["id"] == "test-open-2022-viktor-axelsen-jonatan-christie"
    assert m["youtubeId"] == "abcdefghijk"
    assert m["nearFirst"] == "B"
    assert m["playerA"] == {"id": "viktor-axelsen", "name": "Viktor Axelsen", "event": "MS"}


def test_build_meta_new_player_needs_event():
    with pytest.raises(IngestError, match="--event"):
        build_meta(URL, ["Viktor Axelsen", "New Guy"], "winner", "test-open-2022", "QF", "2022-01-01", None, PLAYERS, TOURNAMENTS)
    m, created = build_meta("https://youtu.be/abcdefghijk", ["Viktor Axelsen", "New Guy"], "winner",
                            "test-open-2022", "QF", "2022-01-01", "MS", PLAYERS, TOURNAMENTS)
    assert created == ["new-guy"]
    assert m["playerB"] == {"id": "new-guy", "name": "New Guy", "event": "MS"}
    assert m["nearFirst"] == "A"


def test_ingest_stores_unpublished(attributed):
    store, dl = MemoryStore(), FakeDownloader()
    out = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl)
    mid = "test-open-2022-viktor-axelsen-jonatan-christie"
    assert out["matchId"] == mid and out["status"] == "stored"
    doc = store.get(f"matches/{mid}")
    assert doc["status"] == "unpublished" and doc["insights"] is None
    assert doc["players"]["B"]["id"] == "jonatan-christie"
    assert doc["accuracy"] is None
    assert not dl.paths[0].exists()          # downloaded video deleted
    assert not dl.paths[0].parent.exists()   # and its temp dir
    assert store.paths() == [f"matches/{mid}"]


def test_ingest_skip_existing(attributed):
    store, dl = MemoryStore(), FakeDownloader()
    ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl)
    fake = FakeAnalyzer(attributed)
    out = ingest(URL, meta(), store, runner=fake, downloader=dl)
    assert out["status"] == "skipped"
    assert fake.videos == [] and len(dl.paths) == 1   # nothing downloaded or analysed


def test_force_keeps_published_and_recomputes(attributed, capsys):
    store, dl = MemoryStore(), FakeDownloader()
    mid = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl)["matchId"]
    pub.publish(store, mid)
    before = store.get(f"matches/{mid}")
    assert before["insights"] is not None
    capsys.readouterr()

    changed_result = copy.deepcopy(attributed)
    changed_result["events"][0]["detailType"] = "smash"
    out = ingest(URL, meta(), store, runner=FakeAnalyzer(changed_result), downloader=dl, force=True)
    assert out["status"] == "stored"
    doc = store.get(f"matches/{mid}")
    assert doc["status"] == "published"
    assert doc["insights"] is not None                    # recompute ran
    assert doc["rallies"][0]["shots"][0]["d"] == "smash"
    assert out["changed"] and f"matches/{mid}" in out["changed"]
    printed = capsys.readouterr().out
    assert f"matches/{mid}" in printed


def test_force_unpublished_stays_unpublished_without_recompute(attributed, monkeypatch):
    store, dl = MemoryStore(), FakeDownloader()
    ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl)
    monkeypatch.setattr(ing, "recompute_after_write", lambda *a, **k: pytest.fail("recompute must not run"))
    out = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl, force=True)
    assert out["status"] == "stored" and out["changed"] == []
    assert store.get(f"matches/{out['matchId']}")["status"] == "unpublished"


def test_force_published_but_now_unattributed_is_unpublished(attributed, product_result):
    store, dl = MemoryStore(), FakeDownloader()
    mid = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl)["matchId"]
    pub.publish(store, mid)
    out = ingest(URL, meta(), store, runner=FakeAnalyzer(product_result), downloader=dl, force=True)
    doc = store.get(f"matches/{mid}")
    assert doc["status"] == "unpublished" and doc["insights"] is None
    assert any("not attributed" in w for w in out["warnings"])
    assert store.get("library/index")["matches"] == []


def test_video_deleted_on_failure(attributed):
    store, dl = MemoryStore(), FakeDownloader()
    with pytest.raises(RuntimeError, match="boom"):
        ingest(URL, meta(), store, runner=FakeAnalyzer(attributed, fail=True), downloader=dl)
    assert not dl.paths[0].exists()
    assert store.paths() == []


def test_keep_video(attributed):
    dl = FakeDownloader()
    ingest(URL, meta(), MemoryStore(), runner=FakeAnalyzer(attributed), downloader=dl, keep_video=True)
    assert dl.paths[0].exists()


def test_user_video_never_deleted(attributed, tmp_path):
    video = tmp_path / "mine.mp4"
    video.write_bytes(b"x")
    fake = FakeAnalyzer(attributed, fail=True)
    with pytest.raises(RuntimeError):
        ingest(str(video), meta(), MemoryStore(), runner=fake,
               downloader=lambda *a: pytest.fail("must not download"))
    assert fake.videos == [video] and video.exists()


def test_timings_recorded(attributed, monkeypatch):
    seen = {}

    def fake_accuracy(res, match):
        seen["args"] = (res, match)
        return {"hitF1": 90.0, "side": 99.0, "type6": 88.0, "ten": 70.0}

    monkeypatch.setattr(runners, "shuttleset_accuracy", fake_accuracy)
    store = MemoryStore()
    out = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=FakeDownloader(),
                 shuttleset="Some_Match")
    steps = ["download_s", "analyse_s", "segment_s", "scoreboard_s", "accuracy_s", "store_s"]
    assert list(out["timings"]) == steps
    assert all(isinstance(v, float) and v >= 0 for v in out["timings"].values())
    doc = store.get(f"matches/{out['matchId']}")
    assert list(doc["analyzer"]["timings"]["ingest"]) == steps[:-1]
    # accuracy is scored on the internal (segmented, scoreboard-read) result
    assert seen["args"] == ({"internal": True, "segmented": True, "scored": True}, "Some_Match")
    assert doc["accuracy"] == out["accuracy"] == {"hitF1": 90.0, "side": 99.0, "type6": 88.0, "ten": 70.0}


def test_accuracy_from_report():
    overall = {"hits": {"f1": 0.9012}, "side": {"accuracy": 1.0},
               "type": {"accuracy": 0.8771}, "ten": {"accuracy": None}}
    report = {"hits_after": {"excl_serves": overall, "incl_serves": {}}}
    assert accuracy_from_report(report) == {"hitF1": 90.1, "side": 100.0, "type6": 87.7, "ten": None}


def batch_entries():
    base = {"players": ["Viktor Axelsen", "Jonatan Christie"], "nearFirst": "loser",
            "tournament": "test-open-2022", "round": "Final", "date": "2022-08-01"}
    return [
        {"url": URL, "meta": {**base, "round": "QF"}, "runner": "fail"},
        {"url": URL, "meta": {**base, "players": ["Viktor Axelsen", "Nobody New"]}},   # no event
        {"url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "meta": base, "runner": "ok"},
    ]


def test_batch_continues_after_failure(attributed, capsys):
    store = MemoryStore()

    def analyzer_for(spec):
        return FakeAnalyzer(attributed, fail=spec == "fail")

    results = run_batch(batch_entries(), store, PLAYERS, TOURNAMENTS, downloader=FakeDownloader(),
                        analyzer_for=analyzer_for)
    assert [r["status"] for r in results] == ["failed", "failed", "stored"]
    assert "boom" in results[0]["error"] and "--event" in results[1]["error"]
    assert store.paths() == ["matches/test-open-2022-viktor-axelsen-jonatan-christie"]
    # resumable: a second run skips the stored match
    again = run_batch(batch_entries()[2:], store, PLAYERS, TOURNAMENTS, downloader=FakeDownloader(),
                      analyzer_for=analyzer_for)
    assert again[0]["status"] == "skipped"
    assert "failed" in capsys.readouterr().out


def test_batch_force_reruns_stored(attributed):
    store = MemoryStore()

    def analyzer_for(spec):
        return FakeAnalyzer(attributed)

    entries = batch_entries()[2:]
    run_batch(entries, store, PLAYERS, TOURNAMENTS, downloader=FakeDownloader(), analyzer_for=analyzer_for)
    again = run_batch(entries, store, PLAYERS, TOURNAMENTS, downloader=FakeDownloader(),
                      analyzer_for=analyzer_for, force=True)
    assert again[0]["status"] != "skipped"


def test_batch_dry_run_touches_nothing(tmp_path, capsys):
    f = tmp_path / "b.json"
    f.write_text(json.dumps(batch_entries()))
    code = main(["--batch", str(f), "--dry-run"], players=PLAYERS, tournaments=TOURNAMENTS,
                store_factory=lambda: pytest.fail("no store on a dry run"),
                downloader=lambda *a: pytest.fail("no download on a dry run"))
    out = capsys.readouterr().out
    assert "test-open-2022-viktor-axelsen-jonatan-christie" in out
    assert "--event" in out          # the bad entry is reported, not fatal
    assert code == 1


def test_cli_single_new_player_requires_event(capsys):
    with pytest.raises(SystemExit):
        main([URL, "--players", "Viktor Axelsen", "New Guy", "--near-first", "winner",
              "--tournament", "test-open-2022", "--round", "QF", "--date", "2022-01-01", "--dry-run"],
             players=PLAYERS, tournaments=TOURNAMENTS, store_factory=lambda: pytest.fail("no store"))
    assert "--event" in capsys.readouterr().err


def test_cli_single_dry_run_prints_created(capsys):
    code = main([URL, "--players", "Viktor Axelsen", "New Guy", "--near-first", "winner",
                 "--tournament", "test-open-2022", "--round", "QF", "--date", "2022-01-01", "--event", "MS",
                 "--runner", "merged:~/x.json", "--dry-run"],
                players=PLAYERS, tournaments=TOURNAMENTS, store_factory=lambda: pytest.fail("no store"))
    out = capsys.readouterr().out
    assert code == 0
    assert "new player: new-guy" in out and "merged:~/x.json" in out and "test-open-2022-viktor-axelsen-new-guy" in out
    assert "merged result not found" in out


def test_cli_single_stores(attributed, monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(ing, "make_analyzer", lambda spec: FakeAnalyzer(attributed))
    code = main([URL, "--players", "Viktor Axelsen", "Jonatan Christie", "--near-first", "loser",
                 "--tournament", "test-open-2022", "--round", "Final", "--date", "2022-08-01"],
                players=PLAYERS, tournaments=TOURNAMENTS, store_factory=lambda: store, downloader=FakeDownloader())
    assert code == 0
    assert store.get("matches/test-open-2022-viktor-axelsen-jonatan-christie")["status"] == "unpublished"


def test_make_analyzer_specs(tmp_path):
    assert make_analyzer("modal").name == "modal"
    assert make_analyzer("local").name == "local"
    m = make_analyzer("merged:~/some/fullmatch_1.json")
    assert m.name == "merged" and str(m.path).startswith(str(tmp_path.home()))
    with pytest.raises(ValueError):
        make_analyzer("gpu-cluster")


def test_force_without_shuttleset_keeps_accuracy(attributed, monkeypatch):
    monkeypatch.setattr(runners, "shuttleset_accuracy", lambda res, match: {"hitF1": 1.0})
    store, dl = MemoryStore(), FakeDownloader()
    mid = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl,
                 shuttleset="M")["matchId"]
    assert store.get(f"matches/{mid}")["accuracy"] == {"hitF1": 1.0}
    out = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl, force=True)
    assert store.get(f"matches/{mid}")["accuracy"] == {"hitF1": 1.0}
    assert out["accuracy"] == {"hitF1": 1.0}


def test_missing_video_is_an_error(attributed, tmp_path):
    missing = str(tmp_path / "nope.mp4")
    with pytest.raises(IngestError, match="nope.mp4"):
        ingest(URL, meta(), MemoryStore(), runner=FakeAnalyzer(attributed), video=missing,
               downloader=lambda *a: pytest.fail("must not download"))
    with pytest.raises(SystemExit):
        main([URL, "--players", "Viktor Axelsen", "Jonatan Christie", "--near-first", "loser",
              "--tournament", "test-open-2022", "--round", "QF", "--date", "2022-01-01", "--video", missing, "--dry-run"],
             players=PLAYERS, tournaments=TOURNAMENTS, store_factory=lambda: pytest.fail("no store"))
    entry = {**batch_entries()[2], "runner": "modal", "video": missing}
    results = run_batch([entry], MemoryStore(), PLAYERS, TOURNAMENTS, dry_run=True)
    assert results[0]["status"] == "failed" and "nope.mp4" in results[0]["error"]


def test_batch_dry_run_validates_runner():
    entry = {**batch_entries()[2], "runner": "gpu-cluster"}
    results = run_batch([entry], None, PLAYERS, TOURNAMENTS, dry_run=True)
    assert results[0]["status"] == "failed" and "unknown runner" in results[0]["error"]


def test_unknown_edition_rejected(capsys):
    with pytest.raises(IngestError, match="tournaments.json"):
        build_meta(URL, ["Viktor Axelsen", "Jonatan Christie"], "loser", "no-such-open-2099", "QF",
                   "2022-01-01", None, PLAYERS, TOURNAMENTS)
    # single, also on --dry-run
    with pytest.raises(SystemExit):
        main([URL, "--players", "Viktor Axelsen", "Jonatan Christie", "--near-first", "loser",
              "--tournament", "no-such-open-2099", "--round", "QF", "--date", "2022-01-01", "--dry-run"],
             players=PLAYERS, tournaments=TOURNAMENTS, store_factory=lambda: pytest.fail("no store"))
    assert "tournaments.json" in capsys.readouterr().err
    # batch and batch --dry-run: the entry fails, nothing is stored
    entry = {**batch_entries()[2], "meta": {**batch_entries()[2]["meta"], "tournament": "no-such-open-2099"}}
    for dry in (True, False):
        store = MemoryStore()
        results = run_batch([entry], store, PLAYERS, TOURNAMENTS, dry_run=dry,
                            downloader=lambda *a: pytest.fail("no download"),
                            analyzer_for=lambda spec: pytest.fail("no analyzer"))
        assert results[0]["status"] == "failed" and "tournaments.json" in results[0]["error"]
        assert store.list_ids("matches") == []


def test_force_recompute_failure_says_how_to_recover(attributed, monkeypatch, capsys):
    store, dl = MemoryStore(), FakeDownloader()
    mid = ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl)["matchId"]
    pub.publish(store, mid)

    def boom(*a, **k):
        raise RuntimeError("firestore down")
    monkeypatch.setattr(pub, "build_library", boom)
    with pytest.raises(RuntimeError, match="firestore down"):
        ingest(URL, meta(), store, runner=FakeAnalyzer(attributed), downloader=dl, force=True)
    assert "python -m library.publish recompute" in capsys.readouterr().err
