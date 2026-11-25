# Ported from COURTSIDE src/badminton/scoreboard.py (align_scores and side_map
# from build() in src/badminton/labelfree.py), jayclim/BadmintonAI at commit
# 5c356f05cde0ed90c75316c133e0aba495e5232b.
# MIT License, Copyright (c) 2026 Jayden Lim
"""Read the BWF score graphic: score after every rally, set boundaries, and
which player is on which end.

The BWF World Tour graphic is two gray name rows with dark score cells to
their right (completed sets first, CURRENT set points last; digits white,
yellow for the server). Digits are template-matched against
`scoreboard_digits.npz`, harvested once from a labelled ShuttleSet match
(train/harvest_scoreboard.py); the file lives in the eval cache and on the
models volume, never in git.

    timeline(video)        sampled reads of the graphic (local cv2 pass)
 -> events(timeline)       debounced score changes
 -> align_scores(rallies)  each change goes to the latest already-ended rally;
                           scores (A, B) with A = the match winner, set finals
                           closed by the scoring rules (score_seq)
 -> side_map(rallies)      per set (and after the 11-point end change in a
                           deciding set) which player is near: the rally
                           winner serves next

Pixel geometry is upstream's, for a 1280x720 frame; other sizes are resized to
720 rows first. cv2 is imported inside the functions that need it, so the
pure part (events / align_scores / side_map) imports without it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from fullmatch import score_seq

GLYPH_SHAPE = (14, 10)   # all glyph masks normalized to this for matching
STRIP_W = 130            # px of score cells right of the name strip
NUM_GAP = 10             # px gap between glyph clusters = separate numbers
MIN_MATCH = 0.55         # min normalized correlation to accept a digit
QUIET_CHROMA = 20        # plain score-cell background chroma (see _content_width)
MIN_QUIET_RUN = 8        # plain columns needed to call a gap real
FRAME_H = 720            # upstream's geometry is in 720p pixels
# Name-strip detection. Upstream (2022 graphics): 0.15 / 25 / 0.5. The 2021
# graphic's gray strip is narrower (~165 of the 680 px searched, so its text
# rows sit at 0.14-0.17) and its player names split the strip's columns into
# runs shorter than 80 px at 0.5, so the box was never found; these are relaxed.
BOX_ROW_FRAC = 0.10      # gray fraction for a row to belong to the strip
BOX_MIN_ROWS = 20        # rows needed
BOX_COL_FRAC = 0.30      # gray fraction (over those rows) for a strip column
FLIPPED = {"near": "far", "far": "near"}


# ------------------------------------------------------------- box location

def _to_720(frame: np.ndarray) -> np.ndarray:
    if frame.shape[0] == FRAME_H:
        return frame
    import cv2
    w = round(frame.shape[1] * FRAME_H / frame.shape[0])
    return cv2.resize(frame, (w, FRAME_H), interpolation=cv2.INTER_AREA)


def locate_rows(frame: np.ndarray):
    """(y0, y1, x0, x1) of the gray name-strip box in this frame, or None."""
    import cv2
    reg = frame[5:100, 80:760]
    g = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY).astype(np.float32)
    chroma = reg.max(axis=2).astype(int) - reg.min(axis=2).astype(int)
    gray = (g > 140) & (g < 240) & (chroma < 45)
    rowfrac = gray.mean(axis=1)
    ys = np.where(rowfrac > BOX_ROW_FRAC)[0]
    if len(ys) < BOX_MIN_ROWS:
        return None
    y0, y1 = ys.min(), ys.max()
    if not 30 <= y1 - y0 <= 70:
        return None
    colfrac = gray[y0:y1 + 1].mean(axis=0)
    xs = np.where(colfrac > BOX_COL_FRAC)[0]
    if len(xs) < 80:
        return None
    runs, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] <= 4:
            cur.append(x)
        else:
            runs.append(cur)
            cur = [x]
    runs.append(cur)
    best = max(runs, key=len)
    if len(best) < 80:
        return None
    return int(y0) + 5, int(y1) + 5, int(best[0]) + 80, int(best[-1]) + 80


def calibrate_box(video: Path, n: int = 120):
    """Median box geometry over sampled frames (the graphic is static)."""
    import cv2
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    boxes = []
    for f in np.linspace(total * 0.1, total * 0.9, n).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, fr = cap.read()
        if ok:
            b = locate_rows(_to_720(fr))
            if b:
                boxes.append(b)
    cap.release()
    if len(boxes) < n * 0.25:
        return None
    return tuple(int(np.median([b[i] for b in boxes])) for i in range(4))


# ----------------------------------------------------------- glyph extraction

def _content_width(strip: np.ndarray) -> int:
    """How much of the strip, from x=0, is score-cell territory: cut at the
    last run of >= MIN_QUIET_RUN plain-background columns when a decorative
    badge follows the cells (its background stays saturated to the edge)."""
    import cv2
    g = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY).astype(int)
    bgr = strip.astype(int)
    chroma = bgr.max(axis=2) - bgr.min(axis=2)
    white = (g > 150) & (chroma < 70)
    yellow = (g > 110) & (bgr[:, :, 2] > 140) & (bgr[:, :, 1] > 140) & (bgr[:, :, 0] < 120)
    bg_chroma = np.where(white | yellow, -1, chroma)
    run = 0
    for x in range(strip.shape[1] - 1, -1, -1):
        col = bg_chroma[:, x]
        col = col[col >= 0]
        plain = len(col) == 0 or np.median(col) < QUIET_CHROMA
        if not plain:
            run = 0
            continue
        run += 1
        if run >= MIN_QUIET_RUN:
            return x + MIN_QUIET_RUN
    return strip.shape[1]


def _row_glyphs(strip: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """Bright digit glyphs on dark cell background in one row strip."""
    import cv2
    strip = strip[:, :_content_width(strip)]
    g = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY).astype(int)
    bgr = strip.astype(int)
    chroma = bgr.max(axis=2) - bgr.min(axis=2)
    white = (g > 150) & (chroma < 70)
    yellow = (g > 110) & (bgr[:, :, 2] > 140) & (bgr[:, :, 1] > 140) & (bgr[:, :, 0] < 120)
    mask = (white | yellow).astype(np.uint8)
    nlab, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    H = mask.shape[0]
    out = []
    for i in range(1, nlab):
        x, y, w, h, area = stats[i]
        if not (H * 0.45 <= h <= H * 0.9) or not (4 <= w <= 16) or area < 12:
            continue
        # digits sit on a dark cell; logo/feather edges don't
        x0, x1 = max(0, x - 2), min(strip.shape[1], x + w + 2)
        y0, y1 = max(0, y - 1), min(H, y + h + 1)
        around = g[y0:y1, x0:x1][lab[y0:y1, x0:x1] != i]
        if len(around) == 0 or np.median(around) > 100:
            continue
        out.append((int(x), (lab[y:y + h, x:x + w] == i).astype(np.uint8)))
    out.sort(key=lambda t: t[0])
    return out


def row_strips(frame: np.ndarray, box) -> dict[str, np.ndarray]:
    y0, y1, x0, x1 = box
    h2 = (y1 - y0) // 2
    return {"top": frame[y0:y0 + h2 + 1, x1 + 1:x1 + STRIP_W],
            "bot": frame[y1 - h2:y1 + 1, x1 + 1:x1 + STRIP_W]}


def norm_glyph(mask: np.ndarray) -> np.ndarray:
    import cv2
    return cv2.resize(mask.astype(np.float32), GLYPH_SHAPE[::-1], interpolation=cv2.INTER_AREA)


def group_numbers(glyphs: list[tuple[int, np.ndarray]]) -> list[list]:
    """Cluster x-sorted glyphs into numbers (cells) split at gaps > NUM_GAP."""
    if not glyphs:
        return []
    groups = [[glyphs[0]]]
    for x, m in glyphs[1:]:
        px, pm = groups[-1][-1]
        if x - (px + pm.shape[1]) > NUM_GAP:
            groups.append([(x, m)])
        else:
            groups[-1].append((x, m))
    return groups


def row_groups(frame: np.ndarray, box) -> dict[str, list[list]]:
    """{'top'|'bot': glyph groups (one per score cell)} for a frame (any size)."""
    return {row: group_numbers(_row_glyphs(strip))
            for row, strip in row_strips(_to_720(frame), box).items()}


# ------------------------------------------------------------- reading

def load_templates(path: Path) -> dict[str, np.ndarray]:
    z = np.load(path)
    return {k: z[k] for k in z.files}


def _classify(mask: np.ndarray, tpl: dict[str, np.ndarray]) -> str | None:
    v = norm_glyph(mask).ravel()
    v = v - v.mean()
    nv = np.linalg.norm(v)
    if nv == 0:
        return None
    best, best_c = None, MIN_MATCH
    for ch, t in tpl.items():
        u = t.ravel() - t.mean()
        c = float(np.dot(u, v) / (np.linalg.norm(u) * nv + 1e-9))
        if c > best_c:
            best, best_c = ch, c
    return best


def read_frame(frame: np.ndarray, box, templates) -> dict | None:
    """{'top': [nums...], 'bot': [nums...]} (cells left to right) or None."""
    out = {}
    for row, groups in row_groups(frame, box).items():
        nums = []
        for group in groups:
            digits = [_classify(m, templates) for _, m in group]
            if any(d is None for d in digits):
                return None
            nums.append(int("".join(digits)))
        out[row] = nums
    if not out["top"] or not out["bot"] or len(out["top"]) != len(out["bot"]):
        return None
    return out


def timeline(video: Path, fps: float, step: int = 30, templates=None, box=None,
             log=print) -> list[dict]:
    """Readable score samples over the whole video, one every `step` frames at
    30 fps (scaled to the video's fps): [{"frame", "cells", "top", "bot",
    "topAll", "botAll"}]. Reads the video sequentially (grab, decode only the
    sampled frames). Empty when the graphic is never found."""
    import cv2
    if templates is None:
        raise ValueError("templates are required (load_templates(scoreboard_digits.npz))")
    box = box or calibrate_box(video)
    if box is None:
        log(f"[scoreboard] score box not found in {video}")
        return []
    every = max(1, round(step * fps / 30))
    cap = cv2.VideoCapture(str(video))
    rows, f, sampled = [], 0, 0
    try:
        while cap.grab():
            if f % every == 0:
                ok, fr = cap.retrieve()
                sampled += 1
                r = read_frame(fr, box, templates) if ok else None
                if r is not None:
                    rows.append({"frame": f, "cells": len(r["top"]), "top": r["top"][-1],
                                 "bot": r["bot"][-1], "topAll": r["top"], "botAll": r["bot"]})
            f += 1
    finally:
        cap.release()
    log(f"[scoreboard] timeline: {len(rows)} readable samples of {sampled} (every {every} frames), box {box}")
    return rows


# ------------------------------------------------------------- score events

def events(tl: list[dict]) -> list[dict]:
    """Score changes from a timeline. A reading is accepted only when two
    consecutive samples agree (kills one-sample misreads). Each event:
    {"frame" (first appearance), "set" (1 + completed-set cells), "score"
    (top, bot), "newSet", "winner" ('top'|'bot' when exactly one row gained),
    "jump" (points gained, None at a set start)}. The overlay can update 15+ s
    late, so events are aligned to rallies by order (align_scores)."""
    ev = []
    prev = None          # accepted (cells, top, bot)
    pend = None          # (candidate, frame) awaiting confirmation
    for r in tl:
        cur = (int(r["cells"]), int(r["top"]), int(r["bot"]))
        if prev is not None and cur == prev:
            pend = None
            continue
        if pend is not None and cur == pend[0]:
            nc, t, b = cur
            new_set = prev is not None and (nc > prev[0] or (t < prev[1] and b < prev[2]))
            if prev is None or new_set:
                winner = None
            else:
                dt, db = t - prev[1], b - prev[2]
                winner = "top" if dt > 0 and db == 0 else "bot" if db > 0 and dt == 0 else None
            ev.append({"frame": int(pend[1]), "set": nc, "score": (t, b), "newSet": bool(new_set),
                       "winner": winner,
                       "jump": None if prev is None or new_set else max(t - prev[1], b - prev[2])})
            prev = cur
            pend = None
        else:
            pend = (cur, r["frame"])
    return ev


def _match_winner_row(set_final: dict[int, tuple[int, int]]) -> str:
    top_sets = sum(t > b for t, b in set_final.values())
    bot_sets = sum(b > t for t, b in set_final.values())
    if top_sets != bot_sets:
        return "top" if top_sets > bot_sets else "bot"
    t, b = set_final[max(set_final)]        # a set end was missed: the last set decides
    return "bot" if b > t else "top"        # (upstream: a tie goes to bot; here to top)


def align_scores(rallies: list[dict], score_events: list[dict]) -> list[dict]:
    """Attach the score to frame-ordered rallies, in place (and returned).

    Each event goes to the LATEST already-ended unassigned rally (endFrame <=
    event frame); earlier unassigned rallies are passed over for good. 0-0
    events (a set opening) are not given to a rally. Scores are (A, B) with A =
    the row that wins the match (ShuttleSet's convention); a rally without an
    event keeps the previous score and no winner. The last rally of each set
    gets the set's final from the legal point log (score_seq), which finishes
    a set the broadcast cut away from on set point.

    Sets on each rally: "set", "scoreAfter" (A, B), "winner" ('A'|'B'|None),
    "scoreRead" (an event was assigned). Events missing "set" count as set 1.
    """
    for r in rallies:
        r["set"], r["scoreAfter"], r["winner"], r["scoreRead"] = None, None, None, False
    if not rallies or not score_events:
        return rallies
    evs = [{**e, "set": int(e.get("set", 1))} for e in score_events]

    assigned: dict[int, dict] = {}
    unassigned = list(range(len(rallies)))
    for e in evs:
        if tuple(e["score"]) == (0, 0):
            continue
        cands = [i for i in unassigned if rallies[i]["endFrame"] <= e["frame"]]
        if not cands:
            continue
        assigned[cands[-1]] = e
        unassigned = [j for j in unassigned if j not in cands]

    set_final = {}
    for e in evs:
        set_final[e["set"]] = tuple(e["score"])
    row_a = _match_winner_row(set_final)

    def oriented(score):
        t, b = score
        return (t, b) if row_a == "top" else (b, t)

    # set of each rally: its event's, else the next assigned rally's
    nxt = max(set_final)
    for i in range(len(rallies) - 1, -1, -1):
        if i in assigned:
            nxt = assigned[i]["set"]
        rallies[i]["set"] = nxt

    # A set whose last reading isn't a finished game lost its set-point
    # reading (the broadcast cut away): the unread rally right after its last
    # read rally is that set point, not the next set's first rally.
    plog = score_seq.point_log([(e["set"], e["score"][0], e["score"][1], k) for k, e in enumerate(evs)])
    finals = score_seq.set_finals(plog)
    for sn in finals:
        read = [i for i in assigned if assigned[i]["set"] == sn]
        if not read or score_seq.is_final(*assigned[max(read)]["score"]):
            continue
        j = max(read) + 1
        if j < len(rallies) and j not in assigned and rallies[j]["set"] != sn:
            rallies[j]["set"] = sn

    prev: dict[int, tuple[int, int]] = {}
    for i, r in enumerate(rallies):
        sn = r["set"]
        pa, pb = prev.get(sn, (0, 0))
        e = assigned.get(i)
        if e is None:
            r["scoreAfter"] = (pa, pb)
        else:
            a, b = oriented(e["score"])
            r["scoreAfter"], r["scoreRead"] = (a, b), True
            w = e.get("winner")
            r["winner"] = None if w not in ("top", "bot") else ("A" if w == row_a else "B")
            if (a - pa, b - pb) == (1, 0):
                r["winner"] = "A"
            elif (a - pa, b - pb) == (0, 1):
                r["winner"] = "B"
        prev[sn] = r["scoreAfter"]

    for sn, final in finals.items():
        fa, fb = oriented(final)
        in_set = [i for i, r in enumerate(rallies) if r["set"] == sn]
        if not in_set or rallies[in_set[-1]]["scoreAfter"] == (fa, fb):
            continue
        k = in_set[-1]
        pa, pb = rallies[in_set[-2]]["scoreAfter"] if len(in_set) > 1 else (0, 0)
        rallies[k]["scoreAfter"] = (fa, fb)
        da, db = fa - pa, fb - pb
        if da or db:                      # who took the game-winning rally
            rallies[k]["winner"] = "A" if da >= db else "B"
    return rallies


# ------------------------------------------------------------- side map

def side_map(rallies: list[dict]) -> list[dict]:
    """Which player (A = match winner) is near, per set and after the
    deciding set's end change at 11; also sets rally["near"] ('A'|'B'|None).

    Needs per rally "set", "scoreAfter", "winner" (align_scores) and
    "serveSide" ('near'|'far'|None, the serve's end). The rally winner serves
    the next rally, so each single-point rally followed by a rally of the same
    set is one vote for A's end. The rules fix everything but one bit: ends
    alternate between sets and a deciding set (3rd) changes ends when the
    leader reaches 11; A's set-1 end is fitted on all sets' votes pooled.

    Returns [{"set", "fromRally" (index into rallies), "fromScore" (A, B
    before that rally), "near", "far"}] in rally order; [] without votes.
    """
    for r in rallies:
        r["near"] = None
    sets = sorted({r["set"] for r in rallies if r.get("set") is not None})
    if not sets:
        return []
    prev_score, counter, ids = [], {}, []
    last: dict[int, tuple[int, int]] = {}
    for r in rallies:
        sn = r.get("set")
        prev_score.append(last.get(sn, (0, 0)))
        counter[sn] = counter.get(sn, 0) + 1
        ids.append(counter[sn])
        if r.get("scoreAfter") is not None:
            last[sn] = tuple(r["scoreAfter"])

    votes: dict[int, list[tuple[int, str]]] = {}     # set -> [(rally id in set, A's end)]
    for i, r in enumerate(rallies[:-1]):
        sn, w, s = r.get("set"), r.get("winner"), r.get("scoreAfter")
        if sn is None or w not in ("A", "B") or s is None:
            continue
        pa, pb = prev_score[i]
        if (s[0] - pa) + (s[1] - pb) != 1:
            continue                                  # a rally (or a reading) was missed
        nxt = rallies[i + 1]
        if nxt.get("set") != sn or nxt.get("serveSide") not in ("near", "far"):
            continue                                  # set point: next serve is next set's
        a_side = nxt["serveSide"] if w == "A" else FLIPPED[nxt["serveSide"]]
        votes.setdefault(sn, []).append((ids[i + 1], a_side))
    if not votes:
        return []

    flip_at: dict[int, int] = {}
    deciding = sets[-1]
    if deciding >= 3:
        in_set = [i for i, r in enumerate(rallies) if r.get("set") == deciding]
        cands = [ids[i] for i in in_set if max(prev_score[i]) == 11]
        if not cands:                                 # the point at 11 was missed
            cands = [ids[i] for i in in_set if max(prev_score[i]) in (10, 12)]
        if cands:
            flip_at[deciding] = min(cands)

    def start(sn, s1):
        return s1 if (sn - 1) % 2 == 0 else FLIPPED[s1]

    def a_side_at(sn, rid, s1):
        k = flip_at.get(sn)
        s = start(sn, s1)
        return s if k is None or rid < k else FLIPPED[s]

    best = None
    for s1 in ("near", "far"):
        score = sum(a_side_at(sn, rid, s1) == s for sn, vs in votes.items() for rid, s in vs)
        if best is None or score > best[0]:
            best = (score, s1)
    s1 = best[1]

    out, cur = [], None
    for i, r in enumerate(rallies):
        sn = r.get("set")
        if sn is None:
            continue
        near = "A" if a_side_at(sn, ids[i], s1) == "near" else "B"
        r["near"] = near
        if cur != (sn, near):
            out.append({"set": sn, "fromRally": i, "fromScore": prev_score[i], "near": near,
                        "far": "B" if near == "A" else "A"})
            cur = (sn, near)
    return out


def rally_serve_sides(res: dict) -> None:
    """rally["serveSide"]: the server's end ('near' = Bottom). A rally that
    opens on a serve (isServe) is served from that event's end. One that opens
    on a plain hit has lost its serve (no kink and no motion onset), and that
    first hit is then mostly the RETURN, so the server is at the other end
    (opposite in 66 of 74 such rallies on 3 ShuttleSet matches; taking its own
    end put the side map wrong on 2 of the 5 matches)."""
    events = res["events"]
    for r in res["rallies"]:
        e = events[r["eventIndices"][0]] if r.get("eventIndices") else {}
        side = {"Bottom": "near", "Top": "far"}.get(e.get("side"))
        r["serveSide"] = side if side is None or e.get("isServe") else FLIPPED[side]
