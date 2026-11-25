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
(first shot - PRE_ROLL .. last shot + POST_ROLL), with and without serves.
Prints per-stage timings; raw results (and the merged per-frame tracks,
gzipped, for later tuning without re-running Modal) go under --cache-dir.

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
    PRODUCT_TYPES, fit_frame_offset, parse_rallies, score_labelled_hits, score_rally, summarize,
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


@app.local_entrypoint()
def main(match: str = DEFAULT_MATCH, set_num: int = 1, rallies: str = "",
         max_rallies: int = 0, tolerance: int = 3, cache_dir: str = "",
         gt_hits: bool = False, full_match: bool = False, max_containers: int = 20):
    cache = pathlib.Path(cache_dir or pathlib.Path.home() / ".cache" / "shuttleye-eval") / match
    if full_match:
        return _run_full_match(match, cache, tolerance, max_containers)
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


def _run_full_match(match: str, cache: pathlib.Path, tolerance: int, max_containers: int):
    from fullmatch.run import analyze_full_match

    url, sets = _labelled_sets(match)
    print(f"[eval] {match}: full match, labelled sets {sorted(sets)}")
    video = cache / "match.mp4"
    _download_match(url, video)
    fps = probe_fps(video)
    if abs(fps - FPS) > 0.01:
        raise SystemExit(f"[eval] downloaded video is {fps:.3f}fps; ShuttleSet labels assume {FPS}fps")

    worker = EvalWorker.with_options(max_containers=max_containers)()
    res = analyze_full_match(
        video, fps, analyze_chunks=lambda jobs: list(worker.analyze_chunk.starmap(jobs)),
        verify_chunks=3)
    events = res["events"]

    # Each set is scored over the span the one-video baseline used:
    # first shot - PRE_ROLL .. last shot + POST_ROLL (exclusive).
    windows = {}
    for set_num, rallies in sets.items():
        frames = [s["frame"] for shots in rallies.values() for s in shots]
        windows[set_num] = (max(0, min(frames) - PRE_ROLL), max(frames) + POST_ROLL - 1)

    def in_window(f, w):
        return w[0] <= f <= w[1]

    # One label->video offset for the match, serves excluded as in scoring.
    pred_in = [e["frame"] for e in events if any(in_window(e["frame"], w) for w in windows.values())]
    gt_all = [s["frame"] for r in sets.values() for shots in r.values() for s in shots if not s["serve"]]
    offset = fit_frame_offset(pred_in, gt_all, search=OFFSETS, tolerance=tolerance)
    print(f"[eval] fitted label frame offset: {offset:+d}")

    per_set, ex_scores, in_scores = [], [], []
    for set_num, rallies in sorted(sets.items()):
        w = windows[set_num]
        preds = [e for e in events if in_window(e["frame"], w)]
        gt = sorted(({**s, "frame": s["frame"] + offset} for shots in rallies.values() for s in shots),
                    key=lambda s: s["frame"])
        ex = score_rally(preds, gt, tolerance)
        inc = score_rally(preds, gt, tolerance, include_serves=True)
        ex_scores.append(ex)
        in_scores.append(inc)
        per_set.append((set_num, sum(not g["serve"] for g in gt), ex))
        si = summarize([inc])["hits"]
        print(f"[eval] set {set_num}: frames {w[0]}-{w[1]}, {len(preds)} predicted hits, "
              f"{len(gt)} labelled shots ({len(rallies)} rallies); incl. serves "
              f"P/R/F1 {_pct(si['precision'])}/{_pct(si['recall'])}/{_pct(si['f1'])}")

    overall = summarize(ex_scores)
    overall_incl = summarize(in_scores)
    overall["frame_offset"] = offset
    per_set_summary = {n: {"excl_serves": summarize([e]), "incl_serves": summarize([i])}
                       for (n, _, e), i in zip(per_set, in_scores)}
    outside = len(events) - len(pred_in)

    print("\nSERVES EXCLUDED (comparable with the baseline)")
    _print_report(per_set, overall, label="set")
    h = overall_incl["hits"]
    print("\nSERVES INCLUDED")
    print(f"  hits:  precision {_pct(h['precision'])}  recall {_pct(h['recall'])}  F1 {_pct(h['f1'])}  "
          f"(tp={h['tp']} fp={h['fp']} fn={h['fn']})")
    print(f"\n[eval] {len(events)} predicted hits in the whole video, {outside} outside the labelled sets' spans")
    no_court = [i for i, c in enumerate(res["chunks"]) if not c["court_found"]]
    print(f"[eval] chunks without a court: {len(no_court)}/{len(res['chunks'])} {no_court}")
    print(f"[eval] chunks with a court off the match's mode court: {len(res['court_outliers'])} {res['court_outliers']}")
    for v in res["verify"]:
        diffs = ", ".join(f"k={d['k']}: {d['same']:.2f} (prev {d['prev'] if d['prev'] is None else round(d['prev'], 2)}, "
                          f"next {d['next'] if d['next'] is None else round(d['next'], 2)})" for d in v["diffs"])
        print(f"[eval] verify_cut chunk {v['chunk']} start {v['start']}: {v.get('status', 'ok' if v['ok'] else 'FAIL')}  [{diffs}]")
    _print_timings(res["timings"], len(res["chunks"]))

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = cache / f"fullmatch_{stamp}.json"
    out.write_text(json.dumps({
        "match": match, "commit": _git_commit(), "tolerance": tolerance, "fps": res["fps"],
        "totalFrames": res["totalFrames"], "windows": windows, "frame_offset": offset,
        "overall_excl_serves": overall, "overall_incl_serves": overall_incl, "per_set": per_set_summary,
        "outside_sets": outside, "timings": res["timings"], "verify": res["verify"],
        "chunks": res["chunks"], "court": res["court"], "court_outliers": res["court_outliers"],
        "events": events,
    }, indent=1, default=str))
    tracks = cache / f"fullmatch_{stamp}_tracks.json.gz"
    with gzip.open(tracks, "wt") as f:
        json.dump({"tracking": res["tracking"], "shuttle": res["shuttle"]}, f)
    print(f"\n[eval] raw results: {out}\n[eval] merged tracks: {tracks}")
