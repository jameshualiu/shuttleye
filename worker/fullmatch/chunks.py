"""Split a full broadcast into frame-exact, overlapping chunks and merge the
per-chunk pipeline results back into full-video frames.

Pure Python + numpy; video work goes through ffmpeg/ffprobe subprocesses (no
cv2/decord), so this imports on a laptop without the ML stack.
"""
import subprocess
from pathlib import Path

import numpy as np

CHUNK = 1800     # frames per chunk (60 s at 30 fps)
OVERLAP = 60     # frames shared by neighbouring chunks (2 s at 30 fps)

# verify_cut compares frames downscaled to this size, as 8-bit grey.
VERIFY_SIZE = (320, 180)
# Max mean absolute grey-level difference (0-255) between a chunk frame and the
# source frame it should be. A CRF-18 re-encode of the same frame, averaged down
# to 320x180, differs by 0.28-0.63 levels (19 samples over three chunks of the
# Christie broadcast); the neighbouring source frames differed by 0.28-13.4
# (as low as the encode noise in static pre-match footage, 2-13 in play). 1.0
# lets encode noise through with ~1.6x margin. A sample whose neighbours also
# fall under 1.0 can't tell an off-by-one apart, so verify_cut also needs at
# least one decisive sample: its own frame under 1.0 and both neighbours at or
# above it. An off-by-one cut then fails on that sample.
MAX_MEAN_ABS_DIFF = 1.0

# Two chunks' estimates of one boundary hit are paired when this close; same as
# the per-clip hit debounce (pipeline._merge_hits debounce=20), so hits closer
# than this would have been merged inside a single chunk too.
BOUNDARY_MATCH = 20


def plan_chunks(total_frames: int, chunk: int = CHUNK, overlap: int = OVERLAP) -> list[tuple[int, int]]:
    """Inclusive [start, end] frame ranges covering every frame; neighbours share `overlap` frames."""
    if total_frames <= 0:
        return []
    if not 0 <= overlap < chunk:
        raise ValueError("need 0 <= overlap < chunk")
    plan, start = [], 0
    while True:
        end = min(start + chunk - 1, total_frames - 1)
        plan.append((start, end))
        if end == total_frames - 1:
            return plan
        start = end - overlap + 1


def frame_to_sec(frame: int, fps: float) -> float:
    return frame / fps


def _owned_ranges(plan: list[tuple[int, int]], overlap: int) -> list[tuple[int, int]]:
    """Full-video frames each chunk is authoritative for. Inside an overlap the
    later chunk owns frames from its start + overlap // 2, so every frame has
    one owner and each side keeps >= overlap // 2 frames of context."""
    owned = []
    for i, (start, end) in enumerate(plan):
        lo = start + overlap // 2 if i else start
        hi = plan[i + 1][0] + overlap // 2 - 1 if i + 1 < len(plan) else end
        owned.append((lo, hi))
    return owned


