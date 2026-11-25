"""Adapt a Firestore match document into the pro_profiles Match model."""
from pro_profiles.load import Match, Rally, Shot


def to_match(doc: dict) -> Match:
    ids = {"A": doc["players"]["A"]["id"], "B": doc["players"]["B"]["id"]}
    rallies = []
    for r in doc["rallies"]:
        before = r.get("scoreBefore") or [None, None]   # unread: clip labels say so
        shots = tuple(
            Shot(
                rally=r["n"],
                order=i,
                time_sec=s["t"],
                player=ids.get(s["p"], "?"),
                group=s["g"],
                is_serve=bool(s["s"]),
                detail=s.get("d"),
                zone=s.get("z"),
            )
            for i, s in enumerate(r["shots"], 1)
        )
        rallies.append(Rally(
            match_id=doc["id"],
            set_no=r.get("set") or 1,
            number=r["n"],
            shots=shots,
            winner=ids.get(r.get("winner")),
            score_a=before[0],
            score_b=before[1],
        ))
    return Match(
        id=doc["id"],
        source="Analyzer",
        edition_id=doc["editionId"],
        round=doc["round"],
        date=doc["date"],
        winner=ids["A"],
        loser=ids["B"],
        youtube_url=f"https://www.youtube.com/watch?v={doc['youtubeId']}",
        rallies=tuple(rallies),
        set_scores=tuple((g["a"], g["b"]) for g in doc.get("games") or ()),
    )
