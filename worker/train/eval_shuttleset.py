# worker/train/eval_shuttleset.py
"""
Offline accuracy eval of the full pipeline against a held-out ShuttleSet match.

Default match: Axelsen vs Christie, YONEX Thailand Open 2021 QF, which falls in
the hit detector's held-out test split (train_detector.split_npz_files), so hit
and side scores aren't inflated by training data. BST was trained upstream on
ShuttleSet with its own split, so treat shot-type scores as an upper bound.

Steps:
  1. Fetch the match's ShuttleSet labels + homography from GitHub
  2. Download the match video once with yt-dlp (720p30, cached locally)
  3. Cut each rally frame-exactly to constant 30fps with no B-frames, so clip
     frame == original frame - clip start (no edit-list offset)
  4. Run BadmintonPipeline.process_video() on Modal, one rally per call, using
     the worker image and model volume (no webhook, Firestore or R2)
  5. Fit one frame offset between detected hits and the labels
     (eval_scoring.fit_frame_offset) and shift the label frames by it
  6. Score with train/eval_scoring.py and print a per-rally + overall report;
     raw results are saved under --cache-dir, outside git

--full-match runs fullmatch.run.analyze_full_match on the whole downloaded
broadcast (frame-exact 1800-frame chunks, analysed in parallel by
EvalWorker.analyze_chunk, merged back to full-video frames), fits one label
frame offset for the match, and scores every labelled set over its span
(first shot - PRE_ROLL .. last shot + POST_ROLL), with and without serves,
before and after rally segmentation (fullmatch.segment). It also scores the
rallies themselves (score_segments; ground truth = first..last labelled shot of
every rally), the inserted serves, and hits in dead time. Prints per-stage
timings; raw results (and the merged per-frame tracks, gzipped) go under
--cache-dir. --from-merged <fullmatch_<stamp>.json> re-segments and re-scores
such a saved result locally, without Modal (also runnable as a plain script).
--shot-stack <shot_stack.joblib> re-classifies the segmented hits with the
stacked shot classifier (fullmatch.shot_features, train/train_shot_stack.py);
without it the eval scores BST-0 + side decode's types.

--gt-hits also runs BST-0 at the (offset-shifted) labelled hit frames, using
the same pipeline run's tracks and shuttle, and reports 10-class, 6-class and
side accuracy there -- stroke classification on its own, without hit-detection
misses or frame error.

Not part of the runtime pipeline. Needs ffmpeg on PATH and the eval deps:
    pip install -r worker/requirements.txt -r worker/requirements-eval.txt

Usage (from the repo root -- worker_image resolves "worker/" relative to it):
    python -m modal run worker/train/eval_shuttleset.py \
        [--set-num 1] [--rallies 1,5,10] [--max-rallies 5] [--tolerance 3] [--gt-hits]
    python -m modal run worker/train/eval_shuttleset.py --full-match [--max-containers 20]
    python worker/train/eval_shuttleset.py --from-merged ~/.cache/shuttleye-eval/<match>/fullmatch_<stamp>.json \
        [--match <match>] [--shot-stack shot_stack.joblib]
"""
import csv
import datetime
import gzip
import io
import itertools
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

import modal

