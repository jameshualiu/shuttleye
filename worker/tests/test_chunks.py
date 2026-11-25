"""Chunked full-match processing: planning, merging, frame-exact cuts.

Pure tests run anywhere; the cut/verify and analyze_full_match tests need
ffmpeg/ffprobe on PATH and are skipped without them.
"""
import shutil

import pytest

from fullmatch.chunks import cut_exact, frame_to_sec, merge_chunks, plan_chunks, verify_cut


def _result(events=(), n=0, court=True):
    return {
        "events": [{"frame": f} for f in events],
        "tracking": [{"frame": i, "players": [{"id": i}]} for i in range(n)],
        "shuttle_debug": [{"frame": i, "pos": [i, i], "confidence": 1.0} for i in range(n)],
        "geometry": {"court_keypoints_6": []} if court else None,
        "court_found": court,
    }


# --- brief tests -------------------------------------------------------------

def test_plan_chunks_covers_everything_with_overlap():
    p = plan_chunks(4000, chunk=1800, overlap=60)
    assert p[0] == (0, 1799) and p[-1][1] == 3999
    assert all(b[0] == a[1] - 60 + 1 for a, b in zip(p, p[1:]))


def test_merge_keeps_overlap_hit_once():
    plan = [(0, 1799), (1740, 3539)]
    r0 = {"events": [{"frame": 1770}], "tracking": [], "shuttle_debug": [], "geometry": {}, "court_found": True}
    r1 = {"events": [{"frame": 30}], "tracking": [], "shuttle_debug": [], "geometry": {}, "court_found": True}
    assert [e["frame"] for e in merge_chunks([r0, r1], plan)["events"]] == [1770]


def test_chunk_without_court_contributes_nothing():
    plan = [(0, 1799)]
    r = {"events": [], "tracking": [], "shuttle_debug": [], "geometry": None, "court_found": False}
    m = merge_chunks([r], plan)
    assert m["events"] == [] and m["chunks"][0]["court_found"] is False


def test_seconds_use_probed_fps():
    assert frame_to_sec(50, fps=25.0) == 2.0


# --- additional coverage -----------------------------------------------------

def test_plan_short_video_is_one_chunk():
    assert plan_chunks(500) == [(0, 499)]
    assert plan_chunks(1800) == [(0, 1799)]


def test_plan_every_frame_owned_by_exactly_one_chunk():
    for total in (1801, 1860, 3540, 3541, 91050):
        plan = plan_chunks(total)
        n = plan[-1][1] + 1
        results = [_result(n=e - s + 1) for s, e in plan]
        m = merge_chunks(results, plan)
        assert n == total
        assert [t["frame"] for t in m["tracking"]] == list(range(total))
        assert [s["frame"] for s in m["shuttle"]] == list(range(total))


def test_merge_offsets_frames_and_keeps_interior_events():
    plan = [(0, 1799), (1740, 3539)]
    r0 = _result(events=[10, 1768, 1769], n=1800)
    r1 = _result(events=[28, 29, 30, 500], n=1800)
    m = merge_chunks([r0, r1], plan)
    # chunk 0 owns full frames < 1770, chunk 1 owns >= 1770 (local 30)
    assert [e["frame"] for e in m["events"]] == [10, 1768, 1769, 1770, 2240]
    assert m["tracking"][1770]["players"] == [{"id": 30}]     # from chunk 1
    assert m["tracking"][1769]["players"] == [{"id": 1769}]   # from chunk 0
    assert m["shuttle"][2000]["pos"] == [260, 260]


def test_merge_does_not_mutate_chunk_results():
    plan = [(0, 1799), (1740, 3539)]
    r1 = _result(events=[100], n=1800)
    merge_chunks([_result(n=1800), r1], plan)
    assert r1["events"][0]["frame"] == 100
    assert r1["tracking"][5]["frame"] == 5


def test_no_court_chunk_frames_are_empty_not_missing():
    plan = [(0, 1799), (1740, 3539)]
    m = merge_chunks([_result(n=0, court=False), _result(events=[100], n=1800)], plan)
    assert len(m["tracking"]) == 3540
    assert m["tracking"][5] == {"frame": 5, "players": []}
    assert m["shuttle"][5]["pos"] is None
    assert [c["court_found"] for c in m["chunks"]] == [False, True]
    assert m["chunks"][0] == {"start": 0, "end": 1799, "court_found": False, "geometry": None}


def test_merge_requires_one_result_per_chunk():
    with pytest.raises(ValueError):
        merge_chunks([_result()], [(0, 1799), (1740, 3539)])


