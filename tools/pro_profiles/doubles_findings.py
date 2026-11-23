"""Generate a doubles pair's findings and header summary.

Rules follow the doubles spec's "Findings and summary" section. Wording lives
in content/doubles_templates.json and content/doubles_tips.json, not here.
Findings reuse the singles `Finding`; doubles has no clips yet, so `clips` is
always empty.

- A share measure is a "style" finding when the pair is top or bottom EDGE of
  its event group (EDGE_SMALL in groups under SMALL_GROUP) and at least
  MIN_GAP from the typical pair.
- A win rate is a "strength" finding on the same rule, top side only.
- The weakness is the win rate furthest below its typical value, when that gap
  is at least WEAKNESS_GAP (ties: serve, receive, first4). One weakness per
  pair: a low win rate that isn't the weakness is not a finding (the page shows
  it as a number), so win-rate keys are only ever `.top` or `.weakness`.
"""

from __future__ import annotations

from functools import cache

from .doubles_load import DPlayer, Pair
from .doubles_stats import MEASURES, PairStats, rank_measure, ranked_pairs
from .findings import ALMOST_NEVER as RARELY, MAX_FINDINGS, Finding, Kind
from .load import load_content
from .stats import Ranked

EDGE = 2  # top 2 / bottom 2 of the event group
EDGE_SMALL = 1  # top 1 / bottom 1 in a small group
SMALL_GROUP = 8  # groups under 8 pairs (mixed doubles) use EDGE_SMALL
MIN_GAP = 0.05  # 5+ percentage points from the typical pair
WEAKNESS_GAP = 0.03  # a weakness is 3+ percentage points below typical
RARELY_MAX = 0.15  # "rarely" also needs the value itself to be 15% or less
EPS = 1e-9  # float tolerance on the gaps

WIN_RATES = ("serve.win_rate", "receive.win_rate", "first4.win_rate")
SHARES = tuple(k for k in MEASURES if k not in WIN_RATES)


@cache
def _templates() -> dict:
    return load_content("doubles_templates")


@cache
def _tips() -> dict:
    return load_content("doubles_tips")


@cache
def _display_names() -> dict:
    names = load_content("doubles_display_names")
    return {k: v for k, v in names.items() if not k.startswith("_")}


def all_keys() -> list[str]:
    """Every finding key select_pair_findings can produce."""
    return [f"{m}.{side}" for m in SHARES for side in ("top", "bottom")] + [
        f"{m}.{side}" for m in WIN_RATES for side in ("top", "weakness")
    ]


def _not_rally(key: str) -> bool:
    return not key.startswith("rally.")


def _measure(key: str) -> str:
    return key.rsplit(".", 1)[0]


# Pairs of measures the summary never joins with "and". Only the two first-4
# measures: "see more rallies end within 4 shots and win more of them" reads
# as one claim about the same rallies.
NO_PAIRING = frozenset({frozenset({"first4.share", "first4.win_rate"})})


def _can_pair(a: str, b: str) -> bool:
    return frozenset({_measure(a), _measure(b)}) not in NO_PAIRING


def _first(r: Ranked) -> bool:
    return r.below == r.of - 1  # strictly above every other pair


def _last(r: Ranked) -> bool:
    # Strictly below every other pair. `below == 0` would also be true when
    # tied for last, so the rank is used.
    return r.rank == r.of


def _phrase(measure: str, side: str, r: Ranked) -> str:
    t = _templates()
    if side == "top":
        variant = "top1" if _first(r) else "top"
    elif side == "weakness":
        variant = "weakness1" if _last(r) else "weakness"
    elif r.value < RARELY * r.typical and r.value <= RARELY_MAX + EPS:
        # Doubles says "rarely" where singles says "almost never". The ceiling
        # stops "rarely serve short" at 40% when the typical pair is at 88%.
        variant = "rarely"
    else:
        variant = "bottom1" if _last(r) else "bottom"
    return t[f"phrase.{measure}.{variant}"]


def render(key: str, r: Ranked) -> tuple[str, str, str, str]:
    """(claim, figure, comparison, phrase) for one finding. The phrase is a
    lower-case verb phrase for style and strength findings and a full sentence
    (pronoun "They") for the weakness."""
    t = _templates()
    measure, side = key.rsplit(".", 1)
    phrase = _phrase(measure, side, r)
    words = {"typical": round(r.typical * 100), "below": r.below, "others": r.of - 1}
    if measure in WIN_RATES:
        if side == "top":
            words["better"] = (t["better.all"] if _first(r) else t["better.some"]).format(**words)
            comparison = t[f"comparison.{measure}.strength"]
        else:
            comparison = t[f"comparison.{measure}.weakness"]
    else:
        comparison = t[f"comparison.{measure}"]
    claim = t["claim"].format(pair="They", phrase=phrase)
    if side == "weakness":
        phrase = t[f"sentence.{measure}.weakness"].format(pair="They")
    return claim, f"{round(r.value * 100)}%", comparison.format(**words), phrase


def _edge(r: Ranked) -> int:
    return EDGE_SMALL if r.of < SMALL_GROUP else EDGE


