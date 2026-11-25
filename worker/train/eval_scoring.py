# worker/train/eval_scoring.py
"""
Scoring for the offline ShuttleSet accuracy eval (eval_shuttleset.py).

Pure Python on purpose -- no torch/decord/numpy -- so worker/tests/ can import
it directly instead of mirroring it.

Compares pipeline output (analysis.json "events") against ShuttleSet per-shot
labels for one rally clip:
  - hits:      one-to-one matching within +/- tolerance frames (precision/recall/F1)
  - side:      Top/Bottom hitter on matched hits
  - shot type: product 6-class type on matched hits (+ confusion matrix)

Serves are excluded from hit ground truth (same as hit-detector training, see
train/extract_features.py), and predicted hits that land on a serve are dropped
rather than counted as false positives.
"""
from collections import Counter

# Mirrors train/extract_features.SERVICE_TYPES_ZH (not imported: that module
# pulls in torch and decord at import time).
SERVICE_TYPES_ZH = {"發短球", "發長球"}
UNKNOWN_TYPE_ZH = "未知球種"

# ShuttleSet label -> product 6-class taxonomy (Clear/Smash/Drop/Drive/Net/Lob),
# consistent with detectors/stroke_classifier.TYPE_EN + PRODUCT_TYPE. The
# ShuttleSet-only fine-grained labels are folded into their parent class.
ZH_TO_PRODUCT = {
    "放小球": "Net",      # net shot
    "擋小球": "Net",      # block
    "撲球": "Net",        # net kill
    "勾球": "Net",        # cross-court net
    "殺球": "Smash",
    "點扣": "Smash",      # wrist smash
    "挑球": "Lob",        # lift
    "防守回挑": "Lob",    # defensive lift
    "長球": "Clear",
    "平球": "Drive",
    "推球": "Drive",      # push
    "防守回抽": "Drive",  # defensive drive
    "小平球": "Drive",    # driven flight
    "後場抽平球": "Drive",  # back-court drive
    "切球": "Drop",
    "過度切球": "Drop",   # passive drop
}

# ShuttleSet label -> the 10 canonical shot classes (short service, long service,
# clear, drive, drop, lob, net shot, smash, push/rush, defensive shot). Copied from
# COURTSIDE's ShuttleSet CN->EN map (jayclim/BadmintonAI, src/badminton/shuttleset.py
# at commit 5c356f05cde0ed90c75316c133e0aba495e5232b, MIT License), i.e. the
# official ShuttleSet22 two-step mapping flattened. 小平球 and 未知球種 are unmapped.
ZH_TO_TEN = {
    "發短球": "short service",
    "發長球": "long service",
    "長球": "clear",
    "平球": "drive",
    "後場抽平球": "drive",
    "切球": "drop",
    "過度切球": "drop",
    "挑球": "lob",
    "放小球": "net shot",
    "勾球": "net shot",
    "殺球": "smash",
    "點扣": "smash",
    "推球": "push/rush",
    "撲球": "push/rush",
    "擋小球": "defensive shot",
    "防守回挑": "defensive shot",
    "防守回抽": "defensive shot",
}

PRODUCT_TYPES = ["Clear", "Drive", "Drop", "Lob", "Net", "Smash"]


def project(h, x, y):
    """Apply a 3x3 homography (nested lists) to a pixel point."""
    px = h[0][0] * x + h[0][1] * y + h[0][2]
    py = h[1][0] * x + h[1][1] * y + h[1][2]
    pw = h[2][0] * x + h[2][1] * y + h[2][2]
    return px / pw, py / pw


def side_from_location(h, far_corner, near_corner, x, y):
    """Top/Bottom for a player at pixel (x, y), using ShuttleSet's per-match
    pixel->court homography. far_corner/near_corner are pixel corners on the far
    and near baselines; the net is halfway between them on the court plane."""
    if x is None or y is None:
        return None
    far_y = project(h, *far_corner)[1]
    near_y = project(h, *near_corner)[1]
    net_y = (far_y + near_y) / 2
    py = project(h, x, y)[1]
    return "Top" if (py - net_y) * (far_y - net_y) > 0 else "Bottom"


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_rallies(rows, h, far_corner, near_corner):
    """Group ShuttleSet CSV rows (dicts) into rallies.

    Returns {rally_id: [shot, ...]} with shots sorted by frame, each:
      {"frame": int, "serve": bool, "type": product type | None,
       "ten": 10-class name | None, "side": "Top"|"Bottom"|None}
    """
    rallies = {}
    for row in rows:
        frame = _float_or_none(row.get("frame_num"))
        if frame is None:
            continue
        zh = (row.get("type") or "").strip()
        shot = {
            "frame": int(frame),
            "serve": zh in SERVICE_TYPES_ZH,
            "type": ZH_TO_PRODUCT.get(zh),
            "ten": ZH_TO_TEN.get(zh),
            "side": side_from_location(
                h, far_corner, near_corner,
                _float_or_none(row.get("player_location_x")),
                _float_or_none(row.get("player_location_y")),
            ),
        }
        rallies.setdefault(int(float(row["rally"])), []).append(shot)
    for shots in rallies.values():
        shots.sort(key=lambda s: s["frame"])
    return rallies


