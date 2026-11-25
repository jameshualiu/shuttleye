"""Map rallies to BWF YouTube clip windows."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .load import CONTENT_DIR, Match, Rally, load_content, load_dataset

LEAD_SEC = 2
TAIL_SEC = 3
SOURCES_PATH = CONTENT_DIR / "clip_sources.json"

ROUND_WORDS = {
    "Finals": "final",
    "Semi-finals": "semi-final",
    "Quarter-finals": "quarter-final",
    "Group-Stage": "group stage",
}


@dataclass(frozen=True)
class Clip:
    match_id: str
    youtube_id: str
    start_sec: int
    end_sec: int
    match_label: str
    score_label: str


def youtube_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").removeprefix("www.")
    if host == "youtu.be" and parsed.path.strip("/"):
        return parsed.path.strip("/").split("/")[0]
    if host.endswith("youtube.com"):
        ids = parse_qs(parsed.query).get("v")
        if ids and ids[0]:
            return ids[0]
    raise ValueError(f"Not a recognised YouTube URL: {url!r}")


def default_labels(
    match: Match, rally: Rally, player: str, players: dict, tournaments: dict
) -> tuple[str, str]:
    """(match_label, score_label) from `player`'s perspective."""
    edition = tournaments[match.edition_id]
    opponent = match.loser if player == match.winner else match.winner
    round_word = ROUND_WORDS.get(match.round, match.round.lower())
    match_label = (
        f"{edition['name']} {edition['season']} {round_word} "
        f"against {players[opponent]['name']}"
    )
    if rally.score_a is None or rally.score_b is None:
        return match_label, f"game {rally.set_no}, score not read"
    mine, theirs = (
        (rally.score_a, rally.score_b)
        if player == match.winner
        else (rally.score_b, rally.score_a)
    )
    return match_label, f"game {rally.set_no} at {mine}–{theirs}"


def make_labels(
    player: str, players: dict, tournaments: dict
) -> Callable[[Match, Rally], tuple[str, str]]:
    """Bind a player so default_labels fits clip_for_rally's `labels` callable."""
    return lambda match, rally: default_labels(match, rally, player, players, tournaments)


def clip_for_rally(
    match: Match,
    rally: Rally,
    sources: dict,
    labels: Callable[[Match, Rally], tuple[str, str]],
) -> Clip | None:
    source = sources.get(match.id)
    if source is None or not rally.shots:
        return None
    offset = source.get("offsetSec", 0)
    first = min(s.time_sec for s in rally.shots)
    last = max(s.time_sec for s in rally.shots)
    start = max(0, math.floor(first - LEAD_SEC + offset))
    end = math.ceil(last + TAIL_SEC + offset)
    match_label, score_label = labels(match, rally)
    return Clip(match.id, youtube_id(source["url"]), start, end, match_label, score_label)


def load_sources() -> dict:
    return load_content("clip_sources")


def init_sources(source_dir: Path, path: Path = SOURCES_PATH) -> int:
    """Write clip_sources.json from match.csv URLs, keeping existing entries."""
    matches = load_dataset(source_dir, load_content("players"), load_content("tournaments"))
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out = dict(existing)
    for m in sorted(matches, key=lambda m: m.id):
        if m.youtube_url and m.id not in out:
            out[m.id] = {"url": m.youtube_url, "offsetSec": 0, "checked": False}
    path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return len(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m pro_profiles.clips")
    ap.add_argument("--init", action="store_true", help="write content/clip_sources.json")
    ap.add_argument("--source", default=os.environ.get("SHUTTLESET_DIR"))
    args = ap.parse_args(argv)
    if not args.init:
        ap.error("nothing to do; pass --init")
    if not args.source:
        ap.error("--source or SHUTTLESET_DIR required")
    print(f"wrote {init_sources(Path(args.source))} entries to {SOURCES_PATH}")


if __name__ == "__main__":
    main()
