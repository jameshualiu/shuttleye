"""The six per-player insights shown on player and match pages."""
from __future__ import annotations

from pro_profiles.load import Match
from pro_profiles.stats import (
    BANDS,
    MIN_BAND_RALLIES,
    SHOWN_GROUPS as _PROFILE_GROUPS,
    Ranked,
    _band_of,
    rank_value,
)

MIN_SHARE_SHOTS = 50
MIN_COMPARED = 10
MIN_GAPS = 50
MIN_RALLIES = 30
MIN_SERVES = 30
PHASES = (("start", 1, 4), ("mid", 5, 12), ("late", 13, None))
# The profile groups plus Block, which only the analyzer labels (ShuttleSet
# profiles fold blocks into Net).
SHOWN_GROUPS = (*_PROFILE_GROUPS, "Block")
ZONES = tuple(f"{d}-{s}" for d in ("front", "mid", "rear") for s in ("left", "right"))

Insights = dict


def _pct(num: int, den: int) -> float:
    return round(num / den * 100, 1)


def _mix(groups: list[str]) -> dict:
    n = len(groups)
    if n < MIN_SHARE_SHOTS:
        return {**{g: None for g in SHOWN_GROUPS}, "shots": n}
    return {**{g: _pct(groups.count(g), n) for g in SHOWN_GROUPS}, "shots": n}


def _rate(wins: int, n: int, minimum: int) -> float | None:
    return _pct(wins, n) if n >= minimum and n else None


def _serve_length(shots, server: str) -> str | None:
    """short/long for a serve: the detail type when it names one, else the depth
    the receiver hit the next shot from (rear = long, front/mid = short)."""
    d = shots[0].detail
    if d == "short service":
        return "short"
    if d == "long service":
        return "long"
    if len(shots) < 2:
        return None
    reply = shots[1]
    if reply.player in (server, "?", None) or reply.zone not in ZONES:
        return None
    return "long" if reply.zone.startswith("rear-") else "short"


def player_insights(matches: list[Match], player: str) -> Insights:
    phase = {k: [] for k, _, _ in PHASES}
    replies = {g: [] for g in SHOWN_GROUPS}
    zones: list[str] = []
    gaps: list[float] = []
    lengths: list[int] = []
    band_n = {k: 0 for k, *_ in BANDS}
    band_w = {k: 0 for k, *_ in BANDS}
    serves = short = long_ = 0
    won = {"short": [0, 0], "long": [0, 0]}  # [wins, rallies]
    smashes = smash_wins = 0

    for m in matches:
        if player not in (m.winner, m.loser):
            continue
        for r in m.rallies:
            shots = r.shots
            mine = [s for s in shots if s.player == player]
            if mine:
                lengths.append(len(shots))
            for i, s in enumerate(shots):
                if s.player != player:
                    continue
                if s.group in SHOWN_GROUPS:
                    for key, lo, hi in PHASES:
                        if s.order >= lo and (hi is None or s.order <= hi):
                            phase[key].append(s.group)
                    if i > 0:
                        prev = shots[i - 1]
                        if prev.player not in (player, "?") and prev.group in SHOWN_GROUPS:
                            replies[prev.group].append(s.group)
                if s.zone in ZONES:
                    zones.append(s.zone)
                if i > 0:
                    gaps.append(s.time_sec - shots[i - 1].time_sec)

            read = r.winner is not None
            if read and shots:
                band = _band_of(len(shots))
                band_n[band] += 1
                band_w[band] += r.winner == player

            if shots and shots[0].is_serve and shots[0].player == player:
                serves += 1
                kind = _serve_length(shots, player)
                if kind:
                    short += kind == "short"
                    long_ += kind == "long"
                    if read:
                        won[kind][1] += 1
                        won[kind][0] += r.winner == player

            if read:
                tail = len(shots) - 1
                for i, s in enumerate(shots):
                    if s.player == player and s.group == "Smash":
                        smashes += 1
                        if r.winner == player and i >= tail - 1:
                            smash_wins += 1

    n_zone = len(zones)
    zone_out = {z: (_pct(zones.count(z), n_zone) if n_zone >= MIN_SHARE_SHOTS else None) for z in ZONES}
    return {
        "phaseMix": {k: _mix(phase[k]) for k, _, _ in PHASES},
        "replies": {g: _mix(replies[g]) for g in SHOWN_GROUPS},
        "zones": {**zone_out, "shots": n_zone},
        "tempo": {
            "secPerShot": round(sum(gaps) / len(gaps), 2) if len(gaps) >= MIN_GAPS else None,
            "rallyShots": round(sum(lengths) / len(lengths), 2) if len(lengths) >= MIN_RALLIES else None,
        },
        "bands": [
            {"band": k, "label": label, "rallies": band_n[k],
             "winRate": _rate(band_w[k], band_n[k], MIN_BAND_RALLIES)}
            for k, label, _lo, _hi in BANDS
        ],
        "serve": {
            "serves": serves,
            "shortShare": _rate(short, short + long_, MIN_SERVES),
            "pointsWonShort": _rate(won["short"][0], won["short"][1], MIN_SERVES),
            "pointsWonLong": _rate(won["long"][0], won["long"][1], MIN_SERVES),
        },
        "smashWins": {
            "smashes": smashes,
            "winShare": _rate(smash_wins, smashes, MIN_SHARE_SHOTS),
        },
    }


def _at(ins: Insights, path: tuple[str, ...]):
    cur = ins
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def rank_insight(all: dict[str, Insights], player: str, path: tuple[str, ...]) -> Ranked | None:
    values = {p: v for p, ins in all.items() if (v := _at(ins, path)) is not None}
    if player not in values or len(values) < MIN_COMPARED:
        return None
    return rank_value(values, player)
