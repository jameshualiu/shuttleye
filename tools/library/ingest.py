"""Ingest a BWF singles match into the library: download 720p, analyse, store
the match document as `unpublished`, delete the video.

    python -m library.ingest <youtube-url> --players "<winner>" "<loser>" \\
        --near-first winner|loser --tournament <editionId> --round <round> --date <YYYY-MM-DD> \\
        [--event MS|WS] [--runner modal|local|merged:<path>] [--video <path>] \\
        [--shuttleset <match>] [--force] [--keep-video] [--dry-run]
    python -m library.ingest --batch <file.json> [--dry-run]

Needs GOOGLE_APPLICATION_CREDENTIALS pointing at a service-account key (kept outside the repo).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from pro_profiles.load import load_content

from . import runners
from .match_doc import MatchMeta, match_doc
from .players import resolve_player, slugify
from .publish import recompute_after_write
from .runners import Analyzer, download_720p, make_analyzer
from .store import FirestoreStore, Store

EVENTS = ("MS", "WS")
UNATTRIBUTED_WARNING = "was published but the re-run is not attributed; stored unpublished"
_YOUTUBE_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})")


class IngestError(Exception):
    pass


def youtube_id(url: str) -> str:
    m = _YOUTUBE_ID.search(url)
    if not m:
        raise IngestError(f"no YouTube video id in {url!r}")
    return m.group(1)


def build_meta(url: str, names: list[str], near_first: str, edition_id: str, round_: str, date: str,
               event: str | None, players: dict, tournaments: dict) -> tuple[MatchMeta, list[str]]:
    """(meta, ids of players not in players.json). names = [winner, loser];
    near_first = "winner" | "loser". A new player needs `event`; the edition must be
    in tournaments.json."""
    if edition_id not in tournaments:
        raise IngestError(f"--tournament {edition_id!r} is not an editionId in tournaments.json")
    if len(names) != 2:
        raise IngestError("--players takes the winner then the loser")
    if near_first not in ("winner", "loser"):
        raise IngestError("--near-first is winner or loser")
    if event is not None and event not in EVENTS:
        raise IngestError(f"--event is one of {EVENTS}")
    refs, created = [], []
    for name in names:
        pid, new = resolve_player(name, players)
        if new:
            if event is None:
                raise IngestError(f"{name!r} is a new player ({pid}): pass --event MS|WS")
            created.append(pid)
            refs.append({"id": pid, "name": name.strip(), "event": event})
        else:
            p = players[pid]
            ev = p.get("event") or event
            refs.append({"id": pid, "name": p["name"], **({"event": ev} if ev else {})})
    meta: MatchMeta = {
        "id": f"{edition_id}-{slugify(refs[0]['id'])}-{slugify(refs[1]['id'])}",
        "youtubeId": youtube_id(url), "editionId": edition_id, "round": round_, "date": date,
        "playerA": refs[0], "playerB": refs[1], "nearFirst": "A" if near_first == "winner" else "B",
    }
    return meta, created


def _existing_video(video: str) -> Path:
    p = Path(video).expanduser()
    if not p.is_file():
        raise IngestError(f"--video {video}: no such file")
    return p


@contextmanager
def _timed(timings: dict, step: str):
    t = time.perf_counter()
    try:
        yield
    finally:
        timings[f"{step}_s"] = round(time.perf_counter() - t, 3)


def ingest(url_or_file: str, meta: MatchMeta, store: Store, *, runner: str | Analyzer = "modal",
           force: bool = False, keep_video: bool = False, shuttleset: str | None = None,
           video: str | None = None, downloader=download_720p) -> dict:
    """Analyse one match and store it. `url_or_file` is a YouTube URL (downloaded
    to a temp dir, deleted afterwards unless keep_video) or a local video, which is
    used as is and never deleted; so is `video`, which must exist. Returns {matchId, status: skipped|stored,
    timings, warnings, accuracy, changed}."""
    mid = meta["id"]
    path = f"matches/{mid}"
    if video is not None:
        url_or_file = str(_existing_video(video))
    prev = store.get(path)
    if prev is not None and not force:
        print(f"[ingest] {mid}: already stored ({prev.get('status')}); skipped (--force to re-run)")
        return {"matchId": mid, "status": "skipped", "timings": {}, "warnings": [],
                "accuracy": prev.get("accuracy"), "changed": []}
    analyzer = make_analyzer(runner) if isinstance(runner, str) else runner
    timings: dict = {}
    tmp = None
    try:
        with _timed(timings, "download"):
            local = Path(url_or_file).expanduser()
            if local.is_file():
                src = local
            else:
                tmp = Path(tempfile.mkdtemp(prefix="shuttleye-ingest-"))
                src = Path(downloader(url_or_file, tmp))
        print(f"[ingest] {mid}: video {src}; analysing with {analyzer.name}")
        with _timed(timings, "analyse"):
            res = analyzer.analyse(src)
        with _timed(timings, "segment"):
            analyzer.segment(res)
        with _timed(timings, "scoreboard"):
            analyzer.scoreboard(res, src)
        product = analyzer.product(res)
        # Without --shuttleset a re-run keeps the accuracy stored before (if any).
        accuracy = prev.get("accuracy") if prev is not None else None
        if shuttleset:
            with _timed(timings, "accuracy"):
                accuracy = runners.shuttleset_accuracy(res, shuttleset)
    finally:
        if tmp is not None:
            if keep_video:
                print(f"[ingest] video kept: {tmp}")
            else:
                shutil.rmtree(tmp, ignore_errors=True)

    with _timed(timings, "store"):
        doc = match_doc(product, meta)
        doc["accuracy"] = accuracy
        doc["analyzer"]["timings"] = {**(doc["analyzer"]["timings"] or {}),
                                      "ingest": {k: v for k, v in timings.items() if k != "store_s"}}
        was_published = prev is not None and prev.get("status") == "published"
        if prev is not None:
            doc["status"] = prev.get("status", "unpublished")
        if doc["status"] == "published" and not doc["attributed"]:
            doc["status"] = "unpublished"
            doc["analyzer"]["warnings"].append(UNATTRIBUTED_WARNING)
        store.set(path, json.loads(json.dumps(doc)))
    changed: list[str] = []
    if was_published:
        changed = recompute_after_write(store, f"storing {mid}")
        print(f"[ingest] {mid}: recomputed the library; changed:\n" + ("\n".join(changed) or "no changes"))
    warnings = doc["analyzer"]["warnings"]
    for w in warnings:
        print(f"[ingest] {mid}: WARNING {w}")
    print(f"[ingest] {mid}: stored ({doc['status']}, attributed {doc['attributed']}, "
          f"{doc['summary']['rallies']} rallies); timings {timings}; accuracy {accuracy}")
    return {"matchId": mid, "status": "stored", "timings": timings, "warnings": warnings,
            "accuracy": accuracy, "changed": changed}


def _entry_meta(entry: dict, players: dict, tournaments: dict) -> tuple[MatchMeta, list[str]]:
    m = entry["meta"]
    return build_meta(entry["url"], m["players"], m["nearFirst"], m["tournament"], m["round"],
                      m["date"], m.get("event"), players, tournaments)


def _plan(meta: MatchMeta, created: list[str], source: str, runner: str, shuttleset: str | None) -> str:
    lines = [f"[ingest] {meta['id']}: runner {runner}, source {source}, shuttleset {shuttleset or '-'}",
             "  " + json.dumps(meta, ensure_ascii=False)]
    lines += [f"  new player: {pid}" for pid in created]
    if runner.startswith("merged:") and not Path(runner[len("merged:"):]).expanduser().is_file():
        lines.append(f"  WARNING: merged result not found: {runner[len('merged:'):]}")
    return "\n".join(lines)


def run_batch(entries: list[dict], store: Store | None, players: dict, tournaments: dict, *, dry_run: bool = False,
              downloader=download_720p, analyzer_for=make_analyzer) -> list[dict]:
    """Each entry: {url, meta: {players: [winner, loser], nearFirst: winner|loser,
    tournament, round, date, event?}, shuttleset?, runner?, video?, force?}.
    Stored ids are skipped (resumable); a failing entry is reported and the batch goes on."""
    results = []
    for n, entry in enumerate(entries, 1):
        label = f"entry {n}"
        try:
            meta, created = _entry_meta(entry, players, tournaments)
            label = meta["id"]
            spec = entry.get("runner", "modal")
            analyzer = analyzer_for(spec)   # validates the spec before any work (lazy: no Modal yet)
            if entry.get("video"):
                _existing_video(entry["video"])
            source = entry.get("video") or entry["url"]
            if dry_run:
                print(_plan(meta, created, source, spec, entry.get("shuttleset")))
                results.append({"matchId": meta["id"], "status": "planned"})
                continue
            for pid in created:
                print(f"[ingest] new player: {pid}")
            out = ingest(entry["url"], meta, store, runner=analyzer, force=entry.get("force", False),
                         shuttleset=entry.get("shuttleset"), video=entry.get("video"), downloader=downloader)
            results.append(out)
        except Exception as exc:     # one bad match must not stop the batch
            err = f"{type(exc).__name__}: {exc}"
            print(f"[ingest] {label}: failed ({err})")
            results.append({"matchId": label, "status": "failed", "error": err})
    counts = {s: sum(r["status"] == s for r in results) for s in ("planned", "stored", "skipped", "failed")}
    print(f"[ingest] batch: {', '.join(f'{v} {k}' for k, v in counts.items() if v)}")
    return results


def main(argv: list[str] | None = None, *, players: dict | None = None, tournaments: dict | None = None,
         store_factory=FirestoreStore, downloader=download_720p) -> int:
    ap = argparse.ArgumentParser(prog="python -m library.ingest",
                                 description="Analyse a BWF singles match into the library (unpublished).")
    ap.add_argument("url", nargs="?", help="YouTube URL of the match")
    ap.add_argument("--batch", help="JSON list of {url, meta, shuttleset, runner, video}")
    ap.add_argument("--players", nargs=2, metavar=("WINNER", "LOSER"))
    ap.add_argument("--near-first", choices=["winner", "loser"], help="who is on the near side in rally 1")
    ap.add_argument("--tournament", help="editionId from tournaments.json")
    ap.add_argument("--round")
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--event", choices=EVENTS, help="required when a player is new")
    ap.add_argument("--runner", default="modal", help="modal (default) | local | merged:<fullmatch_*.json>")
    ap.add_argument("--video", help="use this local video instead of downloading (never deleted)")
    ap.add_argument("--shuttleset", help="ShuttleSet match name: score accuracy against its labels")
    ap.add_argument("--force", action="store_true", help="re-run a stored match (keeps its status)")
    ap.add_argument("--keep-video", action="store_true", help="keep the downloaded video")
    ap.add_argument("--dry-run", action="store_true", help="print the resolved meta and plan; touch nothing")
    args = ap.parse_args(argv)
    players = load_content("players") if players is None else players
    tournaments = load_content("tournaments") if tournaments is None else tournaments

    if args.batch:
        if args.url:
            ap.error("give a URL or --batch, not both")
        entries = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        store = None if args.dry_run else store_factory()
        results = run_batch(entries, store, players, tournaments, dry_run=args.dry_run, downloader=downloader)
        return 1 if any(r["status"] == "failed" for r in results) else 0

    missing = [o for o, v in (("url", args.url), ("--players", args.players), ("--near-first", args.near_first),
                              ("--tournament", args.tournament), ("--round", args.round),
                              ("--date", args.date)) if not v]
    if missing:
        ap.error(f"missing {', '.join(missing)}")
    try:
        meta, created = build_meta(args.url, args.players, args.near_first, args.tournament, args.round,
                                   args.date, args.event, players, tournaments)
        make_analyzer(args.runner)   # validate the spec before any work
        if args.video:
            _existing_video(args.video)
    except (IngestError, ValueError) as exc:
        ap.error(str(exc))
    if args.dry_run:
        print(_plan(meta, created, args.video or args.url, args.runner, args.shuttleset))
        return 0
    for pid in created:
        print(f"[ingest] new player: {pid}")
    ingest(args.url, meta, store_factory(), runner=args.runner, force=args.force,
           keep_video=args.keep_video, shuttleset=args.shuttleset, video=args.video, downloader=downloader)
    return 0


if __name__ == "__main__":
    sys.exit(main())
