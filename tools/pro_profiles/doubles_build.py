"""Build the static doubles pair and tournament JSON the frontend renders.

Run from `tools/`:
    python -m pro_profiles.doubles_build --source <DShuttleNet dir> --out <dir>
The source files are checked against content/doubles_checksums.json first.
Output is deterministic (sorted keys, defined list orders, no timestamps) and
is written only under `--out`: LICENSE, pairs/ and tournaments/. The contract
is in data-flow.md, section 6.
"""

from __future__ import annotations

import argparse
import os
import statistics
from pathlib import Path

from .build import _finding_json, _pct, _write, game_finished
from .clips import ROUND_WORDS
from .doubles_findings import full_name, pair_name, pair_summary, select_pair_findings
from .doubles_load import DMatch, DPlayer, Pair, load_doubles, verify_checksums
from .doubles_stats import (
    MEASURES,
    MIN_SAMPLE,
    PairStats,
    pair_stats,
    rank_measure,
    ranked_pairs,
)
from .load import load_content

KAGGLE_URL = "https://www.kaggle.com/datasets/anonymousay58dki/dshuttlenet"

LICENSE_TEXT = f"""Licence: CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/)

Doubles data from DShuttleNet (Kaggle, CC BY-NC-SA 4.0), labelled by professional players from BWF World Tour matches. Shared under the same licence; non-commercial use only.

Dataset: {KAGGLE_URL}
DOI: 10.34740/kaggle/dsv/16097938

The files in this folder are derived from that dataset (per-pair statistics,
findings and tournament results). They are shared under the same licence.
Singles data elsewhere in pro-data/ has its own licence and is not part of this folder.
"""

SEP = " / "


def edition_names(doubles_tournaments: dict, singles_tournaments: dict) -> dict[str, dict]:
    """Name and season per edition id. Editions shared with singles take them
    from singles (content/tournaments.json), the rest from the doubles content."""
    out = {}
    for eid in sorted(set(doubles_tournaments["ids"].values()) | set(doubles_tournaments["editions"])):
        src = singles_tournaments.get(eid) or doubles_tournaments["editions"][eid]
        out[eid] = {"name": src["name"], "season": src["season"]}
    return out


def _player_name(p: DPlayer) -> str:
    """The display full name (doubles_findings.full_name). The display
    last-name override only changes the short name used in pair names."""
    return full_name(p)


def _names(pair_id: str, pairs: dict[str, Pair], players: dict[str, DPlayer]) -> str:
    return pair_name(pair_id, pairs, players, sep=SEP)


def _typical(all_stats: dict[str, PairStats], pairs: dict[str, Pair]) -> dict[str, dict[str, float]]:
    """Per event, the median of each measure over the comparison group."""
    out: dict[str, dict[str, float]] = {}
    for event in sorted({p.event for p in pairs.values()}):
        group = ranked_pairs(all_stats, pairs, event)
        out[event] = {}
        for k in MEASURES:
            vals = [v for p in group if (v := all_stats[p].values[k]) is not None]
            if vals:
                out[event][k] = _pct(statistics.median(vals))
    return out


def _dist(st: PairStats, key: str, names: dict[str, str]) -> dict[str, float | None]:
    """A distribution as shares; null for every key below MIN_SAMPLE."""
    d = st.dists[key]
    enough = st.samples[key] >= MIN_SAMPLE
    return {out: _pct(d[k]) if enough and d[k] is not None else None for out, k in names.items()}


def _val(st: PairStats, key: str) -> float | None:
    v = st.values[key]
    return None if v is None else _pct(v)