def match_hits(pred_frames, gt_frames, tolerance):
    """One-to-one matching of predicted to ground-truth frames.

    Pairs are taken closest-first, so each frame is used at most once.
    Returns a list of (pred_index, gt_index) pairs.
    """
    candidates = sorted(
        (abs(p - g), pi, gi)
        for pi, p in enumerate(pred_frames)
        for gi, g in enumerate(gt_frames)
        if abs(p - g) <= tolerance
    )
    used_p, used_g, pairs = set(), set(), []
    for _, pi, gi in candidates:
        if pi in used_p or gi in used_g:
            continue
        used_p.add(pi)
        used_g.add(gi)
        pairs.append((pi, gi))
    return sorted(pairs)


def score_rally(pred_events, gt_shots, tolerance=3, include_serves=False):
    """Score one rally. Frames on both sides must be in the same (clip) frame space.

    By default serves are excluded from ground truth and predicted hits on a
    serve are dropped. With include_serves, serves are ordinary hits (a predicted
    event with isServe matches them like any other).
    """
    if include_serves:
        gt = list(gt_shots)
        preds = list(pred_events)
    else:
        serve_frames = [s["frame"] for s in gt_shots if s["serve"]]
        gt = [s for s in gt_shots if not s["serve"]]

        # Predicted hits on a serve are neither true nor false positives.
        on_serve = {pi for pi, _ in match_hits([e["frame"] for e in pred_events], serve_frames, tolerance)}
        preds = [e for i, e in enumerate(pred_events) if i not in on_serve]

    pairs = match_hits([e["frame"] for e in preds], [s["frame"] for s in gt], tolerance)

    side_total = side_correct = side_missing = 0
    type_total = type_correct = 0
    ten_total = ten_correct = 0
    confusion = Counter()
    for pi, gi in pairs:
        p, g = preds[pi], gt[gi]
        if g["side"] is not None:
            side_total += 1
            if p.get("side") is None:
                side_missing += 1
            elif p["side"] == g["side"]:
                side_correct += 1
        if g["type"] is not None:
            type_total += 1
            pred_type = p.get("type") or "Unknown"
            confusion[(g["type"], pred_type)] += 1
            if pred_type == g["type"]:
                type_correct += 1
        if g.get("ten") is not None:
            ten_total += 1
            if p.get("detailType") == g["ten"]:
                ten_correct += 1

    return {
        "tp": len(pairs),
        "fp": len(preds) - len(pairs),
        "fn": len(gt) - len(pairs),
        "side_total": side_total,
        "side_correct": side_correct,
        "side_missing": side_missing,
        "type_total": type_total,
        "type_correct": type_correct,
        "ten_total": ten_total,
        "ten_correct": ten_correct,
        "confusion": confusion,
        "frame_offsets": [preds[pi]["frame"] - gt[gi]["frame"] for pi, gi in pairs],
    }


def label_matched_events(pred_events, gt_shots, tolerance=3):
    """{index into pred_events: matched ShuttleSet shot} using score_rally's
    serves-excluded matching (predicted hits on a serve and unmatched hits
    get no label). Training labels for the stacked shot classifier."""
    serve_frames = [s["frame"] for s in gt_shots if s["serve"]]
    gt = [s for s in gt_shots if not s["serve"]]
    on_serve = {pi for pi, _ in match_hits([e["frame"] for e in pred_events], serve_frames, tolerance)}
    keep = [i for i in range(len(pred_events)) if i not in on_serve]
    pairs = match_hits([pred_events[i]["frame"] for i in keep], [s["frame"] for s in gt], tolerance)
    return {keep[pi]: gt[gi] for pi, gi in pairs}


def _overlap(a, b):
    """Frames shared by two inclusive (start, end) intervals."""
    return max(0, min(a[1], b[1]) - max(a[0], b[0]) + 1)


