# Ported from COURTSIDE src/badminton/segment.py (and _combined_score / attribute_hits
# from src/badminton/hits.py), jayclim/BadmintonAI at commit
# 5c356f05cde0ed90c75316c133e0aba495e5232b.
# MIT License, Copyright (c) 2026 Jayden Lim
"""Label-free rally segmentation over a merged full-match result.

Primary signal: both players tracked in court ("camera runs"). A broadcast only
shows the calibrated main camera during play; replays, close-ups and crowd
shots lose the in-court near+far detections. COURTSIDE measured both-tracked on
97.6-98.2% of rally frames vs 7-18% of gap frames.

Within each run (padded by RUN_PAD):
  1. the run's hits grouped at gaps over SPLIT_GAP;
  2. a motion-onset serve (fullmatch.serves) searched before each group's
     first hit and prepended to the group;
  3. groups split at dead-shuttle restarts (a non-first hit whose incoming
     speed is ~zero: pickup taps, knock-backs to the server);
  4. wrist gates: a group whose median hit-to-wrist distance is large is
     TrackNet ghost kinks in non-play footage; trailing hits far from any
     wrist are floor/net impacts and are trimmed;
  5. keep rules (keep_group); the rally ends at the last hit's landing
     (upstream find_landing, frame only);
then surviving segments closer than MERGE_SEG are re-merged.

Upstream ran its own kink hit detector; here the hits are our pipeline's merged
events, and `score` (_combined_score) and `v_in` are computed for them from the
merged shuttle track (InpaintNet-filled points excluded, see shuttle_xy). The
changes from upstream values are grouped under "adaptations" below.

Units: positions are converted from 512x288 to 1280x720 (units.SCALE_TO_HD) and
velocities to px per 30-fps frame, so every upstream pixel/speed threshold
below applies unchanged. Frame counts marked (time) are scaled by fps/30.
Pure numpy; no DuckDB, no match_id.
"""
import numpy as np

from fullmatch.serves import MIN_GAP, MIN_SPEED, serve_onset
from fullmatch.units import REF_FPS, SCALE_TO_HD, frames_at, speed_at

# --- segment.py constants (upstream values) ---------------------------------
MERGE_GAP = 45      # frames (time): bridge both-tracked dropouts shorter than this
MIN_RUN = 45        # frames (time): drop camera runs shorter than this (1.5 s)
RUN_PAD = 30        # frames (time): pad each run (a serve can precede the second
                    # player's first in-court detection slightly)
SPLIT_GAP = 90      # frames (time): hits farther apart belong to different rallies
MIN_SOLO_SCORE = 2.0  # a 1-2 hit group must hold an unambiguous contact. Upstream
                      # 3.0 on its own kink hits; our window-max score puts only
                      # 56% of matched hits >= 3 (median 3.4), so 2.0 here
RESTART_SPEED = 2.5   # px/frame (720p, 30 fps): a non-first hit with incoming speed
                      # below this is a dead-shuttle restart
BBOX_TOL = 0.25     # a run's median box height may deviate this fraction from the
                    # match-wide reference
GROUP_WRIST_PX = 150  # px (720p): group MEDIAN hit-to-wrist distance above this =
                      # nobody is striking (real groups ~52 px, spurious ~264 px)
TRAIL_WRIST_PX = 130  # px (720p): trailing hits beyond this from any wrist are
                      # floor/net impacts -- trimmed
MIN_PAIR_DT = 13    # frames (time): a 2-hit group needs at least this between hits
MERGE_SEG = 120     # frames (time): surviving segments closer than this are
                    # fragments of one rally (except pre-serve handling before a
                    # restart; see segment_rallies)

# --- adaptations to our pipeline (tuned on Axelsen v Christie only) ---------
SCORE_WIN = 4       # frames (time): an event's `score` is the best kink within
                    # +-this (upstream hits sit on their kink's peak; ours can be
                    # a few frames off it: at the event frame only 41% of matched
                    # hits score >= 1, the +-4 max puts 87% there)
SERVE_LOOKBACK = 45  # frames (time): a group's serve is searched from this far
                     # before its first hit (upstream searched the whole camera
                     # run once; our runs often hold several rallies)
SERVE_HIT_GAP = 8   # frames (time): a motion onset this close to a detected hit
                    # is that hit (upstream 2 * MIN_GAP = 16, which also swallowed
                    # serves followed by a fast return 13-16 frames later)

