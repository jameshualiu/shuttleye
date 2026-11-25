"""Time one chunk of analysis on this machine and estimate a full match.

    python -m library.time_local <video> [--start-frame 9000] [--seconds 60]
        [--device mps] [--compare-merged <fullmatch_*.json>]

Cuts one chunk with fullmatch.chunks.cut_exact, runs it through the local
runner, prints seconds, the estimate for a 50-minute match (seconds x the
chunks plan_chunks gives) and, with --compare-merged, the share of the saved
merged hits in that frame range that have a local hit within 3 frames.
Run it with the venv from README.md. The agreement is written to
LOCAL_CHECK (keyed by device) so `--runner local` can warn when it is below 95%.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from . import runners   # puts worker/ on sys.path

MATCH_MINUTES = 50
AGREEMENT_FLOOR = 95.0
TOLERANCE = 3                       # frames
LOCAL_CHECK = Path("~/.cache/shuttleye-models/local-check.json").expanduser()


def estimate_full_match(seconds_per_chunk: float, minutes: float = MATCH_MINUTES, fps: float = 30.0) -> dict:
    """Local time for a whole match: seconds per chunk x the chunks plan_chunks makes."""
    from fullmatch.chunks import plan_chunks
    chunks = len(plan_chunks(int(round(minutes * 60 * fps))))
    total = seconds_per_chunk * chunks
    return {"chunks": chunks, "seconds": total, "minutes": total / 60}


def agreement(saved_frames: list[int], local_frames: list[int], tolerance: int = TOLERANCE) -> float | None:
    """Percent of saved hits with a local hit within `tolerance` frames (None if no saved hits)."""
    if not saved_frames:
        return None
    local = sorted(local_frames)
    hit = sum(1 for f in saved_frames if any(abs(f - g) <= tolerance for g in local))
    return 100.0 * hit / len(saved_frames)


def saved_hit_frames(path: Path, start: int, n_frames: int) -> list[int]:
    """Merged hit frames in [start, start + n_frames), as chunk-local frames."""
    d = json.loads(Path(path).expanduser().read_text())
    ev = d.get("rawEvents") or d["events"]
    return [e["frame"] - start for e in ev if start <= e["frame"] < start + n_frames]


def local_agreement_warning(device: str = "mps") -> str | None:
    """The warning --runner local prints when the last recorded check for `device` is below the floor."""
    try:
        rec = json.loads(LOCAL_CHECK.read_text())[device]
        pct = rec["agreement"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if pct is not None and pct < AGREEMENT_FLOOR:
        return (f"WARNING: local analysis agreed with Modal on only {pct:.1f}% of hits "
                f"(floor {AGREEMENT_FLOOR:.0f}%, checked {rec.get('when', '?')}); "
                "results from --runner local differ from Modal.")
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video")
    ap.add_argument("--start-frame", type=int, default=9000)
    ap.add_argument("--seconds", type=float, default=60, help="chunk length (default 60 s)")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--compare-merged", metavar="PATH", help="saved merged result to compare hit frames with")
    a = ap.parse_args(argv)

    from fullmatch.chunks import cut_exact, probe_fps
    video = Path(a.video).expanduser()
    fps = probe_fps(video)
    n = int(round(a.seconds * fps))
    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "chunk.mp4"
        cut_exact(video, a.start_frame, n, clip, fps)
        data = clip.read_bytes()
    print(f"[time_local] frames {a.start_frame}..{a.start_frame + n - 1} ({a.seconds:g} s at {fps:g} fps)")

    t0 = time.perf_counter()
    run = runners.local_runner(a.device)
    load_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    (res,) = run([(0, data)])
    secs = time.perf_counter() - t0
    if isinstance(res, BaseException):
        print(f"[time_local] chunk failed: {res!r}", file=sys.stderr)
        return 1
    local_frames = [e["frame"] for e in res["events"]]
    print(f"[time_local] model load {load_s:.1f} s; chunk {secs:.1f} s; "
          f"court_found={res['court_found']}; {len(local_frames)} hits")

    est = estimate_full_match(secs * 60 / a.seconds, fps=fps)   # per 60 s chunk
    print(f"[time_local] 50-minute match: {est['chunks']} chunks x {secs * 60 / a.seconds:.1f} s "
          f"= {est['minutes']:.0f} min")

    if a.compare_merged:
        saved = saved_hit_frames(a.compare_merged, a.start_frame, n)
        pct = agreement(saved, local_frames)
        if pct is None:
            print("[time_local] no saved hits in that range to compare")
        else:
            print(f"[time_local] agreement with saved Modal result: {pct:.1f}% of {len(saved)} hits "
                  f"(within {TOLERANCE} frames)")
            LOCAL_CHECK.parent.mkdir(parents=True, exist_ok=True)
            try:
                checks = json.loads(LOCAL_CHECK.read_text())
                checks = checks if isinstance(checks, dict) and "agreement" not in checks else {}
            except (OSError, ValueError):
                checks = {}
            checks[a.device] = {"agreement": round(pct, 1), "hits": len(saved), "when": time.strftime("%Y-%m-%d"),
                                "seconds_per_chunk": round(secs, 1)}
            LOCAL_CHECK.write_text(json.dumps(checks))
            if pct < AGREEMENT_FLOOR:
                print(f"[time_local] WARNING: below {AGREEMENT_FLOOR:.0f}%; --runner local will warn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
