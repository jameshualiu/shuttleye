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

## Doubles pair profiles

A second build, `doubles_build.py`, reads the DShuttleNet dataset and writes the
doubles pair and tournament JSON to `public/pro-data/doubles/` (`LICENSE`,
`pairs/`, `tournaments/`). It is separate from the singles build and never
writes outside `--out`. The contract is in `data-flow.md`, section 6.

**Get the data.** DShuttleNet is on Kaggle
(`anonymousay58dki/dshuttlenet`, <https://www.kaggle.com/datasets/anonymousay58dki/dshuttlenet>).
Downloading needs a free Kaggle sign-in. Unzip it and keep the seven CSVs
(`match`, `player`, `rally`, `set`, `shot`, `shot_merge_all`, `tournament`) in
one directory. The CSVs are not committed.

**Checksums.** The uploader is anonymous, so the dataset could change.
`content/doubles_checksums.json` records each file's SHA-256, and the build
verifies them first and stops with a `ChecksumError` on any difference. If the
dataset legitimately changes, inspect it before updating the checksums.

**Run it.** From `tools/`:

```bash
python -m pro_profiles.doubles_build --source <dir with the CSVs> --out ../frontend/badminton-ai/public/pro-data/doubles
DSHUTTLENET_DIR=<dir> python -m pytest pro_profiles/tests   # also runs the real-data doubles tests
```

`--source` defaults to `$DSHUTTLENET_DIR`. Output is deterministic. The fixture
tests (`tests/fixtures/doubles_mini`) run without the dataset. CI does not
download from Kaggle, so the committed doubles JSON is checked locally: rebuild
and `git diff`. CI's singles stale check ignores the `doubles/` folder.

**Content files:** `doubles_tournaments.json` (DShuttleNet tournament ids to
edition ids, plus names for doubles-only editions and match overrides),
`doubles_player_aliases.json`, `doubles_display_names.json` (short last names),
`doubles_full_names.json` (given-name-first full names for Western players),
`doubles_templates.json`, `doubles_tips.json`, `clip_sources_doubles.json`
(empty until doubles clips exist).

**Licence.** DShuttleNet is CC BY-NC-SA 4.0. The derived doubles JSON is shared
under the same licence, for non-commercial use only, and `doubles/LICENSE`
states it with the attribution the doubles pages show in their footer. Singles
output keeps its own licence and attribution; no file mixes the two.