# --- hits.py constants (upstream values) ------------------------------------
DELTA = 4           # frames (time): velocity half-window
MIN_DV = 30.0       # |dv| px/frame (720p, 30 fps) normaliser of the score
MIN_TURN = 20.0     # (1-cos)*speed normaliser of the score
MIN_TURN_COS = 0.5  # a reversal needs >= 60 deg turn
GAP_INTERP = 6      # frames (time): interpolate visibility gaps up to this long
WRIST_IDX = (9, 10)  # COCO left/right wrist

SIDES = ("Top", "Bottom")   # pipeline sorts the two players Top first


# ---------------------------------------------------------------------------
# camera runs
# ---------------------------------------------------------------------------

def both_tracked(tracking: list[dict], total_frames: int) -> np.ndarray:
    """bool[frame]: two in-court players (the pipeline keeps at most two,
    after its in-court filter)."""
    out = np.zeros(total_frames, dtype=bool)
    for t in tracking:
        f = t["frame"]
        if 0 <= f < total_frames and len(t.get("players") or []) >= 2:
            out[f] = True
    return out


def camera_runs(tracked: np.ndarray, merge_gap: int = MERGE_GAP,
                min_run: int = MIN_RUN) -> list[tuple[int, int]]:
    """Maximal inclusive [f0, f1] spans of both-tracked frames, dropouts up to
    merge_gap bridged, runs shorter than min_run dropped."""
    idx = np.flatnonzero(tracked)
    if len(idx) == 0:
        return []
    runs = [[int(idx[0]), int(idx[0])]]
    for f in idx[1:]:
        if f - runs[-1][1] <= merge_gap:
            runs[-1][1] = int(f)
        else:
            runs.append([int(f), int(f)])
    return [(a, b) for a, b in runs if b - a >= min_run]


def box_heights(tracking: list[dict], total_frames: int) -> np.ndarray:
    """(total_frames, 2) box heights of the Top and Bottom player on frames
    with two players; NaN elsewhere."""
    h = np.full((total_frames, 2), np.nan)
    for t in tracking:
        f, ps = t["frame"], t.get("players") or []
        if 0 <= f < total_frames and len(ps) >= 2:
            for k in range(2):
                b = ps[k].get("box") or []
                if len(b) == 4:
                    h[f, k] = b[3] - b[1]
    return h


def filter_runs_by_bbox(runs: list[tuple[int, int]], box_heights: np.ndarray,
                        tol: float = BBOX_TOL) -> list[tuple[int, int]]:
    """Keep runs whose median box height (per player column) is within `tol`
    of the median over all runs. Rally runs dominate and cluster tightly;
    close-ups and zoomed replays land far off. 0/NaN heights are missing."""
    if not runs:
        return []
    h = np.asarray(box_heights, dtype=float)
    if h.ndim == 1:
        h = h[:, None]
    h = np.where(h > 0, h, np.nan)
    meds = []
    for a, b in runs:
        seg = h[a:b + 1]
        meds.append([np.nanmedian(c) if np.isfinite(c).any() else np.nan for c in seg.T])
    meds = np.array(meds)
    ref = np.array([np.nanmedian(c) if np.isfinite(c).any() else np.nan for c in meds.T])
    keep = []
    for run, m in zip(runs, meds):
        ok = all(np.isfinite(mi) and np.isfinite(ri) and abs(mi - ri) <= tol * ri
                 for mi, ri in zip(m, ref))
        if ok:
            keep.append(run)
    return keep


# ---------------------------------------------------------------------------
# per-hit features
# ---------------------------------------------------------------------------

def shuttle_xy(shuttle: list[dict], total_frames: int) -> np.ndarray:
    """(total_frames, 2) detected shuttle positions in 1280x720 px; NaN when
    unseen. InpaintNet-filled points count as unseen: upstream works on
    TrackNet's visible detections only, and where the shuttle is out of sight
    for long (before a serve) the inpainted track is a repeating 16-frame
    pattern moving at serve speed, which fires the serve detector."""
    xy = np.full((total_frames, 2), np.nan)
    for s in shuttle:
        f, p = s["frame"], s.get("pos")
        if p is not None and not s.get("inpainted") and 0 <= f < total_frames:
            xy[f] = (p[0] * SCALE_TO_HD, p[1] * SCALE_TO_HD)
    return xy


