# Pro profile build script

Offline, stdlib-only Python (3.11). Reads the ShuttleSet and ShuttleSet22 CSVs
and writes the static JSON the pro player and tournament pages render. It is
not part of the worker runtime. The JSON contract is documented in
`data-flow.md`, section 5.

## Run it

From `tools/`, with a checkout of CoachAI-Projects:

```bash
python -m pro_profiles.build --source <checkout> --out ../frontend/badminton-ai/public/pro-data
python -m pytest pro_profiles/tests      # set SHUTTLESET_DIR=<checkout> for the real-data tests
```

`--source` defaults to `$SHUTTLESET_DIR`. Output is deterministic (sorted keys,
fixed list order, no timestamps), and CI rebuilds it and fails if the committed
JSON differs.

## Pinned dataset

Commit `45517f7d4cb936b03f3eabf939cc7959d39226fe` of
`https://github.com/wywyWang/CoachAI-Projects`. Only `ShuttleSet/set` and
`CoachAI-Challenge-IJCAI2023/ShuttleSet22/set` are needed (sparse checkout).
The SHA is `PINNED_SHA` in `build.py` and `generatedFrom` in
`players/index.json`; the CI job uses the same one. To bump it, change all three
and rebuild.

## Content files (`content/`)

- `players.json`, `tournaments.json`: name and tournament maps (aliases to ids).
- `templates.json`, `tips.json`: finding wording and coaching tips.
- `clip_sources.json`: YouTube URL, `offsetSec` and `checked` per match.
- `photos.json` (optional): `{player_id: {sourceUrl, author, licence, focusX, focusY}}`.
  Without it every `photo` is null.

## Clip sources

`python -m pro_profiles.clips --init` adds any match with a URL in `match.csv`
to `clip_sources.json`, keeping existing entries. Watch a few clips, correct
`offsetSec` where the video timing is off, and set `checked` to true. Rebuild
afterwards.

## Photos

Photos come from Wikimedia Commons, only under CC BY, CC BY-SA, CC0 or public
domain, and only after a human approves each one. Run from `tools/`:

1. `python -m pro_profiles.photos candidates` looks up each player's English
   Wikipedia page image and writes `.superpowers/photo-candidates/contact-sheet.html`
   (gitignored) plus `candidates.json`. It sleeps 2s between requests, retries
   on HTTP 429, and uses the User-Agent `shuttleye-photo-fetch/0.1`.
2. Open the contact sheet, judge each photo, and adjust the focus point
   (percent X,Y of the crop, default 50,30).
3. `python -m pro_profiles.photos approve <player_id> --focus X,Y` records the
   approval in `content/photos.json`.
4. `python -m pro_profiles.photos download` fetches approved images (400px wide)
   into `public/pro-data/photos/`.
5. Rebuild the JSON (see Run it) and commit `photos.json`, the images and the
   JSON. CI excludes `photos/` from its diff because the build does not write it.
