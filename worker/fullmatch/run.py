"""Full-match analysis: full broadcast in, merged full-video result out.

probe fps -> plan chunks -> cut frame-exactly -> analyse chunks in parallel ->
merge back to full-video frames -> segment into rallies (with serves).
(Classification and scoring are added by later tasks on top of that.)

The parallel step is injected (`analyze_chunks`), so this module never imports
modal; the eval passes e.g. `lambda jobs: list(EvalWorker().analyze_chunk.starmap(jobs))`.
`analyze_chunk_clip` is the in-container body of that Modal method.
"""
import os
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Callable

from fullmatch.chunks import (
    CHUNK, OVERLAP, count_frames, cut_diffs, cut_exact, cut_status, frame_to_sec, merge_chunks,
    plan_chunks, probe_fps,
)
from fullmatch.court import court_outliers
from fullmatch.segment import segment_rallies

ChunkRunner = Callable[[list[tuple[int, bytes]]], list[dict]]


def analyze_full_match(video: Path, fps: float | None = None, analyze_chunks: ChunkRunner | None = None,
                       *, chunk: int = CHUNK, overlap: int = OVERLAP, work_dir: Path | None = None,
                       verify_chunks: int = 0, log=print) -> dict:
    """Analyse a whole broadcast chunk by chunk and merge the results.

    Any fps is accepted; seconds always use the probed (or given) fps.
    Chunks go to `work_dir` and are kept (re-runs skip the cut); without it a
    temp dir next to the video is used and removed afterwards.
    `verify_chunks` > 0 checks that many chunks (first/middle/last) with verify_cut.
    """
    if analyze_chunks is None:
        raise ValueError("analyze_chunks is required (e.g. a Modal starmap over analyze_chunk)")
    video = Path(video)
    t_start = time.perf_counter()
    timings = {}

    t = time.perf_counter()
    fps = fps or probe_fps(video)
    total = count_frames(video)
    plan = plan_chunks(total, chunk=chunk, overlap=overlap)
    timings["probe_s"] = time.perf_counter() - t
    log(f"[fullmatch] {total} frames @ {fps:.3f} fps -> {len(plan)} chunks of {chunk} (overlap {overlap})")

    temp = work_dir is None
    if temp:
        (video.parent / "chunks").mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="run_", dir=video.parent / "chunks"))
    work_dir = Path(work_dir)
    try:
        t = time.perf_counter()
        paths = []
        for i, (s, e) in enumerate(plan):
            p = work_dir / f"chunk_{i:03d}_{s}_{e}.mp4"
            cut_exact(video, s, e - s + 1, p, fps)
            paths.append(p)
        timings["cut_s"] = time.perf_counter() - t
        log(f"[fullmatch] cut {len(paths)} chunks in {timings['cut_s']:.1f}s -> {work_dir}")

        verify = []
        if verify_chunks:
            t = time.perf_counter()
            picks = sorted({round(k * (len(plan) - 1) / max(verify_chunks - 1, 1))
                            for k in range(verify_chunks)})
            for i in picks:
                rows = cut_diffs(video, paths[i], plan[i][0])   # same check as verify_cut
                status = cut_status(rows)
                verify.append({"chunk": i, "start": plan[i][0], "ok": status == "ok",
                               "status": status, "diffs": rows})
                log(f"[fullmatch] verify chunk {i} (start {plan[i][0]}): {status}")
            timings["verify_s"] = time.perf_counter() - t

        jobs = [(i, p.read_bytes()) for i, p in enumerate(paths)]
        upload_bytes = sum(len(b) for _, b in jobs)
    finally:
        if temp:
            shutil.rmtree(work_dir, ignore_errors=True)

    log(f"[fullmatch] analysing {len(jobs)} chunks ({upload_bytes / 1e6:.0f} MB)...")
    dispatch_at = time.time()
    t = time.perf_counter()
    results = analyze_chunks(jobs)
    timings["analyze_s"] = time.perf_counter() - t
    del jobs
    results = sorted(results, key=lambda r: r["chunk_id"])
    if [r["chunk_id"] for r in results] != list(range(len(plan))):
        raise RuntimeError("chunk results don't match the plan")

    t = time.perf_counter()
    merged = merge_chunks(results, plan, overlap=overlap)
    for e in merged["events"]:
        e["timeSec"] = frame_to_sec(e["frame"], fps)
    for c, r in zip(merged["chunks"], results):
        c["court_support"] = r.get("court_support")
    mode_court, outliers = court_outliers(merged["chunks"])
    timings["merge_s"] = time.perf_counter() - t
    if outliers:   # report only; no automatic re-run
        log(f"[fullmatch] WARNING: {len(outliers)} chunk(s) with a court off the match's mode court: {outliers}")

    chunk_s = [r.get("timings", {}).get("total_s") for r in results]
    timings["chunk_s"] = chunk_s
    known = [c for c in chunk_s if c is not None]
    if known:
        timings["chunk_min_s"], timings["chunk_median_s"], timings["chunk_max_s"] = (
            min(known), statistics.median(known), max(known))
        timings["chunk_sum_s"] = sum(known)
    starts = [r["timings"]["started_at"] for r in results if "started_at" in r.get("timings", {})]
    ends = [r["timings"]["finished_at"] for r in results if "finished_at" in r.get("timings", {})]
    if starts and ends:
        # container clocks vs local clock: NTP-synced, so good to ~a second
        timings["first_chunk_start_s"] = min(starts) - dispatch_at   # cold start + first upload
        timings["last_chunk_end_s"] = max(ends) - dispatch_at
    timings["upload_mb"] = upload_bytes / 1e6

    res = {
        "fps": fps,
        "totalFrames": total,
        "durationSec": frame_to_sec(total, fps),
        "events": merged["events"],
        "tracking": merged["tracking"],
        "shuttle": merged["shuttle"],
        "chunks": merged["chunks"],
        "court": mode_court,
        "court_outliers": outliers,
        "verify": verify,
        "timings": timings,
    }
    apply_segmentation(res, log=log)
    timings["total_s"] = time.perf_counter() - t_start
    return res