def score_segments(pred, gt, min_overlap=0.5):
    """Score predicted rally intervals against ground truth (inclusive frames).

    One-to-one matching, best overlap first, where overlap is the fraction of the
    ground-truth interval covered. Unmatched predictions that overlap a matched
    ground-truth rally are the extra pieces of a split rally ("split"), not false
    positives. Unmatched ground-truth rallies that overlap a matched prediction
    were swallowed by it ("merged"); they still count as false negatives.
    """
    candidates = sorted(
        ((_overlap(p, g) / (g[1] - g[0] + 1), pi, gi)
         for pi, p in enumerate(pred) for gi, g in enumerate(gt)),
        key=lambda c: (-c[0], c[1], c[2]),
    )
    used_p, used_g = set(), set()
    for frac, pi, gi in candidates:
        if frac < min_overlap or pi in used_p or gi in used_g:
            continue
        used_p.add(pi)
        used_g.add(gi)

    split = fp = 0
    for pi, p in enumerate(pred):
        if pi in used_p:
            continue
        if any(_overlap(p, gt[gi]) > 0 for gi in used_g):
            split += 1
        else:
            fp += 1
    merged = sum(
        1 for gi, g in enumerate(gt)
        if gi not in used_g and any(_overlap(pred[pi], g) > 0 for pi in used_p)
    )

    tp = len(used_g)
    fn = len(gt) - tp
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": f1, "split": split, "merged": merged}


def fit_frame_offset(pred_frames, gt_frames, search=range(-8, 9), tolerance=3):
    """Offset to add to gt frames that maximises one-to-one matches with pred_frames.

    Ties go to the offset with the smallest total distance between matched
    frames, then to the one closest to zero.
    """
    def key(off):
        shifted = [g + off for g in gt_frames]
        pairs = match_hits(pred_frames, shifted, tolerance)
        dist = sum(abs(pred_frames[pi] - shifted[gi]) for pi, gi in pairs)
        return (len(pairs), -dist, -abs(off), -off)

    return max(search, key=key)


def score_labelled_hits(gt_shots, pred_labels):
    """Score a classifier run AT the labelled hit frames (no hit matching).

    pred_labels[i] = (side "Top"|"Bottom"|None, BST merged zh type|None) for
    gt_shots[i]; (None, None) is BST's unknown class. Counts:
      ten_*:  10-class over shots with a "ten" label, serves included; *_known
              skips unknown predictions (COURTSIDE's bst_eval reporting)
      type_*: product 6-class over non-serve shots with a "type"
      side_*: Top/Bottom over shots with a side; *_known skips unknowns
    """
    c = Counter()
    for g, (side, zh) in zip(gt_shots, pred_labels):
        known = zh is not None
        if g.get("ten") is not None:
            ok = known and ZH_TO_TEN.get(zh) == g["ten"]
            c["ten_total"] += 1
            c["ten_correct"] += ok
            c["ten_known"] += known
            c["ten_known_correct"] += ok
        if not g["serve"] and g.get("type") is not None:
            c["type_total"] += 1
            c["type_correct"] += known and ZH_TO_PRODUCT.get(zh) == g["type"]
        if g.get("side") is not None:
            ok = side is not None and side == g["side"]
            c["side_total"] += 1
            c["side_correct"] += ok
            c["side_known"] += side is not None
            c["side_known_correct"] += ok
    return c


def summarize(rally_scores, segment_scores=None):
    """Aggregate score_rally() results into overall metrics."""
    total = Counter()
    confusion = Counter()
    offsets = []
    for s in rally_scores:
        for k in ("tp", "fp", "fn", "side_total", "side_correct", "side_missing",
                  "type_total", "type_correct", "ten_total", "ten_correct"):
            total[k] += s.get(k, 0)
        confusion.update(s["confusion"])
        offsets.extend(s["frame_offsets"])

    def ratio(a, b):
        return a / b if b else None

    precision = ratio(total["tp"], total["tp"] + total["fp"])
    recall = ratio(total["tp"], total["tp"] + total["fn"])
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)
    out = {
        "hits": {"tp": total["tp"], "fp": total["fp"], "fn": total["fn"],
                 "precision": precision, "recall": recall, "f1": f1,
                 "mean_frame_offset": ratio(sum(offsets), len(offsets))},
        "side": {"accuracy": ratio(total["side_correct"], total["side_total"]),
                 "scored": total["side_total"], "missing": total["side_missing"]},
        "type": {"accuracy": ratio(total["type_correct"], total["type_total"]),
                 "scored": total["type_total"]},
        "ten": {"accuracy": ratio(total["ten_correct"], total["ten_total"]),
                "scored": total["ten_total"]},
        "confusion": {f"{g}->{p}": n for (g, p), n in sorted(confusion.items())},
    }
    if segment_scores:
        seg = Counter()
        for sc in segment_scores:
            for k in ("tp", "fp", "fn", "split", "merged"):
                seg[k] += sc[k]
        p = ratio(seg["tp"], seg["tp"] + seg["fp"])
        r = ratio(seg["tp"], seg["tp"] + seg["fn"])
        out["segments"] = {**{k: seg[k] for k in ("tp", "fp", "fn", "split", "merged")},
                           "precision": p, "recall": r,
                           "f1": 2 * p * r / (p + r) if p and r else None}
    return out


