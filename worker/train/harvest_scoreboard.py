# Ported from COURTSIDE src/badminton/scoreboard.py (harvest_templates),
# jayclim/BadmintonAI at commit 5c356f05cde0ed90c75316c133e0aba495e5232b.
# MIT License, Copyright (c) 2026 Jayden Lim
"""Build the BWF score-graphic digit templates from a labelled ShuttleSet match.

ShuttleSet gives the exact score after every rally, so at each rally end the
digits the graphic shows are known: rows whose glyph count matches the
expected digits are harvested, and each digit's template is the mean glyph
mask. The graphic's row order (A on top or B on top) is unknown, so both are
tried and the one that harvests consistently wins.

Sampling differs from upstream (one frame at min(next rally's last shot - 45,
this rally's last shot + 240)): the overlay lags a rally by 2-15 s and is
hidden during replays, so one frame per rally harvested only 33 of 61
rallies on Axelsen v Christie, with 3 examples of 8 (read as 3 afterwards).
Here every rally is sampled every WINDOW_STEP frames from just before its
serve to just before its last shot, against the score BEFORE it (final by
the next serve, as upstream relies on; at a set start the graphic shows the
finished set's cell plus 0-0).

Output: scoreboard_digits.npz in the eval cache (not committed); upload it to
the models volume for the ingest command:
    modal volume put badminton-models ~/.cache/shuttleye-eval/scoreboard_digits.npz /scoreboard_digits.npz

Needs opencv-python-headless locally. Usage (from worker/):
    python train/harvest_scoreboard.py [--match <ShuttleSet match>] [--offset 0]
"""
import argparse
import csv
import io
import itertools
import json
import pathlib
import sys
import urllib.error
import urllib.request

_WORKER_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKER_DIR))

from train.eval_scoring import parse_rally_scores  # noqa: E402

SHUTTLESET_RAW = "https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/main/ShuttleSet/set"
DEFAULT_MATCH = "Viktor_Axelsen_Jonatan_Christie_YONEX_Thailand_Open_2021_QuarterFinals"
CACHE = pathlib.Path.home() / ".cache" / "shuttleye-eval"
TEMPLATES = CACHE / "scoreboard_digits.npz"
WINDOW_BEFORE_SERVE = 60    # frames before a rally's serve where sampling starts
WINDOW_END_MARGIN = 30      # ... and before its last shot where it stops
WINDOW_STEP = 15            # frames between samples


def _fetch_csv(url: str) -> list[dict]:
    with urllib.request.urlopen(url) as resp:
        return list(csv.DictReader(io.StringIO(resp.read().decode("utf-8-sig"))))


def load_rally_scores(match: str) -> dict[int, list[dict]]:
    """{set_no: parse_rally_scores(...)} for every set ShuttleSet labels
    (frames are ShuttleSet frames; add the label->video offset)."""
    hom = next(r for r in _fetch_csv(f"{SHUTTLESET_RAW}/homography.csv") if r["video"] == match)
    h = json.loads(hom["homography_matrix"])
    far = (float(hom["upleft_x"]), float(hom["upleft_y"]))
    near = (float(hom["downleft_x"]), float(hom["downleft_y"]))
    sets = {}
    for set_num in itertools.count(1):
        try:
            rows = _fetch_csv(f"{SHUTTLESET_RAW}/{match}/set{set_num}.csv")
        except urllib.error.HTTPError as e:
            if e.code == 404 and sets:
                return sets
            raise
        sets[set_num] = parse_rally_scores(rows, h, far, near)


def harvest(video: pathlib.Path, sets: dict[int, list[dict]], offset: int = 0, log=print) -> dict:
    """Digit templates {'0'..'9': mean normalized glyph mask} from one match."""
    import cv2
    import numpy as np

    from fullmatch.scoreboard import calibrate_box, norm_glyph, row_groups

    box = calibrate_box(video)
    if box is None:
        raise RuntimeError("score box not found")
    log(f"[harvest] score box {box}")
    rallies = [(sn, r) for sn in sorted(sets) for r in sets[sn]]
    cap = cv2.VideoCapture(str(video))
    buckets = {k: {d: [] for d in range(10)} for k in ("AB", "BA")}
    n_used = {"AB": 0, "BA": 0}
    finals: dict[int, tuple[int, int]] = {}
    before = (0, 0)                  # score before rally j in its set
    for j, (sn, r) in enumerate(rallies):
        if j and rallies[j - 1][0] != sn:
            before = (0, 0)
        done = [finals[s_] for s_ in sorted(finals) if s_ < sn]
        shown = done + [before]       # what the graphic shows while rally j is played
        lo = r["first"] + offset - WINDOW_BEFORE_SERVE
        hi = r["last"] + offset - WINDOW_END_MARGIN
        for f in range(lo, max(lo, hi) + 1, WINDOW_STEP):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
            ok, fr = cap.read()
            if not ok:
                continue
            groups = row_groups(fr, box)
            for key in ("AB", "BA"):
                assign = []
                for row in ("top", "bot"):
                    want = [str(pair[0] if (row == "top") == (key == "AB") else pair[1]) for pair in shown]
                    got = groups[row]
                    if len(got) != len(want) or any(len(g) != len(w) for g, w in zip(got, want)):
                        break
                    for g, w in zip(got, want):
                        assign += [(int(ch), m) for (_, m), ch in zip(g, w)]
                else:
                    n_used[key] += 1
                    for d, m in assign:
                        buckets[key][d].append(norm_glyph(m))
        before = r["scoreAfter"]
        finals[sn] = r["scoreAfter"]
    cap.release()

    key = "AB" if n_used["AB"] >= n_used["BA"] else "BA"
    other = "BA" if key == "AB" else "AB"
    log(f"[harvest] row order {key}, {n_used[key]} frames usable over {len(rallies)} rallies "
        f"(other order: {n_used[other]})")
    tpl = {str(d): np.mean(v, axis=0) for d, v in buckets[key].items() if v}
    log(f"[harvest] glyphs per digit: { {d: len(v) for d, v in buckets[key].items()} }")
    missing = [d for d in range(10) if str(d) not in tpl]
    if missing:
        log(f"[harvest] WARNING: no examples for digits {missing}")
    return tpl


def main():
    import numpy as np

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--match", default=DEFAULT_MATCH)
    ap.add_argument("--video", default="", help="default: <cache>/<match>/match.mp4")
    ap.add_argument("--offset", type=int, default=0, help="ShuttleSet -> video frame offset")
    ap.add_argument("--out", default=str(TEMPLATES))
    a = ap.parse_args()
    video = pathlib.Path(a.video) if a.video else CACHE / a.match / "match.mp4"
    tpl = harvest(video, load_rally_scores(a.match), a.offset)
    out = pathlib.Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, **tpl)
    print(f"[harvest] wrote {out}")


if __name__ == "__main__":
    main()
