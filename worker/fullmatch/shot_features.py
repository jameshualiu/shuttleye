# Ported from COURTSIDE src/badminton/pipeline.py (classify) and
# src/badminton/shotclass.py, jayclim/BadmintonAI at commit
# 5c356f05cde0ed90c75316c133e0aba495e5232b.
# MIT License, Copyright (c) 2026 Jayden Lim
"""Stacked shot classifier: features and inference (no torch/modal; sklearn and
joblib are imported only where a model is loaded).

COURTSIDE (jayclim/BadmintonAI at 5c356f05cde0ed90c75316c133e0aba495e5232b,
pipeline.classify / shotclass) reached 75-88% on ShuttleSet's 10 classes by
stacking gradient-boosted trees over BST-0's probabilities plus court
geometry and contact height. This is that stack on our merged full-match
result, plus the neighbouring strokes' predicted classes (TemPose-TF-ASF's
context idea):

- the 25 BST-0 probabilities (as Task 6 left them on the event)
- hitter / receiver feet and the landing point (= the next hitter's feet, as
  COURTSIDE does: feet are on the floor plane, a mid-air shuttle is not), in
  court coordinates normalised by court size and mirrored so the hitter is
  always at the y = 0 end (COURTSIDE's "hitter at the bottom")
- time since the previous / until the next hit (s) and COURTSIDE's derived
  depth/lateral deltas and speed proxy, with its plausibility gates
- contact height (m) from fullmatch.contact's person ruler
- the previous and next events' 10-class ids from the first pass (Task 6's
  detailId); -1 at rally ends, NaN when the neighbour has no 10-class id

Missing values are NaN; HistGradientBoostingClassifier handles them natively.
"""
from pathlib import Path

import numpy as np

from fullmatch.bst_inputs import TEN_CLASSES, TEN_TO_PRODUCTS
from fullmatch.contact import contact_height
from fullmatch.units import REF_FPS, SCALE_TO_HD

COURT_W, COURT_L = 6.1, 13.4          # pipeline.TARGET_CORNERS (metres)
MAX_DT_S = 2.0                        # COURTSIDE: > 60 frames at 30 fps -> missed hit
MIN_LAND_Y = 5.5 / COURT_L            # COURTSIDE: landing short of 5.5 m didn't cross
NEAREST_FRAMES = 4                    # COURTSIDE merge_asof tolerance for tracks

N_PROBS = 25
GEOMETRY = ["hitter_nx", "hitter_ny", "recv_nx", "recv_ny", "land_nx", "land_ny",
            "dt_prev", "dt_next", "depth_delta", "lat_delta", "speed_proxy", "opp_depth_delta"]
FEATURES = [f"p{i}" for i in range(N_PROBS)] + GEOMETRY + ["contact_h", "prev_type", "next_type"]


# --------------------------------------------------------------------------
# Court coordinates
# --------------------------------------------------------------------------

def homography_from_kp6(kp6) -> np.ndarray:
    """3x3 pixel -> court-metre homography from court_keypoints_6, using the
    same four corners as pipeline.setup_homography (kp6 0, 1, 5, 4 ->
    (0, 0), (W, 0), (W, L), (0, L)). Plain DLT, so no cv2."""
    src = np.array([kp6[0], kp6[1], kp6[5], kp6[4]], dtype=float)
    dst = np.array([[0, 0], [COURT_W, 0], [COURT_W, COURT_L], [0, COURT_L]], dtype=float)
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    h = np.linalg.solve(np.array(a), np.array(b))
    return np.append(h, 1.0).reshape(3, 3)


def _safe_homography(kp6):
    """homography_from_kp6, or None for a degenerate / non-finite court (that
    court's events then get NaN positions instead of failing the stack)."""
    try:
        h = homography_from_kp6(kp6)
    except (np.linalg.LinAlgError, ValueError, TypeError, IndexError):
        return None
    return h if np.isfinite(h).all() else None


def to_court(h: np.ndarray, x: float, y: float) -> np.ndarray:
    p = h @ np.array([x, y, 1.0])
    return p[:2] / p[2]


