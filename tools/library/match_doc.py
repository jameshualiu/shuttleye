"""Convert an analyzer full-match product result into a Firestore match document."""
from typing import TypedDict


class PlayerRef(TypedDict):
    id: str
    name: str


class MatchMeta(TypedDict):
    id: str
    youtubeId: str
    editionId: str
    round: str
    date: str
    playerA: PlayerRef   # the match winner, already resolved by the caller
    playerB: PlayerRef
    nearFirst: str  # "A" | "B": who is on the near side in rally 1


GROUP_OF_DETAIL: dict[str, str | None] = {
    "clear": "Clear", "drive": "Drive", "drop": "Drop", "lob": "Lift",
    "net shot": "Net", "smash": "Smash", "push/rush": "Push",
    "defensive shot": "Lift", "short service": None, "long service": None,
}

# Court coordinates (worker/pipeline.py): 6.1 x 13.4 m, far baseline y = 0,
# x = 0 at the image's left, net at y = 6.7.
_NET_Y = 6.7
_CENTRE_X = 3.05
_FRONT_M = 1.98
_REAR_M = 4.72
NEAR_FIRST_WARNING = "near side at rally 1 disagrees with --near-first"


def zone_of(location_m: list[float] | None, hitter_near: bool) -> str | None:
    if not location_m:
        return None
    x, y = location_m[0], location_m[1]
    dist = abs(y - _NET_Y)
    depth = "front" if dist < _FRONT_M else "rear" if dist > _REAR_M else "mid"
    image_left = x < _CENTRE_X
    # The near player faces up the image (their left is image left); the far player faces down.
    left = image_left if hitter_near else not image_left
    return f"{depth}-{'left' if left else 'right'}"


def _other(p: str) -> str:
    return "B" if p == "A" else "A"


def _pair(v):
    return [v[0], v[1]] if v else None


def match_doc(result: dict, meta: MatchMeta) -> dict:
    events = result["events"]
    rallies_in = result["rallies"]
    rallies = []
    prev_after: dict = {}   # set -> last scoreAfter (None once unread)
    for n, r in enumerate(rallies_in, 1):
        near = r.get("nearPlayer")
        s = r.get("set")
        if s not in prev_after:
            before = [0, 0]
        else:
            before = _pair(prev_after[s])
        prev_after[s] = r.get("scoreAfter") if r.get("scoreRead") else None
        shots = []
        for i in r["eventIndices"]:
            e = events[i]
            side = e.get("side")
            if near and side in ("Bottom", "Top"):
                p = near if side == "Bottom" else _other(near)
                hitter_near = side == "Bottom"
            else:
                p, hitter_near = None, side == "Bottom"
            loc = e.get("location_m")
            shots.append({
                "t": e["timeSec"], "p": p,
                "g": GROUP_OF_DETAIL.get(e.get("detailType")),
                "d": e.get("detailType"),
                "z": zone_of(loc, hitter_near) if side in ("Bottom", "Top") else None,
                "s": bool(e.get("isServe")),
            })
        rallies.append({
            "n": n, "set": s, "startSec": r["startSec"], "endSec": r["endSec"],
            "scoreBefore": before, "winner": r.get("winner"), "shots": shots,
        })

    warnings = list(result.get("warnings") or [])
    if rallies_in and rallies_in[0].get("nearPlayer") not in (None, meta["nearFirst"]):
        warnings.append(NEAR_FIRST_WARNING)

    finals = [_pair(s.get("finalScore")) for s in result.get("sets") or []]
    games = finals if finals and all(finals) else None
    total = sum(len(r["shots"]) for r in rallies)
    summary = result.get("summary") or {}
    return {
        "id": meta["id"], "youtubeId": meta["youtubeId"], "editionId": meta["editionId"],
        "round": meta["round"], "date": meta["date"],
        "players": {"A": {"id": meta["playerA"]["id"], "name": meta["playerA"]["name"]},
                    "B": {"id": meta["playerB"]["id"], "name": meta["playerB"]["name"]}},
        "winner": "A",
        "games": games,
        "attributed": bool(rallies_in) and all(r.get("nearPlayer") for r in rallies_in),
        "status": "unpublished",
        "analyzer": {"models": result.get("models"), "warnings": warnings,
                     "skippedSteps": result.get("skippedSteps") or [],
                     "timings": result.get("timings")},
        "accuracy": None,
        "summary": {"rallies": len(rallies),
                    "avgShots": round(total / len(rallies), 1) if rallies else 0,
                    "durationSec": summary.get("durationSec")},
        "rallies": rallies,
        "insights": None,
    }
