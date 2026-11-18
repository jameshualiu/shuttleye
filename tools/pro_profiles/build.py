"""Build the static pro-profile and tournament JSON the frontend renders.

Run from `tools/`:
    python -m pro_profiles.build --source <CoachAI-Projects checkout> --out <dir>
Output is deterministic: sorted keys, defined list orders, no timestamps.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path

from .clips import Clip, clip_for_rally, make_labels
from .findings import Finding, select_findings, summary
from .load import CONTENT_DIR, Match, load_content, load_dataset
from .stats import (
    BANDS,
    MIN_BAND_RALLIES,
    MIN_GROUPED_SHOTS,
    SHOWN_GROUPS,
    PlayerStats,
    _band_of,
    player_stats,
    rank_shot_share,
    share,
    win_rate,
)

PINNED_SHA = "45517f7d4cb936b03f3eabf939cc7959d39226fe"
PHOTOS_PATH = CONTENT_DIR / "photos.json"
ROUND_WORDS = {
    "Finals": "final",
    "Semi-finals": "semi-final",
    "Quarter-finals": "quarter-final",
    "Group-Stage": "group stage",
}


def _pct(x: float) -> float:
    return round(x * 100, 1)


def _clip_json(c: Clip) -> dict:
    return {
        "youtubeId": c.youtube_id,
        "startSec": c.start_sec,
        "endSec": c.end_sec,
        "matchLabel": c.match_label,
        "scoreLabel": c.score_label,
    }


def _finding_json(f: Finding) -> dict:
    return {
        "key": f.key,
        "kind": f.kind,
        "claim": f.claim,
        "figure": f.figure,
        "comparison": f.comparison,
        "tip": f.tip,
        "clips": [_clip_json(c) for c in f.clips],
    }


def _photo_json(pid: str, photos: dict) -> dict | None:
    p = photos.get(pid)
    if not p:
        return None
    return {
        "src": f"/pro-data/photos/{pid}.jpg",
        "credit": f"Photo: {p['author']}, {p['licence']}",
        "sourceUrl": p["sourceUrl"],
        "focusX": p["focusX"],
        "focusY": p["focusY"],
    }


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def _typical_shares(all_stats: dict[str, PlayerStats]) -> dict[str, float]:
    ranked = [s for s in all_stats.values() if s.grouped_shots >= MIN_GROUPED_SHOTS]
    return {
        g: statistics.median(share(s, g) for s in ranked) if ranked else 0.0
        for g in SHOWN_GROUPS
    }


def _typical_win_rates(all_stats: dict[str, PlayerStats]) -> dict[str, float]:
    out = {}
    for b, *_ in BANDS:
        rates = [w for s in all_stats.values() if (w := win_rate(s, b)) is not None]
        out[b] = statistics.median(rates) if rates else 0.0
    return out


def _view(
    kind: str,
    player: str,
    subset: list[Match],
    all_stats: dict[str, PlayerStats],
    typical_share: dict[str, float],
    typical_win: dict[str, float],
    *,
    ranked: bool,
    full: bool,
    sources: dict,
    players: dict,
    tournaments: dict,
) -> dict:
    ps = player_stats(subset, player)
    shot_rows = []
    for g in SHOWN_GROUPS:
        r = rank_shot_share(all_stats, player, g) if full and ranked else None
        shot_rows.append({
            "group": g,
            "share": _pct(share(ps, g)),
            "count": ps.shots_by_group.get(g, 0),
            "rank": r.rank if r else None,
            "of": r.of if r else None,
            "typical": _pct(typical_share[g]),
        })
    band_rows = [
        {
            "band": key,
            "label": label,
            "rallies": ps.rallies_by_band[key],
            "winRate": None if (w := win_rate(ps, key)) is None else round(w * 100),
            "typical": round(typical_win[key] * 100),
        }
        for key, label, _lo, _hi in BANDS
    ]
    findings: list[Finding] = []
    browser: list[Clip] = []
    if full and ranked:
        findings = select_findings(
            player, all_stats, subset, sources, players=players, tournaments=tournaments
        )
    if not full:
        labels = make_labels(player, players, tournaments)
        for m in sorted(subset, key=lambda m: (m.date, m.id)):
            for r in sorted(m.rallies, key=lambda r: (r.set_no, r.number)):
                clip = clip_for_rally(m, r, sources, labels)
                if clip is not None:
                    browser.append(clip)
    return {
        "kind": kind,
        "shots": ps.grouped_shots,
        "rallies": sum(ps.rallies_by_band.values()),
        "shotChoice": shot_rows,
        "bands": band_rows,
        "findings": [_finding_json(f) for f in findings],
        "rallyBrowser": [_clip_json(c) for c in browser],
    }


def _game_scores(m: Match) -> list[list[int]]:
    games = []
    for set_no in sorted({r.set_no for r in m.rallies}):
        won = sum(1 for r in m.rallies if r.set_no == set_no and r.winner == m.winner)
        lost = sum(1 for r in m.rallies if r.set_no == set_no and r.winner == m.loser)
        games.append([won, lost])
    return games


def _match_label(m: Match, player: str, players: dict, tournaments: dict) -> str:
    e = tournaments[m.edition_id]
    opp = m.loser if player == m.winner else m.winner
    return (f"{e['name']} {e['season']} {ROUND_WORDS.get(m.round, m.round.lower())}"
            f" vs {players[opp]['name']}")


def build(
    source_dir: Path,
    out_dir: Path,
    *,
    players: dict | None = None,
    tournaments: dict | None = None,
    sources: dict | None = None,
    photos: dict | None = None,
) -> None:
    players = players if players is not None else load_content("players")
    tournaments = tournaments if tournaments is not None else load_content("tournaments")
    sources = sources if sources is not None else load_content("clip_sources")
    if photos is None:
        photos = (
            json.loads(PHOTOS_PATH.read_text(encoding="utf-8")) if PHOTOS_PATH.exists() else {}
        )
    out_dir = Path(out_dir)
    matches = load_dataset(Path(source_dir), players, tournaments)

    all_stats = {pid: player_stats(matches, pid) for pid in players}
    ranked_ids = {p for p, s in all_stats.items() if s.grouped_shots >= MIN_GROUPED_SHOTS}
    typical_share = _typical_shares(all_stats)
    typical_win = _typical_win_rates(all_stats)

    index_rows = []
    for pid, info in players.items():
        mine = [m for m in matches if pid in (m.winner, m.loser)]
        if not mine:
            continue
        ranked = pid in ranked_ids
        photo = _photo_json(pid, photos)
        years = [int(m.date[:4]) for m in mine]
        kw = dict(
            all_stats=all_stats, typical_share=typical_share, typical_win=typical_win,
            ranked=ranked, sources=sources, players=players, tournaments=tournaments,
        )
        views = {"all": _view("all", pid, mine, full=True, **kw)}
        filters = [{"id": "all", "label": f"All {len(mine)} matches", "kind": "all",
                    "matches": len(mine)}]
        editions = sorted(
            {m.edition_id for m in mine},
            key=lambda e: (-tournaments[e]["season"], tournaments[e]["name"], e),
        )
        for e in editions:
            sub = [m for m in mine if m.edition_id == e]
            fid = f"t:{e}"
            views[fid] = _view("tournament", pid, sub, full=False, **kw)
            filters.append({"id": fid, "kind": "tournament", "matches": len(sub),
                            "label": f"{tournaments[e]['name']} {tournaments[e]['season']}"})
        for m in sorted(mine, key=lambda m: (m.date, m.id)):
            fid = f"m:{m.id}"
            views[fid] = _view("match", pid, [m], full=False, **kw)
            filters.append({"id": fid, "kind": "match", "matches": 1,
                            "label": _match_label(m, pid, players, tournaments)})
        findings = select_findings(
            pid, all_stats, mine, sources, players=players, tournaments=tournaments
        ) if ranked else []
        _write(out_dir / "players" / f"{pid}.json", {
            "id": pid,
            "name": info["name"],
            "event": info["event"],
            "context": {
                "matches": len(mine),
                "firstYear": min(years),
                "lastYear": max(years),
                "comparedWith": len(ranked_ids) - (1 if ranked else 0),
            },
            "summary": summary(pid, findings, players=players) if ranked else None,
            "photo": photo,
            "filters": filters,
            "views": views,
        })
        index_rows.append({"id": pid, "name": info["name"], "event": info["event"],
                           "matches": len(mine), "ranked": ranked, "photo": photo})
    index_rows.sort(key=lambda r: (r["event"] != "MS", r["name"], r["id"]))
    _write(out_dir / "players" / "index.json",
           {"generatedFrom": PINNED_SHA, "players": index_rows})

    edition_rows = []
    for eid, e in tournaments.items():
        ems = sorted((m for m in matches if m.edition_id == eid), key=lambda m: (m.date, m.id))
        if not ems:
            continue
        ids = {p for m in ems for p in (m.winner, m.loser)}
        _write(out_dir / "tournaments" / f"{eid}.json", {
            "id": eid,
            "name": e["name"],
            "season": e["season"],
            "matches": [{
                "id": m.id,
                "round": m.round,
                "date": m.date,
                "winner": {"id": m.winner, "name": players[m.winner]["name"]},
                "loser": {"id": m.loser, "name": players[m.loser]["name"]},
                "games": _game_scores(m),
            } for m in ems],
            "players": [{"id": p, "name": players[p]["name"], "event": players[p]["event"]}
                        for p in sorted(ids, key=lambda p: (players[p]["event"] != "MS",
                                                            players[p]["name"], p))],
        })
        edition_rows.append({"id": eid, "name": e["name"], "season": e["season"],
                             "matches": len(ems)})
    edition_rows.sort(key=lambda r: (-r["season"], r["name"], r["id"]))
    _write(out_dir / "tournaments" / "index.json", {"editions": edition_rows})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m pro_profiles.build")
    ap.add_argument("--source", default=os.environ.get("SHUTTLESET_DIR"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if not args.source:
        ap.error("--source or SHUTTLESET_DIR required")
    build(Path(args.source), Path(args.out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
