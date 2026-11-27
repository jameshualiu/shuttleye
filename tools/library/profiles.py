"""Build the library's Firestore documents: player profiles, their views,
tournaments and the list index. Mirrors pro_profiles.build's JSON, with the
six insights in place of the shot-choice table and rally bands."""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from pro_profiles.build import (
    _all_label,
    _clip_json,
    _finding_json,
    _match_label,
    _photo_json,
    _tournament_match_json,
)
from pro_profiles.clips import Clip, clip_for_rally, make_labels
from pro_profiles.findings import (
    EDGE,
    PRONOUNS,
    WEAKNESS_GAP,
    Finding,
    _spread_clips,
    order_findings,
    sample_clips,
    summary,
)
from pro_profiles.load import Match, Rally
from pro_profiles.stats import MIN_GROUPED_SHOTS, Ranked, _band_of, player_stats

from .insights import MIN_COMPARED, PHASES, Insights, player_insights, rank_insight
from .to_model import to_match

TEMPLATES_PATH = Path(__file__).parent / "content" / "insight_templates.json"
DEFAULT_EVENT = "MS"  # players not yet in players.json

# (insight path, rule, template family). Rules: "share" and "tempo" give a
# style finding at the top/bottom EDGE; "rate" gives a strength at the top;
# "band" is a rate whose lowest value can also be the weakness.
# "bandWin" is bands[*].winRate keyed by band (see _rankable).
_PHASE_GROUPS = ("Smash", "Net", "Lift", "Block", "Drop", "Clear")
FINDING_SCALARS: list[tuple[tuple[str, ...], str, str]] = [
    *[(("phaseMix", "late", g), "share", "phase") for g in _PHASE_GROUPS],
    *[(("phaseMix", "start", g), "share", "phase") for g in _PHASE_GROUPS],
    (("replies", "Smash", "Net"), "share", "reply"),
    (("replies", "Smash", "Lift"), "share", "reply"),
    (("replies", "Smash", "Block"), "share", "reply"),
    *[(("zones", z), "share", "zone") for z in ("rear-left", "rear-right", "front-left", "front-right")],
    (("tempo", "secPerShot"), "tempo", "tempo"),  # higher = slower: top is slowest
    (("serve", "shortShare"), "share", "serveShort"),
    *[(("bandWin", b), "band", "band") for b in ("short", "mid", "long")],
    (("smashWins", "winShare"), "rate", "smashWins"),
    (("serve", "pointsWonShort"), "rate", "serveWon"),
]
_PHASE_RANGE = {k: (lo, hi) for k, lo, hi in PHASES}


@cache
def templates() -> dict:
    return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))


def people(docs: list[dict], players: dict) -> dict:
    """players.json entries plus anyone only known from a match doc
    (their doc name, and the doc's event, else DEFAULT_EVENT)."""
    out = {pid: dict(p) for pid, p in players.items()}
    for d in docs:
        for ref in d["players"].values():
            out.setdefault(ref["id"], {"name": ref["name"], "event": ref.get("event") or DEFAULT_EVENT})
    return out


def _library_match_json(m: Match, players: dict) -> dict:
    """pro_profiles' tournament match row, with games as [{a, b}] (Firestore has no nested arrays)."""
    row = _tournament_match_json(m, players)
    row["games"] = [{"a": a, "b": b} for a, b in row["games"]]
    return row


def _rankable(ins: Insights) -> Insights:
    return {**ins, "bandWin": {b["band"]: b["winRate"] for b in ins["bands"]}}


def fmt(rule: str, v: float) -> str:
    if rule == "share":
        return f"{v:.1f}%"
    if rule == "tempo":
        return f"{v:.2f}s"
    return f"{round(v)}%"


def words(path: tuple[str, ...], family: str, event: str) -> dict:
    """Pronouns plus the family's vocabulary for this scalar, with `of` rendered."""
    t = templates()
    w = dict(PRONOUNS[event])
    w["His"] = w["his"].capitalize()
    if family == "phase":
        w["when"] = t["when"][path[1]]
        w["verb_s"], w["verb_ed"] = t["verbs"][path[2]]
    elif family == "reply":
        w["reply"] = t["replyWords"][path[2]]
    elif family == "zone":
        w["where"] = t["where"][path[1]]
    elif family == "band":
        w.update(t["bands"][path[1]])
    fam = t[family]
    w["of"] = fam["of"].format(**w)
    if "did" in fam:
        w["did"] = fam["did"].format(**w)
    return w


