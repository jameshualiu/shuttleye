# worker/train/bfmd.py
"""
BFMD annotation loader for the full-match eval (eval_shuttleset.py --bfmd).

BFMD (Ding, Fujii, Tamaki, "BFMD: A Full-Match Badminton Dense Dataset for
Dense Shot Captioning", CVSports @ CVPR 2026; github.com/Ning-D/BFMD) labels
12 men's singles broadcasts from four 2025 BWF World Tour events. It states no
licence: it is used for evaluation only, stays in the local eval cache
(~/.cache/shuttleye-eval/bfmd/) and is never committed or redistributed. Videos
are BWF TV uploads on YouTube (Badminton_video_list.csv), re-downloaded locally.

Files read, per match (keyed by the match name):
  annotations/metadata/<match>.json      players, games, rally intervals,
                                         score after every rally, game1_top_player
  annotations/hit_inferred/<match>.json  {"hits": [{frame, shot_type, side
                                         ('top'|'bottom'), player, game, rally}]}
Frames are 0-based decode order of the 1280x720 30 fps broadcast.

Shots come out as the dicts eval_scoring.parse_rallies returns ("frame",
"serve", "type" product 6-class, "ten" 10-class, "side" Top/Bottom) plus
provenance ("label" = BFMD shot_type, "set", "rally", "player" 'A'|'B'), with
A = player1 and B = player2. As with ShuttleSet's ball_round 1, a rally's first
stroke is its serve whatever it is typed: BFMD types ~10% of first strokes as
net_shot/lift/clear/smash, at the same delay after the rally start as typed
serves (median 9-11 frames), and never types a later stroke as a serve.

Shot-type mapping (BFMD -> 10-class ZH_TO_TEN targets / product 6-class):
  serve -> short service / -      flick_serve -> long service / -
  clear -> clear / Clear          drop        -> drop / Drop
  smash -> smash / Smash          drive       -> drive / Drive
  net_shot -> net shot / Net      lift        -> lob / Lob
  push  -> push/rush / Drive      net_kill    -> push/rush / Net
  block -> defensive shot / Net
press is excluded from both (no type, still a hit): BFMD's own captions use it
for both a forecourt push-down and an overhead slice to the forecourt, so it
has no single class. hit (a generic hit) is a hit with no type; bounce and
net_hit are not strokes and are dropped. Counts of all three groups are
returned in "excluded".
"""
import json
from collections import Counter
from pathlib import Path

FPS = 30.0
SERVE_TYPES = {"serve", "flick_serve"}

BFMD_TO_TEN = {
    "serve": "short service",
    "flick_serve": "long service",
    "clear": "clear",
    "drop": "drop",
    "smash": "smash",
    "drive": "drive",
    "net_shot": "net shot",
    "lift": "lob",
    "push": "push/rush",
    "net_kill": "push/rush",
    "block": "defensive shot",
}

# Same folds as eval_scoring.ZH_TO_PRODUCT: push = 推球 -> Drive, net kill =
# 撲球 -> Net, block = 擋小球 -> Net, lift = 挑球 -> Lob. Serves have no type.
BFMD_TO_PRODUCT = {
    "clear": "Clear",
    "drop": "Drop",
    "smash": "Smash",
    "drive": "Drive",
    "net_shot": "Net",
    "lift": "Lob",
    "push": "Drive",
    "net_kill": "Net",
    "block": "Net",
}

UNTYPED_HITS = {"press", "hit"}     # strokes with no class in our taxonomies
NOT_STROKES = {"bounce", "net_hit"}  # not a player hitting the shuttle

DEFAULT_ROOT = Path.home() / ".cache" / "shuttleye-eval" / "bfmd" / "data"


def metadata_path(match: str, root: Path = DEFAULT_ROOT) -> Path:
    return Path(root) / "annotations" / "metadata" / f"{match}.json"