def interpolate_gaps(xy: np.ndarray, max_gap: int = GAP_INTERP) -> np.ndarray:
    """Linear fill of NaN gaps of at most `max_gap` frames between two seen
    frames. (Upstream's pandas interpolate(limit=6) also part-fills the first
    6 frames of longer gaps; only short gaps are filled here, as intended.)"""
    out = xy.copy()
    seen = np.flatnonzero(~np.isnan(xy[:, 0]))
    for a, b in zip(seen[:-1], seen[1:]):
        gap = b - a - 1
        if 0 < gap <= max_gap:
            t = np.arange(1, gap + 1)[:, None] / (gap + 1)
            out[a + 1:b] = xy[a] + t * (xy[b] - xy[a])
    return out


def combined_score(v_in: np.ndarray, v_out: np.ndarray,
                   min_dv: float = MIN_DV, min_turn: float = MIN_TURN) -> float:
    """Normalised union of two contact signals (>= 1.0 means 'hit'): |dv|
    (accelerations) and (1-cos)*speed (reversals, incl. slow net play)."""
    sp_in, sp_out = float(np.linalg.norm(v_in)), float(np.linalg.norm(v_out))
    s_dv = float(np.linalg.norm(v_out - v_in)) / min_dv
    s_turn = 0.0
    if sp_in > 1.0 and sp_out > 1.0:
        cos = float(np.dot(v_in, v_out) / (sp_in * sp_out))
        if cos < MIN_TURN_COS:
            s_turn = (1.0 - cos) * min(sp_in, sp_out) * DELTA / min_turn
    return max(s_dv, s_turn)


def _score_at(f: int, xy_i: np.ndarray, d: int, vscale: float) -> float:
    n = len(xy_i)
    if d <= f < n - d and not np.isnan(xy_i[[f - d, f, f + d]]).any():
        v_in = (xy_i[f] - xy_i[f - d]) / d * vscale
        v_out = (xy_i[f + d] - xy_i[f]) / d * vscale
        return combined_score(v_in, v_out)
    return 0.0


def _hit_features(f: int, xy_i: np.ndarray, d: int, vscale: float, win: int = 0) -> dict:
    """For an event at frame f: `score`, the largest _combined_score within
    +-win frames (upstream hits sit on their kink's peak by construction; our
    detector's frame can be a few frames off it), `v_in` (px per 30-fps frame)
    at f, and the shuttle position at f, from the interpolated track. None /
    0.0 where the window isn't fully seen."""
    n = len(xy_i)
    out = {"score": max(_score_at(g, xy_i, d, vscale) for g in range(f - win, f + win + 1)),
           "v_in": None, "x": None, "y": None}
    if 0 <= f < n and not np.isnan(xy_i[f]).any():
        out["x"], out["y"] = float(xy_i[f, 0]), float(xy_i[f, 1])
    if d <= f < n and not np.isnan(xy_i[[f - d, f]]).any():
        out["v_in"] = float(np.linalg.norm((xy_i[f] - xy_i[f - d]) / d * vscale))
    return out


def landing_frame(xy: np.ndarray, last_hit: int, search: int = 120, step: int = 2,
                  vscale: float = 1.0) -> int | None:
    """Upstream find_landing, frame only: follow the CONTINUOUS track after the
    last hit (a jump too big for a shuttle = cut/replay, stop there) and take
    its lowest screen point (the floor is the bottom of every flight arc)."""
    n = len(xy)
    land, prev, steps = None, None, 0
    for i in range(last_hit + step, min(n, last_hit + search + 1)):
        if np.isnan(xy[i]).any():
            continue
        if prev is not None and steps:
            gap = i - prev
            dist = float(np.linalg.norm(xy[i] - xy[prev])) * vscale
            if dist > (100.0 if gap == 1 else min(45.0 * gap, 250.0)):
                break
        if land is None or xy[i, 1] > xy[land, 1]:
            land = i
        prev = i
        steps += 1
    return land if land is not None and steps >= 3 else None


def _player_refs(players: list[dict]) -> list[tuple[str | None, list[tuple[float, float]]]]:
    """[(side, [reference points in 720p px])] per player: wrists when
    detected (pipeline skeletons are 0,0 for a missed keypoint), else the box
    centre. Side is Top/Bottom only when both players are present."""
    out = []
    for k, p in enumerate(players):
        sk = p.get("skeleton") or []
        pts = [(sk[j][0] * SCALE_TO_HD, sk[j][1] * SCALE_TO_HD) for j in WRIST_IDX
               if len(sk) > j and (sk[j][0] or sk[j][1])]
        box = p.get("box") or []
        if not pts and len(box) == 4:
            pts = [((box[0] + box[2]) / 2 * SCALE_TO_HD, (box[1] + box[3]) / 2 * SCALE_TO_HD)]
        out.append((SIDES[k] if len(players) == 2 and k < 2 else None, pts))
    return out


