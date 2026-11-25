"""Full-match result contract (fullmatch.run.assemble_result, data-flow.md
"Full-match result") and the guarded optional post-GPU steps of
analyze_full_match. No ffmpeg or Modal: probing, cutting and segmentation are
stubbed where analyze_full_match is exercised."""
from pathlib import Path

import pytest

from fullmatch import run
from fullmatch.run import assemble_result, match_sets

INTERNAL_EVENT_KEYS = ("probs", "hitterM", "receiverM", "contactHeightM", "detailId", "serveScore")
RALLY_KEYS = {"id", "set", "startFrame", "endFrame", "startSec", "endSec", "eventIndices",
              "scoreAfter", "winner", "nearPlayer", "scoreRead"}


def test_full_match_result_shape():
    r = assemble_result(fps=25.0, events=[{"frame": 50, "type": "Serve", "isServe": True}],
                        rallies=[{"startFrame": 40, "endFrame": 120, "eventIndices": [0]}], sets=[], timings={})
    assert r["rallies"][0]["startSec"] == 1.6 and r["events"][0]["timeSec"] == 2.0
    assert r["summary"]["rallyCount"] == 1 and "tracking" not in r


def test_internal_fields_are_stripped():
    ev = {"frame": 100, "type": "Smash", "detailType": "smash", "typeConfidence": 0.9, "side": "Top",
          "sideOverridden": False, "location_px": [1, 2], "location_m": [3.0, 4.0], "confidence": 0.8,
          "confirmed": True, "source": "hitnet", "timeSec": 99.0,
          "probs": [0.1] * 25, "hitterM": [1, 2], "receiverM": [3, 4], "contactHeightM": 2.1,
          "detailId": 7, "serveScore": 3.0}
    rally = {"startFrame": 90, "endFrame": 200, "lastHitFrame": 150, "eventIndices": [0], "set": 1,
             "scoreAfter": (1, 0), "winner": "A", "scoreRead": True, "serveSide": "far", "near": "B"}
    r = assemble_result(30.0, [ev], [rally], [], {"total_s": 1.0}, total_frames=300)
    for key in ("tracking", "shuttle", "shuttle_debug", "rawEvents", "chunks", "scoreTimeline",
                "scoreEvents", "verify"):
        assert key not in r
    e = r["events"][0]
    for key in INTERNAL_EVENT_KEYS:
        assert key not in e
    assert e["timeSec"] == 3.333          # recomputed from frame (not copied), rounded to ms
    assert e["isServe"] is False and e["detailType"] == "smash" and e["side"] == "Top"
    assert set(r["rallies"][0]) == RALLY_KEYS
    assert r["rallies"][0]["scoreAfter"] == [1, 0] and r["rallies"][0]["nearPlayer"] == "B"
    assert r["rallies"][0]["id"] == 1
    assert r["summary"]["durationSec"] == 10.0 and r["summary"]["totalShots"] == 1
    assert r["summary"]["shotCounts"] == {"Smash": 1}
    assert r["timings"] == {"total_s": 1.0}
    # inputs are not mutated
    assert "probs" in ev and rally["scoreAfter"] == (1, 0)


def test_rally_and_event_keys_present_without_scoreboard():
    r = assemble_result(30.0, [{"frame": 10, "type": "Clear"}],
                        [{"startFrame": 0, "endFrame": 20, "eventIndices": [0]}], [], {})
    rally = r["rallies"][0]
    assert set(rally) == RALLY_KEYS
    assert rally["set"] is None and rally["scoreAfter"] is None and rally["winner"] is None
    assert rally["nearPlayer"] is None and rally["scoreRead"] is False
    e = r["events"][0]
    assert e["isServe"] is False and e["sideOverridden"] is False and e["detailType"] is None
    assert e["side"] is None and e["location_px"] is None and e["location_m"] is None
    assert "confidence" not in e and "typeConfidence" not in e
    assert r["sets"] == [] and r["summary"]["serveCount"] == 0
    assert r["skippedSteps"] == []


def test_sets_and_timings_are_copied():
    sets = [{"set": 1, "nearPlayer": "A", "finalScore": [21, 14]}]
    timings = {"chunk_s": [1.0, 2.0]}
    r = assemble_result(30.0, [], [], sets, timings)
    r["sets"][0]["finalScore"][0] = 0
    r["timings"]["chunk_s"].append(3.0)
    assert sets[0]["finalScore"] == [21, 14] and timings["chunk_s"] == [1.0, 2.0]