def apply_segmentation(res: dict, log=print) -> dict:
    """Segment a merged result into rallies, in place.

    `rawEvents` keeps every merged hit (it is reused when present, so this can
    be re-run on a saved result); `events` becomes the hits inside rallies plus
    the inserted serves, frame-sorted; `rallies` is
    [{"startFrame", "endFrame", "lastHitFrame", "startSec", "endSec",
    "eventIndices"}] with indices into `events` (endFrame = landing of the
    last hit when the track shows it).
    """
    t = time.perf_counter()
    fps = res["fps"]
    raw = res.get("rawEvents", res["events"])
    events = [dict(e) for e in raw]
    rallies = segment_rallies(events, res["tracking"], res["shuttle"], res["totalFrames"], fps)
    keep = sorted({i for r in rallies for i in r["eventIndices"]})
    new_index = {old: new for new, old in enumerate(keep)}
    events = [events[i] for i in keep]
    for e in events:
        e["timeSec"] = frame_to_sec(e["frame"], fps)
    res["rawEvents"] = raw
    res["events"] = events
    res["rallies"] = [{"startFrame": r["startFrame"], "endFrame": r["endFrame"],
                       "lastHitFrame": r["lastHitFrame"],
                       "startSec": frame_to_sec(r["startFrame"], fps),
                       "endSec": frame_to_sec(r["endFrame"], fps),
                       "eventIndices": [new_index[i] for i in r["eventIndices"]]}
                      for r in rallies]
    res.setdefault("timings", {})["segment_s"] = time.perf_counter() - t
    serves = sum(bool(e.get("isServe")) for e in events)
    log(f"[fullmatch] segmentation: {len(rallies)} rallies, {len(events)} events "
        f"({serves} serves) kept of {len(raw)} merged hits in {res['timings']['segment_s']:.1f}s")
    return res


def analyze_chunk_clip(inference, chunk_id: int, clip: bytes) -> dict:
    """Modal-side body of `analyze_chunk`: run the per-clip pipeline on one chunk.

    The court is searched over the whole chunk (a chunk that opens on a replay
    still finds the court later on) and the largest agreeing cluster of
    detections wins, not the first. No court anywhere -> court_found False and
    nothing else is run. Frames are chunk-local; merge_chunks shifts them.
    """
    from pipeline import BadmintonPipeline     # container-only (torch, decord, cv2)

    started_at = time.time()
    t = time.perf_counter()
    path = f"/tmp/chunk_{chunk_id}_{os.getpid()}.mp4"
    with open(path, "wb") as f:
        f.write(clip)
    pipe = BadmintonPipeline(inference)
    try:
        res = pipe.process_video(path, court_search_limit=None, skip_without_court=True,
                                 court_consensus=True)
    finally:
        os.remove(path)
    court = res["geometry"] is not None
    return {
        "chunk_id": chunk_id,
        "court_found": court,
        "geometry": res["geometry"],
        "court_support": list(pipe.court_support),   # [agreeing, detections]
        "summary": res["summary"],
        "events": res["events"] if court else [],
        "tracking": res["tracking"],
        "shuttle_debug": res["shuttle_debug"],
        "timings": {"total_s": time.perf_counter() - t, "started_at": started_at,
                    "finished_at": time.time()},
    }