def _render(path, rule, family, side, r: Ranked, event) -> tuple[str, str, str, str]:
    """(claim, figure, comparison, phrase) for a profile finding."""
    t = templates()
    fam = t[family]
    w = words(path, family, event)
    w.update(typical=fmt(rule, r.typical), below=r.below, others=r.of - 1)
    if side == "strength":
        w["better"] = t["better.all" if r.below == r.of - 1 else "better.some"].format(**w)
        comparison = t["comparison.better"]
    else:
        comparison = t["comparison.typical"]
    return (fam[f"claim.{side}"].format(**w), fmt(rule, r.value),
            comparison.format(**w), fam[f"phrase.{side}"].format(**w))


def _candidates(pool: dict[str, Insights], pid: str) -> list[tuple]:
    """(path, rule, family, side, kind, Ranked) like findings._candidates."""
    out, bands = [], []
    for path, rule, family in FINDING_SCALARS:
        r = rank_insight(pool, pid, path)
        if r is None or (r.rank == 1 and r.below == 0):
            continue  # not enough players, or everyone level
        if rule in ("share", "tempo"):
            if r.rank <= EDGE:
                out.append((path, rule, family, "top", "style", r))
            elif r.rank >= r.of - (EDGE - 1):
                out.append((path, rule, family, "bottom", "style", r))
            continue
        if r.rank <= EDGE:
            out.append((path, rule, family, "strength", "strength", r))
        if rule == "band":
            bands.append((path, rule, family, r))
    if bands:
        path, rule, family, r = min(bands, key=lambda b: b[3].value)
        if r.value <= r.typical - WEAKNESS_GAP * 100 + 1e-9 and r.rank > EDGE:
            out.append((path, rule, family, "weakness", "weakness", r))
    return out


def shows(path: tuple[str, ...], side: str, player: str, rally: Rally) -> bool:
    """Does this rally show the finding? Real rallies only."""
    shots = rally.shots
    if rally.winner is None or not shots:
        return False
    won = rally.winner == player
    mine = [(i, s) for i, s in enumerate(shots) if s.player == player]
    head = path[0]
    if head == "phaseMix":
        lo, hi = _PHASE_RANGE[path[1]]
        return won and any(s.group == path[2] and s.order >= lo and (hi is None or s.order <= hi)
                           for _, s in mine)
    if head == "replies":
        return won and any(s.group == path[2] and i > 0 and shots[i - 1].group == path[1]
                           and shots[i - 1].player not in (player, "?") for i, s in mine)
    if head == "zones":
        return won and any(s.zone == path[1] for _, s in mine)
    if head == "tempo":
        return won and len(shots) >= 9  # long exchanges show the pace
    if head == "serve":
        serve = shots[0].detail if shots[0].player == player else None
        if path[1] == "shortShare":
            return serve == ("short service" if side == "top" else "long service")
        return won != (side == "weakness") and serve == "short service"
    if head == "bandWin":
        return _band_of(len(shots)) == path[1] and won == (side != "weakness")
    if head == "smashWins":
        # Strength: won within a shot of the smash. Weakness: smashed late and lost.
        return won != (side == "weakness") and any(
            s.group == "Smash" and i >= len(shots) - 2 for i, s in mine)
    return False


def sources_for(matches: list[Match]) -> dict:
    return {m.id: {"url": m.youtube_url, "offsetSec": 0, "checked": True} for m in matches}


def finding_clips(player, path, side, matches, sources, players, tournaments) -> list[Clip]:
    return _spread_clips(player, matches, sources, lambda r: shows(path, side, player, r),
                         players, tournaments)


def _findings(pid, pool, mine, sources, players, tournaments) -> list[Finding]:
    event = players[pid]["event"]
    where = {}
    cands = []
    for path, rule, family, side, kind, r in _candidates(pool, pid):
        key = ".".join((*path, side))
        where[key] = (path, side)
        claim, figure, comparison, phrase = _render(path, rule, family, side, r, event)
        cands.append(Finding(key=key, kind=kind, claim=claim, figure=figure, comparison=comparison,
                             tip=None, percentile_distance=round(abs(r.percentile - 50), 6),
                             phrase=phrase))
    chosen = order_findings(cands)
    for f in chosen:
        f.clips = finding_clips(pid, *where[f.key], mine, sources, players, tournaments)
    return chosen


def _view(kind, pid, subset, sources, players, tournaments, *, full, findings=()) -> dict:
    ps = player_stats(subset, pid)
    browser: list[Clip] = []
    if full and not findings:
        browser = sample_clips(pid, subset, sources, players=players, tournaments=tournaments)
    if not full:
        labels = make_labels(pid, players, tournaments)
        for m in sorted(subset, key=lambda m: (m.date, m.id)):
            for r in sorted(m.rallies, key=lambda r: (r.set_no, r.number)):
                if r.winner is not None and (clip := clip_for_rally(m, r, sources, labels)):
                    browser.append(clip)
    return {
        "kind": kind,
        "shots": ps.grouped_shots,
        "rallies": sum(ps.rallies_by_band.values()),
        "insights": player_insights(subset, pid),
        "findings": [_finding_json(f) for f in findings] if full else [],
        "rallyBrowser": [_clip_json(c) for c in browser],
    }