def attribute(h: dict, by_frame: dict) -> None:
    """Set h['player'] (Top/Bottom/None) and h['dist_px'] (720p) by the
    nearest wrist (or box centre) within +-1 frame of the hit."""
    h["player"], h["dist_px"] = None, None
    if h.get("x") is None:
        return
    best, best_d, found = None, np.inf, False
    for df in (-1, 0, 1):
        for side, pts in _player_refs(by_frame.get(h["frame"] + df) or []):
            for x, y in pts:
                d = float(np.hypot(x - h["x"], y - h["y"]))
                if d < best_d:
                    best, best_d, found = side, d, True
    if found:
        h["player"], h["dist_px"] = best, best_d


# ---------------------------------------------------------------------------
# grouping rules
# ---------------------------------------------------------------------------

def split_at_restarts(group: list[dict], restart_speed: float = RESTART_SPEED) -> list[list[dict]]:
    """Split at every NON-FIRST hit whose incoming speed (`v_in`, px per 30-fps
    frame) is below restart_speed: a dead-shuttle restart starts from rest,
    like a serve. Each part is judged on its own by keep_group."""
    if len(group) < 2:
        return [group]
    parts = [[group[0]]]
    for h in group[1:]:
        v = h.get("v_in")
        if v is not None and v < restart_speed:
            h["restart"] = True
            parts.append([h])
        else:
            parts[-1].append(h)
    return parts


def _who(h: dict):
    return h.get("side") or h.get("player")


def keep_group(g: list[dict], min_pair_dt: int = MIN_PAIR_DT) -> bool:
    """A plausible rally, judged by structure (upstream _keep_group):
    - mostly attributable to someone (`side`, else the attributed player);
    - 3+ hits: the hitter alternates at least once;
    - 2 hits: at least min_pair_dt frames apart, plus the rule below;
    - 1-2 hits: a serve, or a hit scoring >= MIN_SOLO_SCORE;
    - (not upstream) at least one detected hit: a motion-onset serve with no
      following hit is dropped, so a serve stays attached to the exchange it
      starts (upstream's run-level onset could stand alone; with the onset
      searched before every hit group here, a lone onset part split off by a
      restart would otherwise always survive on isServe)."""
    if not g or all(h.get("isServe") or h.get("serve") for h in g):
        return False
    who = [_who(h) for h in g]
    if sum(p is None for p in who) * 2 > len(g):
        return False
    if len(g) >= 3:
        known = [p for p in who if p is not None]
        return any(a != b for a, b in zip(known, known[1:]))
    if len(g) == 2 and g[1]["frame"] - g[0]["frame"] < min_pair_dt:
        return False
    return any(h.get("isServe") or h.get("serve") for h in g) \
        or any(h.get("score", 0.0) >= MIN_SOLO_SCORE for h in g)


# ---------------------------------------------------------------------------
# full segmentation
# ---------------------------------------------------------------------------

