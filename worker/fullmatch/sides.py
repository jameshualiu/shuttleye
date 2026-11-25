"""Alternating-side decode: in singles the hitter alternates every shot.

BST-0 already gives each hit 25 class probabilities (index 0 = unknown, 1-12 Top,
13-24 Bottom) and its own side call is ~99% right; this is a cheap guard on top.
Per rally a two-state Viterbi enforces alternation, then each hit's type is
re-picked within its decoded side. Pure numpy, no torch.
"""
import numpy as np

from fullmatch.bst_inputs import MERGED_TO_PRODUCT, MERGED_TO_TEN, MERGED_TYPES_ZH, TEN_CLASSES

N_TYPES = len(MERGED_TYPES_ZH)          # 12 per side
SERVE_OFFSETS = (10, 11)                # 發短球, 發長球 within a side's 12 classes
P_POSITION = 0.8                        # side evidence for a hit with no probs


def side_probs(probs: np.ndarray) -> np.ndarray:
    """(n, 25) -> (n,) P(Top) = Top mass / (Top + Bottom mass); 0.5 if both are 0."""
    probs = np.asarray(probs, dtype=float).reshape(-1, 1 + 2 * N_TYPES)
    top = probs[:, 1:1 + N_TYPES].sum(axis=1)
    bottom = probs[:, 1 + N_TYPES:].sum(axis=1)
    tot = top + bottom
    return np.where(tot > 0, top / np.where(tot > 0, tot, 1.0), 0.5)


def decode_sides(p_top: np.ndarray, p_alternate: float = 0.95, strong: float = 0.9,
                 eps: float = 0.1) -> tuple[list[str], list[bool]]:
    """Viterbi over Top/Bottom with P(switch) = p_alternate between hits.

    Emissions are P(Top) clipped to [eps, 1 - eps], so one hit's evidence can
    never outvote the alternation prior by itself. `overridden[i]` is True when
    the decoded side disagrees with a hit whose own probability for the other
    side is >= `strong` (from the unclipped input).
    """
    p = np.asarray(p_top, dtype=float)
    n = len(p)
    if n == 0:
        return [], []
    c = np.clip(p, eps, 1 - eps)
    emit = np.log(np.stack([c, 1 - c], axis=1))          # state 0 = Top, 1 = Bottom
    stay, switch = np.log(1 - p_alternate), np.log(p_alternate)
    score = emit[0].copy()
    back = np.zeros((n, 2), dtype=int)
    for i in range(1, n):
        new = np.empty(2)
        for s in (0, 1):
            from_stay, from_switch = score[s] + stay, score[1 - s] + switch
            back[i, s] = s if from_stay >= from_switch else 1 - s
            new[s] = max(from_stay, from_switch) + emit[i, s]
        score = new
    state = int(score.argmax())
    path = [state]
    for i in range(n - 1, 0, -1):
        state = back[i, state]
        path.append(state)
    path.reverse()
    sides = ["Top" if s == 0 else "Bottom" for s in path]
    over = [(s == "Bottom" and p[i] >= strong) or (s == "Top" and 1 - p[i] >= strong)
            for i, s in enumerate(sides)]
    return sides, over


def best_type_within_side(probs: np.ndarray, side: str, exclude_serves: bool = False) -> int:
    """Argmax class index over `side`'s 12 classes (serve classes optionally skipped)."""
    base = 1 if side == "Top" else 1 + N_TYPES
    seg = np.asarray(probs, dtype=float)[base:base + N_TYPES].copy()
    if exclude_serves:
        seg[list(SERVE_OFFSETS)] = -1.0
    return base + int(seg.argmax())


def apply_side_decode(res: dict, log=print) -> dict:
    """Decode alternating sides per rally, in place on res["events"].

    Sets side, sideOverridden, and (for hits with probs, not serves) re-picks
    type / detailType / detailId / typeConfidence within the decoded side.
    Serves and hits without probs join the alternation with positional
    evidence (their current side: 0.8/0.2; unknown: 0.5) and keep their type.
    """
    events = res["events"]
    changed = overridden = retyped = 0
    for r in res.get("rallies", []):
        idx = r["eventIndices"]
        evs = [events[i] for i in idx]
        p_top = np.empty(len(evs))
        for k, e in enumerate(evs):
            if e.get("probs") is not None and not e.get("isServe"):
                p_top[k] = side_probs(np.asarray(e["probs"])[None])[0]
            else:
                p_top[k] = {"Top": P_POSITION, "Bottom": 1 - P_POSITION}.get(e.get("side"), 0.5)
        sides, over = decode_sides(p_top)
        for e, side, o in zip(evs, sides, over):
            changed += e.get("side") != side
            overridden += o
            e["side"], e["sideOverridden"] = side, bool(o)
            if e.get("probs") is None or e.get("isServe"):
                dt = e.get("detailType")
                e["detailId"] = TEN_CLASSES.index(dt) if dt in TEN_CLASSES else None
                continue
            probs = np.asarray(e["probs"])
            dt = e.get("detailType")
            e["detailId"] = TEN_CLASSES.index(dt) if dt in TEN_CLASSES else None
            own = int(probs.argmax())
            own_side = None if own == 0 else ("Top" if own <= N_TYPES else "Bottom")
            base = 1 if side == "Top" else 1 + N_TYPES
            if own_side is None or own_side == side or probs[base:base + N_TYPES].sum() <= 0:
                continue        # own pick already agrees (or nothing to pick from): keep it
            cls = best_type_within_side(probs, side, exclude_serves=True)
            zh = MERGED_TYPES_ZH[(cls - 1) % N_TYPES]
            ten = MERGED_TO_TEN[zh]
            retyped += e.get("detailType") != ten
            e["type"], e["detailType"] = MERGED_TO_PRODUCT[zh], ten
            e["detailId"] = TEN_CLASSES.index(ten)
            e["typeConfidence"] = round(float(probs[cls]), 3)
    log(f"[fullmatch] side decode: {changed} sides changed, {overridden} flagged sideOverridden, "
        f"{retyped} detail types re-picked, of {len(events)} events")
    return res
