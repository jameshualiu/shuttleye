"""Load DShuttleNet (doubles) and normalise it into typed records.

Column meanings are in the doubles spec. In short: `win_A`/`win_B` are the
match-winning pair, `lose_C`/`lose_D` the losing pair, and rally.csv's
`current_win_score`/`current_lose_score` are those pairs' scores after the
rally. Rally winners come from which score went up.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .load import MappingError, _read_csv, load_content

EVENTS = {"1": "MD", "2": "WD", "3": "XD"}
ATTACK_TYPES = frozenset({"smash", "drop", "push"})
SERVE_TYPES = {"short serve": "short", "long serve": "long"}

# Letters NFKD doesn't split into a base letter and an accent.
_ASCII_FOLD = str.maketrans({"ø": "o", "æ": "ae", "ß": "ss", "đ": "d", "ł": "l", "œ": "oe"})


class ChecksumError(ValueError):
    """An input file is missing or differs from the recorded SHA-256."""


@dataclass(frozen=True)
class DPlayer:
    id: str
    name: str
    last_name: str
    gender: str
    nationality: str


@dataclass(frozen=True)
class Pair:
    id: str  # slug of the two last names, event suffix only on a clash
    event: str
    players: tuple[str, str]  # player ids, sorted


@dataclass(frozen=True)
class DShot:
    num: int
    player: str  # "" when the data leaves it blank (2 shots)
    type: str | None
    formation: str | None  # "Attack" / "Defense", from shot_merge_all.csv
    # (return_x, return_y) in court units of ~10 cm (x 0-61, y 0-134). Passed
    # through as recorded: 1,747 of the 58,359 real shots fall outside that
    # range (e.g. x = -1199), so consumers must filter them.
    met_at: tuple[float, float] | None


@dataclass(frozen=True)
class DRally:
    match_id: str
    set_no: int
    number: int
    server: str
    receiver: str | None  # the shot 2 hitter
    winner: str | None  # pair id; None when neither score went up
    serve_type: str | None  # "short" / "long"; None when shot 1 has no serve type
    shots: tuple[DShot, ...]
    lose_reason: str | None
    fault_player: str | None  # kept only when on the pair that lost the rally
    before: tuple[int, int]  # score before the rally, match-winner pair first


@dataclass(frozen=True)
class DMatch:
    id: str
    edition_id: str
    round: str
    date: str
    event: str
    winner: str  # pair ids
    loser: str
    rallies: tuple[DRally, ...]
    # Per set, in set order: the max (win, lose) rally score, match winner first.
    set_scores: tuple[tuple[int, int], ...]


def verify_checksums(source_dir: Path, expected: dict[str, str]) -> None:
    for name, sha in sorted(expected.items()):
        path = Path(source_dir) / name
        if not path.is_file():
            raise ChecksumError(f"{name}: missing from {source_dir}")
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != sha:
            raise ChecksumError(
                f"{name}: SHA-256 {h.hexdigest()} does not match the recorded {sha}. "
                "The dataset changed; check it before updating doubles_checksums.json."
            )


def _id(raw: str) -> str:
    """Ids come as "5" or "5.0"; normalise to "5". Blank stays blank."""
    raw = raw.strip()
    return str(int(float(raw))) if raw else ""


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower().translate(_ASCII_FOLD))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _initials(p: DPlayer) -> str:
    """Given-name initials: the words of `name` other than the last name."""
    last = p.last_name.casefold().split()
    words = [w for w in p.name.split() if w.casefold() not in last]
    return "".join(_slug(w)[:1] for w in words)


def _group(items: dict, key) -> dict:
    groups: dict = {}
    for k, v in items.items():
        groups.setdefault(key(k, v), []).append(k)
    return groups


def _make_pairs(
    keys: set[tuple[str, tuple[str, str]]], players: dict[str, DPlayer]
) -> dict[tuple[str, tuple[str, str]], Pair]:
    """Give each (event, players) key a slug id: the two last names. Pairs in
    the same event sharing a slug all get the given-name initials of the
    partner(s) not common to the clash; slugs still shared across events then
    get the event suffix. Anything still clashing is an error."""
    slug = {k: "-".join(_slug(players[p].last_name) for p in k[1]) for k in keys}
    for ks in _group(slug, lambda k, s: (k[0], s)).values():
        if len(ks) > 1:
            common = set.intersection(*(set(k[1]) for k in ks))
            for k in ks:
                varying = [p for p in k[1] if p not in common]
                slug[k] += "-" + "".join(_initials(players[p]) for p in varying)
    for ks in _group(slug, lambda k, s: s).values():
        if len(ks) > 1:
            for k in ks:
                slug[k] += f"-{k[0].lower()}"
    for s, ks in _group(slug, lambda k, s: s).items():
        if len(ks) > 1:
            raise MappingError(f"Pair slug {s!r} is shared by {sorted(ks)}")
    return {k: Pair(id=slug[k], event=k[0], players=k[1]) for k in keys}


def _sorted_ids(a: str, b: str) -> tuple[str, str]:
    x, y = sorted((a, b), key=lambda s: (len(s), s))  # numeric order for digit ids
    return (x, y)


def _shots(rows: list[dict], formation: dict[str, str], pid) -> tuple[DShot, ...]:
    rows = sorted(rows, key=lambda r: (int(r["shot_num"]), int(r["shot_id"])))
    shots = []
    for r in rows:
        x, y = r["return_x"].strip(), r["return_y"].strip()
        shots.append(DShot(
            num=int(r["shot_num"]),
            player=pid(r["player"]),
            type=r["ball_type"].strip() or None,
            formation=formation.get(r["shot_id"]) or None,
            met_at=(float(x), float(y)) if x and y else None,
        ))
    return tuple(shots)


def load_doubles(
    source_dir: Path, tournaments: dict, player_aliases: dict[str, str] | None = None
) -> tuple[list[DMatch], dict[str, Pair], dict[str, DPlayer]]:
    """Load the seven DShuttleNet CSVs.

    `tournaments` is the `doubles_tournaments` content: `ids` maps each
    DShuttleNet tournament_id to an edition id, and `match_overrides` replaces
    the tournament_id of matches the data mis-tags. `player_aliases` maps
    duplicate player ids to the canonical one (default: the
    `doubles_player_aliases` content); aliased ids are dropped from players.
    """
    src = Path(source_dir)
    read = lambda name: _read_csv(src / name)  # noqa: E731
    aliases = load_content("doubles_player_aliases") if player_aliases is None else player_aliases
    pid = lambda raw: aliases.get(_id(raw), _id(raw))  # noqa: E731

    players = {
        _id(r["player_id"]): DPlayer(
            id=_id(r["player_id"]),
            name=r["name"].strip(),
            last_name=r["last_name"].strip(),
            gender=r["gender"].strip(),
            nationality=r["nationality"].strip(),
        )
        for r in read("player.csv")
        if _id(r["player_id"]) not in aliases
    }
    match_rows = read("match.csv")

    sides: dict[str, tuple[tuple[str, tuple[str, str]], tuple[str, tuple[str, str]]]] = {}
    for r in match_rows:
        mid = _id(r["match_id"])
        try:
            event = EVENTS[_id(r["event"])]
        except KeyError:
            raise MappingError(f"Unknown event code {r['event']!r} (match {mid})") from None
        ids = [pid(r[c]) for c in ("win_A", "win_B", "lose_C", "lose_D")]
        for p in ids:
            if p not in players:
                raise MappingError(f"Unknown player id {p!r} (match {mid})")
        sides[mid] = ((event, _sorted_ids(*ids[:2])), (event, _sorted_ids(*ids[2:])))
    pair_by_key = _make_pairs({k for w_l in sides.values() for k in w_l}, players)

    sets = {_id(r["set_id"]): r for r in read("set.csv")}
    formation = {r["shot_id"]: r["player_formation"].strip() for r in read("shot_merge_all.csv")}
    shots_by_rally: dict[str, list[dict]] = {}
    for r in read("shot.csv"):
        shots_by_rally.setdefault(_id(r["rally_id"]), []).append(r)
    rallies_by_match: dict[str, list[tuple[int, int, dict]]] = {}
    for r in read("rally.csv"):
        s = sets[_id(r["set_id"])]
        rallies_by_match.setdefault(_id(s["match_id"]), []).append(
            (int(s["set_num"]), int(r["rally_num"]), r)
        )

    matches: list[DMatch] = []
    for r in match_rows:
        mid = _id(r["match_id"])
        try:
            tid = tournaments.get("match_overrides", {}).get(mid) or _id(r["tournament_id"])
            edition_id = tournaments["ids"][tid]
        except KeyError:
            raise MappingError(f"Unmapped tournament_id {tid!r} (match {mid})") from None
        win_key, lose_key = sides[mid]
        winner, loser = pair_by_key[win_key].id, pair_by_key[lose_key].id
        members = {winner: set(win_key[1]), loser: set(lose_key[1])}

        rallies: list[DRally] = []
        max_scores: dict[int, tuple[int, int]] = {}
        before: dict[int, tuple[int, int]] = {}
        for set_no, number, row in sorted(rallies_by_match.get(mid, []), key=lambda t: t[:2]):
            prev = before.get(set_no, (0, 0))
            after = (int(row["current_win_score"]), int(row["current_lose_score"]))
            rally_winner = winner if after[0] > prev[0] else loser if after[1] > prev[1] else None
            rally_loser = None if rally_winner is None else (loser if rally_winner == winner else winner)
            fault = pid(row["fault_player"])
            shots = _shots(shots_by_rally.get(_id(row["rally_id"]), []), formation, pid)
            first = shots[0] if shots and shots[0].num == 1 else None
            second = next((s for s in shots if s.num == 2), None)
            rallies.append(DRally(
                match_id=mid,
                set_no=set_no,
                number=number,
                server=pid(row["serve_player"]),
                receiver=(second.player or None) if second else None,
                winner=rally_winner,
                serve_type=SERVE_TYPES.get(first.type) if first and first.type else None,
                shots=shots,
                lose_reason=row["lose_reason"].strip() or None,
                fault_player=fault if rally_loser and fault in members[rally_loser] else None,
                before=prev,
            ))
            before[set_no] = after
            m = max_scores.get(set_no, (0, 0))
            max_scores[set_no] = (max(m[0], after[0]), max(m[1], after[1]))

        matches.append(DMatch(
            id=mid,
            edition_id=edition_id,
            round=r["round"].strip(),
            date=r["date"].strip(),
            event=win_key[0],
            winner=winner,
            loser=loser,
            rallies=tuple(rallies),
            set_scores=tuple(max_scores[s] for s in sorted(max_scores)),
        ))

    matches.sort(key=lambda m: int(m.id))
    pairs = {p.id: p for p in sorted(pair_by_key.values(), key=lambda p: (p.event, p.id))}
    return matches, pairs, players