def known_editions(docs: list[dict], tournaments: dict) -> list[dict]:
    """The docs whose editionId is in tournaments.json; the rest are skipped with a warning."""
    keep = []
    for d in docs:
        if d.get("editionId") in tournaments:
            keep.append(d)
        else:
            print(f"[library] WARNING {d.get('id')}: editionId {d.get('editionId')!r} is not in "
                  f"tournaments.json; left out of the library")
    return keep


def build_library(docs: list[dict], players: dict, tournaments: dict, photos: dict) -> dict[str, dict]:
    """Firestore path -> document for the published match `docs` (docs of an
    edition missing from `tournaments` are skipped with a warning)."""
    docs = known_editions(docs, tournaments)
    players = people(docs, players)
    matches = [to_match(d) for d in docs]
    sources = sources_for(matches)
    ids = sorted({p for m in matches for p in (m.winner, m.loser)})
    mine_of = {p: [m for m in matches if p in (m.winner, m.loser)] for p in ids}
    ranked_ids = {p for p in ids if player_stats(mine_of[p], p).grouped_shots >= MIN_GROUPED_SHOTS}
    comparing = len(ranked_ids) >= MIN_COMPARED
    pool = {p: _rankable(player_insights(mine_of[p], p)) for p in ranked_ids} if comparing else {}

    out: dict[str, dict] = {}
    index_rows = []
    for pid in ids:
        info, mine = players[pid], mine_of[pid]
        ranked = pid in ranked_ids
        kw = dict(sources=sources, players=players, tournaments=tournaments)
        findings = _findings(pid, pool, mine, **kw) if comparing and ranked else []
        base = f"players/{pid}"
        out[f"{base}/views/all"] = _view("all", pid, mine, full=True, findings=findings, **kw)
        filters = [{"id": "all", "label": _all_label(len(mine)), "kind": "all", "matches": len(mine)}]
        editions = sorted({m.edition_id for m in mine},
                          key=lambda e: (-tournaments[e]["season"], tournaments[e]["name"], e))
        for e in editions:
            sub = [m for m in mine if m.edition_id == e]
            out[f"{base}/views/t:{e}"] = _view("tournament", pid, sub, full=False, **kw)
            filters.append({"id": f"t:{e}", "kind": "tournament", "matches": len(sub),
                            "label": f"{tournaments[e]['name']} {tournaments[e]['season']}"})
        for m in sorted(mine, key=lambda m: (m.date, m.id)):
            out[f"{base}/views/m:{m.id}"] = _view("match", pid, [m], full=False, **kw)
            filters.append({"id": f"m:{m.id}", "kind": "match", "matches": 1,
                            "label": _match_label(m, pid, players, tournaments)})
        years = [int(m.date[:4]) for m in mine]
        photo = _photo_json(pid, photos)
        out[base] = {
            "id": pid,
            "name": info["name"],
            "event": info["event"],
            "context": {
                "matches": len(mine),
                "firstYear": min(years),
                "lastYear": max(years),
                "comparedWith": len(ranked_ids) - ranked if comparing else 0,
            },
            "summary": summary(pid, findings, players=players),
            "photo": photo,
            "filters": filters,
        }
        index_rows.append({"id": pid, "name": info["name"], "event": info["event"],
                           "matches": len(mine), "ranked": ranked, "photo": photo})
    index_rows.sort(key=lambda r: (r["event"] != "MS", r["name"], r["id"]))

    edition_rows = []
    for eid in sorted({m.edition_id for m in matches}):
        e = tournaments[eid]
        ems = sorted((m for m in matches if m.edition_id == eid), key=lambda m: (m.date, m.id))
        pids = {p for m in ems for p in (m.winner, m.loser)}
        out[f"tournaments/{eid}"] = {
            "id": eid,
            "name": e["name"],
            "season": e["season"],
            "matches": [_library_match_json(m, players) for m in ems],
            "players": [{"id": p, "name": players[p]["name"], "event": players[p]["event"]}
                        for p in sorted(pids, key=lambda p: (players[p]["event"] != "MS",
                                                             players[p]["name"], p))],
        }
        edition_rows.append({"id": eid, "name": e["name"], "season": e["season"], "matches": len(ems)})
    edition_rows.sort(key=lambda r: (-r["season"], r["name"], r["id"]))

    out["library/index"] = {
        "players": index_rows,
        "editions": edition_rows,
        "matches": [
            {"id": d["id"], "editionId": d["editionId"], "round": d["round"], "date": d["date"],
             "players": d["players"], "games": d.get("games"), "youtubeId": d["youtubeId"]}
            for d in sorted(docs, key=lambda d: (d["date"], d["id"]))
        ],
    }
    return out