# Locally the worker dir holds app.py; inside the container it's /root.
_WORKER_DIR = pathlib.Path(__file__).resolve().parents[1]
for _p in (str(_WORKER_DIR), "/root"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app as worker_app  # noqa: E402  (worker_image, models_volume, model targets)
from fullmatch.chunks import cut_exact, probe_fps  # noqa: E402
from train.eval_scoring import (  # noqa: E402
    PRODUCT_TYPES, fit_frame_offset, match_hits, parse_rallies, score_labelled_hits, score_rally,
    score_segments, summarize,
)

SHUTTLESET_RAW = "https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/main/ShuttleSet/set"
DEFAULT_MATCH = "Viktor_Axelsen_Jonatan_Christie_YONEX_Thailand_Open_2021_QuarterFinals"
FPS = 30            # ShuttleSet frame_num is at 30fps; clips are cut at the same rate
PRE_ROLL = 30       # frames kept before a rally's first shot
POST_ROLL = 45      # frames kept after its last shot
OFFSETS = range(-8, 9)  # label->video frame offsets searched by fit_frame_offset

app = modal.App("shuttleset-eval")


@app.cls(
    image=worker_app.worker_image,
    volumes={str(worker_app.MODELS_DIR): worker_app.models_volume},
    gpu="T4",
    timeout=1800,
    max_containers=5,
)
class EvalWorker:
    @modal.enter()
    def load_models(self):
        from inference import BadmintonInference

        files = {f.name: str(f) for f in worker_app.MODELS_DIR.glob("**/*") if f.is_file()}
        paths = {}
        for key, filename in {**worker_app.MODEL_TARGETS, **worker_app.OPTIONAL_MODEL_TARGETS}.items():
            if filename not in files and key in worker_app.MODEL_TARGETS:
                raise FileNotFoundError(f"{filename} missing from the models volume")
            paths[key] = files.get(filename)
        self.inference = BadmintonInference(
            paths["tracknet"], paths["court_kprcnn"], paths["net_kprcnn"], paths["yolo_pose"],
            lstm_path=paths["lstm"],
            tracknet_v3_path=paths["tracknet_v3"],
            inpaintnet_path=paths["inpaintnet"],
            hit_detector_path=paths["hit_detector"],
            bst_path=paths["bst"],
            bst0_path=paths["bst0"],
        )

    @modal.method()
    def analyze(self, rally_id: int, clip: bytes, gt_frames: list | None = None) -> dict:
        """Run the pipeline on one clip. With gt_frames, also return BST-0
        probabilities at every gt frame + offset in OFFSETS (the offset is
        fitted locally afterwards), keyed by clip frame."""
        from pipeline import BadmintonPipeline

        path = f"/tmp/rally_{rally_id}.mp4"
        with open(path, "wb") as f:
            f.write(clip)
        try:
            results = BadmintonPipeline(self.inference).process_video(path)
        finally:
            os.remove(path)
        out = {
            "rally": rally_id,
            "court_found": results["geometry"] is not None,
            "summary": results["summary"],
            "events": results["events"],
        }
        if gt_frames is not None:
            clf = self.inference.bst_clf
            if not hasattr(clf, "probs_at"):
                raise RuntimeError("--gt-hits needs BST-0 (bst_0_JnB_bone_merged.pt) loaded")
            n = len(results["shuttle_debug"])
            frames = sorted({g + o for g in gt_frames for o in OFFSETS if 0 <= g + o < n})
            probs = clf.probs_at(frames, results["shuttle_debug"], results["tracking"])
            out["gt_probs"] = {f: p.tolist() for f, p in zip(frames, probs)}
        return out

    @modal.method()
    def analyze_chunk(self, chunk_id: int, clip: bytes) -> dict:
        """One chunk of a full broadcast (--full-match); same body as
        BadmintonWorker.analyze_chunk."""
        from fullmatch.run import analyze_chunk_clip

        return analyze_chunk_clip(self.inference, chunk_id, clip)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _fetch_csv(url: str) -> list[dict]:
    with urllib.request.urlopen(url) as resp:
        return list(csv.DictReader(io.StringIO(resp.read().decode("utf-8-sig"))))


def _load_labels(match: str, set_num: int):
    match_row = next(r for r in _fetch_csv(f"{SHUTTLESET_RAW}/match.csv") if r["video"] == match)
    hom_row = next(r for r in _fetch_csv(f"{SHUTTLESET_RAW}/homography.csv") if r["video"] == match)
    h = json.loads(hom_row["homography_matrix"])
    far = (float(hom_row["upleft_x"]), float(hom_row["upleft_y"]))
    near = (float(hom_row["downleft_x"]), float(hom_row["downleft_y"]))
    rows = _fetch_csv(f"{SHUTTLESET_RAW}/{match}/set{set_num}.csv")
    return match_row["url"], parse_rallies(rows, h, far, near)


def _download_match(url: str, out: pathlib.Path) -> None:
    if out.exists():
        return
    subprocess.run(
        [sys.executable, "-m", "yt_dlp", "-q", "--no-warnings",
         "-f", "bv*[height=720][fps=30][ext=mp4]/bv*[height=720][ext=mp4]",
         "-o", str(out), url],
        check=True,
    )


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _pct(x):
    return "  n/a" if x is None else f"{x * 100:5.1f}%"


def _print_report(per_rally: list[tuple[int, int, dict]], overall: dict, label: str = "rally") -> None:
    print(f"\n{label:>5}  gt_hits   tp   fp   fn   side    type")
    for rally_id, n_gt, s in per_rally:
        side = s["side_correct"] / s["side_total"] if s["side_total"] else None
        typ = s["type_correct"] / s["type_total"] if s["type_total"] else None
        print(f"{rally_id:5d}  {n_gt:7d}  {s['tp']:3d}  {s['fp']:3d}  {s['fn']:3d}  {_pct(side)}  {_pct(typ)}")

    hits, side, typ = overall["hits"], overall["side"], overall["type"]
    print("\nOVERALL")
    offset = hits["mean_frame_offset"]
    print(f"  hits:  precision {_pct(hits['precision'])}  recall {_pct(hits['recall'])}  "
          f"F1 {_pct(hits['f1'])}  (tp={hits['tp']} fp={hits['fp']} fn={hits['fn']}, "
          f"mean offset {'n/a' if offset is None else f'{offset:+.2f}'} frames)")
    print(f"  side:  accuracy {_pct(side['accuracy'])} on {side['scored']} matched hits "
          f"({side['missing']} with no predicted side)")
    print(f"  type:  accuracy {_pct(typ['accuracy'])} on {typ['scored']} matched hits")
    ten = overall["ten"]
    print(f"  ten:   accuracy {_pct(ten['accuracy'])} on {ten['scored']} matched hits (detailType)")

    cols = PRODUCT_TYPES + ["Unknown"]
    print("\n  confusion (rows = ShuttleSet, cols = pipeline)")
    print("  " + " " * 7 + "".join(f"{c[:7]:>8}" for c in cols))
    for g in PRODUCT_TYPES:
        print(f"  {g:7}" + "".join(f"{overall['confusion'].get(f'{g}->{p}', 0):8d}" for p in cols))


def _score_gt_hits(res: dict, gt: list, total):
    """Add one rally's labelled-hit BST-0 scores (gt frames already shifted)."""
    from collections import Counter

    from fullmatch.bst_inputs import class_label

    probs = {int(f): p for f, p in res["gt_probs"].items()}
    shots, preds = [], []
    for g in gt:
        p = probs.get(g["frame"])
        if p is None:
            continue    # shifted outside the clip
        side, zh, _ = class_label(max(range(len(p)), key=p.__getitem__))
        shots.append(g)
        preds.append((side, zh))
    return (total or Counter()) + score_labelled_hits(shots, preds)


def _print_gt_hits(c) -> dict:
    def ratio(a, b):
        return c[a] / c[b] if c[b] else None

    out = {
        "ten": ratio("ten_correct", "ten_total"), "ten_n": c["ten_total"],
        "ten_known": ratio("ten_known_correct", "ten_known"), "ten_known_n": c["ten_known"],
        "type6": ratio("type_correct", "type_total"), "type6_n": c["type_total"],
        "side": ratio("side_correct", "side_total"), "side_n": c["side_total"],
        "side_known": ratio("side_known_correct", "side_known"),
    }
    print("\nBST-0 AT LABELLED HITS (offset-shifted)")
    print(f"  10-class: {_pct(out['ten'])} of {out['ten_n']} shots (serves incl.; unknown = wrong), "
          f"{_pct(out['ten_known'])} of {out['ten_known_n']} with a known prediction")
    print(f"  6-class:  {_pct(out['type6'])} of {out['type6_n']} non-serve shots")
    print(f"  side:     {_pct(out['side'])} of {out['side_n']} shots, "
          f"{_pct(out['side_known'])} with a known prediction")
    return out


def _cache_dir(cache_dir: str, match: str) -> pathlib.Path:
    return pathlib.Path(cache_dir or pathlib.Path.home() / ".cache" / "shuttleye-eval") / match


@app.local_entrypoint()
def main(match: str = DEFAULT_MATCH, set_num: int = 1, rallies: str = "",
         max_rallies: int = 0, tolerance: int = 3, cache_dir: str = "",
         gt_hits: bool = False, full_match: bool = False, max_containers: int = 20,
         from_merged: str = "", shot_stack: str = ""):
    cache = _cache_dir(cache_dir, match)
    if full_match or from_merged:
        return _run_full_match(match, cache, tolerance, max_containers, from_merged, shot_stack)
    clips_dir = cache / f"set{set_num}_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    url, labeled = _load_labels(match, set_num)
    ids = sorted(labeled)
    if rallies:
        wanted = {int(r) for r in rallies.split(",")}
        ids = [r for r in ids if r in wanted]
    if max_rallies:
        ids = ids[:max_rallies]
    print(f"[eval] {match} set {set_num}: {len(ids)} rallies")

    video = cache / "match.mp4"
    _download_match(url, video)
    fps = probe_fps(video)
    if abs(fps - FPS) > 0.01:
        raise SystemExit(f"[eval] downloaded video is {fps:.3f}fps; labels assume {FPS}fps")

    jobs, starts = [], {}
    for rally_id in ids:
        shots = labeled[rally_id]
        start = max(0, shots[0]["frame"] - PRE_ROLL)
        n_frames = shots[-1]["frame"] + POST_ROLL - start
        clip = clips_dir / f"rally_{rally_id:03d}_{start}.mp4"
        cut_exact(video, start, n_frames, clip, FPS)
        starts[rally_id] = start
        gt_frames = [s["frame"] - start for s in shots] if gt_hits else None
        jobs.append((rally_id, clip.read_bytes(), gt_frames))
    print(f"[eval] cut {len(jobs)} clips into {clips_dir}; running pipeline on Modal...")

    results = sorted(EvalWorker().analyze.starmap(jobs), key=lambda r: r["rally"])

    # One label->video offset for the match, fitted on absolute frames (rallies
    # are far apart, so they can't cross-match), serves excluded as in scoring.
    pred_abs = [e["frame"] + starts[r["rally"]] for r in results for e in r["events"]]
    gt_abs = [s["frame"] for r in results for s in labeled[r["rally"]] if not s["serve"]]
    offset = fit_frame_offset(pred_abs, gt_abs, search=OFFSETS, tolerance=tolerance)
    print(f"[eval] fitted label frame offset: {offset:+d}")

    per_rally, scores, labelled = [], [], None
    for res in results:
        rally_id = res["rally"]
        gt = [{**s, "frame": s["frame"] + offset - starts[rally_id]} for s in labeled[rally_id]]
        if gt_hits:
            labelled = _score_gt_hits(res, gt, labelled)
        s = score_rally(res["events"], gt, tolerance)
        scores.append(s)
        per_rally.append((rally_id, sum(not g["serve"] for g in gt), s))
        if not res["court_found"]:
            print(f"[eval] WARNING: no court found in rally {rally_id}")

    overall = summarize(scores)
    overall["frame_offset"] = offset
    _print_report(per_rally, overall)
    if labelled is not None:
        overall["gt_hits"] = _print_gt_hits(labelled)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = cache / f"results_set{set_num}_{stamp}.json"
    out.write_text(json.dumps({
        "match": match, "set": set_num, "commit": _git_commit(), "tolerance": tolerance,
        "overall": overall, "rallies": results, "clip_starts": starts,
    }, indent=1, default=str))
    print(f"\n[eval] raw results: {out}")


# ---------------------------------------------------------------------------
# --full-match
# ---------------------------------------------------------------------------

def _labelled_sets(match: str):
    """{set_num: {rally_id: [shot, ...]}} for every set ShuttleSet labels."""
    url, sets = None, {}
    for set_num in itertools.count(1):
        try:
            url, sets[set_num] = _load_labels(match, set_num)
        except urllib.error.HTTPError as e:
            if e.code == 404 and sets:
                return url, sets
            raise


def _print_timings(t: dict, n_chunks: int) -> None:
    def row(name, v):
        print(f"  {name:<34}{'n/a' if v is None else f'{v:9.1f}'}")

    print(f"\nTIMINGS ({n_chunks} chunks, seconds)")
    row("probe", t.get("probe_s"))
    row("cut (local ffmpeg)", t.get("cut_s"))
    row("verify_cut (local, 3 chunks)", t.get("verify_s"))
    row("analyze (dispatch -> all results)", t.get("analyze_s"))
    row("  first chunk start after dispatch", t.get("first_chunk_start_s"))
    row("  last chunk end after dispatch", t.get("last_chunk_end_s"))
    row("  per chunk min", t.get("chunk_min_s"))
    row("  per chunk median", t.get("chunk_median_s"))
    row("  per chunk max", t.get("chunk_max_s"))
    row("  sum over chunks (GPU-busy)", t.get("chunk_sum_s"))
    row("merge", t.get("merge_s"))
    row("total wall clock", t.get("total_s"))
    print(f"  upload: {t.get('upload_mb', 0):.0f} MB of chunk bytes")


def _run_full_match(match: str, cache: pathlib.Path, tolerance: int, max_containers: int,
                    from_merged: str = "", shot_stack: str = ""):
    from fullmatch.run import analyze_full_match, apply_segmentation

    if from_merged:
        res, merged_json, saved_match = _load_merged(pathlib.Path(from_merged).expanduser())
        if match is None:
            match = saved_match
        elif saved_match and match != saved_match:
            raise SystemExit(f"[eval] --match {match} but {merged_json} is {saved_match}; "
                             f"omit --match (plain script) or pass the saved match")
        cache = merged_json.parent       # save next to the merged result
    url, sets = _labelled_sets(match)
    print(f"[eval] {match}: full match, labelled sets {sorted(sets)}")
    if from_merged:
        print(f"[eval] re-segmenting saved merged result {merged_json} (no Modal)")
        apply_segmentation(res, shot_stack=shot_stack or False)
    else:
        video = cache / "match.mp4"
        _download_match(url, video)
        fps = probe_fps(video)
        if abs(fps - FPS) > 0.01:
            raise SystemExit(f"[eval] downloaded video is {fps:.3f}fps; ShuttleSet labels assume {FPS}fps")
        worker = EvalWorker.with_options(max_containers=max_containers)()
        res = analyze_full_match(
            video, fps, analyze_chunks=lambda jobs: list(worker.analyze_chunk.starmap(jobs)),
            verify_chunks=3, shot_stack=shot_stack or False)
        merged_json = None
    report = _score_full_match(res, sets, tolerance)

    if not from_merged:
        no_court = [i for i, c in enumerate(res["chunks"]) if not c["court_found"]]
        print(f"[eval] chunks without a court: {len(no_court)}/{len(res['chunks'])} {no_court}")
        print(f"[eval] chunks with a court off the match's mode court: "
              f"{len(res['court_outliers'])} {res['court_outliers']}")
        for v in res["verify"]:
            diffs = ", ".join(f"k={d['k']}: {d['same']:.2f} (prev {d['prev'] if d['prev'] is None else round(d['prev'], 2)}, "
                              f"next {d['next'] if d['next'] is None else round(d['next'], 2)})" for d in v["diffs"])
            print(f"[eval] verify_cut chunk {v['chunk']} start {v['start']}: "
                  f"{v.get('status', 'ok' if v['ok'] else 'FAIL')}  [{diffs}]")
    _print_timings(res["timings"], len(res["chunks"]))

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = cache / f"fullmatch_{stamp}{'_resegmented' if from_merged else ''}.json"
    cache.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "match": match, "commit": _git_commit(), "tolerance": tolerance, "fps": res["fps"],
        "totalFrames": res["totalFrames"], "merged_from": str(merged_json) if merged_json else None,
        **report, "timings": res["timings"], "verify": res.get("verify"),
        "chunks": res["chunks"], "court": res.get("court"), "court_outliers": res.get("court_outliers"),
        "rawEvents": res["rawEvents"], "events": res["events"], "rallies": res["rallies"],
        "shotStack": res.get("shotStack"),
    }, indent=1, default=str))
    print(f"\n[eval] raw results: {out}")
    if not from_merged:
        tracks = cache / f"fullmatch_{stamp}_tracks.json.gz"
        with gzip.open(tracks, "wt") as f:
            json.dump({"tracking": res["tracking"], "shuttle": res["shuttle"]}, f)
        print(f"[eval] merged tracks: {tracks}\n[eval] re-score offline with --from-merged {out}")


