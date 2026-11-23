"""Per-player shot shares, rally-band win rates and comparison-group ranks."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass

from .load import Match

SHOWN_GROUPS = ("Lift", "Smash", "Net", "Drive", "Push", "Clear", "Drop")  # Net kill: denominator only
BANDS = (
    ("short", "4 shots or fewer", 0, 4),
    ("mid", "5 to 8 shots", 5, 8),
    ("long", "9 shots or more", 9, None),
)

MIN_GROUPED_SHOTS = 300
MIN_BAND_RALLIES = 30


@dataclass
class PlayerStats:
    player: str
    shots_by_group: dict[str, int]
    grouped_shots: int
    rallies_by_band: dict[str, int]
    wins_by_band: dict[str, int]


@dataclass
class Ranked:
    value: float
    rank: int
    of: int
    below: int
    typical: float
    percentile: float


def _band_of(length: int) -> str:
    for key, _label, lo, hi in BANDS:
        if length >= lo and (hi is None or length <= hi):
            return key
    raise ValueError(length)


def player_stats(matches: list[Match], player: str) -> PlayerStats:
    groups: Counter[str] = Counter()
    rallies = {key: 0 for key, *_ in BANDS}
    wins = {key: 0 for key, *_ in BANDS}
    for m in matches:
        if player not in (m.winner, m.loser):
            continue
        for r in m.rallies:
            for s in r.shots:
                if s.player == player and s.group is not None:
                    groups[s.group] += 1
            if r.winner is None:
                continue  # no recorded winner: not a real rally for band stats
            band = _band_of(len(r.shots))
            rallies[band] += 1
            if r.winner == player:
                wins[band] += 1
    return PlayerStats(player, dict(groups), sum(groups.values()), rallies, wins)


def share(ps: PlayerStats, group: str) -> float:
    return ps.shots_by_group.get(group, 0) / ps.grouped_shots if ps.grouped_shots else 0.0


def win_rate(ps: PlayerStats, band: str) -> float | None:
    n = ps.rallies_by_band[band]
    return ps.wins_by_band[band] / n if n >= MIN_BAND_RALLIES else None


def _rank(values: dict[str, float], player: str) -> Ranked:
    v = values[player]
    of = len(values)
    below = sum(1 for p, x in values.items() if p != player and x < v)
    above = sum(1 for x in values.values() if x > v)
    return Ranked(
        value=v,
        rank=above + 1,
        of=of,
        below=below,
        typical=statistics.median(values.values()),
        percentile=below / (of - 1) * 100 if of > 1 else 50.0,
    )


def rank_value(values: dict[str, float], player: str) -> Ranked:
    """Rank `player` among `values` (higher is better); `typical` is the median."""
    return _rank(values, player)


def rank_shot_share(all_stats: dict[str, PlayerStats], player: str, group: str) -> Ranked | None:
    values = {p: share(s, group) for p, s in all_stats.items() if s.grouped_shots >= MIN_GROUPED_SHOTS}
    return _rank(values, player) if player in values else None


def rank_band(all_stats: dict[str, PlayerStats], player: str, band: str) -> Ranked | None:
    values = {p: w for p, s in all_stats.items() if (w := win_rate(s, band)) is not None}
    return _rank(values, player) if player in values else None
