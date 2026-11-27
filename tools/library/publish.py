"""Publish / unpublish matches and recompute every derived library document.

    python -m library.publish {publish|unpublish|recompute} [match_id]

Needs GOOGLE_APPLICATION_CREDENTIALS pointing at a service-account key (kept outside the repo).
"""
from __future__ import annotations

import argparse
import json
import sys

from pro_profiles.build import PHOTOS_PATH
from pro_profiles.load import load_content

from .insights import player_insights
from .match_insights import match_insights
from .profiles import build_library, known_editions
from .store import FirestoreStore, Store
from .to_model import to_match


class PublishError(Exception):
    pass


RECOMPUTE_HINT = "Run `python -m library.publish recompute` to rebuild the library."


def load_context() -> dict:
    photos = json.loads(PHOTOS_PATH.read_text(encoding="utf-8")) if PHOTOS_PATH.exists() else {}
    return {"players": load_content("players"), "tournaments": load_content("tournaments"),
            "photos": photos}


def _plain(x):
    """JSON round trip, so a built document compares equal to what a store returns."""
    return json.loads(json.dumps(x))


def _write(store: Store, path: str, data: dict, changed: list[str]) -> None:
    data = _plain(data)
    if store.get(path) != data:
        store.set(path, data)
        if path not in changed:
            changed.append(path)


def _stale(store: Store, keep: set[str]) -> list[str]:
    found = [f"players/{p}" for p in store.list_ids("players")]
    for p in store.list_ids("players"):
        found += [f"players/{p}/views/{v}" for v in store.list_ids(f"players/{p}/views")]
    found += [f"tournaments/{t}" for t in store.list_ids("tournaments")]
    found.append("library/index")
    return [p for p in found if p not in keep and store.get(p) is not None]


def recompute(store: Store, *, changed: list[str] | None = None) -> list[str]:
    """Rebuild players, views, tournaments, the index and each match's `insights`
    from the published matches. Returns the paths written with new content or deleted."""
    changed = [] if changed is None else changed
    ctx = load_context()
    published = sorted(store.list("matches", ("status", "==", "published")), key=lambda d: d["id"])
    # A doc whose edition is not in tournaments.json is left out (with a warning), not fatal.
    published = known_editions(published, ctx["tournaments"])

    built = build_library(published, ctx["players"], ctx["tournaments"], ctx["photos"])
    for path, data in built.items():
        _write(store, path, data, changed)
    for path in _stale(store, set(built)):
        store.delete(path)
        changed.append(path)

    matches = {d["id"]: to_match(d) for d in published}
    for d in published:
        usual = {}
        for side in ("A", "B"):
            pid = d["players"][side]["id"]
            others = [m for mid, m in matches.items()
                      if mid != d["id"] and pid in (m.winner, m.loser)]
            if others:
                usual[pid] = player_insights(others, pid)
        insights = match_insights(d, usual, players=ctx["players"], tournaments=ctx["tournaments"])
        _write(store, f"matches/{d['id']}", {**d, "insights": insights}, changed)
    for d in store.list("matches", ("status", "==", "unpublished")):
        if d.get("insights") is not None:
            _write(store, f"matches/{d['id']}", {**d, "insights": None}, changed)
    return changed


def recompute_after_write(store: Store, what: str, *, changed: list[str] | None = None) -> list[str]:
    """recompute() after `what` was already written; on failure say how to recover, then re-raise."""
    try:
        return recompute(store, changed=changed)
    except Exception as exc:
        print(f"[library] recompute failed after {what} ({type(exc).__name__}: {exc}). {RECOMPUTE_HINT}",
              file=sys.stderr)
        raise


def _set_status(store: Store, match_id: str, status: str, changed: list[str]) -> None:
    doc = store.get(f"matches/{match_id}")
    if doc is None:
        raise PublishError(f"no such match: {match_id}")
    if status == "published" and not doc.get("attributed"):
        warnings = (doc.get("analyzer") or {}).get("warnings") or []
        raise PublishError(f"{match_id} is not attributed (rally sides unresolved, or the analyzer "
                           f"disagrees with the given winner / near side); fix and re-ingest. "
                           f"Warnings: {'; '.join(warnings) or 'none'}")
    _write(store, f"matches/{match_id}", {**doc, "status": status}, changed)


def publish(store: Store, match_id: str) -> list[str]:
    changed: list[str] = []
    _set_status(store, match_id, "published", changed)
    return recompute_after_write(store, f"publishing {match_id}", changed=changed)


def unpublish(store: Store, match_id: str) -> list[str]:
    changed: list[str] = []
    _set_status(store, match_id, "unpublished", changed)
    return recompute_after_write(store, f"unpublishing {match_id}", changed=changed)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m library.publish")
    ap.add_argument("command", choices=["publish", "unpublish", "recompute"])
    ap.add_argument("match_id", nargs="?")
    args = ap.parse_args(argv)
    store = FirestoreStore()
    if args.command == "recompute":
        changed = recompute(store)
    elif not args.match_id:
        ap.error(f"{args.command} needs a match_id")
    else:
        changed = (publish if args.command == "publish" else unpublish)(store, args.match_id)
    print("\n".join(changed) or "no changes")


if __name__ == "__main__":
    main()
