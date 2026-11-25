"""Player id resolution against tools/pro_profiles/content/players.json."""
import re
import unicodedata


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def resolve_player(name: str, players: dict) -> tuple[str, bool]:
    """(player id, created). Matches the name or any alias case-insensitively."""
    key = name.strip().lower()
    for pid, p in players.items():
        names = [p.get("name", ""), *p.get("aliases", [])]
        if any(n.strip().lower() == key for n in names):
            return pid, False
    return slugify(name), True