def segment_rallies(events: list[dict], tracking: list[dict], shuttle: list[dict],
                    total_frames: int, fps: float = REF_FPS) -> list[dict]:
    """Rallies over a merged full-match result.

    Returns [{"startFrame", "endFrame", "lastHitFrame", "eventIndices"}] sorted
    by start; endFrame is the last hit's landing (the last hit when the track
    doesn't show one). Serves found by motion onset in a kept rally are
    inserted into `events` (in place, list re-sorted by frame) as
    {"type": "Serve", "isServe": True, "detailType": None, ...};
    eventIndices index the updated list. Events in no rally stay in `events`.
    """
    if total_frames <= 0:
        return []
    T = lambda n: frames_at(n, fps)     # noqa: E731  (time-based frame counts)
    vscale = fps / REF_FPS              # px/frame at fps -> px per 30-fps frame

    runs = camera_runs(both_tracked(tracking, total_frames), T(MERGE_GAP), T(MIN_RUN))
    runs = filter_runs_by_bbox(runs, box_heights(tracking, total_frames), BBOX_TOL)
    if not runs:
        return []

    raw = shuttle_xy(shuttle, total_frames)
    xy_i = interpolate_gaps(raw, T(GAP_INTERP))
    by_frame = {t["frame"]: t.get("players") or [] for t in tracking}
    d = max(1, T(DELTA))

    order = sorted(range(len(events)), key=lambda i: events[i]["frame"])
    used, rows = set(), []
    pad = T(RUN_PAD)
    srv_speed, srv_gap = speed_at(MIN_SPEED, fps), T(MIN_GAP)
    guard = T(SERVE_HIT_GAP)

    def serve_hit(lo, hi, hit_frames):
        # serve_onset skips onsets within 2 * min_gap of a hit
        srv = serve_onset(raw[lo:hi + 1], np.arange(lo, hi + 1), hit_frames, srv_speed, guard / 2)
        if srv is None:
            return None
        h = {**srv, "side": None, "ev": None, "v_in": None,
             "x": float(raw[srv["frame"], 0]), "y": float(raw[srv["frame"], 1])}
        attribute(h, by_frame)
        return h

    for f0, f1 in runs:
        w0, w1 = max(0, f0 - pad), min(total_frames - 1, f1 + pad)
        dh = []
        for i in order:
            f = events[i]["frame"]
            if w0 <= f <= w1 and i not in used:
                used.add(i)
                h = {"frame": f, "side": events[i].get("side"), "ev": events[i],
                     **_hit_features(f, xy_i, d, vscale, T(SCORE_WIN))}
                attribute(h, by_frame)
                dh.append(h)
        if not dh:
            continue
        hit_frames = [h["frame"] for h in dh]

        groups = [[dh[0]]]
        for h in dh[1:]:
            if h["frame"] - groups[-1][-1]["frame"] > T(SPLIT_GAP):
                groups.append([h])
            else:
                groups[-1].append(h)
        # motion-onset serve before each group's first hit; the window runs
        # a little past it so an onset AT the first hit counts as that hit
        prev = w0 - 1
        for g in groups:
            first = g[0]["frame"]
            lo = max(w0, prev + 1, first - T(SERVE_LOOKBACK))
            srv = serve_hit(lo, min(w1, first + 2 * srv_gap), hit_frames) if lo < first else None
            if srv is not None and srv["frame"] < first:
                g.insert(0, srv)
            prev = g[-1]["frame"]
        for g0 in groups:
            for g in split_at_restarts(g0, RESTART_SPEED):
                dists = [h["dist_px"] for h in g if h.get("dist_px") is not None]
                if dists and float(np.median(dists)) > GROUP_WRIST_PX:
                    continue
                while g and (g[-1].get("dist_px") or 0) > TRAIL_WRIST_PX:
                    g.pop()
                if not keep_group(g, T(MIN_PAIR_DT)):
                    continue
                land = landing_frame(xy_i, g[-1]["frame"], T(120), T(2), vscale)
                end = land if land is not None else g[-1]["frame"]
                rows.append({"start": g[0]["frame"], "last": g[-1]["frame"], "end": end,
                             "hits": list(g)})
    rows.sort(key=lambda r: r["start"])

    # re-merge fragments split by a missed hit (gap past SPLIT_GAP)
    # A segment that starts at a restart split, right after a 1-2 hit segment
    # from the same hit group (within SPLIT_GAP), is a serve after pre-serve
    # handling: the short segment is dropped rather than merged, so the rally
    # starts at the serve and not at a pickup tap. Longer segments are merged
    # as upstream (a false mid-rally restart: v_in is noise-zero on ~3% of
    # real strokes).
    merged = []
    for r in rows:
        prev = merged[-1] if merged else None
        if prev is not None and r["hits"][0].get("restart") and len(prev["hits"]) <= 2 \
                and r["start"] - prev["last"] <= T(SPLIT_GAP):
            merged[-1] = r
        elif prev is not None and r["start"] - prev["last"] <= T(MERGE_SEG):
            merged[-1]["last"] = max(merged[-1]["last"], r["last"])
            merged[-1]["end"] = max(merged[-1]["end"], r["end"])
            merged[-1]["hits"] += r["hits"]
        else:
            merged.append(r)

    # insert kept serves as events, then index
    for r in merged:
        for h in r["hits"]:
            if h["ev"] is None:
                h["ev"] = {"frame": h["frame"], "type": "Serve", "isServe": True,
                           "detailType": None, "side": h.get("player"),
                           "source": "serve_onset", "confidence": None,
                           "serveScore": h["score"]}
                events.append(h["ev"])
    events.sort(key=lambda e: e["frame"])
    pos = {id(e): i for i, e in enumerate(events)}
    return [{"startFrame": r["start"], "endFrame": r["end"], "lastHitFrame": r["last"],
             "eventIndices": sorted(pos[id(h["ev"])] for h in r["hits"])}
            for r in merged]
