"""Per-pair serve, receive and rally measures for doubles, and event ranks.

All counts come from the pair's own matches. Denominators (each measure is
None in `values` when its sample is below MIN_SAMPLE; `samples` always holds
the count):

- serve.short_share: the pair's serves with a known type (short or long).
- serve.win_rate: rallies they served with a known winner.
- serve.third_down: rallies they served whose shot 3 exists, is hit by one of
  them and has a known type. Numerator: that shot is attacking (smash, drop,
  push). Shot type is used, not `ball_up_down` (see the spec).
- receive.attack_share: their returns (shot 2 of a rally the opponents served,
  hit by one of them) with a known type. Numerator: attacking returns.
- receive.win_rate: rallies they received (the opponents served) with a known
  winner.
- first4.share: their rallies with a known winner. Numerator: rallies of 4 or
  fewer shots.
- first4.win_rate: those rallies of 4 or fewer shots (known winner). Numerator:
  the ones they won.
- rally.attack_share: the pair's own shots after the serve (shot 2 onward) with
  a known type. Serves (shot 1) are excluded: they are never attacking and
  belong to the serve section. Numerator: attacking shots.
- rally.formation_attack: the pair's own shots after the serve (shot 2 onward;
  serves excluded) with a known `player_formation`. Numerator: shots in the
  Attack state.

Rallies with no known winner count in no win rate and no first-4 stat; their
shots still count in the shot-type shares.

Display-only distributions in `dists` (shares; None for every key when the
sample is 0; samples under the same key):

- serve.placement: serves with a known type and a `met_at` inside the court
  (x 0-61, y 0-134), by `placement_zone`.
- receive.mix: their returns with a known type, by shot type.
- roles: per partner, their share of the pair's smashes and net shots (all of
  the pair's shots of that type).
- points.lost: rallies they lost with a known `lose_reason`, by clean label.
  Every reason but `opp_winner` is the pair's own error.
- points.won: rallies they won with a known reason: `winner` (the opponents
  let it land in) or `opp_error`.
- mixed.serve_by / mixed.receive_by (XD only): the man's and the woman's share
  of the pair's serves (all) and returns (all).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .doubles_load import ATTACK_TYPES, DMatch, Pair
from .stats import Ranked, rank_value

MIN_MATCHES = 2
MIN_SAMPLE = 30
MEASURES = (
    "serve.short_share",
    "serve.win_rate",
    "serve.third_down",
    "receive.attack_share",
    "receive.win_rate",
    "first4.share",
    "first4.win_rate",
    "rally.attack_share",
    "rally.formation_attack",
)
PLACEMENT_ZONES = ("centre", "middle", "wide", "back_centre", "back_wide")
RETURN_TYPES = ("net shot", "push", "smash", "lift", "drive", "clear", "drop")
ROLE_TYPES = ("smash", "net shot")
LOST_REASONS = {
    "Opp Grounded within Boundaries": "opp_winner",
    "Net Fault": "net_fault",
    "Out of Bounds": "out",
    "Failed Return": "failed_return",
    "Judgment Error": "judgment_error",
    "Faults": "fault",
}
WINNER_REASON = "Opp Grounded within Boundaries"
GENDERS = {"Male": "man", "Female": "woman"}

CENTRE_LINE = 30.5
CENTRE_HALF_WIDTH = 10  # 1.0 m either side of the centre line
COURT_X, COURT_Y = 61, 134
# Wide: x <= 14 or x >= 46 (within ~1.4 m of a sideline). Set from the real
# met_at histogram, where wide serves form humps at about x 8-14 and 46-52;
# the spec's first guess of 0.8 m (x <= 8 / >= 53) split those humps.
WIDE_LEFT, WIDE_RIGHT = 14, 46


@dataclass
class PairStats:
    pair: str
    matches: int
    values: dict[str, float | None]
    samples: dict[str, int]
    dists: dict[str, dict]


def placement_zone(met_at: tuple[float, float], serve_type: str) -> str:
    """Where the receiver met the serve, across the court (x, in ~10 cm units).
    Short: centre if |x - 30.5| <= 10, wide if x <= 14 or x >= 46, else middle.
    Long: back_wide if x <= 14 or x >= 46, else back_centre."""
    x = met_at[0]
    wide = x <= WIDE_LEFT or x >= WIDE_RIGHT
    if serve_type == "long":
        return "back_wide" if wide else "back_centre"
    if abs(x - CENTRE_LINE) <= CENTRE_HALF_WIDTH:
        return "centre"
    return "wide" if wide else "middle"


def _in_court(met_at: tuple[float, float] | None) -> bool:
    return met_at is not None and 0 <= met_at[0] <= COURT_X and 0 <= met_at[1] <= COURT_Y


def _shares(counts: Counter, keys) -> dict[str, float | None]:
    n = sum(counts.values())
    return {k: counts[k] / n if n else None for k in keys}


class _Ratio:
    def __init__(self) -> None:
        self.hit = 0
        self.n = 0

    def add(self, hit: bool) -> None:
        self.n += 1
        self.hit += bool(hit)

    def value(self) -> float | None:
        return self.hit / self.n if self.n >= MIN_SAMPLE else None


def pair_stats(matches: list[DMatch], pair: Pair, players: dict) -> PairStats:
    us = set(pair.players)
    ratios = {k: _Ratio() for k in MEASURES}
    placement: Counter = Counter()
    returns: Counter = Counter()
    roles = {t: Counter() for t in ROLE_TYPES}
    lost: Counter = Counter()
    won: Counter = Counter()
    serve_by: Counter = Counter()
    receive_by: Counter = Counter()
    n_matches = 0

    for m in matches:
        if pair.id not in (m.winner, m.loser):
            continue
        n_matches += 1
        for r in m.rallies:
            served = r.server in us
            known = r.winner is not None
            win = r.winner == pair.id
            shot = {s.num: s for s in r.shots}

            if served:
                serve_by[players[r.server].gender] += 1
                if r.serve_type is not None:
                    ratios["serve.short_share"].add(r.serve_type == "short")
                    if _in_court(shot[1].met_at):
                        placement[placement_zone(shot[1].met_at, r.serve_type)] += 1
                if known:
                    ratios["serve.win_rate"].add(win)
                third = shot.get(3)
                if third and third.player in us and third.type is not None:
                    ratios["serve.third_down"].add(third.type in ATTACK_TYPES)
            else:
                ret = shot.get(2)
                if ret and ret.player in us:
                    receive_by[players[ret.player].gender] += 1
                    if ret.type is not None:
                        ratios["receive.attack_share"].add(ret.type in ATTACK_TYPES)
                        returns[ret.type] += 1
                if known:
                    ratios["receive.win_rate"].add(win)

            if known:
                short = len(r.shots) <= 4
                ratios["first4.share"].add(short)
                if short:
                    ratios["first4.win_rate"].add(win)
                if r.lose_reason is not None:
                    if win:
                        won["winner" if r.lose_reason == WINNER_REASON else "opp_error"] += 1
                    else:
                        lost[LOST_REASONS[r.lose_reason]] += 1

            for s in r.shots:
                if s.player not in us:
                    continue
                if s.type in roles:
                    roles[s.type][s.player] += 1
                if s.num == 1:
                    continue  # the serve is not part of "the rest of the rally"
                if s.type is not None:
                    ratios["rally.attack_share"].add(s.type in ATTACK_TYPES)
                if s.formation is not None:
                    ratios["rally.formation_attack"].add(s.formation == "Attack")

    dists = {
        "serve.placement": _shares(placement, PLACEMENT_ZONES),
        "receive.mix": _shares(returns, RETURN_TYPES),
        "roles": {
            p: {t: (roles[t][p] / n if (n := sum(roles[t].values())) else None) for t in ROLE_TYPES}
            for p in pair.players
        },
        "points.lost": _shares(lost, LOST_REASONS.values()),
        "points.won": _shares(won, ("winner", "opp_error")),
    }
    samples = {k: r.n for k, r in ratios.items()}
    samples.update({
        "serve.placement": sum(placement.values()),
        "receive.mix": sum(returns.values()),
        "points.lost": sum(lost.values()),
        "points.won": sum(won.values()),
    })
    if pair.event == "XD":
        for key, counts in (("mixed.serve_by", serve_by), ("mixed.receive_by", receive_by)):
            dists[key] = _shares(Counter({GENDERS[g]: c for g, c in counts.items()}), GENDERS.values())
            samples[key] = sum(counts.values())

    return PairStats(
        pair=pair.id,
        matches=n_matches,
        values={k: r.value() for k, r in ratios.items()},
        samples=samples,
        dists=dists,
    )


def ranked_pairs(all_stats: dict[str, PairStats], pairs: dict[str, Pair], event: str) -> list[str]:
    """The event's comparison group: pairs with MIN_MATCHES or more matches."""
    return sorted(
        pid for pid, st in all_stats.items()
        if pairs[pid].event == event and st.matches >= MIN_MATCHES
    )


def rank_measure(
    all_stats: dict[str, PairStats], pairs: dict[str, Pair], pair_id: str, key: str
) -> Ranked | None:
    """Rank a measure within the pair's event group. `typical` is the median
    over the group's pairs with a value, including this pair. None if the pair
    is unranked or its value is None."""
    group = ranked_pairs(all_stats, pairs, pairs[pair_id].event)
    if pair_id not in group or all_stats[pair_id].values[key] is None:
        return None
    values = {p: v for p in group if (v := all_stats[p].values[key]) is not None}
    return rank_value(values, pair_id)