def _load_merged(path: pathlib.Path) -> tuple[dict, pathlib.Path, str | None]:
    """A saved --full-match result (fullmatch_<stamp>.json, or its
    _tracks.json.gz) as an analyze_full_match-shaped dict, merged hits in
    rawEvents (older saves only have `events`, which were the merged hits)."""
    name = path.name
    if name.endswith("_tracks.json.gz"):
        path = path.with_name(name[:-len("_tracks.json.gz")] + ".json")
    saved = json.loads(path.read_text())
    stem = path.name[:-len(".json")].removesuffix("_resegmented")
    tracks_path = path.with_name(stem + "_tracks.json.gz")
    if saved.get("merged_from"):        # a re-segmented save points at the original
        res, orig, match = _load_merged(pathlib.Path(saved["merged_from"]))
        return res, orig, match or saved.get("match")
    with gzip.open(tracks_path, "rt") as f:
        tracks = json.load(f)
    res = {k: saved.get(k) for k in ("fps", "totalFrames", "chunks", "court", "court_outliers", "verify")}
    res["timings"] = {}
    res["rawEvents"] = saved.get("rawEvents", saved["events"])
    res["events"] = res["rawEvents"]
    res["tracking"], res["shuttle"] = tracks["tracking"], tracks["shuttle"]
    return res, path, saved.get("match")