def parse_rally_scores(rows, h, far_corner, near_corner):
    """Per-rally score labels from one set's ShuttleSet CSV rows (dicts).

    ShuttleSet repeats the score AFTER the rally (roundscore_A/B) on every
    shot of it. Returns rallies in order: {"rally", "first", "last" (shot
    frames), "scoreAfter" (A, B), "winner" ('A'|'B'|None, from the score
    delta), "aSide" ('near'|'far'|None, majority of the hitters' positions)}.
    """
    by_rally = {}
    for row in rows:
        frame = _float_or_none(row.get("frame_num"))
        if frame is None:
            continue
        by_rally.setdefault(int(float(row["rally"])), []).append((int(frame), row))
    out, prev = [], (0, 0)
    for rid in sorted(by_rally):
        shots = sorted(by_rally[rid], key=lambda t: t[0])
        a = max(int(float(r["roundscore_A"])) for _, r in shots)
        b = max(int(float(r["roundscore_B"])) for _, r in shots)
        delta = (a - prev[0], b - prev[1])
        winner = "A" if delta == (1, 0) else "B" if delta == (0, 1) else None
        votes = Counter()
        for _, r in shots:
            side = side_from_location(h, far_corner, near_corner,
                                      _float_or_none(r.get("player_location_x")),
                                      _float_or_none(r.get("player_location_y")))
            if side is None or r.get("player") not in ("A", "B"):
                continue
            near = (side == "Bottom") == (r["player"] == "A")
            votes["near" if near else "far"] += 1
        a_side = None
        if votes and votes["near"] != votes["far"]:
            a_side = "near" if votes["near"] > votes["far"] else "far"
        out.append({"rally": rid, "first": shots[0][0], "last": shots[-1][0], "scoreAfter": (a, b),
                    "winner": winner, "aSide": a_side})
        prev = (a, b)
    return out


def score_scoreboard(pred_rallies, gt_sets, pad=15):
    """Score scoreboard-derived rally scores against parse_rally_scores labels.

    gt_sets: {set_no: [label rally, ...]} with frames already in video frames.
    Each label rally is paired with the predicted rally overlapping its
    first..last shot (+-pad) the most; an unpaired label counts as wrong.
    Scores are (A, B) on both sides with A = the match winner (ShuttleSet's
    convention; the caller flips the labels if their A lost).
    Counts: score_correct (set and scoreAfter equal), winner_correct, and
    side_correct (the predicted near player is the labelled one; labels
    without a side are skipped, side_total counts the rest). finals: per set,
    the last predicted rally of that set vs the last label.
    """
    c = Counter()
    for sn, labels in gt_sets.items():
        for g in labels:
            c["rallies"] += 1
            lo, hi = g["first"] - pad, g["last"] + pad
            best, best_ov = None, 0
            for p in pred_rallies:
                ov = min(hi, p["endFrame"]) - max(lo, p["startFrame"])
                if ov > best_ov:
                    best, best_ov = p, ov
            if g["aSide"] is not None:
                c["side_total"] += 1
            if best is None:
                continue
            c["matched"] += 1
            score = best.get("scoreAfter")
            c["score_correct"] += best.get("set") == sn and score is not None and tuple(score) == g["scoreAfter"]
            c["winner_correct"] += g["winner"] is not None and best.get("winner") == g["winner"]
            if g["aSide"] is not None and best.get("near") is not None:
                c["side_correct"] += (best["near"] == "A") == (g["aSide"] == "near")
    finals = {}
    for sn, labels in gt_sets.items():
        in_set = [p for p in pred_rallies if p.get("set") == sn and p.get("scoreAfter") is not None]
        pred = tuple(in_set[-1]["scoreAfter"]) if in_set else None
        finals[sn] = {"pred": pred, "gt": labels[-1]["scoreAfter"], "exact": pred == labels[-1]["scoreAfter"]}
    return {**{k: c[k] for k in ("rallies", "matched", "score_correct", "winner_correct",
                                 "side_total", "side_correct")},
            "winner_total": sum(g["winner"] is not None for ls in gt_sets.values() for g in ls),
            "finals": finals, "finals_exact": all(f["exact"] for f in finals.values())}