def video_url(match: str, root: Path = DEFAULT_ROOT) -> str:
    """YouTube URL of a match from BFMD's Badminton_video_list.csv."""
    import csv

    with open(Path(root) / "Badminton_video_list.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["match_name"] == match:
                return row["youtube_url"]
    raise KeyError(f"{match} not in {root}/Badminton_video_list.csv")


def load_match(path: Path) -> dict:
    """Load one BFMD match from its metadata/<match>.json path.

    Returns {"video_id", "fps", "players" (player1, player2), "rallies"
    [(start, end)] (every annotated rally, game order), "shots" (all strokes,
    frame order), "sets" {game: {rally index in game: [shots]}} (rallies with
    strokes only; the shape eval_shuttleset scores), "scores" {game:
    [parse_rally_scores-style rally]} (score after the rally (A, B), winner,
    A's end from the hitters, first/last stroke frame or the rally interval
    when it has none, plus the interval as start/end), "excluded" Counter of BFMD labels with no type or
    dropped}.
    """
    path = Path(path)
    meta = json.loads(path.read_text())
    if isinstance(meta, list):           # the README's layout: a one-element list
        meta = meta[0]
    hits = json.loads((path.parent.parent / "hit_inferred" / path.name).read_text())["hits"]
    p1, p2 = meta["player1_name"], meta["player2_name"]
    who = {p1: "A", p2: "B"}

    by_rally: dict[tuple[int, int], list[dict]] = {}
    for h in hits:
        by_rally.setdefault((int(h["game"]), int(h["rally"])), []).append(h)

    excluded: Counter = Counter()
    rallies, shots, sets, scores = [], [], {}, {}
    for key in sorted(meta["games"], key=lambda g: int(g.removeprefix("game"))):
        game = int(key.removeprefix("game"))
        g = meta["games"][key]
        events = g.get("score_events") or []
        prev = (0, 0)
        scores[game] = []
        for i, r in enumerate(g["rallies"]):
            start, end = int(r["start"]), int(r["end"])
            rallies.append((start, end))
            rally_shots = []
            for h in sorted(by_rally.get((game, i), []), key=lambda h: h["frame"]):
                label = h["shot_type"]
                if label in NOT_STROKES:
                    excluded[label] += 1
                    continue
                if label in UNTYPED_HITS:
                    excluded[label] += 1
                rally_shots.append({
                    "frame": int(h["frame"]),
                    "serve": label in SERVE_TYPES or not rally_shots,
                    "type": BFMD_TO_PRODUCT.get(label),
                    "ten": BFMD_TO_TEN.get(label),
                    "side": {"top": "Top", "bottom": "Bottom"}.get(h.get("side")),
                    "label": label, "set": game, "rally": i, "player": who.get(h.get("player")),
                })
            if rally_shots:
                sets.setdefault(game, {})[i] = rally_shots
                shots.extend(rally_shots)

            ev = events[i] if i < len(events) else None
            after = None
            if ev is not None:
                sa = ev["score_after_rally"]
                after = (int(sa["player1"]), int(sa["player2"]))
            delta = None if after is None else (after[0] - prev[0], after[1] - prev[1])
            votes = Counter()
            for s in rally_shots:
                if s["player"] in ("A", "B") and s["side"] is not None:
                    near = (s["side"] == "Bottom") == (s["player"] == "A")
                    votes["near" if near else "far"] += 1
            a_side = None
            if votes and votes["near"] != votes["far"]:
                a_side = "near" if votes["near"] > votes["far"] else "far"
            scores[game].append({
                "rally": i, "start": start, "end": end,
                "first": rally_shots[0]["frame"] if rally_shots else start,
                "last": rally_shots[-1]["frame"] if rally_shots else end,
                "scoreAfter": after,
                "winner": "A" if delta == (1, 0) else "B" if delta == (0, 1) else None,
                "aSide": a_side,
            })
            if after is not None:
                prev = after
    shots.sort(key=lambda s: s["frame"])
    return {"video_id": meta.get("match_name", path.stem), "fps": FPS, "players": (p1, p2),
            "rallies": rallies, "shots": shots, "sets": sets, "scores": scores,
            "excluded": excluded}