def test_event_without_product_type_is_unknown():
    r = assemble_result(30.0, [{"frame": 10, "type": None, "detailType": "short service"}], [], [], {})
    assert r["events"][0]["type"] == "Unknown" and r["events"][0]["detailType"] == "short service"
    assert r["summary"]["shotCounts"] == {"Unknown": 1}


def test_match_sets_from_scored_rallies():
    rallies = [
        {"set": 1, "scoreAfter": (1, 0), "near": "B"},
        {"set": 1, "scoreAfter": (21, 14), "near": "B"},
        {"set": 2, "scoreAfter": (0, 1), "near": None},
        {"set": 2, "scoreAfter": (21, 5), "near": "A"},
        {"set": None, "scoreAfter": None, "near": None},
    ]
    assert match_sets(rallies) == [
        {"set": 1, "nearPlayer": "B", "finalScore": [21, 14]},
        {"set": 2, "nearPlayer": "A", "finalScore": [21, 5]},
    ]
    assert match_sets([{"startFrame": 0}]) == []


# --- Ruling 20: optional post-GPU steps never discard the GPU result -----------

def _fake_cut(video, start, n, path, fps):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0\0\0\0ftyp")


def _stub_full_match(monkeypatch, tmp_path):
    """analyze_full_match without ffmpeg: 100 frames @ 25 fps, two chunks,
    one hit per chunk, segmentation returns one rally over both hits."""
    monkeypatch.setattr(run, "probe_fps", lambda video: 25.0)
    monkeypatch.setattr(run, "count_frames", lambda video: 100)
    monkeypatch.setattr(run, "cut_exact", _fake_cut)

    def fake_segment(events, tracking, shuttle, total, fps):
        return [{"startFrame": 5, "endFrame": 90, "lastHitFrame": 80,
                 "eventIndices": list(range(len(events)))}]
    monkeypatch.setattr(run, "segment_rallies", fake_segment)

    def runner(jobs):
        return [{"chunk_id": cid, "court_found": True, "geometry": {}, "events": [{"frame": 20}],
                 "tracking": [], "shuttle_debug": [], "summary": {"resolution": [512, 288]},
                 "timings": {"total_s": 1.0}} for cid, _ in jobs]
    return dict(analyze_chunks=runner, chunk=60, overlap=10, work_dir=tmp_path / "chunks",
                shot_stack=False, scoreboard=False, log=lambda *_: None)


def test_failing_scoreboard_is_skipped_not_fatal(monkeypatch, tmp_path):
    def boom(res, video, templates=None, log=print, tl=None):
        res["rallies"][0]["set"] = 99           # half-applied before failing
        res["scoreEvents"] = ["partial"]
        raise RuntimeError("template file corrupt")
    monkeypatch.setattr(run, "apply_scoreboard", boom)
    kw = _stub_full_match(monkeypatch, tmp_path)

    internal = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert len(internal["rawEvents"]) == 2 and len(internal["rallies"]) == 1
    assert internal["rallies"][0].get("set") is None           # half-applied change rolled back
    assert "scoreEvents" not in internal
    assert internal["skippedSteps"][0]["step"] == "scoreboard"
    assert "RuntimeError" in internal["skippedSteps"][0]["error"]
    assert "total_s" in internal["timings"]

    product = run.analyze_full_match(tmp_path / "match.mp4", **kw)
    assert product["summary"]["rallyCount"] == 1 and len(product["events"]) == 2
    assert product["rallies"][0]["set"] is None and product["sets"] == []
    assert product["summary"]["resolution"] == [512, 288]
    assert [x["step"] for x in product["skippedSteps"]] == ["scoreboard"]
    assert "tracking" not in product and "rawEvents" not in product


def test_failing_side_decode_is_skipped_not_fatal(monkeypatch, tmp_path):
    def boom(res, log=print):
        res["events"][0]["side"] = "Nowhere"
        raise ValueError("bad probs")
    monkeypatch.setattr(run, "apply_side_decode", boom)
    monkeypatch.setattr(run, "apply_scoreboard", lambda res, *a, **k: res)
    kw = _stub_full_match(monkeypatch, tmp_path)

    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert [e.get("side") for e in res["events"]] == [None, None]
    assert [s["step"] for s in res["skippedSteps"]] == ["side decode"]