def foot_pixel(player: dict):
    """Ankle midpoint, else box-bottom centre (pipeline._foot_pixel)."""
    sk = player.get("skeleton") or []
    la = sk[15] if len(sk) > 15 else None
    ra = sk[16] if len(sk) > 16 else None
    if la and ra and (la[0] or la[1]) and (ra[0] or ra[1]):
        return (la[0] + ra[0]) / 2, (la[1] + ra[1]) / 2
    box = player.get("box") or []
    if len(box) == 4:
        return (box[0] + box[2]) / 2, box[3]
    return None


def _chunk_homographies(res: dict):
    """[(start, end, H)] per chunk whose court agrees with the match court
    (not in court_outliers), plus the match court's H as the fallback."""
    match_h = _safe_homography(res["court"]) if res.get("court") else None
    outliers = set(res.get("court_outliers") or [])
    spans = []
    for i, c in enumerate(res.get("chunks") or []):
        kp6 = (c.get("geometry") or {}).get("court_keypoints_6")
        if c.get("court_found") and kp6 and i not in outliers:
            # a degenerate chunk court keeps its span with H None -> NaN there
            spans.append((c["start"], c["end"], _safe_homography(kp6)))
    return spans, match_h


def _h_at(frame, spans, match_h):
    for s, e, h in spans:
        if s <= frame <= e:
            return h
    return match_h


def _slots(players: list, h) -> dict:
    """{"Top": player, "Bottom": player} for one frame. Two players keep the
    pipeline's Top-first order; a lone player goes by its court half."""
    if len(players) >= 2:
        return {"Top": players[0], "Bottom": players[1]}
    if len(players) == 1 and h is not None:
        f = foot_pixel(players[0])
        if f is not None:
            y = to_court(h, *f)[1]
            if np.isfinite(y):
                return {("Top" if y < COURT_L / 2 else "Bottom"): players[0]}
    return {}


def _player_near(by_frame: dict, frame: int, side: str, h):
    for d in sorted(range(-NEAREST_FRAMES, NEAREST_FRAMES + 1), key=abs):
        p = _slots(by_frame.get(frame + d) or [], h).get(side)
        if p is not None:
            return p
    return None


def _ruler_tracks(by_frame: dict) -> dict:
    """Per side: (box heights, box bottoms) in HD px over all two-player frames."""
    out = {"Top": ([], []), "Bottom": ([], [])}
    for players in by_frame.values():
        if len(players) < 2:
            continue
        for side, p in (("Top", players[0]), ("Bottom", players[1])):
            b = p.get("box") or []
            if len(b) == 4 and b[3] > b[1]:
                out[side][0].append((b[3] - b[1]) * SCALE_TO_HD)
                out[side][1].append(b[3] * SCALE_TO_HD)
    return {k: (np.array(hs), np.array(bs)) for k, (hs, bs) in out.items()}


def attach_geometry(res: dict) -> dict:
    """Add hitterM / receiverM (court metres, unmirrored) and contactHeightM to
    every event in res["events"], in place; None where it can't be measured.
    Needs res["tracking"], res["court"] (and optionally chunks/court_outliers,
    res["shuttle"] for hits without location_px)."""
    by_frame = {t["frame"]: t.get("players") or [] for t in res.get("tracking") or []}
    shuttle = {s["frame"]: s.get("pos") for s in res.get("shuttle") or []}
    spans, match_h = _chunk_homographies(res)
    rulers = _ruler_tracks(by_frame)
    for e in res["events"]:
        e["hitterM"] = e["receiverM"] = e["contactHeightM"] = None
        side, f = e.get("side"), e["frame"]
        h = _h_at(f, spans, match_h)
        if side not in ("Top", "Bottom") or h is None:
            continue
        other = "Bottom" if side == "Top" else "Top"
        hitter, receiver = _player_near(by_frame, f, side, h), _player_near(by_frame, f, other, h)
        for key, p in (("hitterM", hitter), ("receiverM", receiver)):
            foot = foot_pixel(p) if p is not None else None
            if foot is not None:
                e[key] = [round(float(v), 3) for v in to_court(h, *foot)]
        loc = e.get("location_px") or shuttle.get(f)
        foot = foot_pixel(hitter) if hitter is not None else None
        box = (hitter or {}).get("box") or []
        if loc is not None and foot is not None and len(box) == 4:
            heights, bottoms = rulers[side]
            ch = contact_height(heights, bottoms, ground_y=foot[1] * SCALE_TO_HD,
                                bottom_y=box[3] * SCALE_TO_HD, shuttle_y=loc[1] * SCALE_TO_HD)
            e["contactHeightM"] = None if np.isnan(ch) else ch
    return res


