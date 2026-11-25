"""How ingest gets a full-match result: the YouTube download, the chunk runners
(Modal or this machine) and the analysis steps ingest times one by one.

Everything heavy (modal, the worker's fullmatch code, the ShuttleSet eval) is
imported lazily, so the library tests run without it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

WORKER_DIR = Path(__file__).resolve().parents[2] / "worker"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

ChunkRunner = Callable[[list[tuple[int, bytes]]], list[dict | BaseException]]

YTDLP_FORMAT = "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]"
MODAL_APP, MODAL_CLASS = "badminton-ai-worker", "BadmintonWorker"
LOCAL_MODELS_DIR = Path(os.environ.get("SHUTTLEYE_MODELS_DIR", "~/.cache/shuttleye-eval/models")).expanduser()
SHUTTLESET_TOLERANCE = 3   # frames; the eval's default


def download_720p(url: str, out_dir: Path) -> Path:
    """Download `url` at <=720p into out_dir/match.mp4 with yt-dlp (Python API
    when importable, else the yt-dlp executable)."""
    out = Path(out_dir) / "match.mp4"
    opts = {"format": YTDLP_FORMAT, "outtmpl": str(out), "merge_output_format": "mp4",
            "quiet": True, "no_warnings": True}
    try:
        import yt_dlp
    except ImportError:
        exe = shutil.which("yt-dlp")
        if exe is None:
            raise RuntimeError("yt-dlp is not installed (pip install yt-dlp, or put yt-dlp on PATH)")
        subprocess.run([exe, "-q", "--no-warnings", "-f", YTDLP_FORMAT, "--merge-output-format", "mp4",
                        "-o", str(out), url], check=True)
    else:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    if not out.exists():
        raise RuntimeError(f"yt-dlp finished but {out} is missing")
    return out


def modal_runner(max_containers: int = 50) -> ChunkRunner:
    """Chunks analysed in parallel by the deployed worker's analyze_chunk."""
    import modal

    cls = modal.Cls.from_name(MODAL_APP, MODAL_CLASS).with_options(max_containers=max_containers)

    def run(jobs):
        return list(cls().analyze_chunk.starmap(jobs, return_exceptions=True))
    return run


def local_runner(models_dir: Path = LOCAL_MODELS_DIR) -> ChunkRunner:
    """Chunks analysed one after another on this machine, with the worker's
    models from `models_dir` ($SHUTTLEYE_MODELS_DIR). Same files the Modal
    worker loads (app.MODEL_TARGETS / OPTIONAL_MODEL_TARGETS)."""
    from app import MODEL_TARGETS, OPTIONAL_MODEL_TARGETS
    from fullmatch.run import analyze_chunk_clip
    from inference import BadmintonInference

    models_dir = Path(models_dir).expanduser()
    missing = [f for f in MODEL_TARGETS.values() if not (models_dir / f).exists()]
    if missing:
        raise RuntimeError(f"local runner: {missing} not in {models_dir} (set SHUTTLEYE_MODELS_DIR)")

    def path(key):
        f = models_dir / {**MODEL_TARGETS, **OPTIONAL_MODEL_TARGETS}[key]
        return str(f) if f.exists() else None

    inference = BadmintonInference(
        path("tracknet"), path("court_kprcnn"), path("net_kprcnn"), path("yolo_pose"),
        lstm_path=path("lstm"), tracknet_v3_path=path("tracknet_v3"), inpaintnet_path=path("inpaintnet"),
        hit_detector_path=path("hit_detector"), bst_path=path("bst"), bst0_path=path("bst0"))

    def run(jobs):
        out = []
        for chunk_id, clip in jobs:
            try:
                out.append(analyze_chunk_clip(inference, chunk_id, clip))
            except Exception as exc:     # one lost chunk must not lose the match
                out.append(exc)
        return out
    return run


class Analyzer:
    """The analysis steps ingest times separately. `analyse` returns the
    merged internal result; segment and scoreboard work on it in place;
    `product` is the analyzer's product contract (data-flow.md section 7)."""
    name = "base"

    def analyse(self, video: Path) -> dict:
        raise NotImplementedError

    def segment(self, res: dict) -> None:
        from fullmatch.run import apply_segmentation, default_shot_stack
        apply_segmentation(res, shot_stack=default_shot_stack() or False)

    def scoreboard(self, res: dict, video: Path) -> None:
        # Optional, as inside analyze_full_match: a crash is recorded in skippedSteps.
        from fullmatch.run import _optional_step, apply_scoreboard
        _optional_step("scoreboard", res, ("rallies", "scoreTimeline", "scoreEvents", "sides", "models"),
                       print, lambda: apply_scoreboard(res, video))

    def product(self, res: dict) -> dict:
        from fullmatch.run import product_result
        return product_result(res)


class ChunkAnalyzer(Analyzer):
    """Cut, analyse chunks with a ChunkRunner, merge. analyze_full_match always
    segments; it runs here without the shot stack or scoreboard, and the
    `segment` step re-segments from rawEvents with them (cheap next to the GPU work)."""

    def __init__(self, name: str, make_runner: Callable[[], ChunkRunner]):
        self.name, self._make_runner = name, make_runner

    def analyse(self, video):
        from fullmatch.run import analyze_full_match
        return analyze_full_match(video, None, analyze_chunks=self._make_runner(), verify_chunks=3,
                                  internal=True, shot_stack=False, scoreboard=False)


class MergedAnalyzer(Analyzer):
    """A saved merged internal result (the eval cache's fullmatch_<stamp>.json
    with its _tracks.json.gz) instead of chunk analysis. The video is still
    needed for the scoreboard read."""
    name = "merged"

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def analyse(self, video):
        from train.eval_shuttleset import _load_merged   # pulls in modal and the worker app
        res, _, _ = _load_merged(self.path)
        res.pop("labels", None)
        return res


def merged_runner(path: str | Path) -> MergedAnalyzer:
    return MergedAnalyzer(path)


def make_analyzer(spec: str) -> Analyzer:
    """'modal' | 'local' | 'merged:<path>'."""
    if spec == "modal":
        return ChunkAnalyzer("modal", modal_runner)
    if spec == "local":
        return ChunkAnalyzer("local", local_runner)
    if spec.startswith("merged:") and len(spec) > len("merged:"):
        return merged_runner(spec[len("merged:"):])
    raise ValueError(f"unknown runner {spec!r}: modal, local or merged:<path>")


def _pct(x):
    return None if x is None else round(x * 100, 1)


def accuracy_from_report(report: dict) -> dict:
    """The eval's whole-match OVERALL numbers (hits after segmentation, serves
    excluded) as 0-100: hitF1 = hits.f1, side = side.accuracy,
    type6 = type.accuracy (6 product groups), ten = ten.accuracy (detailType)."""
    o = report["hits_after"]["excl_serves"]
    return {"hitF1": _pct(o["hits"]["f1"]), "side": _pct(o["side"]["accuracy"]),
            "type6": _pct(o["type"]["accuracy"]), "ten": _pct(o["ten"]["accuracy"])}


def shuttleset_accuracy(res: dict, match: str) -> dict:
    """Score an internal (segmented) result against ShuttleSet's labels for
    `match` with the eval's own scoring. Fetches the labels from GitHub."""
    from train.eval_shuttleset import _labels, _score_full_match   # pulls in modal and the worker app
    _, sets, _ = _labels(match, False)
    return accuracy_from_report(_score_full_match(res, sets, SHUTTLESET_TOLERANCE))
