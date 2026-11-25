"""Full-match analysis: full broadcast in, merged full-video result out.

probe fps -> plan chunks -> cut frame-exactly -> analyse chunks in parallel ->
merge back to full-video frames -> segment into rallies (with serves) ->
decode alternating sides per rally -> (optional) stacked shot classifier ->
read the score graphic locally over the full video (fullmatch.scoreboard:
score after each rally, winner, set, which player is near) -> assemble_result.

Two shapes come out of here. The internal result (analyze_full_match(...,
internal=True)) keeps everything later steps and the eval need: rawEvents,
per-frame tracking/shuttle, BST probabilities, chunk diagnostics. The eval
caches it and --from-merged re-segments and re-scores it offline. The product
result (the default) is assemble_result's documented contract (data-flow.md,
"Full-match result"): no per-frame data, no model internals.

The steps after the GPU work that the product can do without (side decode,
shot stack, scoreboard, the court check) are guarded: an unexpected exception
is logged, recorded in res["skippedSteps"], the step's partial changes are
rolled back, and the rest of the result is kept.

The parallel step is injected (`analyze_chunks`), so this module never imports
modal; the eval passes e.g.
`lambda jobs: list(EvalWorker().analyze_chunk.starmap(jobs, return_exceptions=True))`.
The runner may return an exception in place of a chunk's result (in job
order): that chunk counts as court_found False and is listed in skippedSteps.
`analyze_chunk_clip` is the in-container body of that Modal method.

res["models"] records what actually ran (stroke classifier the chunks
loaded, shot stack and digit templates used, None when not) and
res["warnings"] conditions that make the result less trustworthy (a source
that is not 30 fps).
"""
import copy
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
from fullmatch.scoreboard import (
    align_scores, events as score_events, load_templates, rally_serve_sides, side_map, timeline,
)
from fullmatch.segment import segment_rallies
from fullmatch.shot_features import apply_shot_stack
from fullmatch.sides import apply_side_decode


def _candidates(env_var: str, *paths: str) -> list[Path]:
    """$env_var (when set), then `paths`; the first that exists is used."""
    return [Path(p).expanduser() for p in (os.environ.get(env_var, ""), *paths) if p]


# Stacked shot classifier (fullmatch.shot_features, trained by
# train/train_shot_stack.py). On the Modal volume and in the local eval cache,
# never in git; analyze_full_match runs it locally, so the local cache counts.
# When none is found BST-0 + side decode's types are kept.
SHOT_STACK_PATHS = _candidates("SHOT_STACK_PATH", "/models/shot_stack.joblib",
                               "~/.cache/shuttleye-eval/shot_stack.joblib")
SHOT_STACK_DEFAULT = True    # kept (#74): beat BST-0 + side decode on all 5 held-out matches

# Score-graphic digit templates (train/harvest_scoreboard.py). On the Modal
# volume and in the local eval cache, never in git; when none is found the
# scoreboard step is skipped and rallies carry no score.
SCOREBOARD_TEMPLATES = _candidates("SCOREBOARD_TEMPLATES", "/models/scoreboard_digits.npz",
                                   "~/.cache/shuttleye-eval/scoreboard_digits.npz")

# Model windows (BST-0's 30 frames, the hit detector's) are fixed frame counts
# trained at 30 fps. Other rates run unchanged and are flagged in "warnings";
# resampling to 30 fps is #76.
MODEL_FPS = 30.0


def default_shot_stack() -> Path | None:
    """The first of SHOT_STACK_PATHS that exists, or None."""
    return next((p for p in SHOT_STACK_PATHS if p.exists()), None)


def _models(res: dict) -> dict:
    """res["models"], created with every key None."""
    return res.setdefault("models", {"strokes": None, "shotStack": None, "scoreboardTemplates": None})


def _strokes(results: list[dict]) -> str | None:
    """The stroke classifier(s) the chunks report ("strokes"), comma-joined
    when they differ; None when no chunk reports one."""
    names = sorted({r["strokes"] for r in results if r.get("strokes")})
    return ", ".join(names) or None

# Returns one result per job, in job order; an exception may stand in for a
# failed chunk's result (Modal starmap(..., return_exceptions=True)).
ChunkRunner = Callable[[list[tuple[int, bytes]]], list[dict | BaseException]]