def _view(
    kind: str,
    pair: Pair,
    subset: list[DMatch],
    st: PairStats,
    typical: dict[str, float],
    ranks: dict,
    findings: list,
) -> dict:
    mixed = None
    if pair.event == "XD":
        both = {"man": "man", "woman": "woman"}
        mixed = {
            "serveBy": _dist(st, "mixed.serve_by", both),
            "receiveBy": _dist(st, "mixed.receive_by", both),
        }
    roles = [
        {
            "playerId": p,
            "smashShare": None if (v := st.dists["roles"][p]["smash"]) is None else _pct(v),
            "netShare": None if (v := st.dists["roles"][p]["net shot"]) is None else _pct(v),
        }
        for p in pair.players
    ]
    return {
        "kind": kind,
        "rallies": sum(1 for m in subset for r in m.rallies if r.winner is not None),
        "serve": {
            "shortShare": _val(st, "serve.short_share"),
            "winRate": _val(st, "serve.win_rate"),
            "thirdDown": _val(st, "serve.third_down"),
            "placement": _dist(st, "serve.placement", {
                "centre": "centre", "middle": "middle", "wide": "wide",
                "backCentre": "back_centre", "backWide": "back_wide",
            }),
            "serves": st.samples["serve.short_share"],
        },
        "receive": {
            "attackShare": _val(st, "receive.attack_share"),
            "winRate": _val(st, "receive.win_rate"),
            "mix": _dist(st, "receive.mix", {
                t: t for t in ("net shot", "push", "smash", "lift", "drive", "clear", "drop")
            }),
            "returns": st.samples["receive.attack_share"],
        },
        "first4": {"share": _val(st, "first4.share"), "winRate": _val(st, "first4.win_rate")},
        "mixed": mixed,
        "rest": {
            "attackShare": _val(st, "rally.attack_share"),
            "formationAttack": _val(st, "rally.formation_attack"),
            "roles": roles,
            "pointsLost": _dist(st, "points.lost", {
                k: k for k in ("opp_winner", "net_fault", "out", "failed_return",
                               "judgment_error", "fault")
            }),
            "pointsWon": _dist(st, "points.won", {"winner": "winner", "oppError": "opp_error"}),
        },
        "ranks": ranks,
        "samples": dict(st.samples),
        "typical": typical,
        "findings": [_finding_json(f) for f in findings],
    }


def _all_label(n: int) -> str:
    return f"All {n} match" if n == 1 else f"All {n} matches"


def game_scores(m: DMatch) -> tuple[list[list[int]], list[int]]:
    games = [[a, b] for a, b in m.set_scores]
    return games, [i for i, (a, b) in enumerate(m.set_scores) if not game_finished(a, b)]


def _match_sort(m: DMatch) -> tuple[str, int]:
    return (m.date, int(m.id))