# --- ffmpeg-backed ------------------------------------------------------------

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not on PATH")


def _synthetic(path, fps, seconds):
    """testsrc2 draws a moving pattern + frame counter, so neighbouring frames differ."""
    import subprocess
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         f"testsrc2=size=320x180:rate={fps}:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True)


@needs_ffmpeg
def test_cut_exact_is_frame_exact_and_verify_catches_offset(tmp_path):
    src = tmp_path / "src.mp4"
    _synthetic(src, 25, 8)
    out = tmp_path / "chunk.mp4"
    cut_exact(src, 50, 60, out, fps=25.0)
    assert verify_cut(src, out, 50)
    assert not verify_cut(src, out, 51)
    assert not verify_cut(src, out, 49)


@needs_ffmpeg
def test_analyze_full_match_with_injected_runner(tmp_path):
    from fullmatch import chunks as chunks_mod
    from fullmatch.run import analyze_full_match

    src = tmp_path / "match.mp4"
    _synthetic(src, 25, 6)          # 150 frames @ 25 fps
    seen = []

    def fake_runner(jobs):
        seen.extend(cid for cid, _ in jobs)
        out = []
        for cid, clip in jobs:
            assert clip[4:8] == b"ftyp"        # real mp4 bytes
            out.append({"chunk_id": cid, "court_found": True, "geometry": {},
                        "events": [{"frame": 20}], "tracking": [], "shuttle_debug": [],
                        "summary": {}, "timings": {"total_s": 1.0}})
        return out

    res = analyze_full_match(src, analyze_chunks=fake_runner, chunk=60, overlap=10,
                             work_dir=tmp_path / "chunks")
    assert res["fps"] == 25.0
    assert res["totalFrames"] == 150
    plan = chunks_mod.plan_chunks(150, chunk=60, overlap=10)
    assert sorted(seen) == list(range(len(plan)))
    assert [e["frame"] for e in res["rawEvents"]] == [s + 20 for s, _ in plan if s + 20 <= 149]
    assert res["rawEvents"][0]["timeSec"] == pytest.approx(20 / 25)
    # no player tracks -> no camera runs -> no rallies; merged hits stay in rawEvents
    assert res["events"] == [] and res["rallies"] == []
    for stage in ("probe_s", "cut_s", "analyze_s", "merge_s", "segment_s", "total_s"):
        assert stage in res["timings"]
    assert res["timings"]["chunk_s"] == [1.0] * len(plan)
    assert res["court"] is None and res["court_outliers"] == []   # fake geometry has no kp6


def test_cut_status_static_vs_mismatch():
    from fullmatch.chunks import cut_status
    decisive = {"k": 5, "prev": 4.0, "same": 0.4, "next": 5.0}
    static = {"k": 9, "prev": 0.35, "same": 0.4, "next": 0.38}
    assert cut_status([static, decisive]) == "ok"
    assert cut_status([static, static]) == "static"
    assert cut_status([decisive, {"k": 1, "prev": 0.4, "same": 3.0, "next": 6.0}]) == "mismatch"


# --- boundary hits (Ruling 7) -------------------------------------------------

def _two_chunk_events(e0, e1):
    """Chunk 0 events in full frames, chunk 1 events in full frames (start 1740)."""
    plan = [(0, 1799), (1740, 3539)]
    r0 = _result(events=e0, n=0)
    r1 = _result(events=[f - 1740 for f in e1], n=0)
    return [e["frame"] for e in merge_chunks([r0, r1], plan)["events"]]


def test_boundary_hit_estimates_straddling_ownership_line_kept_once():
    # 1769 (chunk 0) vs 1771 (chunk 1): previously both kept
    assert _two_chunk_events([1769], [1771]) == [1771]


def test_boundary_hit_estimates_both_on_wrong_side_kept_once():
    # 1771 (chunk 0) vs 1768 (chunk 1): previously both dropped
    assert _two_chunk_events([1771], [1768]) == [1771]


def test_distinct_hits_in_overlap_both_survive():
    assert _two_chunk_events([1750, 1771], [1750, 1771]) == [1750, 1771]
    assert _two_chunk_events([1750], [1771]) == [1750, 1771]


def test_hit_seen_by_one_chunk_only_is_kept_either_side():
    assert _two_chunk_events([1790], []) == [1790]
    assert _two_chunk_events([], [1745]) == [1745]


def test_hit_just_outside_overlap_is_not_duplicated():
    # chunk 0 sees it at 1735 (before the overlap), chunk 1 at its local frame 1
    assert _two_chunk_events([1735], [1741]) == [1735]