def _merge_events(per_chunk: list[list[dict]], plan, overlap: int) -> list[dict]:
    """Join chunk events (already in full-video frames) so each hit appears once.

    Two chunks estimate a boundary hit from different context, so their frames
    can differ by a frame or two and fall either side of the ownership line.
    Around each boundary (the overlap widened by BOUNDARY_MATCH on both sides)
    events from the two chunks are paired one-to-one, closest first, when
    within BOUNDARY_MATCH frames; a pair keeps the estimate of the chunk that
    owns the pair's mean frame. An event only one chunk saw is kept wherever
    it falls. Away from boundaries the ownership rule applies.
    """
    n = len(plan)
    owned = _owned_ranges(plan, overlap)
    windows = [(plan[j + 1][0] - BOUNDARY_MATCH, plan[j][1] + BOUNDARY_MATCH) for j in range(n - 1)]
    lines = [plan[j + 1][0] + overlap // 2 for j in range(n - 1)]   # first frame owned by j + 1
    sides = [([], []) for _ in range(n - 1)]
    kept = []
    for c, evs in enumerate(per_chunk):
        for e in evs:
            f = e["frame"]
            if c > 0 and windows[c - 1][0] <= f <= windows[c - 1][1]:
                sides[c - 1][1].append(e)
            elif c < n - 1 and windows[c][0] <= f <= windows[c][1]:
                sides[c][0].append(e)
            elif owned[c][0] <= f <= owned[c][1]:
                kept.append(e)

    for (left, right), line in zip(sides, lines):
        pairs = sorted((abs(a["frame"] - b["frame"]), i, k)
                       for i, a in enumerate(left) for k, b in enumerate(right)
                       if abs(a["frame"] - b["frame"]) <= BOUNDARY_MATCH)
        used_l, used_r = set(), set()
        for _, i, k in pairs:
            if i in used_l or k in used_r:
                continue
            used_l.add(i)
            used_r.add(k)
            a, b = left[i], right[k]
            kept.append(a if (a["frame"] + b["frame"]) / 2 < line else b)
        kept += [e for i, e in enumerate(left) if i not in used_l]
        kept += [e for k, e in enumerate(right) if k not in used_r]
    return sorted(kept, key=lambda e: e["frame"])


def merge_chunks(results: list[dict], plan: list[tuple[int, int]], overlap: int = OVERLAP) -> dict:
    """Shift each chunk's events/tracking/shuttle to full-video frames.

    Events: each hit once, see _merge_events. Tracking/shuttle: each frame from
    the chunk that owns it, dense (index == frame); frames from a chunk with
    no court, or missing from a chunk's output, are empty entries.
    Input dicts are not modified.
    """
    if len(results) != len(plan):
        raise ValueError(f"{len(results)} chunk results for {len(plan)} planned chunks")
    total = plan[-1][1] + 1 if plan else 0
    tracking = [{"frame": f, "players": []} for f in range(total)]
    shuttle = [{"frame": f, "pos": None, "confidence": 0.0} for f in range(total)]
    per_chunk, chunks = [], []

    for res, (start, end), (lo, hi) in zip(results, plan, _owned_ranges(plan, overlap)):
        court = bool(res.get("court_found"))
        chunks.append({"start": start, "end": end, "court_found": court,
                       "geometry": res.get("geometry") if court else None})
        if not court:
            per_chunk.append([])
            continue
        per_chunk.append([{**e, "frame": e["frame"] + start} for e in res.get("events", [])])
        for t in res.get("tracking", []):
            f = t["frame"] + start
            if lo <= f <= hi:
                tracking[f] = {**t, "frame": f}
        for s in res.get("shuttle_debug", []):
            f = s["frame"] + start
            if lo <= f <= hi:
                shuttle[f] = {**s, "frame": f}

    events = _merge_events(per_chunk, plan, overlap)
    return {"events": events, "tracking": tracking, "shuttle": shuttle, "chunks": chunks}


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def probe_fps(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    num, _, den = out.partition("/")
    return float(num) / float(den or 1)


def count_frames(path: Path) -> int:
    """Video packet count (one packet per frame in mp4/h264); demux only, no decode."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return int(out.split(",")[0])


def cut_exact(src: Path, start: int, n_frames: int, out: Path, fps: float) -> None:
    """Frame-exact re-encode of frames [start, start + n_frames): constant fps,
    no audio, no B-frames, so the MP4 edit list skips nothing and decoded
    index == chunk frame. Skips the work if `out` already exists."""
    out = Path(out)
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part" + out.suffix)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{start / fps:.6f}", "-i", str(src),
         "-frames:v", str(n_frames), "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "18", "-bf", "0", "-r", f"{fps:.6f}", "-fps_mode", "cfr",
         "-movflags", "+faststart", str(tmp)],
        check=True,
    )
    tmp.rename(out)     # a killed run never leaves a truncated chunk behind


def _decode_grey(path: Path, indices) -> dict[int, np.ndarray]:
    """Decode the frames at the given decode-order indices (counted from the
    first frame, no seeking) as small grey images."""
    wanted = sorted({i for i in indices if i >= 0})
    if not wanted:
        return {}
    w, h = VERIFY_SIZE
    select = "+".join(f"eq(n\\,{i})" for i in wanted)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-an",
         "-vf", f"select={select},scale={w}:{h}:flags=area",
         "-fps_mode", "passthrough", "-frames:v", str(len(wanted)),
         "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
        check=True, capture_output=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
    return dict(zip(wanted, frames))


def cut_diffs(src: Path, out: Path, start: int, samples: int = 3) -> list[dict]:
    """For `samples` chunk frames spread over the chunk, the mean abs grey
    difference to source frames start+k-1, start+k, start+k+1."""
    n = count_frames(out)
    ks = sorted({round(i * (n - 1) / max(samples - 1, 1)) for i in range(samples)})
    chunk = _decode_grey(out, ks)
    source = _decode_grey(src, [start + k + d for k in ks for d in (-1, 0, 1)])
    rows = []
    for k in ks:
        row = {"k": k}
        for d, name in ((-1, "prev"), (0, "same"), (1, "next")):
            s = source.get(start + k + d)
            row[name] = None if s is None or k not in chunk else float(
                np.abs(chunk[k].astype(np.int16) - s.astype(np.int16)).mean())
        rows.append(row)
    return rows


def cut_status(rows: list[dict]) -> str:
    """'ok', 'mismatch' (a sampled frame isn't its source frame) or 'static'
    (all samples match, but no sample's neighbours differ enough to rule out
    an off-by-one, e.g. a still end card)."""
    if any(r["same"] is None or r["same"] >= MAX_MEAN_ABS_DIFF for r in rows):
        return "mismatch"
    decisive = any(all(r[k] is None or r[k] >= MAX_MEAN_ABS_DIFF for k in ("prev", "next"))
                   and (r["prev"], r["next"]) != (None, None) for r in rows)
    return "ok" if decisive else "static"


def verify_cut(src: Path, out: Path, start: int, samples: int = 3) -> bool:
    """True when every sampled chunk frame matches its source frame within
    encode noise (MAX_MEAN_ABS_DIFF) and at least one sample is decisive (its
    neighbouring source frames differ by more than that), so an off-by-one
    cut can't pass. Static chunks return False: unverifiable, see cut_status."""
    return cut_status(cut_diffs(src, out, start, samples)) == "ok"
