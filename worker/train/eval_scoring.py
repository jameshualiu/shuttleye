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
      {"frame": int, "serve": bool, "type": product type | None, "side": "Top"|"Bottom"|None}
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


def score_rally(pred_events, gt_shots, tolerance=3):
    """Score one rally. Frames on both sides must be in the same (clip) frame space."""
    serve_frames = [s["frame"] for s in gt_shots if s["serve"]]
    gt = [s for s in gt_shots if not s["serve"]]

    # Predicted hits on a serve are neither true nor false positives.
    on_serve = {pi for pi, _ in match_hits([e["frame"] for e in pred_events], serve_frames, tolerance)}
    preds = [e for i, e in enumerate(pred_events) if i not in on_serve]

    pairs = match_hits([e["frame"] for e in preds], [s["frame"] for s in gt], tolerance)

    side_total = side_correct = side_missing = 0
    type_total = type_correct = 0
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

    return {
        "tp": len(pairs),
        "fp": len(preds) - len(pairs),
        "fn": len(gt) - len(pairs),
        "side_total": side_total,
        "side_correct": side_correct,
        "side_missing": side_missing,
        "type_total": type_total,
        "type_correct": type_correct,
        "confusion": confusion,
        "frame_offsets": [preds[pi]["frame"] - gt[gi]["frame"] for pi, gi in pairs],
    }


def summarize(rally_scores):
    """Aggregate score_rally() results into overall metrics."""
    total = Counter()
    confusion = Counter()
    offsets = []
    for s in rally_scores:
        for k in ("tp", "fp", "fn", "side_total", "side_correct", "side_missing",
                  "type_total", "type_correct"):
            total[k] += s[k]
        confusion.update(s["confusion"])
        offsets.extend(s["frame_offsets"])

    def ratio(a, b):
        return a / b if b else None

    precision = ratio(total["tp"], total["tp"] + total["fp"])
    recall = ratio(total["tp"], total["tp"] + total["fn"])
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)
    return {
        "hits": {"tp": total["tp"], "fp": total["fp"], "fn": total["fn"],
                 "precision": precision, "recall": recall, "f1": f1,
                 "mean_frame_offset": ratio(sum(offsets), len(offsets))},
        "side": {"accuracy": ratio(total["side_correct"], total["side_total"]),
                 "scored": total["side_total"], "missing": total["side_missing"]},
        "type": {"accuracy": ratio(total["type_correct"], total["type_total"]),
                 "scored": total["type_total"]},
        "confusion": {f"{g}->{p}": n for (g, p), n in sorted(confusion.items())},
    }