# --------------------------------------------------------------------------
# Feature matrix
# --------------------------------------------------------------------------

def _norm(xy, side):
    """Court metres -> [0, 1] by court size, mirrored so `side`'s hitter is at y = 0."""
    if xy is None or side not in ("Top", "Bottom"):
        return np.nan, np.nan
    x, y = xy[0] / COURT_W, xy[1] / COURT_L
    return (1 - x, 1 - y) if side == "Bottom" else (x, y)


def _time(e, fps):
    if e.get("timeSec") is not None:
        return float(e["timeSec"])
    return e["frame"] / (fps or REF_FPS)


def _type_id(e):
    d = e.get("detailId")
    return np.nan if d is None else float(d)


def build_features(events: list[dict], rallies: list[dict], fps: float | None = None) -> np.ndarray:
    """(len(events), len(FEATURES)) float matrix, NaN for missing. Neighbours
    (landing, dt, prev/next type) only come from the same rally; an event in
    no rally is its own one-event rally."""
    X = np.full((len(events), len(FEATURES)), np.nan)
    col = {f: i for i, f in enumerate(FEATURES)}
    neighbours = {i: (None, None) for i in range(len(events))}
    for r in rallies:
        idx = sorted(r["eventIndices"], key=lambda i: events[i]["frame"])
        for k, i in enumerate(idx):
            neighbours[i] = (idx[k - 1] if k else None, idx[k + 1] if k + 1 < len(idx) else None)

    for i, e in enumerate(events):
        row = X[i]
        if e.get("probs") is not None and len(e["probs"]) == N_PROBS:
            row[:N_PROBS] = np.asarray(e["probs"], dtype=float)
        prev, nxt = neighbours[i]
        side = e.get("side")
        row[col["hitter_nx"]], row[col["hitter_ny"]] = _norm(e.get("hitterM"), side)
        row[col["recv_nx"]], row[col["recv_ny"]] = _norm(e.get("receiverM"), side)
        t = _time(e, fps)
        if prev is not None:
            dt = t - _time(events[prev], fps)
            row[col["dt_prev"]] = dt if dt <= MAX_DT_S else np.nan
        if nxt is not None:
            dt = _time(events[nxt], fps) - t
            row[col["dt_next"]] = dt if dt <= MAX_DT_S else np.nan
            lx, ly = _norm(events[nxt].get("hitterM"), side)
            if dt <= MAX_DT_S and not (ly < MIN_LAND_Y):      # NaN passes; gated below
                row[col["land_nx"]], row[col["land_ny"]] = lx, ly
        hx, hy = row[col["hitter_nx"]], row[col["hitter_ny"]]
        lx, ly = row[col["land_nx"]], row[col["land_ny"]]
        row[col["depth_delta"]] = ly - hy
        row[col["lat_delta"]] = abs(lx - hx)
        row[col["speed_proxy"]] = np.hypot(lx - hx, ly - hy) / row[col["dt_next"]]
        row[col["opp_depth_delta"]] = ly - row[col["recv_ny"]]
        ch = e.get("contactHeightM")
        row[col["contact_h"]] = np.nan if ch is None else float(ch)
        row[col["prev_type"]] = -1.0 if prev is None else _type_id(events[prev])
        row[col["next_type"]] = -1.0 if nxt is None else _type_id(events[nxt])
    return X


def stack_inputs(res: dict) -> np.ndarray:
    """attach_geometry + build_features on a segmented, side-decoded result:
    the exact inputs both training and inference use."""
    attach_geometry(res)
    return build_features(res["events"], res.get("rallies") or [], fps=res.get("fps"))


