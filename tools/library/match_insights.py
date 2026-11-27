"""Per-match insights for the match page, precomputed by `publish`: each
player's six insights in this match, and findings where the match differs
from the player's usual (their other published matches)."""
from __future__ import annotations

from pro_profiles.build import _finding_json
from pro_profiles.findings import Finding
from pro_profiles.load import load_content

from .insights import Insights, _at, player_insights
from .profiles import (
    FINDING_SCALARS,
    _rankable,
    finding_clips,
    fmt,
    people,
    sources_for,
    templates,
    words,
)
from .to_model import to_match

MAX_MATCH_FINDINGS = 4
# Minimum gap (percentage points) for a finding, by scalar rule. Tempo has no
# agreed threshold, so it is shown in the insights but never as a finding.
MIN_GAP = {"share": 5.0, "rate": 10.0, "band": 10.0}


def _player_findings(match, pid, ins, usual, players, tournaments) -> list[Finding]:
    t = templates()
    event = players[pid]["event"]
    cands = []
    for path, rule, family in FINDING_SCALARS:
        if rule not in MIN_GAP:
            continue
        v, u = _at(_rankable(ins), path), _at(_rankable(usual), path)
        if v is None or u is None or abs(v - u) < MIN_GAP[rule] - 1e-9:
            continue
        more = v > u
        w = words(path, family, event)
        w.update(value=fmt(rule, v), usual=fmt(rule, u))
        kind = "style" if rule == "share" else "strength" if more else "weakness"
        cands.append((abs(v - u), path, Finding(
            key=".".join((*path, "more" if more else "less")),
            kind=kind,
            claim=t[family].get("match", t["match.claim"]).format(**w),
            figure=w["value"],
            comparison=t["match.comparison"].format(**w),
            tip=None,
        )))
    cands.sort(key=lambda c: (-c[0], c[2].key))
    chosen = cands[:MAX_MATCH_FINDINGS]
    sources = sources_for([match])
    for _gap, path, f in chosen:
        side = "strength" if f.kind == "strength" else "weakness" if f.kind == "weakness" else (
            "top" if f.key.endswith(".more") else "bottom")
        f.clips = finding_clips(pid, path, side, [match], sources, players, tournaments)
    return [f for _gap, _path, f in chosen]


def match_insights(
    doc: dict,
    usual: dict[str, Insights],
    *,
    players: dict | None = None,
    tournaments: dict | None = None,
) -> dict:
    """{A: {insights, findings}, B: {...}}. `usual` maps player id -> Insights over
    that player's other published matches; a player missing from it has no
    history, so no findings."""
    players = people([doc], players if players is not None else load_content("players"))
    tournaments = tournaments if tournaments is not None else load_content("tournaments")
    match = to_match(doc)
    out = {}
    for side in ("A", "B"):
        pid = doc["players"][side]["id"]
        ins = player_insights([match], pid)
        found = (_player_findings(match, pid, ins, usual[pid], players, tournaments)
                 if usual.get(pid) else [])
        out[side] = {"insights": ins, "findings": [_finding_json(f) for f in found]}
    return out