def test_failing_shot_stack_is_skipped_not_fatal(monkeypatch, tmp_path):
    def boom(res, path, log=print):
        res["events"][0]["type"] = "Smash"
        res["shotStack"] = {"applied": 1}
        raise MemoryError("joblib load blew up")
    monkeypatch.setattr(run, "apply_shot_stack", boom)
    monkeypatch.setattr(run, "apply_scoreboard", lambda res, *a, **k: res)
    kw = _stub_full_match(monkeypatch, tmp_path)
    kw["shot_stack"] = "/nowhere/shot_stack.joblib"

    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert [e.get("type") for e in res["events"]] == [None, None]
    assert "shotStack" not in res
    assert [x["step"] for x in res["skippedSteps"]] == ["shot stack"]


def test_failing_court_check_is_recorded(monkeypatch, tmp_path):
    def boom(chunks):
        raise ZeroDivisionError("no chunks")
    monkeypatch.setattr(run, "court_outliers", boom)
    monkeypatch.setattr(run, "apply_scoreboard", lambda res, *a, **k: res)
    kw = _stub_full_match(monkeypatch, tmp_path)

    product = run.analyze_full_match(tmp_path / "match.mp4", **kw)
    assert product["court"] is None and product["summary"]["rallyCount"] == 1
    assert product["skippedSteps"] == [{"step": "court check", "error": "ZeroDivisionError: no chunks"}]


# --- final review fixes -------------------------------------------------------

def test_shot_stack_candidates_match_the_templates():
    """#1: the shot stack is found the same way as the digit templates, so a
    local run picks up ~/.cache/shuttleye-eval/shot_stack.joblib."""
    assert Path("/models/shot_stack.joblib") in run.SHOT_STACK_PATHS
    assert Path("~/.cache/shuttleye-eval/shot_stack.joblib").expanduser() in run.SHOT_STACK_PATHS
    assert Path("~/.cache/shuttleye-eval/scoreboard_digits.npz").expanduser() in run.SCOREBOARD_TEMPLATES


def test_default_shot_stack_is_the_first_existing_candidate(monkeypatch, tmp_path):
    local = tmp_path / "shot_stack.joblib"
    local.write_bytes(b"x")
    monkeypatch.setattr(run, "SHOT_STACK_PATHS", [tmp_path / "missing.joblib", local])
    seen = []

    def fake_stack(res, path, log=print):
        seen.append(path)
        res["shotStack"] = {"applied": 2, "model": str(path)}
        return res
    monkeypatch.setattr(run, "apply_shot_stack", fake_stack)
    kw = _stub_full_match(monkeypatch, tmp_path)
    kw["shot_stack"] = None
    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert seen == [local]
    assert res["models"]["shotStack"] == str(local)

    monkeypatch.setattr(run, "SHOT_STACK_PATHS", [tmp_path / "missing.joblib"])
    seen.clear()
    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert seen == [] and res["models"]["shotStack"] is None


def test_models_record_what_ran(monkeypatch, tmp_path):
    kw = _stub_full_match(monkeypatch, tmp_path)
    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert res["models"] == {"strokes": None, "shotStack": None, "scoreboardTemplates": None}
    product = run.analyze_full_match(tmp_path / "match.mp4", **kw)
    assert product["models"] == {"strokes": None, "shotStack": None, "scoreboardTemplates": None}

    # chunks report their stroke classifier; a stack and templates that ran are recorded
    runner = kw["analyze_chunks"]
    kw["analyze_chunks"] = lambda jobs: [{**r, "strokes": "BST0Adapter"} for r in runner(jobs)]

    def fake_stack(res, path, log=print):
        res["shotStack"] = {"applied": 2, "model": str(path)}
        return res
    monkeypatch.setattr(run, "apply_shot_stack", fake_stack)
    templates = tmp_path / "digits.npz"
    templates.write_bytes(b"x")
    monkeypatch.setattr(run, "load_templates", lambda path: None)
    monkeypatch.setattr(run, "timeline", lambda *a, **k: [])
    kw.update(shot_stack=str(tmp_path / "s.joblib"), scoreboard=str(templates))
    product = run.analyze_full_match(tmp_path / "match.mp4", **kw)
    assert product["models"] == {"strokes": "BST0Adapter", "shotStack": str(tmp_path / "s.joblib"),
                                 "scoreboardTemplates": str(templates)}


def test_missing_shot_stack_model_is_not_recorded(monkeypatch, tmp_path):
    kw = _stub_full_match(monkeypatch, tmp_path)
    kw["shot_stack"] = str(tmp_path / "missing.joblib")     # real apply_shot_stack: no model, keeps types
    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert res["models"]["shotStack"] is None and "skippedSteps" not in res