def stack_targets(res: dict) -> list[int]:
    """Indices of the events the stack classifies: hits (not serves) that
    carry BST-0's 25 probabilities. A hit typed by a fallback classifier
    (BST-CG-AP, LSTM, rules) has no probs and keeps its type: the stack's
    main inputs would all be NaN."""
    return [i for i, e in enumerate(res["events"])
            if not e.get("isServe") and len(e.get("probs") or ()) == N_PROBS]


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------

_LOADED: dict = {}


def load_stack(path, log=print):
    """The saved bundle {"features", "ten", "six"?, ...}, or None (missing
    file, no sklearn/joblib, or a feature list that isn't FEATURES)."""
    path = Path(path)
    key = str(path)
    if key in _LOADED:
        return _LOADED[key]
    bundle = None
    if path.is_file():
        try:
            import joblib
            bundle = joblib.load(path)
            if list(bundle.get("features", [])) != FEATURES:
                log(f"[shot-stack] {path}: feature list differs from FEATURES; not used")
                bundle = None
        except Exception as exc:           # sklearn missing or version drift
            log(f"[shot-stack] could not load {path} ({exc}); not used")
            bundle = None
    _LOADED[key] = bundle
    return bundle


def apply_shot_stack(res: dict, path, log=print) -> dict:
    """Overwrite detailType / detailId / type / typeConfidence on the
    stack_targets events (non-serve hits with BST-0 probs) with the stack's predictions, in place. Without a usable model
    (path None or missing), or if building features or predicting fails,
    Task 6's classification is kept unchanged."""
    bundle = load_stack(path, log=log) if path else None
    if bundle is None:
        log(f"[shot-stack] no model at {path}; keeping BST-0 + side decode types")
        return res
    events = res["events"]
    res["events"] = [dict(e) for e in events]      # work on copies; originals stay on failure
    try:
        apply_bundle(res, bundle)
    except Exception as exc:     # sklearn drift at predict time, bad geometry, ...
        res["events"] = events
        res.pop("shotStack", None)
        log(f"[shot-stack] stack failed ({type(exc).__name__}: {exc}); keeping BST-0 + side decode types")
        return res
    res["shotStack"]["model"] = str(path)
    log(f"[shot-stack] re-classified {res['shotStack']['applied']} hits with {path}")
    return res


def product_type(ten: str, six_proba: dict | None = None, current=None):
    """Product 6-class `type` for a 10-class pick, through bst_inputs'
    TEN_TO_PRODUCTS, so type and detailType never contradict. The ambiguous
    class (push/rush: Drive or Net) takes the six head's likelier option,
    else the current type when it is an option, else the first option.
    None for serves / unknown names."""
    options = TEN_TO_PRODUCTS.get(ten) or []
    if len(options) <= 1:
        return options[0] if options else None
    if six_proba:
        return max(options, key=lambda o: six_proba.get(o, 0.0))
    return current if current in options else options[0]


def apply_bundle(res: dict, bundle: dict) -> dict:
    """apply_shot_stack with an in-memory bundle (training's held-out scoring).
    Mutates res["events"]; apply_shot_stack guards it."""
    res["shotStack"] = {"applied": 0, "trainedOn": bundle.get("trained_on")}
    idx = stack_targets(res)
    if not idx:
        return res
    X = stack_inputs(res)[idx]
    ten = bundle["ten"]
    proba = ten.predict_proba(X)
    pick = [str(p) for p in ten.classes_[proba.argmax(axis=1)]]
    six = bundle.get("six")
    six_proba = None
    if six is not None and any(len(TEN_TO_PRODUCTS.get(p) or []) > 1 for p in pick):
        six_proba = [dict(zip(map(str, six.classes_), row)) for row in six.predict_proba(X)]
    for k, i in enumerate(idx):
        e = res["events"][i]
        dt = pick[k]
        e["detailType"] = dt
        e["detailId"] = TEN_CLASSES.index(dt) if dt in TEN_CLASSES else None
        e["typeConfidence"] = round(float(proba[k].max()), 3)
        e["type"] = product_type(dt, six_proba[k] if six_proba else None, e.get("type"))
    res["shotStack"]["applied"] = len(idx)
    return res