def _span_hits(events, gt_rallies, pad):
    """Events not within `pad` frames of any labelled rally (first..last shot)."""
    return [e for e in events if not any(a - pad <= e["frame"] <= b + pad for a, b in gt_rallies)]


def _courtside_approx(pred, gt_rallies, pad=15):
    """An approximation of COURTSIDE segment.validate(): labels padded +-pad
    frames, any overlap can match, one-to-one; every unmatched prediction is a
    false positive, split pieces included (score_segments keeps those apart).
    Upstream pairs greedily by overlap in frames; score_segments pairs by the
    fraction of the label covered, so individual pairings can differ."""
    s = score_segments(pred, [(a - pad, b + pad) for a, b in gt_rallies], min_overlap=1e-9)
    fp = s["fp"] + s["split"]
    p = s["tp"] / (s["tp"] + fp) if s["tp"] + fp else None
    r = s["recall"]
    return {**s, "fp": fp, "precision": p, "f1": 2 * p * r / (p + r) if p and r else None,
            "note": "approximation of COURTSIDE validate(); split pieces counted as fp"}


def _score_full_match(res: dict, sets: dict, tolerance: int) -> dict:
    """Print and return hit (before/after segmentation), serve and rally
    segmentation scores for a full-match result."""
    raw, events, rallies = res["rawEvents"], res["events"], res["rallies"]

    # Each set's hits are scored over the span the one-video baseline used:
    # first shot - PRE_ROLL .. last shot + POST_ROLL (inclusive).
    windows = {}
    for set_num, rs in sets.items():
        frames = [s["frame"] for shots in rs.values() for s in shots]
        windows[set_num] = (max(0, min(frames) - PRE_ROLL), max(frames) + POST_ROLL - 1)

    def in_window(f, w):
        return w[0] <= f <= w[1]

    def in_any(f):
        return any(in_window(f, w) for w in windows.values())

    # One label->video offset for the match, fitted on the merged (unsegmented)
    # non-serve hits as before segmentation, so before/after share it.
    pred_in = [e["frame"] for e in raw if in_any(e["frame"]) and not e.get("isServe")]
    gt_all = [s["frame"] for r in sets.values() for shots in r.values() for s in shots if not s["serve"]]
    offset = fit_frame_offset(pred_in, gt_all, search=OFFSETS, tolerance=tolerance)
    print(f"[eval] fitted label frame offset: {offset:+d}")

    gt_by_set = {n: sorted(({**s, "frame": s["frame"] + offset} for shots in rs.values() for s in shots),
                           key=lambda s: s["frame"]) for n, rs in sets.items()}
    gt_rallies = sorted((shots[0]["frame"] + offset, shots[-1]["frame"] + offset)
                        for rs in sets.values() for shots in rs.values())

    def score_hits(evs, label):
        per_set, ex_scores, in_scores = [], [], []
        for set_num in sorted(sets):
            w = windows[set_num]
            preds = [e for e in evs if in_window(e["frame"], w)]
            gt = gt_by_set[set_num]
            ex = score_rally(preds, gt, tolerance)
            inc = score_rally(preds, gt, tolerance, include_serves=True)
            ex_scores.append(ex)
            in_scores.append(inc)
            per_set.append((set_num, sum(not g["serve"] for g in gt), ex))
        ex_all, in_all = summarize(ex_scores), summarize(in_scores)
        print(f"\n===== HITS {label}: SERVES EXCLUDED =====")
        _print_report(per_set, ex_all, label="set")
        h = in_all["hits"]
        print(f"\n  {label} SERVES INCLUDED: precision {_pct(h['precision'])}  recall {_pct(h['recall'])}  "
              f"F1 {_pct(h['f1'])}  (tp={h['tp']} fp={h['fp']} fn={h['fn']}); "
              f"ten {_pct(in_all['ten']['accuracy'])} on {in_all['ten']['scored']}")
        return {"excl_serves": ex_all, "incl_serves": in_all,
                "per_set": {n: {"excl_serves": summarize([e]), "incl_serves": summarize([i])}
                            for (n, _, e), i in zip(per_set, in_scores)}}

    before = score_hits(raw, "BEFORE SEGMENTATION (merged hits)")
    after = score_hits(events, "AFTER SEGMENTATION")

    # Serves on their own: predicted serve events vs the first shot of every
    # labelled rally (ShuttleSet types many serves 未知球種, so its serve flag
    # only marks some of them; the first shot of a rally is always the serve).
    gt_serves = [a for a, _ in gt_rallies]
    pred_serves = [e["frame"] for e in events if e.get("isServe") and in_any(e["frame"])]
    sp = match_hits(pred_serves, gt_serves, tolerance)
    sp_wide = match_hits(pred_serves, gt_serves, 15)
    serves = {"predicted": len(pred_serves), "rallies": len(gt_serves), "tp": len(sp),
              "tp_within_15": len(sp_wide),
              "labelled_as_serve": sum(s["serve"] for gt in gt_by_set.values() for s in gt),
              "precision": len(sp) / len(pred_serves) if pred_serves else None,
              "recall": len(sp) / len(gt_serves) if gt_serves else None,
              "frame_err": sorted(pred_serves[pi] - gt_serves[gi] for pi, gi in sp_wide)}
    print(f"\nSERVES vs first shot of each rally: {len(pred_serves)} predicted, {len(gt_serves)} rallies "
          f"({serves['labelled_as_serve']} typed as serves in ShuttleSet), {len(sp)} matched within "
          f"+-{tolerance} ({len(sp_wide)} within +-15) -> P {_pct(serves['precision'])} R {_pct(serves['recall'])}")

    # Dead time: predicted hits away from every labelled rally.
    dead = {}
    for name, evs in (("before", raw), ("after", events)):
        far = _span_hits(evs, gt_rallies, tolerance)
        dead[name] = {"in_set_windows": sum(in_any(e["frame"]) for e in far), "whole_video": len(far)}
    print(f"DEAD-TIME HITS (> {tolerance} frames from every labelled rally): "
          f"in set windows {dead['before']['in_set_windows']} -> {dead['after']['in_set_windows']}, "
          f"whole video {dead['before']['whole_video']} -> {dead['after']['whole_video']}")

    # Rally segmentation: ground truth = first..last labelled shot of each rally.
    pred = [(r["startFrame"], r["endFrame"]) for r in rallies]
    seg_all = score_segments(pred, gt_rallies)
    pred_in = [p for p in pred if any(in_window(p[0], w) or in_window(p[1], w) for w in windows.values())]
    seg_in = score_segments(pred_in, gt_rallies)
    seg_all_cs = _courtside_approx(pred, gt_rallies)
    seg_in_cs = _courtside_approx(pred_in, gt_rallies)
    for name, s, n in (("whole video", seg_all, len(pred)), ("in set windows", seg_in, len(pred_in)),
                       ("whole video, approx. COURTSIDE validate()", seg_all_cs, len(pred)),
                       ("in set windows, approx. COURTSIDE validate()", seg_in_cs, len(pred_in))):
        print(f"RALLIES ({name}): {n} predicted, {len(gt_rallies)} labelled -> "
              f"P {_pct(s['precision'])} R {_pct(s['recall'])} F1 {_pct(s['f1'])} "
              f"(tp={s['tp']} fp={s['fp']} fn={s['fn']} split={s['split']} merged={s['merged']})")
    return {"windows": windows, "frame_offset": offset, "hits_before": before, "hits_after": after,
            "serves": serves, "dead_time": dead,
            "segments": {"whole_video": seg_all, "in_set_windows": seg_in,
                         "whole_video_courtside": seg_all_cs, "in_set_windows_courtside": seg_in_cs,
                         "labelled": len(gt_rallies)}}


if __name__ == "__main__":
    # Offline re-scoring of a saved result, without `modal run`:
    #   python worker/train/eval_shuttleset.py --from-merged ~/.cache/.../fullmatch_<stamp>.json
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from-merged", required=True)
    ap.add_argument("--match", default=None, help="default: the saved result's match")
    ap.add_argument("--tolerance", type=int, default=3)
    ap.add_argument("--shot-stack", default="", help="shot_stack.joblib to re-classify hits with")
    a = ap.parse_args()
    _run_full_match(a.match, None, a.tolerance, 0, a.from_merged, a.shot_stack)
