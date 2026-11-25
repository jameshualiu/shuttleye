"""Synthetic Firestore match documents for library tests."""

EDITION = "test-open-2022"
TOURNAMENTS = {EDITION: {"name": "Test Open", "season": 2022}}


def make_rally(n: int, groups: list, winner: str | None = "A", t0: float = 0.0) -> dict:
    """Shots alternate A, B, A, ... starting with A's short serve (groups[0] is ignored)."""
    shots = [
        {"t": t0 + i, "p": "AB"[i % 2], "g": None if i == 0 else g,
         "d": "short service" if i == 0 else None, "z": None, "s": i == 0}
        for i, g in enumerate(groups)
    ]
    return {"n": n, "set": 1, "startSec": t0, "endSec": t0 + len(groups), "scoreBefore": [0, 0],
            "winner": winner, "shots": shots}


def make_doc(mid: str, a: str, b: str, rallies: list, date: str = "2022-08-01") -> dict:
    return {
        "id": mid, "youtubeId": f"yt-{mid}", "editionId": EDITION, "round": "Final", "date": date,
        "players": {"A": {"id": a, "name": a.upper()}, "B": {"id": b, "name": b.upper()}},
        "winner": "A", "games": [[21, 15], [21, 18]], "status": "published",
        "rallies": rallies,
    }


def late_rallies(count: int, smash_a: int, smash_b: int = 0) -> list:
    """16-shot rallies, 10 s apart. Shots 13–16 (A hits 13 and 15, B 14 and 16) are
    Smash in the first `smash_a` / `smash_b` rallies, Clear after; the rest are Drive."""
    out = []
    for n in range(count):
        groups = []
        for i in range(16):
            k = smash_a if i % 2 == 0 else smash_b
            groups.append(("Smash" if n < k else "Clear") if i >= 12 else "Drive")
        out.append(make_rally(n + 1, groups, t0=n * 20.0))
    return out
