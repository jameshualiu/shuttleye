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
  5. Score with train/eval_scoring.py and print a per-rally + overall report;
     raw results are saved under --cache-dir, outside git

Not part of the runtime pipeline. Needs ffmpeg on PATH and the eval deps:
    pip install -r worker/requirements.txt -r worker/requirements-eval.txt

Usage (from the repo root -- worker_image resolves "worker/" relative to it):
    python -m modal run worker/train/eval_shuttleset.py \
        [--set-num 1] [--rallies 1,5,10] [--max-rallies 5] [--tolerance 3]
"""
import csv
import datetime
import io
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

import modal

# Locally the worker dir holds app.py; inside the container it's /root.
_WORKER_DIR = pathlib.Path(__file__).resolve().parents[1]
for _p in (str(_WORKER_DIR), "/root"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app as worker_app  # noqa: E402  (worker_image, models_volume, model targets)
from train.eval_scoring import PRODUCT_TYPES, parse_rallies, score_rally, summarize  # noqa: E402

SHUTTLESET_RAW = "https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/main/ShuttleSet/set"
DEFAULT_MATCH = "Viktor_Axelsen_Jonatan_Christie_YONEX_Thailand_Open_2021_QuarterFinals"
FPS = 30            # ShuttleSet frame_num is at 30fps; clips are cut at the same rate
PRE_ROLL = 30       # frames kept before a rally's first shot
POST_ROLL = 45      # frames kept after its last shot

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
        )

    @modal.method()
    def analyze(self, rally_id: int, clip: bytes) -> dict:
        from pipeline import BadmintonPipeline

        path = f"/tmp/rally_{rally_id}.mp4"
        with open(path, "wb") as f:
            f.write(clip)
        try:
            results = BadmintonPipeline(self.inference).process_video(path)
        finally:
            os.remove(path)
        return {
            "rally": rally_id,
            "court_found": results["geometry"] is not None,
            "summary": results["summary"],
            "events": results["events"],
        }


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


def _probe_fps(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    num, den = out.split("/")
    return float(num) / float(den)


def _cut_rally(src: pathlib.Path, start: int, n_frames: int, out: pathlib.Path) -> None:
    """Frame-exact re-encode: constant FPS, no audio, no B-frames (so the
    MP4 edit list skips nothing and decoded index == clip frame)."""
    if out.exists():
        return
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{start / FPS:.6f}", "-i", str(src),
         "-frames:v", str(n_frames), "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "18", "-bf", "0", "-r", str(FPS), "-fps_mode", "cfr",
         "-movflags", "+faststart", str(out)],
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


def _print_report(per_rally: list[tuple[int, int, dict]], overall: dict) -> None:
    print("\nrally  gt_hits   tp   fp   fn   side    type")
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

    cols = PRODUCT_TYPES + ["Unknown"]
    print("\n  confusion (rows = ShuttleSet, cols = pipeline)")
    print("  " + " " * 7 + "".join(f"{c[:7]:>8}" for c in cols))
    for g in PRODUCT_TYPES:
        print(f"  {g:7}" + "".join(f"{overall['confusion'].get(f'{g}->{p}', 0):8d}" for p in cols))


@app.local_entrypoint()
def main(match: str = DEFAULT_MATCH, set_num: int = 1, rallies: str = "",
         max_rallies: int = 0, tolerance: int = 3, cache_dir: str = ""):
    cache = pathlib.Path(cache_dir or pathlib.Path.home() / ".cache" / "shuttleye-eval") / match
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
    fps = _probe_fps(video)
    if abs(fps - FPS) > 0.01:
        raise SystemExit(f"[eval] downloaded video is {fps:.3f}fps; labels assume {FPS}fps")

    jobs, starts = [], {}
    for rally_id in ids:
        shots = labeled[rally_id]
        start = max(0, shots[0]["frame"] - PRE_ROLL)
        n_frames = shots[-1]["frame"] + POST_ROLL - start
        clip = clips_dir / f"rally_{rally_id:03d}_{start}.mp4"
        _cut_rally(video, start, n_frames, clip)
        starts[rally_id] = start
        jobs.append((rally_id, clip.read_bytes()))
    print(f"[eval] cut {len(jobs)} clips into {clips_dir}; running pipeline on Modal...")

    results = list(EvalWorker().analyze.starmap(jobs))

    per_rally, scores = [], []
    for res in sorted(results, key=lambda r: r["rally"]):
        rally_id = res["rally"]
        gt = [{**s, "frame": s["frame"] - starts[rally_id]} for s in labeled[rally_id]]
        s = score_rally(res["events"], gt, tolerance)
        scores.append(s)
        per_rally.append((rally_id, sum(not g["serve"] for g in gt), s))
        if not res["court_found"]:
            print(f"[eval] WARNING: no court found in rally {rally_id}")

    overall = summarize(scores)
    _print_report(per_rally, overall)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = cache / f"results_set{set_num}_{stamp}.json"
    out.write_text(json.dumps({
        "match": match, "set": set_num, "commit": _git_commit(), "tolerance": tolerance,
        "overall": overall, "rallies": results, "clip_starts": starts,
    }, indent=1, default=str))
    print(f"\n[eval] raw results: {out}")