def write_doubles(
    out_dir: Path,
    matches: list[DMatch],
    pairs: dict[str, Pair],
    players: dict[str, DPlayer],
    editions: dict[str, dict],
) -> None:
    out_dir = Path(out_dir)
    all_stats = {pid: pair_stats(matches, p, players) for pid, p in pairs.items()}
    typical = _typical(all_stats, pairs)
    names = {pid: _names(pid, pairs, players) for pid in pairs}

    index_rows = []
    for pid, pair in pairs.items():
        mine = sorted((m for m in matches if pid in (m.winner, m.loser)), key=_match_sort)
        if not mine:
            continue
        group = ranked_pairs(all_stats, pairs, pair.event)
        ranked = pid in group
        findings = select_pair_findings(pid, all_stats, pairs) if ranked else []
        ranks = {}
        if ranked:
            for k in MEASURES:
                if (r := rank_measure(all_stats, pairs, pid, k)) is not None:
                    ranks[k] = {"rank": r.rank, "of": r.of, "typical": _pct(r.typical)}
        tp = typical[pair.event]
        views = {"all": _view("all", pair, mine, all_stats[pid], tp, ranks, findings)}
        filters = [{"id": "all", "kind": "all", "matches": len(mine), "label": _all_label(len(mine))}]
        eids = sorted(
            {m.edition_id for m in mine},
            key=lambda e: (-editions[e]["season"], editions[e]["name"], e),
        )
        for e in eids:
            sub = [m for m in mine if m.edition_id == e]
            views[f"t:{e}"] = _view("tournament", pair, sub, pair_stats(sub, pair, players), tp, {}, [])
            filters.append({"id": f"t:{e}", "kind": "tournament", "matches": len(sub),
                            "label": f"{editions[e]['name']} {editions[e]['season']}"})
        for m in mine:
            opp = m.loser if pid == m.winner else m.winner
            ed = editions[m.edition_id]
            word = ROUND_WORDS.get(m.round, m.round.lower())
            views[f"m:{m.id}"] = _view("match", pair, [m], pair_stats([m], pair, players), tp, {}, [])
            filters.append({
                "id": f"m:{m.id}", "kind": "match", "matches": 1,
                "label": f"{ed['name']} {ed['season']} {word} against {names[opp]}",
            })
        years = [int(m.date[:4]) for m in mine]
        pl = [players[p] for p in pair.players]
        _write(out_dir / "pairs" / f"{pid}.json", {
            "id": pid,
            "event": pair.event,
            "players": [{"id": p.id, "name": _player_name(p), "nationality": p.nationality,
                         "gender": p.gender} for p in pl],
            "context": {
                "matches": len(mine),
                "firstYear": min(years),
                "lastYear": max(years),
                "comparedWith": len(group) - 1 if ranked else 0,
            },
            "ranked": ranked,
            "summary": pair_summary(pid, findings, pairs, players) if ranked else None,
            "filters": filters,
            "views": views,
        })
        index_rows.append({
            "id": pid, "event": pair.event, "matches": len(mine), "ranked": ranked,
            "players": [{"id": p.id, "name": _player_name(p), "nationality": p.nationality}
                        for p in pl],
        })
    index_rows.sort(key=lambda r: (r["event"], r["players"][0]["name"], r["players"][1]["name"], r["id"]))
    _write(out_dir / "pairs" / "index.json", {"pairs": index_rows})

    edition_rows = []
    for eid, e in editions.items():
        ems = sorted((m for m in matches if m.edition_id == eid), key=_match_sort)
        if not ems:
            continue
        in_edition = {p for m in ems for p in (m.winner, m.loser)}
        rows = []
        for m in ems:
            games, incomplete = game_scores(m)
            rows.append({
                "id": m.id, "event": m.event, "round": m.round, "date": m.date,
                "winner": {"id": m.winner, "names": names[m.winner]},
                "loser": {"id": m.loser, "names": names[m.loser]},
                "games": games, "incomplete": incomplete,
            })
        _write(out_dir / "tournaments" / f"{eid}.json", {
            "id": eid, "name": e["name"], "season": e["season"],
            "matches": rows,
            "pairs": [{"id": p, "event": pairs[p].event, "names": names[p]}
                      for p in sorted(in_edition, key=lambda p: (pairs[p].event, names[p], p))],
        })
        edition_rows.append({"id": eid, "name": e["name"], "season": e["season"],
                             "doublesMatches": len(ems)})
    edition_rows.sort(key=lambda r: (-r["season"], r["name"], r["id"]))
    _write(out_dir / "tournaments" / "index.json", {"editions": edition_rows})

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "LICENSE").write_text(LICENSE_TEXT, encoding="utf-8")


def build(
    source_dir: Path,
    out_dir: Path,
    *,
    tournaments: dict | None = None,
    checksums: dict | None = None,
    aliases: dict | None = None,
    singles_tournaments: dict | None = None,
) -> None:
    tournaments = tournaments if tournaments is not None else load_content("doubles_tournaments")
    checksums = checksums if checksums is not None else load_content("doubles_checksums")
    singles = singles_tournaments if singles_tournaments is not None else load_content("tournaments")
    verify_checksums(Path(source_dir), checksums)
    matches, pairs, players = load_doubles(Path(source_dir), tournaments, aliases)
    write_doubles(out_dir, matches, pairs, players, edition_names(tournaments, singles))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m pro_profiles.doubles_build")
    ap.add_argument("--source", default=os.environ.get("DSHUTTLENET_DIR"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if not args.source:
        ap.error("--source or DSHUTTLENET_DIR required")
    build(Path(args.source), Path(args.out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
