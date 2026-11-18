"""Generate a player's findings, header summary, tips and example clips.

Rules follow the spec's "Findings" and "Example rallies (clips)" sections.
Wording lives in content/templates.json and content/tips.json, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import Callable, Literal

from .clips import Clip, clip_for_rally, make_labels
from .load import Match, Rally, load_content
from .stats import BANDS, SHOWN_GROUPS, PlayerStats, Ranked, _band_of, rank_band, rank_shot_share

MAX_FINDINGS = 4
MAX_CLIPS = 5
EDGE = 4  # top 4 / bottom 4 of the comparison group
WEAKNESS_GAP = 0.03  # a weakness is 3+ percentage points below typical
ALMOST_NEVER = 0.5  # "almost never" only below half the typical share

PRONOUNS = {
    "MS": {"He": "He", "he": "he", "his": "his"},
    "WS": {"He": "She", "he": "she", "his": "her"},
}
KIND_ORDER = {"style": 0, "strength": 1, "weakness": 2}

Kind = Literal["style", "strength", "weakness"]


@dataclass
class Finding:
    key: str  # "shot.Lift.top", "shot.Drop.bottom", "band.long.strength", "band.short.weakness"
    kind: Kind
    claim: str
    figure: str  # "27.7%" (shot share) / "58%" (band win rate)
    comparison: str
    tip: str | None
    clips: list[Clip] = field(default_factory=list)
    percentile_distance: float = 0.0
    # Rendered summary fragment: a lower-case phrase for style/strength
    # findings, a full sentence for a weakness.
    phrase: str = ""


@cache
def _templates() -> dict:
    return load_content("templates")


@cache
def _tips() -> dict:
    return load_content("tips")


def _pronouns(player: str, players: dict) -> dict[str, str]:
    return PRONOUNS[players[player]["event"]]


def render(key: str, kind: Kind, r: Ranked, event: str) -> tuple[str, str, str, str]:
    """(claim, figure, comparison, phrase) for one finding."""
    t = _templates()
    compare: dict[str, str] = {}  # overrides used only in the comparison line
    words = dict(PRONOUNS[event], below=r.below, others=r.of - 1,
                 below_word="one" if r.below == 1 else str(r.below))
    measure, name, side = key.split(".")
    if measure == "shot":
        verb, verb_s = t["verbs"][name]
        words.update(verb=verb, verb_s=verb_s, typical=f"{r.typical * 100:.1f}")
        figure = f"{r.value * 100:.1f}%"

        def shot_claim(variant: str) -> str:
            # A shot can override the generic claim ("plays more net shots").
            return t.get(f"claim.shot.{name}.{variant}", t[f"claim.shot.{variant}"])

        if side == "top":
            # "More than any other pro" only when strictly above everyone else.
            variant = "top1" if r.below == r.of - 1 else "top"
            claim = shot_claim(variant)
            comparison = t["comparison.shot.top"]
            phrase = t[f"phrase.shot.{name}.{variant}"]
        else:
            # Same key either way; the wording softens unless the share is
            # under half the typical pro's.
            variant = "bottom" if r.value < ALMOST_NEVER * r.typical else "bottom_mild"
            claim = shot_claim(variant)
            phrase = t[f"phrase.shot.{name}.{variant}"]
            if r.below == 0:
                comparison = t["comparison.shot.bottom0"]
            else:
                comparison = t["comparison.shot.bottom"]
                # "Only one of 38 pros drops less" / "Only 3 of 38 pros drop less"
                compare["verb_s"] = verb_s if r.below == 1 else verb
    else:
        words["typical"] = str(round(r.typical * 100))
        figure = f"{round(r.value * 100)}%"
        claim = t[f"claim.band.{name}.{side}"]
        comparison = t[f"comparison.band.{name}.{side}"]
        if side == "strength":
            words["better"] = (t["better.all"] if r.below == r.of - 1
                               else t["better.some"]).format(**words)
        phrase = t[f"phrase.band.{name}.strength" if side == "strength"
                   else f"sentence.band.{name}.weakness"]
    return (
        claim.format(**words),
        figure,
        comparison.format(**{**words, **compare}),
        phrase.format(**words),
    )


def _candidates(player: str, all_stats: dict[str, PlayerStats]) -> list[tuple[str, Kind, Ranked]]:
    out: list[tuple[str, Kind, Ranked]] = []
    for g in SHOWN_GROUPS:
        r = rank_shot_share(all_stats, player, g)
        if r is None:
            continue
        if r.rank <= EDGE:
            out.append((f"shot.{g}.top", "style", r))
        elif r.rank >= r.of - (EDGE - 1):
            out.append((f"shot.{g}.bottom", "style", r))
    bands = [(b, r) for b, *_ in BANDS if (r := rank_band(all_stats, player, b)) is not None]
    for b, r in bands:
        if r.rank <= EDGE:
            out.append((f"band.{b}.strength", "strength", r))
    if bands:
        # Lowest band win rate, if 3+ points below typical (unrounded), is the
        # weakness even when it isn't bottom 4. A strength band never is.
        b, r = min(bands, key=lambda br: br[1].value)
        if r.value <= r.typical - WEAKNESS_GAP + 1e-9 and r.rank > EDGE:
            out.append((f"band.{b}.weakness", "weakness", r))
    return out


def order_findings(findings: list[Finding]) -> list[Finding]:
    """Most extreme first (ties: style, strength, weakness, then key), at most
    4, keeping the weakness if there is one and always placing it last."""
    ranked = sorted(
        findings, key=lambda f: (-f.percentile_distance, KIND_ORDER[f.kind], f.key)
    )
    weak = [f for f in ranked if f.kind == "weakness"][:1]
    rest = [f for f in ranked if f.kind != "weakness"]
    return rest[: MAX_FINDINGS - len(weak)] + weak


def _shows(key: str, player: str, rally: Rally) -> bool:
    measure, name, side = key.split(".")
    if rally.winner is None:
        return False
    if measure == "shot":
        return rally.winner == player and any(
            s.player == player and s.group == name for s in rally.shots
        )
    if _band_of(len(rally.shots)) != name:
        return False
    return (rally.winner == player) == (side == "strength")


def _spread_clips(
    player: str,
    matches: list[Match],
    sources: dict,
    shows: Callable[[Rally], bool],
    players: dict | None,
    tournaments: dict | None,
) -> list[Clip]:
    """Up to 5 rallies passing `shows`, from matches with a clip source. One per
    match first (earliest date first), then second picks, and so on; within a
    match, by (set, rally number)."""
    players = players if players is not None else load_content("players")
    tournaments = tournaments if tournaments is not None else load_content("tournaments")
    labels = make_labels(player, players, tournaments)
    queues: list[tuple[Match, list[Rally]]] = []
    for m in sorted(matches, key=lambda m: (m.date, m.id)):
        if player not in (m.winner, m.loser) or m.id not in sources:
            continue
        rallies = sorted((r for r in m.rallies if shows(r)), key=lambda r: (r.set_no, r.number))
        if rallies:
            queues.append((m, rallies))
    clips: list[Clip] = []
    depth = 0
    while len(clips) < MAX_CLIPS and any(depth < len(rs) for _, rs in queues):
        for m, rallies in queues:
            if depth < len(rallies) and len(clips) < MAX_CLIPS:
                clip = clip_for_rally(m, rallies[depth], sources, labels)
                if clip is not None:
                    clips.append(clip)
        depth += 1
    return clips


def pick_clips(
    player: str,
    key: str,
    matches: list[Match],
    sources: dict,
    *,
    players: dict | None = None,
    tournaments: dict | None = None,
) -> list[Clip]:
    """Up to 5 rallies that show the finding `key` (see _spread_clips for order)."""
    return _spread_clips(
        player, matches, sources, lambda r: _shows(key, player, r), players, tournaments
    )


def sample_clips(
    player: str,
    matches: list[Match],
    sources: dict,
    *,
    players: dict | None = None,
    tournaments: dict | None = None,
) -> list[Clip]:
    """Up to 5 of the player's real rallies (winner recorded), in the same order
    as finding clips. Used when the all-matches view has no findings."""
    return _spread_clips(
        player, matches, sources, lambda r: r.winner is not None and bool(r.shots),
        players, tournaments,
    )


def select_findings(
    player: str,
    all_stats: dict[str, PlayerStats],
    matches: list[Match],
    sources: dict,
    *,
    players: dict | None = None,
    tournaments: dict | None = None,
) -> list[Finding]:
    players = players if players is not None else load_content("players")
    event = players[player]["event"]
    tips = _tips()
    candidates = []
    for key, kind, r in _candidates(player, all_stats):
        claim, figure, comparison, phrase = render(key, kind, r, event)
        candidates.append(Finding(
            key=key,
            kind=kind,
            claim=claim,
            figure=figure,
            comparison=comparison,
            tip=tips.get(key),
            # Rounded so equal distances (e.g. 1 of 38 vs 37 of 38) tie exactly.
            percentile_distance=round(abs(r.percentile - 50), 6),
            phrase=phrase,
        ))
    chosen = order_findings(candidates)
    for f in chosen:
        f.clips = pick_clips(
            player, f.key, matches, sources, players=players, tournaments=tournaments
        )
    return chosen


def summary(player: str, findings: list[Finding], *, players: dict | None = None) -> str | None:
    """'{He} <first style phrase> and <first strength phrase>. <weakness sentence>',
    dropping whatever part is missing. None when there are no findings."""
    if not findings:
        return None
    players = players if players is not None else load_content("players")
    first = {kind: next((f for f in findings if f.kind == kind), None) for kind in KIND_ORDER}
    phrases = [f.phrase for f in (first["style"], first["strength"]) if f is not None]
    parts = []
    if phrases:
        parts.append(f"{_pronouns(player, players)['He']} {' and '.join(phrases)}.")
    if first["weakness"] is not None:
        parts.append(first["weakness"].phrase)
    return " ".join(parts)