def test_failed_scoreboard_does_not_record_its_templates(monkeypatch, tmp_path):
    templates = tmp_path / "digits.npz"
    templates.write_bytes(b"x")
    monkeypatch.setattr(run, "load_templates", lambda path: None)
    monkeypatch.setattr(run, "timeline", lambda *a, **k: [{"frame": 0}])
    monkeypatch.setattr(run, "score_events", lambda tl: [{"frame": 0}])

    def boom(*a, **k):
        raise RuntimeError("align bug")
    monkeypatch.setattr(run, "align_scores", boom)
    kw = _stub_full_match(monkeypatch, tmp_path)
    kw["scoreboard"] = str(templates)
    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert [s["step"] for s in res["skippedSteps"]] == ["scoreboard"]
    assert res["models"]["scoreboardTemplates"] is None


def test_strokes_lists_every_classifier_the_chunks_used(monkeypatch, tmp_path):
    kw = _stub_full_match(monkeypatch, tmp_path)
    runner = kw["analyze_chunks"]
    kw["analyze_chunks"] = lambda jobs: [{**r, "strokes": ["BST0Adapter", "LSTM"][r["chunk_id"] % 2]}
                                         for r in runner(jobs)]
    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert res["models"]["strokes"] == "BST0Adapter, LSTM"


@pytest.mark.parametrize("fps,warned", [(25.0, True), (50.0, True), (30.0, False), (29.995, False)])
def test_non_30fps_source_is_warned(monkeypatch, tmp_path, fps, warned):
    """#4 (Ruling 26): model windows are 30-fps frame counts; other rates are
    flagged, not resampled (#76)."""
    kw = _stub_full_match(monkeypatch, tmp_path)
    monkeypatch.setattr(run, "probe_fps", lambda video: fps)
    logs = []
    kw["log"] = logs.append
    internal = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    product = run.analyze_full_match(tmp_path / "match.mp4", **kw)
    if warned:
        assert len(internal["warnings"]) == 1 and f"source fps {fps:.3f}" in internal["warnings"][0]
        assert "30 fps" in internal["warnings"][0] and "unmeasured" in internal["warnings"][0]
        assert any("WARNING" in m and "fps" in m for m in logs)
    else:
        assert internal["warnings"] == []
    assert product["warnings"] == internal["warnings"]


def test_assemble_result_defaults_models_and_warnings():
    r = assemble_result(30.0, [], [], [], {})
    assert r["models"] == {"strokes": None, "shotStack": None, "scoreboardTemplates": None}
    assert r["warnings"] == []


def test_failed_chunk_is_skipped_not_fatal(monkeypatch, tmp_path):
    """#10: the runner may return an exception in a chunk's place (Modal
    starmap(return_exceptions=True)); that chunk counts as no court and the
    rest of the match still merges."""
    kw = _stub_full_match(monkeypatch, tmp_path)
    runner = kw["analyze_chunks"]
    kw["analyze_chunks"] = lambda jobs: [RuntimeError("container died") if r["chunk_id"] == 1 else r
                                         for r in runner(jobs)]
    res = run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert [c["court_found"] for c in res["chunks"]] == [True, False]
    assert [e["frame"] for e in res["rawEvents"]] == [20]
    assert res["skippedSteps"] == [{"step": "chunk 1", "error": "RuntimeError: container died"}]
    product = run.analyze_full_match(tmp_path / "match.mp4", **kw)
    assert product["skippedSteps"] == [{"step": "chunk 1", "error": "RuntimeError: container died"}]
    assert product["summary"]["rallyCount"] == 1


def test_temp_chunks_dir_is_removed_when_this_run_made_it(monkeypatch, tmp_path):
    """#9: without work_dir the temp run dir and the `chunks` dir it made go."""
    kw = _stub_full_match(monkeypatch, tmp_path)
    kw["work_dir"] = None
    run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert not (tmp_path / "chunks").exists()

    other = tmp_path / "chunks" / "keep.txt"          # someone else's chunks dir is left alone
    other.parent.mkdir()
    other.write_text("x")
    run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert sorted(p.name for p in (tmp_path / "chunks").iterdir()) == ["keep.txt"]

    other.unlink()                                    # pre-existing and empty: also left alone
    run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
    assert (tmp_path / "chunks").is_dir()


def test_every_chunk_failing_is_an_error(monkeypatch, tmp_path):
    kw = _stub_full_match(monkeypatch, tmp_path)
    kw["analyze_chunks"] = lambda jobs: [OSError("no GPU") for _ in jobs]
    with pytest.raises(RuntimeError, match="every chunk failed; first: OSError: no GPU"):
        run.analyze_full_match(tmp_path / "match.mp4", internal=True, **kw)