def _candidates(
    pair_id: str, all_stats: dict[str, PairStats], pairs: dict[str, Pair]
) -> list[tuple[str, Kind, Ranked]]:
    ranks = {
        k: r for k in MEASURES if (r := rank_measure(all_stats, pairs, pair_id, k)) is not None
    }
    out: list[tuple[str, Kind, Ranked]] = []
    weak = None
    rates = [(k, ranks[k]) for k in WIN_RATES if k in ranks]  # in tie-break order
    if rates:
        # Furthest below typical; max() keeps the first of equal gaps.
        k, r = max(rates, key=lambda kr: round(kr[1].typical - kr[1].value, 9))
        if r.typical - r.value >= WEAKNESS_GAP - EPS:
            weak = k
            out.append((f"{k}.weakness", "weakness", r))
    for k, r in ranks.items():
        if k == weak:
            continue  # listed once, as the weakness
        edge = _edge(r)
        if r.rank <= edge and r.value - r.typical >= MIN_GAP - EPS:
            out.append((f"{k}.top", "strength" if k in WIN_RATES else "style", r))
        elif k in SHARES and r.rank >= r.of - edge + 1 and r.typical - r.value >= MIN_GAP - EPS:
            out.append((f"{k}.bottom", "style", r))
    return out


def order_pair_findings(findings: list[Finding]) -> list[Finding]:
    """Most extreme first (ties: serve, receive and first-4 measures before
    rally ones, then key), at most 4, keeping the weakness and placing it last.

    Serve and receive come first in the selection too: only two measures are
    rally ones, so at least two of the four places always go to serve,
    receive or first-4 findings when there are any."""
    ranked = sorted(
        findings,
        key=lambda f: (-f.percentile_distance, not _not_rally(f.key), f.key),
    )
    weak = [f for f in ranked if f.kind == "weakness"][:1]
    rest = [f for f in ranked if f.kind != "weakness"]
    return rest[: MAX_FINDINGS - len(weak)] + weak


def select_pair_findings(
    pair_id: str, all_stats: dict[str, PairStats], pairs: dict[str, Pair]
) -> list[Finding]:
    """The pair's findings in display order. Empty for unranked pairs."""
    if pair_id not in ranked_pairs(all_stats, pairs, pairs[pair_id].event):
        return []
    tips = _tips()
    found = []
    for key, kind, r in _candidates(pair_id, all_stats, pairs):
        claim, figure, comparison, phrase = render(key, r)
        found.append(Finding(
            key=key,
            kind=kind,
            claim=claim,
            figure=figure,
            comparison=comparison,
            tip=tips.get(key),
            clips=[],
            # Rounded so equal distances (1st of 10 vs 10th of 10) tie exactly.
            percentile_distance=round(abs(r.percentile - 50), 6),
            phrase=phrase,
        ))
    return order_pair_findings(found)


def display_last_name(player: DPlayer, names: dict[str, str] | None = None) -> str:
    """`names` (default: the doubles_display_names content) overrides by player
    id ("Pearly Tan" -> "Tan"). Otherwise the data mixes "BAEK" and "Lee", so
    all-capital names are title-cased and anything else is kept as written."""
    names = _display_names() if names is None else names
    if player.id in names:
        return names[player.id]
    name = player.last_name
    if not name.isupper():
        return name
    return _title(name)


def _title(name: str) -> str:
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in name.split())


def given_name(player: DPlayer, names: dict[str, str] | None = None) -> str:
    """player.csv's full name without the last name: "Benyapa Aimsaard" ->
    "Benyapa", "KIM Gi Jung" -> "Gi Jung". The display override's last name is
    the one removed, wherever it is ("Pearly Tan Koong Le" -> "Pearly Koong Le").
    The full name if nothing would be left."""
    names = _display_names() if names is None else names
    last = names.get(player.id, player.last_name).casefold().split()
    words = player.name.split()
    n = len(last)
    for i in range(len(words) - n + 1):
        if [w.casefold() for w in words[i:i + n]] == last:
            words = words[:i] + words[i + n:]
            break
    rest = " ".join(words) or player.name
    return _title(rest) if rest.isupper() else rest


def pair_name(
    pair_id: str, pairs: dict[str, Pair], players: dict[str, DPlayer],
    names: dict[str, str] | None = None,
) -> str:
    """"Baek and Lee"; partners sharing a last name get their given names:
    "Benyapa and Nuntakarn Aimsaard"."""
    a, b = (players[p] for p in pairs[pair_id].players)
    la, lb = display_last_name(a, names), display_last_name(b, names)
    if la.casefold() == lb.casefold():
        return f"{given_name(a, names)} and {given_name(b, names)} {la}"
    return f"{la} and {lb}"


def pair_summary(
    pair_id: str, findings: list[Finding], pairs: dict[str, Pair], players: dict[str, DPlayer]
) -> str | None:
    """'{pair name} <lead phrase> and <next phrase>. <weakness sentence>',
    dropping whatever part is missing. The lead is the first serve, receive or
    first-4 finding, or else the first finding. The next phrase is the next
    finding that can pair with it (never first4.share with first4.win_rate).
    With only a weakness, the pair is named in its sentence. None when there
    are no findings."""
    if not findings:
        return None
    names = pair_name(pair_id, pairs, players)
    plain = [f for f in findings if f.kind != "weakness"]
    weak = next((f for f in findings if f.kind == "weakness"), None)
    lead = next((f for f in plain if _not_rally(f.key)), plain[0] if plain else None)
    if lead is None:
        measure = weak.key.rsplit(".", 1)[0]
        return _templates()[f"sentence.{measure}.weakness"].format(pair=names)
    # Never first4.share with first4.win_rate (NO_PAIRING); anything else goes.
    other = next((f for f in plain if f is not lead and _can_pair(f.key, lead.key)), None)
    text = f"{names} {lead.phrase}"
    if other is not None:
        text += f" and {other.phrase}"
    text += "."
    if weak is not None:
        text += f" {weak.phrase}"
    return text