def analyze_full_match(video: Path, fps: float | None = None, analyze_chunks: ChunkRunner | None = None,
                       *, chunk: int = CHUNK, overlap: int = OVERLAP, work_dir: Path | None = None,
                       verify_chunks: int = 0, log=print, shot_stack=None, scoreboard=None,
                       internal: bool = False, on_merged: Callable[[dict], None] | None = None) -> dict:
    """Analyse a whole broadcast chunk by chunk and merge the results.

    Any fps is accepted; seconds always use the probed (or given) fps.
    Chunks go to `work_dir` and are kept (re-runs skip the cut); without it a
    temp dir next to the video is used and removed afterwards.
    `verify_chunks` > 0 checks that many chunks (first/middle/last) with verify_cut.
    `shot_stack` is passed to apply_segmentation, `scoreboard` to apply_scoreboard.
    Returns the product result (assemble_result) unless `internal`, which
    returns the full internal result (what the eval caches).
    `on_merged(res)` is called with the merged, not yet segmented result
    (events = every merged hit, per-frame tracking/shuttle) before any
    post-processing, so a caller can save the GPU work first; it must not
    mutate res. An exception in it is logged and the run goes on.
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
    warnings = []
    if abs(fps - MODEL_FPS) > 0.01:
        warnings.append(f"source fps {fps:.3f}: models were trained at {MODEL_FPS:g} fps; accuracy unmeasured")
        log(f"[fullmatch] WARNING: {warnings[-1]}")

    temp = work_dir is None
    if temp:
        chunks_root = video.parent / "chunks"
        made_root = not chunks_root.exists()
        chunks_root.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="run_", dir=chunks_root))
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
            if made_root:
                try:
                    chunks_root.rmdir()      # only if still empty (a parallel run may use it)
                except OSError:
                    pass

    log(f"[fullmatch] analysing {len(jobs)} chunks ({upload_bytes / 1e6:.0f} MB)...")
    dispatch_at = time.time()
    t = time.perf_counter()
    job_ids = [cid for cid, _ in jobs]
    results, skipped = [], []
    for k, r in enumerate(analyze_chunks(jobs)):
        if isinstance(r, BaseException):     # one lost chunk must not lose the match
            cid = job_ids[k] if k < len(job_ids) else None
            err = f"{type(r).__name__}: {r}"
            skipped.append({"step": f"chunk {cid}", "error": err})
            log(f"[fullmatch] WARNING: chunk {cid} failed ({err}); treated as no court, rest kept")
            r = {"chunk_id": cid, "court_found": False, "geometry": None, "events": [],
                 "tracking": [], "shuttle_debug": [], "summary": None, "timings": {}}
        results.append(r)
    timings["analyze_s"] = time.perf_counter() - t
    del jobs
    if results and len(skipped) == len(results):
        raise RuntimeError(f"every chunk failed; first: {skipped[0]['error']}")
    results = sorted(results, key=lambda r: r["chunk_id"])
    if [r["chunk_id"] for r in results] != list(range(len(plan))):
        raise RuntimeError("chunk results don't match the plan")

    t = time.perf_counter()
    merged = merge_chunks(results, plan, overlap=overlap)
    for e in merged["events"]:
        e["timeSec"] = frame_to_sec(e["frame"], fps)
    for c, r in zip(merged["chunks"], results):
        c["court_support"] = r.get("court_support")
    try:     # report only: never worth losing the GPU result over
        mode_court, outliers = court_outliers(merged["chunks"])
    except Exception as exc:
        mode_court, outliers = None, []
        err = f"{type(exc).__name__}: {exc}"
        skipped.append({"step": "court check", "error": err})
        log(f"[fullmatch] WARNING: court check failed ({err}); step skipped, rest of the result kept")
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
        "resolution": next((r["summary"]["resolution"] for r in results
                            if (r.get("summary") or {}).get("resolution")), None),
        "verify": verify,
        "timings": timings,
        "models": {"strokes": _strokes(results), "shotStack": None, "scoreboardTemplates": None},
        "warnings": warnings,
    }
    if skipped:
        res["skippedSteps"] = skipped
    if on_merged is not None:
        try:
            on_merged(res)
        except Exception as exc:     # saving is a convenience; never lose the run over it
            log(f"[fullmatch] WARNING: on_merged failed ({type(exc).__name__}: {exc})")
    apply_segmentation(res, log=log, shot_stack=shot_stack)
    _optional_step("scoreboard", res, ("rallies", "scoreTimeline", "scoreEvents", "sides", "models"), log,
                   lambda: apply_scoreboard(res, video, templates=scoreboard, log=log))
    timings["total_s"] = time.perf_counter() - t_start
    return res if internal else product_result(res)


def _optional_step(name: str, res: dict, keys: tuple, log, fn) -> bool:
    """Run fn(); on an exception restore res[keys] to their state before the
    step, record {"step", "error"} in res["skippedSteps"], log, and carry on."""
    saved = {k: copy.deepcopy(res[k]) for k in keys if k in res}
    try:
        fn()
        return True
    except Exception as exc:     # any bug in an optional step: keep the GPU result
        for k in keys:
            res.pop(k, None)
        res.update(saved)
        err = f"{type(exc).__name__}: {exc}"
        res.setdefault("skippedSteps", []).append({"step": name, "error": err})
        log(f"[fullmatch] WARNING: {name} failed ({err}); step skipped, rest of the result kept")
        return False


# ------------------------------------------------------------ product result

# Event fields in the product result (data-flow.md, "Full-match result").
# Everything else on an internal event is dropped: BST-0 "probs", the stack's
# geometry ("hitterM", "receiverM", "contactHeightM"), "detailId" (index of
# detailType), "serveScore" (serve-onset detector score).
EVENT_FIELDS = ("frame", "timeSec", "type", "detailType", "typeConfidence", "isServe", "side",
                "sideOverridden", "location_px", "location_m", "confidence", "confirmed", "source")


def _sec(frame: int, fps: float) -> float:
    return round(frame_to_sec(frame, fps), 3)


def _pair(v):
    return None if v is None else list(v)


def match_sets(rallies: list[dict]) -> list[dict]:
    """[{"set", "nearPlayer", "finalScore"}] from scored rallies (apply_scoreboard):
    nearPlayer = who is near ('A'|'B') in the set's first rally that knows,
    finalScore = the last scoreAfter (A, B) in the set. [] when no rally has a set."""
    out: dict[int, dict] = {}
    for r in rallies:
        s = r.get("set")
        if s is None:
            continue
        d = out.setdefault(s, {"set": s, "nearPlayer": None, "finalScore": None})
        if d["nearPlayer"] is None:
            d["nearPlayer"] = r.get("near")
        if r.get("scoreAfter") is not None:
            d["finalScore"] = _pair(r["scoreAfter"])
    return [out[k] for k in sorted(out)]


def assemble_result(fps: float, events: list[dict], rallies: list[dict], sets: list[dict], timings: dict,
                    *, total_frames: int | None = None, court=None, resolution=None,
                    skipped_steps: list[dict] | None = None, models: dict | None = None,
                    warnings: list[str] | None = None) -> dict:
    """The full-match product result (data-flow.md, "Full-match result").

    Frames are full-video frames; every frame has a seconds twin (frame / fps,
    rounded to ms). Events keep EVENT_FIELDS only; type ("Unknown" for None),
    isServe, sideOverridden, detailType, side, location_px and location_m are
    always present (None when unknown). Every rally
    carries the same keys; the scoreboard ones are None (scoreRead False) when
    that step did not run or read nothing. summary.resolution only when known.
    skippedSteps lists optional steps and chunks that failed ([] when none did).
    models: {"strokes", "shotStack", "scoreboardTemplates"} (None = not run /
    not known); warnings: [] when none.
    No per-frame tracking or shuttle data. Inputs are not mutated.
    """
    out_events = []
    for e in events:
        o = {k: e[k] for k in EVENT_FIELDS if k in e}
        o["timeSec"] = _sec(e["frame"], fps)
        o["type"] = e.get("type") or "Unknown"    # None: no product class (e.g. a service pick on a hit)
        o["isServe"] = bool(e.get("isServe"))
        o["sideOverridden"] = bool(e.get("sideOverridden"))
        o["detailType"] = e.get("detailType")
        for k in ("side", "location_px", "location_m"):   # inserted serves have no location
            o.setdefault(k, None)
        out_events.append(o)
    out_rallies = [{
        "id": i + 1,
        "set": r.get("set"),
        "startFrame": r["startFrame"],
        "endFrame": r["endFrame"],
        "startSec": _sec(r["startFrame"], fps),
        "endSec": _sec(r["endFrame"], fps),
        "eventIndices": list(r["eventIndices"]),
        "scoreAfter": _pair(r.get("scoreAfter")),
        "winner": r.get("winner"),
        "nearPlayer": r.get("near"),
        "scoreRead": bool(r.get("scoreRead")),
    } for i, r in enumerate(rallies)]
    counts: dict[str, int] = {}
    for e in out_events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    summary = {
        "durationSec": None if total_frames is None else _sec(total_frames, fps),
        "totalShots": len(out_events),
        "shotCounts": counts,
        "serveCount": sum(e["isServe"] for e in out_events),
        "rallyCount": len(out_rallies),
    }
    if resolution is not None:
        summary["resolution"] = list(resolution)
    return {
        "fps": fps,
        "totalFrames": total_frames,
        "court": court,
        "summary": summary,
        "rallies": out_rallies,
        "sets": [{**s, "finalScore": _pair(s.get("finalScore"))} for s in sets],
        "events": out_events,
        "timings": copy.deepcopy(timings),
        "skippedSteps": [dict(x) for x in skipped_steps or []],
        "models": {"strokes": None, "shotStack": None, "scoreboardTemplates": None, **(models or {})},
        "warnings": list(warnings or []),
    }


def product_result(res: dict) -> dict:
    """assemble_result over an internal (segmented, optionally scored) result."""
    rallies = res.get("rallies", [])
    return assemble_result(res["fps"], res["events"], rallies, match_sets(rallies), res.get("timings", {}),
                           total_frames=res.get("totalFrames"), court=res.get("court"),
                           resolution=res.get("resolution"), skipped_steps=res.get("skippedSteps"),
                           models=res.get("models"), warnings=res.get("warnings"))


def apply_scoreboard(res: dict, video: Path, templates=None, log=print, tl: list | None = None) -> dict:
    """Read the score graphic over the full local video and score the
    segmented rallies, in place: rally "set", "scoreAfter" (A, B), "winner",
    "scoreRead", "serveSide", "near" (A = the match winner); res
    "scoreTimeline", "scoreEvents", "sides" (scoreboard.side_map).

    templates: a scoreboard_digits.npz path, False to skip, None for the first
    of SCOREBOARD_TEMPLATES that exists. Without templates (or without a
    readable graphic) the step is skipped and rallies keep no score.
    `tl` reuses a saved timeline instead of scanning the video.
    """
    if templates is False:
        return res
    t = time.perf_counter()
    if tl is None:
        path = Path(templates).expanduser() if templates else next(
            (p for p in SCOREBOARD_TEMPLATES if p.exists()), None)
        if path is None or not path.exists():
            log(f"[fullmatch] scoreboard skipped: no digit templates ({path or SCOREBOARD_TEMPLATES})")
            return res
        tl = timeline(Path(video), res["fps"], templates=load_templates(path), log=log)
        _models(res)["scoreboardTemplates"] = str(path)
    ev = score_events(tl)
    res["scoreTimeline"], res["scoreEvents"] = tl, ev
    if not ev:
        log("[fullmatch] scoreboard: no score events read; rallies keep no score")
        return res
    rallies = res["rallies"]
    align_scores(rallies, ev)
    rally_serve_sides(res)
    res["sides"] = side_map(rallies)
    finals = {}
    for r in rallies:
        finals[r["set"]] = r["scoreAfter"]
    res.setdefault("timings", {})["scoreboard_s"] = time.perf_counter() - t
    log(f"[fullmatch] scoreboard: {len(ev)} score events, {sum(r['scoreRead'] for r in rallies)}/"
        f"{len(rallies)} rallies read, set finals (A-B) {finals}, sides "
        f"{[(s['set'], s['fromScore'], s['near']) for s in res['sides']]} "
        f"in {res['timings']['scoreboard_s']:.1f}s")
    return res


def apply_segmentation(res: dict, log=print, shot_stack=None) -> dict:
    """Segment a merged result into rallies, in place.

    `rawEvents` keeps every merged hit (it is reused when present, so this can
    be re-run on a saved result); `events` becomes the hits inside rallies plus
    the inserted serves, frame-sorted; `rallies` is
    [{"startFrame", "endFrame", "lastHitFrame", "startSec", "endSec",
    "eventIndices"}] with indices into `events` (endFrame = landing of the
    last hit when the track shows it).

    shot_stack: path to a shot_stack.joblib, False to skip the stack, None for
    the first of SHOT_STACK_PATHS that exists when SHOT_STACK_DEFAULT is on.
    res["models"]["shotStack"] is the model path when the stack re-typed the
    hits, else None.
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
    # Optional refinements: a failure keeps the events as they were before it.
    _optional_step("side decode", res, ("events",), log, lambda: apply_side_decode(res, log=log))
    if shot_stack is None:
        shot_stack = (default_shot_stack() if SHOT_STACK_DEFAULT else False)
        if shot_stack is None:
            log(f"[fullmatch] shot stack skipped: no model at {[str(p) for p in SHOT_STACK_PATHS]}")
    res.pop("shotStack", None)       # a re-run must not report an earlier run's stack
    if shot_stack:   # apply_shot_stack guards predict itself; this also covers load / features
        _optional_step("shot stack", res, ("events", "shotStack"), log,
                       lambda: apply_shot_stack(res, shot_stack, log=log))
    _models(res)["shotStack"] = (res.get("shotStack") or {}).get("model")
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
        "strokes": getattr(inference, "strokes_model", None),   # stroke classifier loaded
        "summary": res["summary"],
        "events": res["events"] if court else [],
        "tracking": res["tracking"],
        "shuttle_debug": res["shuttle_debug"],
        "timings": {"total_s": time.perf_counter() - t, "started_at": started_at,
                    "finished_at": time.time()},
    }
