"""Load ShuttleSet / ShuttleSet22 and normalise it into typed records."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CONTENT_DIR = Path(__file__).parent / "content"

SHUTTLESET_PATH = Path("ShuttleSet/set")
SHUTTLESET22_PATH = Path("CoachAI-Challenge-IJCAI2023/ShuttleSet22/set")

SERVE_TYPES = frozenset({"發短球", "發長球"})
UNKNOWN_TYPE = "未知球種"

# Shot type label -> shot group. `過度切球` is the dataset's spelling of the
# passive drop; the README spells it `過渡切球`. Both map to Drop.
SHOT_GROUPS: dict[str, str] = {
    **dict.fromkeys(["放小球", "擋小球", "勾球"], "Net"),
    **dict.fromkeys(["挑球", "防守回挑"], "Lift"),
    **dict.fromkeys(["殺球", "點扣"], "Smash"),
    **dict.fromkeys(["切球", "過渡切球", "過度切球"], "Drop"),
    "長球": "Clear",
    **dict.fromkeys(["平球", "小平球", "後場抽平球", "防守回抽"], "Drive"),
    "推球": "Push",
    "撲球": "Net kill",
}


class MappingError(ValueError):
    """A raw name or label in the dataset has no entry in our mappings."""


@dataclass(frozen=True)
class Shot:
    rally: int
    order: int
    time_sec: float
    player: str
    group: str | None
    is_serve: bool
    detail: str | None = None  # analyzer fine-grained type (e.g. "net shot")
    zone: str | None = None  # analyzer landing zone (e.g. "rear-left")


@dataclass(frozen=True)
class Rally:
    match_id: str
    set_no: int
    number: int
    shots: tuple[Shot, ...]
    winner: str | None  # None when the data records no point winner
    # Score BEFORE the rally (A = match winner). The CSV's roundscore is the
    # score after the rally, so this is the previous rally's after-score in
    # the same set, or 0-0 for the set's first rally. None when the score was
    # not read (library matches only; ShuttleSet always has it).
    score_a: int | None
    score_b: int | None


@dataclass(frozen=True)
class Match:
    id: str
    source: Literal["ShuttleSet", "ShuttleSet22", "Analyzer"]
    edition_id: str
    round: str
    date: str
    winner: str
    loser: str
    youtube_url: str | None
    rallies: tuple[Rally, ...]
    # Per set, in set order: (max roundscore_A, max roundscore_B) over the
    # set's rows, i.e. the final score as recorded (A = match winner).
    set_scores: tuple[tuple[int, int], ...] = ()


def load_content(name: str) -> dict:
    with open(CONTENT_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _whole(raw: str) -> int:
    return int(float(raw))  # ShuttleSet22 has values like "2022.0" and "1.0"


def _player_lookup(players: dict) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for pid, p in players.items():
        for alias in p["aliases"]:
            if lookup.setdefault(alias, pid) != pid:
                raise MappingError(f"Player alias {alias!r} maps to {lookup[alias]!r} and {pid!r}")
    return lookup


def _edition_lookup(tournaments: dict) -> dict[tuple[str, int], str]:
    lookup: dict[tuple[str, int], str] = {}
    for eid, t in tournaments.items():
        for name, year in t["aliases"]:
            key = (name, _whole(year))
            if lookup.setdefault(key, eid) != eid:
                raise MappingError(f"Tournament alias {key!r} maps to {lookup[key]!r} and {eid!r}")
    return lookup


def _parse_time(raw: str) -> float:
    h, m, s = raw.split(":")
    return float(int(h) * 3600 + int(m) * 60 + int(s))


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _shot_group(shot_type: str) -> str | None:
    if shot_type in SERVE_TYPES or shot_type == UNKNOWN_TYPE:
        return None
    try:
        return SHOT_GROUPS[shot_type]
    except KeyError:
        raise MappingError(f"Unmapped shot type: {shot_type!r}") from None


def _load_rallies(
    folder: Path, match_id: str, winner: str, loser: str
) -> tuple[tuple[Rally, ...], tuple[tuple[int, int], ...]]:
    """The match's rallies and, per set, (max roundscore_A, max roundscore_B)."""
    side = {"A": winner, "B": loser}  # A is the match winner, B the loser
    rallies: list[Rally] = []
    set_scores: list[tuple[int, int]] = []
    for path in sorted(folder.glob("set*.csv"), key=lambda p: int(re.sub(r"\D", "", p.stem))):
        set_no = int(re.sub(r"\D", "", path.stem))
        csv_rows = _read_csv(path)
        if not csv_rows:
            continue
        # Max, not the last row: some sets end with a stray earlier row.
        set_scores.append((
            max(_whole(r["roundscore_A"]) for r in csv_rows),
            max(_whole(r["roundscore_B"]) for r in csv_rows),
        ))
        by_rally: dict[int, list[dict]] = {}
        for row in csv_rows:
            by_rally.setdefault(int(row["rally"]), []).append(row)
        before = (0, 0)  # roundscore is the score after the rally
        for number in sorted(by_rally):
            rows = by_rally[number]
            # Some rallies (mostly a lone 未知球種 row) have no getpoint_player.
            # Keep their shots, but record no winner.
            point = rows[-1]["getpoint_player"]
            if point not in ("", "A", "B"):
                raise MappingError(
                    f"Bad getpoint_player {point!r} in {match_id} set {set_no} rally {number}"
                )
            shots = tuple(
                Shot(
                    rally=number,
                    order=int(float(r["ball_round"])),
                    time_sec=_parse_time(r["time"]),
                    player=side[r["player"]],
                    group=_shot_group(r["type"]),
                    is_serve=r["type"] in SERVE_TYPES,
                )
                for r in rows
            )
            rallies.append(
                Rally(
                    match_id=match_id,
                    set_no=set_no,
                    number=number,
                    shots=shots,
                    winner=side.get(point),
                    score_a=before[0],
                    score_b=before[1],
                )
            )
            before = (_whole(rows[-1]["roundscore_A"]), _whole(rows[-1]["roundscore_B"]))
    return tuple(rallies), tuple(set_scores)


def load_dataset(source_dir: Path, players: dict, tournaments: dict) -> list[Match]:
    """Load both datasets from a CoachAI-Projects checkout.

    A `video` folder present in both keeps the ShuttleSet copy. Rows whose
    folder is missing on disk are skipped.
    """
    player_ids = _player_lookup(players)
    editions = _edition_lookup(tournaments)
    matches: dict[str, Match] = {}
    for source, rel in (("ShuttleSet", SHUTTLESET_PATH), ("ShuttleSet22", SHUTTLESET22_PATH)):
        root = Path(source_dir) / rel
        for row in _read_csv(root / "match.csv"):
            video = row["video"]
            folder = root / video
            if video in matches or not folder.is_dir():
                continue
            try:
                winner = player_ids[row["winner"]]
                loser = player_ids[row["loser"]]
            except KeyError as e:
                raise MappingError(f"Unmapped player name: {e.args[0]!r} ({video})") from None
            year = _whole(row["year"])
            try:
                edition_id = editions[(row["tournament"], year)]
            except KeyError:
                raise MappingError(
                    f"Unmapped tournament: {row['tournament']!r} {year} ({video})"
                ) from None
            rallies, set_scores = _load_rallies(folder, video, winner, loser)
            matches[video] = Match(
                id=video,
                source=source,
                edition_id=edition_id,
                round=row["round"],
                date=f"{year:04d}-{_whole(row['month']):02d}-{_whole(row['day']):02d}",
                winner=winner,
                loser=loser,
                youtube_url=(row.get("url") or "").strip() or None,
                rallies=rallies,
                set_scores=set_scores,
            )
    return list(matches.values())
