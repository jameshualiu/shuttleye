# Pro Player Profiles and Tournament Browsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Public pages in the ShuttlEye web app that profile 43 pro singles players and 31 tournament editions from the hand-labelled ShuttleSet / ShuttleSet22 data, with every claim compared against other pros and linked to BWF YouTube clips.

**Architecture:** An offline, stdlib-only Python build script in `tools/pro_profiles/` reads the CoachAI CSVs, normalises names, computes every number, finding, summary sentence and clip, and writes static JSON to `frontend/badminton-ai/public/pro-data/`. The React app only fetches and renders that JSON. All logic lives in Python and is unit-tested there. There are no backend, Firestore or worker changes.

**Tech Stack:** Python 3.11 (stdlib only: `csv`, `json`, `dataclasses`, `statistics`, `urllib`), pytest; React 19 + TypeScript + Tailwind v4 + react-router 7 (existing).

**Spec:** `docs/superpowers/specs/2026-11-17-pro-player-profiles-design.md`. Approved mockup: `.superpowers/brainstorm/40492-1794951640/content/profile-layout-v9b.html`.

## Global Constraints

- **Process (AGENTS.md):** work happens on `feature/<issue>-pro-player-profiles`, branched from `main`. **Never commit without James saying "Commit these changes" (Gate 2).** Each task ends by staging its files and recording its proposed Conventional Commit message. Commits are made in task order at Gate 2. No Co-Authored-By trailers.
- **Dataset:** `wywyWang/CoachAI-Projects` pinned at commit `45517f7d4cb936b03f3eabf939cc7959d39226fe`. Paths `ShuttleSet/set/` and `CoachAI-Challenge-IJCAI2023/ShuttleSet22/set/`. The script takes the checkout path as `--source` or `SHUTTLESET_DIR`. Dataset CSVs are never copied into this repo.
- **No new runtime dependencies** in the frontend or the script. The frontend gets no test framework, because all logic is in Python.
- **Thresholds:** ranking needs **300+ grouped shots**. A rally band needs **30+ rallies** for that player.
- **Bands:** short ≤4, mid 5–8, long ≥9 shots, where rally length = rows in the rally, serve included.
- **Comparison group:** players with 300+ grouped shots, men and women pooled. Ranks 1..N with the player included. Typical = median over the group, player included. Band group = players with 30+ rallies in that band.
- **Shot groups** (serves `發短球`, `發長球` and `未知球種` excluded everywhere):
  - Net: `放小球`, `擋小球`, `勾球`
  - Lift: `挑球`, `防守回挑`
  - Smash: `殺球`, `點扣`
  - Drop: `切球`, `過渡切球`, `過度切球`
  - Clear: `長球`
  - Drive: `平球`, `小平球`, `後場抽平球`, `防守回抽`
  - Push: `推球`
  - Net kill: `撲球` (counted in the denominator, not shown in the shot-choice panel)
- **De-duplication:** a `video` folder in both datasets keeps the ShuttleSet copy.
- **Clips:** only from `content/clip_sources.json` entries. YouTube embed `https://www.youtube-nocookie.com/embed/{id}?start={s}&end={e}`, where start = first shot time − 2s + offset and end = last shot time + 3s + offset.
- **Attribution footer (exact copy):** "Shot data from ShuttleSet and ShuttleSet22 by the CoachAI team (Wang et al., KDD 2023; IJCAI 2023), labelled by hand from BWF World Tour matches. Clips play from BWF's YouTube channel."
- **UI:** the neutral `theme-ai-saas` tokens; Plus Jakarta Sans; panels `rounded-2xl` on a raised surface with 24px gaps; 12-column grid capped at 1600px with 48px gutters; text 4.5:1 contrast or better; focus rings; 44px tap targets; Strength/Weakness written in words; reduced motion respected.
- **Routes are public:** `/players`, `/players/:playerId`, `/tournaments`, `/tournaments/:editionId`.

## Review Focus

1. **A player who ranks in nothing** (no extreme stat and no band below typical, or under 300 shots): the page still renders with "Nothing stands far out from other pros in this data" and unranked rows. → Task 4 test `test_no_findings_player`. Task 8 renders `findings: []`.
2. **A filtered view with tiny samples** (one match): rows show raw counts and "Too few to compare". Never a rank or a finding. → Task 5 test `test_match_view_has_no_ranks_or_findings`.
3. **Findings whose matches have no clip source** (2022-only players): "No clips available for these matches yet" instead of an empty player. → Task 4 test `test_finding_without_clip_sources`. Task 8 renders empty `clips`.
4. **An unknown or misspelled name or tournament string** in a future dataset revision: the build fails loudly, naming the string. It must not silently drop or merge players. → Task 1 test `test_unmapped_name_raises`.
5. **A bad URL slug** (`/players/nobody`, `/tournaments/x`): a "Not found" page with a link back to the list, not a crash or a blank page. → Task 8 verification step.

---

### Task 0: Issue, branch and housekeeping

**Files:**
- Modify: `.gitignore` (add `.superpowers/`)

- [ ] **Step 1:** Create a GitHub issue titled `feat: pro player profiles and tournament browsing`, labels `frontend` and `feature`. The body links the spec and lists its Goals as acceptance criteria. Record the issue number `<n>`.
- [ ] **Step 2:** `git switch main && git pull && git switch -c feature/<n>-pro-player-profiles`. Leave the untracked `frontend/badminton-ai/public/demo-local/` alone.
- [ ] **Step 3:** Add `.superpowers/` to `.gitignore`. Stage the spec, the research note (`docs/superpowers/research/2026-11-17-sports-dataviz-research.md`), this plan and `.gitignore`.
- [ ] **Step 4:** Proposed commit: `docs: add pro player profiles spec, research and plan`.

---

### Task 1: Load and normalise the dataset

**Files:**
- Create: `tools/pro_profiles/__init__.py`, `tools/pro_profiles/load.py`
- Create: `tools/pro_profiles/content/players.json`, `tools/pro_profiles/content/tournaments.json`
- Create: `tools/pro_profiles/tests/__init__.py`, `tools/pro_profiles/tests/conftest.py`, `tools/pro_profiles/tests/test_load.py`
- Create: `tools/pro_profiles/tests/fixtures/mini/` (a two-match fake dataset in both folder layouts, with one duplicated folder)

**Interfaces:**
- Produces (in `load.py`):
  - `@dataclass(frozen=True) class Shot: rally: int; order: int; time_sec: float; player: str` (player id); `group: str | None` (shot group, or None for serve/unknown); `is_serve: bool`
  - `@dataclass(frozen=True) class Rally: match_id: str; set_no: int; number: int; shots: tuple[Shot, ...]; winner: str` (player id); `score_a: int; score_b: int` (score before the rally, from the first shot's `roundscore_A/B`)
  - `@dataclass(frozen=True) class Match: id: str` (the `video` folder name); `source: Literal["ShuttleSet", "ShuttleSet22"]; edition_id: str; round: str; date: str` (ISO `YYYY-MM-DD`); `winner: str; loser: str` (player ids); `youtube_url: str | None; rallies: tuple[Rally, ...]`
  - `def load_dataset(source_dir: Path, players: dict, tournaments: dict) -> list[Match]`
  - `def load_content(name: str) -> dict` (reads `tools/pro_profiles/content/{name}.json`)
  - `class MappingError(ValueError)`
- Content shapes:
  - `players.json`: `{"<player_id>": {"name": "Viktor Axelsen", "event": "MS"|"WS", "aliases": ["Viktor AXELSEN", ...]}}`. Ids are kebab-case (`viktor-axelsen`). Every raw `winner`/`loser` string in both `match.csv` files must appear in some `aliases`.
  - `tournaments.json`: `{"<edition_id>": {"name": "All England Open", "season": 2022, "aliases": [["YONEX ALL ENGLAND OPEN BADMINTON CHAMPIONSHIPS 2022", "2022"], ...]}}`. Aliases are `[tournament, year]` pairs as they appear in `match.csv`. Edition ids look like `all-england-open-2022`. Use the event's season, not the play date: the 2020 World Tour Finals, played January 2021, gets season 2020.

- [ ] **Step 1: Write failing tests** in `test_load.py`, using the `mini` fixture through a `mini_source` fixture in `conftest.py`:
  - `test_duplicate_folder_keeps_shuttleset_copy`: the duplicated folder yields one `Match` with `source == "ShuttleSet"`.
  - `test_passive_drop_typo_maps_to_drop`: a `過度切球` shot has `group == "Drop"`.
  - `test_serves_and_unknown_have_no_group`: `發短球` → `group is None and is_serve`. `未知球種` → `group is None and not is_serve`.
  - `test_rally_winner_from_last_row`: winner = id of `getpoint_player` (A = match winner) on the rally's last row.
  - `test_time_parsing`: `"00:10:54"` → `654.0`.
  - `test_unmapped_name_raises`: a fixture `match.csv` row with an unknown player raises `MappingError` whose message contains the raw name. Same for an unknown tournament.
  - `test_real_dataset_counts` (skipped unless `SHUTTLESET_DIR` is set): 94 matches, 31 distinct `edition_id`s, 43 distinct player ids, 43 matches with `youtube_url`.
- [ ] **Step 2:** Run `cd tools && python -m pytest pro_profiles/tests/test_load.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `load.py`.
  - Read `match.csv` with `encoding="utf-8-sig"`.
  - Skip rows whose folder is missing on disk.
  - Treat a blank `url` as None.
  - Fill `players.json` (43 players, events from public knowledge) and `tournaments.json` (31 editions) so `test_real_dataset_counts` passes against the pinned checkout.
- [ ] **Step 4:** Run `SHUTTLESET_DIR=<checkout> python -m pytest pro_profiles/tests/test_load.py -v`. Expected: all PASS, real-data test included.
- [ ] **Step 5:** Stage. Proposed commit: `feat(tools): load and normalise ShuttleSet data for pro profiles`.

---

### Task 2: Player stats and comparison group

**Files:**
- Create: `tools/pro_profiles/stats.py`, `tools/pro_profiles/tests/test_stats.py`

**Interfaces:**
- Consumes: `Match`, `Rally`, `Shot` from Task 1.
- Produces (in `stats.py`):
  - `SHOWN_GROUPS = ("Lift", "Smash", "Net", "Drive", "Push", "Clear", "Drop")` (Net kill counts in denominators only)
  - `BANDS = (("short", "4 shots or fewer", 0, 4), ("mid", "5 to 8 shots", 5, 8), ("long", "9 shots or more", 9, None))`
  - `@dataclass class PlayerStats: player: str; shots_by_group: dict[str, int]; grouped_shots: int; rallies_by_band: dict[str, int]; wins_by_band: dict[str, int]`
  - `def player_stats(matches: list[Match], player: str) -> PlayerStats`
  - `def share(ps: PlayerStats, group: str) -> float`
  - `def win_rate(ps: PlayerStats, band: str) -> float | None` (None below 30 rallies)
  - `@dataclass class Ranked: value: float; rank: int; of: int; below: int; typical: float; percentile: float`. Rank uses competition ranking, 1 = highest value. `below` = others strictly lower. `percentile = below / (of - 1) * 100`.
  - `def rank_shot_share(all_stats: dict[str, PlayerStats], player: str, group: str) -> Ranked | None` (None if the player has under 300 grouped shots)
  - `def rank_band(all_stats: dict[str, PlayerStats], player: str, band: str) -> Ranked | None`

- [ ] **Step 1: Write failing tests:**
  - `test_share_denominator_includes_net_kill_excludes_serves` (fixture numbers).
  - `test_rank_ties_use_competition_ranking`: values `[5, 5, 3]` → ranks `1, 1, 3`.
  - `test_band_needs_30_rallies`: 29 short rallies → `win_rate(...)` is None and `rank_band(...)` is None.
  - `test_typical_is_median_including_player`.
  - `test_axelsen_snapshot` (skipped unless `SHUTTLESET_DIR` is set), asserting to 1 decimal place:
    - shares: Net 35.6, Lift 27.7, Smash 15.6, Push 6.4, Drop 5.0, Drive 4.7, Clear 3.8; `grouped_shots == 7080`
    - Lift rank 1 of 39; Smash 5; Drop 38; Clear 36
    - bands: rallies `{"short": 472, "mid": 351, "long": 700}`, win rates 41/60/58 (rounded %), typical 44/51/49
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `stats.py`.
- [ ] **Step 4:** Run with `SHUTTLESET_DIR` set. Expected: PASS. If the snapshot differs, the spec's "Stat definitions" section is the reference. Fix the code, not the numbers.
- [ ] **Step 5:** Stage. Proposed commit: `feat(tools): compute pro shot shares, rally bands and ranks`.

---

### Task 3: Clip sources

**Files:**
- Create: `tools/pro_profiles/clips.py`, `tools/pro_profiles/content/clip_sources.json`, `tools/pro_profiles/tests/test_clips.py`

**Interfaces:**
- Produces:
  - `clip_sources.json`: `{"<match_id>": {"url": "https://www.youtube.com/watch?v=...", "offsetSec": 0, "checked": false}}`. Generated once from the 43 `match.csv` URLs by `python -m pro_profiles.clips --init`, then hand-maintained.
  - `@dataclass(frozen=True) class Clip: match_id: str; youtube_id: str; start_sec: int; end_sec: int; match_label: str; score_label: str`
  - `def youtube_id(url: str) -> str` (handles `watch?v=`, `youtu.be/`, and extra query params)
  - `def clip_for_rally(match: Match, rally: Rally, sources: dict, labels: Callable[[Match, Rally], tuple[str, str]]) -> Clip | None` (None when the match has no source)
  - Labels: `match_label` = `"{Edition name} {season} {round} against {opponent}"` (e.g. "Malaysia Masters 2020 final against Kento Momota"). `score_label` = `"game {set_no} at {a}–{b}"` from the player's perspective.

- [ ] **Step 1: Write failing tests:**
  - `test_youtube_id_variants`.
  - `test_clip_window_applies_offset_and_padding`: first shot at 100s, last at 120s, offset 5 → start 103, end 128.
  - `test_no_source_no_clip`.
  - `test_score_label_from_player_perspective`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Run `--init` against the pinned checkout to write the 43 entries.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Timing spot-check (manual).** For 5 matches, open 3 rallies each at the computed start time and confirm the rally is on screen.
  - Constant offset in a match → record `offsetSec` and set `checked: true`.
  - Drift across ShuttleSet generally → stop and report to James before Task 4 ships clips.
  - Write the results as a table in the task report.
- [ ] **Step 6:** Stage. Proposed commit: `feat(tools): map rallies to BWF YouTube clip windows`.

---

### Task 4: Findings, summary, tips and clip selection

**Files:**
- Create: `tools/pro_profiles/findings.py`, `tools/pro_profiles/content/templates.json`, `tools/pro_profiles/content/tips.json`, `tools/pro_profiles/tests/test_findings.py`

**Interfaces:**
- Consumes: `PlayerStats`, `Ranked`, `rank_shot_share`, `rank_band` (Task 2); `Clip`, `clip_for_rally` (Task 3).
- Produces:
  - `@dataclass class Finding: key: str` (e.g. `"shot.Lift.top"`, `"shot.Drop.bottom"`, `"band.long.strength"`, `"band.short.weakness"`); `kind: Literal["style", "strength", "weakness"]; claim: str; figure: str` ("27.7%" / "58%"); `comparison: str; tip: str | None; clips: list[Clip]; percentile_distance: float`
  - `def select_findings(player, all_stats, matches, sources) -> list[Finding]`. Implements the spec's Findings rules 1–4. Ties on `percentile_distance` order style, then strength, then weakness. The weakness, if any, is always last. Maximum 4.
  - `def summary(player, findings) -> str | None`. Rule: `"{He} " + phrase(first style finding) + " and " + phrase(first strength finding) + ". " + weakness sentence`. Drop any part that doesn't exist. Return None when there are no findings.
  - `def pick_clips(...) -> list[Clip]`. Up to 5 rallies matching the finding (spec "Example rallies"), with distinct matches first, then earliest date and rally number. Only rallies with a clip source count.
- `templates.json` keys and the **exact strings the Axelsen snapshot needs**:
  - `claim.shot.top1`: `"{He} {verb_s} more than any other pro"`
  - `claim.shot.top`: `"{He} {verb_s} more than most pros"`
  - `claim.shot.bottom`: `"{He} almost never {verb}"`
  - `comparison.shot.top`: `"of {his} shots. A typical pro: {typical}%."`
  - `comparison.shot.bottom`: `"Only {below_word} of {others} pros {verb_s} less."` (`below_word` is "one" for 1, otherwise the digits)
  - `claim.band.long.strength`: `"Long rallies go {his} way"`
  - `comparison.band.long.strength`: `"won past 8 shots. Better than {below} of {others} pros."`
  - `claim.band.short.weakness`: `"Short rallies are where {he} loses"`
  - `comparison.band.short.weakness`: `"won in 4 shots or fewer. A typical pro: {typical}%."`
  - `phrase.shot.Lift.top1`: `"lifts more than anyone else in the data"`
  - `phrase.band.long.strength`: `"lets rallies run long, where {he} wins far more than most"`
  - `sentence.band.short.weakness`: `"Keep the rally short and {he}'s beatable."`
  - `verbs`: per group, `[verb, verb_s]`, e.g. `"Lift": ["lift", "lifts"], "Drop": ["drop", "drops"]`
  - Write the remaining band, shot and phrase keys in the same voice.
- `tips.json`: one tip per finding key (8 shot groups × top/bottom + 3 bands × strength/weakness = 22). Casual-player, tactics-only voice. `"shot.Lift.top"` is exactly the mockup's tip: "When you're under pressure, lift high to the back corners instead of forcing a drop. It buys you time to get back to the middle." Mark the file `"_status": "draft — James to review"`.

- [ ] **Step 1: Write failing tests:**
  - `test_axelsen_findings` (real data): keys in order `["shot.Lift.top", "shot.Drop.bottom", "band.long.strength", "band.short.weakness"]`. Claims `"He lifts more than any other pro"`, `"He almost never drops"`, `"Long rallies go his way"`, `"Short rallies are where he loses"`. Comparisons `"of his shots. A typical pro: 18.9%."`, `"Only one of 38 pros drops less."`, `"won past 8 shots. Better than 37 of 38 pros."`, `"won in 4 shots or fewer. A typical pro: 44%."`.
  - `test_axelsen_summary` equals `"He lifts more than anyone else in the data and lets rallies run long, where he wins far more than most. Keep the rally short and he's beatable."`
  - `test_womens_pronouns`: a WS fixture player gets "She"/"her".
  - `test_weakness_kept_when_more_than_four_candidates`.
  - `test_no_findings_player`: returns `[]` and `summary(...)` is None.
  - `test_finding_without_clip_sources`: `clips == []`.
  - `test_every_key_has_template_and_tip`: every key `select_findings` can produce exists in both content files.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `findings.py` and write both content files.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Stage. Proposed commit: `feat(tools): generate pro findings, summaries and example clips`.

---

### Task 5: Build the JSON output

**Files:**
- Create: `tools/pro_profiles/build.py`, `tools/pro_profiles/tests/test_build.py`, `tools/pro_profiles/README.md`
- Create (generated, committed): `frontend/badminton-ai/public/pro-data/players/index.json`, `players/<id>.json`, `tournaments/index.json`, `tournaments/<edition_id>.json`
- Modify: `data-flow.md` (new section "5. Pro profile data (static JSON)" documenting the shapes below)

**Interfaces:**
- Consumes: everything above, plus `photos.json` from Task 6 if present (otherwise `photo: null`).
- Produces the **JSON contract** (camelCase; percentages as numbers 0–100 rounded to 1 decimal; rates rounded to whole numbers):
  - `players/index.json`: `{ "generatedFrom": "<dataset sha>", "players": [{ "id", "name", "event": "MS"|"WS", "matches": number, "ranked": boolean, "photo": Photo|null }] }`
  - `players/<id>.json`:
    - top level: `{ "id", "name", "event", "context": { "matches", "firstYear", "lastYear", "comparedWith": number }, "summary": string|null, "photo": Photo|null, "filters": [{ "id", "label", "kind": "all"|"tournament"|"match", "matches": number }], "views": { "<filterId>": View } }`
    - filter ids: `"all"`, `"t:<edition_id>"`, `"m:<match_id>"`
  - `View`:
    - `{ "kind", "shots": number, "rallies": number, "shotChoice": [ShotRow], "bands": [BandRow], "findings": [Finding], "rallyBrowser": [Clip] }`
    - `findings` is only non-empty in `"all"`. `rallyBrowser` is only non-empty in filtered views (that subset's rallies with clip sources, in order).
  - `ShotRow`: `{ "group", "share": number, "count": number, "rank": number|null, "of": number|null, "typical": number }`. `rank`/`of` are null in filtered views and for unranked players. `typical` is always the all-match median.
  - `BandRow`: `{ "band": "short"|"mid"|"long", "label", "rallies": number, "winRate": number|null, "typical": number }`. `winRate` is null below 30 rallies.
  - `Finding`: `{ "key", "kind", "claim", "figure", "comparison", "tip": string|null, "clips": [Clip] }`
  - `Clip`: `{ "youtubeId", "startSec", "endSec", "matchLabel", "scoreLabel" }`
  - `Photo`: `{ "src": "/pro-data/photos/<id>.jpg", "credit": "Photo: <author>, <licence>", "sourceUrl", "focusX": 0-100, "focusY": 0-100 }`
  - `tournaments/index.json`: `{ "editions": [{ "id", "name", "season", "matches": number }] }`, sorted season descending, then name.
  - `tournaments/<id>.json`: `{ "id", "name", "season", "matches": [{ "id", "round", "date", "winner": {"id","name"}, "loser": {"id","name"}, "games": [[a,b], ...] }], "players": [{ "id", "name", "event" }] }`. Games are points per set from rally winners, winner's score first.
- CLI: `python -m pro_profiles.build --source <checkout> --out ../frontend/badminton-ai/public/pro-data`. Run from `tools/`. Deterministic: same input gives byte-identical output, with keys sorted and lists in a defined order.

- [ ] **Step 1: Write failing tests** (on the `mini` fixture unless noted):
  - `test_match_view_has_no_ranks_or_findings`: every `"m:*"` and `"t:*"` view has `findings == []` and every `ShotRow.rank is None`.
  - `test_tournament_games_from_rally_winners`.
  - `test_output_is_deterministic`: two builds into temp dirs are byte-identical.
  - `test_index_sorted` (players by name within event; editions by season descending).
  - `test_axelsen_file_shape` (real data): `views.all.findings` has 4 entries; `context == {"matches": 20, "firstYear": 2019, "lastYear": 2022, "comparedWith": 38}`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `build.py`. Write `README.md` (how to run it, the pinned SHA, the content files, the clip-source workflow). Add the `data-flow.md` section.
- [ ] **Step 4:** Run the tests, then run the build against the pinned checkout. Expected: tests PASS. `public/pro-data/` holds 43 player files and 31 tournament files, totalling under 3 MB (`du -sh`).
- [ ] **Step 5:** Add a `pro-profiles-checks` job to `.github/workflows/ci.yml`:
  - Python 3.11, `pip install pytest`.
  - Shallow-fetch the pinned dataset commit into `$RUNNER_TEMP/coachai` (git init, add the remote, `git fetch --depth 1 origin <sha>`, sparse checkout of the two paths).
  - Run `SHUTTLESET_DIR=$RUNNER_TEMP/coachai python -m pytest pro_profiles/tests` in `tools/`.
  - Run the build into a temp dir and `diff -r` it against `frontend/badminton-ai/public/pro-data`, so committed JSON can't go stale.
- [ ] **Step 6:** Stage. Proposed commit: `feat(tools): build static pro profile and tournament JSON`.

---

### Task 6: Photo candidates and approvals

**Files:**
- Create: `tools/pro_profiles/photos.py`, `tools/pro_profiles/content/photos.json` (starts as `{}`), `tools/pro_profiles/tests/test_photos.py`
- Create (generated): `frontend/badminton-ai/public/pro-data/photos/<id>.jpg` (approved only)

**Interfaces:**
- Produces:
  - `ALLOWED_LICENCES` = CC BY (any version), CC BY-SA (any version), CC0, public domain, matched on Commons `LicenseShortName`.
  - `def licence_allowed(short_name: str) -> bool`
  - `def credit(author_html: str, licence: str) -> str` (strips HTML; `"Photo: Fauziananta, CC BY 4.0"`)
  - CLI `python -m pro_profiles.photos candidates --out <dir>`:
    - for each player, queries the Wikipedia page image, then the Commons `imageinfo` / `extmetadata`, **sleeping ≥2s between requests**, with a generic User-Agent
    - keeps allowed licences only
    - writes `<dir>/contact-sheet.html`: one card per player with the photo, licence, author, source link, and an editable focus point
  - CLI `python -m pro_profiles.photos approve <player_id> --focus X,Y` adds `{sourceUrl, author, licence, focusX, focusY}` to `photos.json`.
  - CLI `python -m pro_profiles.photos download` fetches approved images at 400px wide into `public/pro-data/photos/`.
  - `build.py` (Task 5) reads `photos.json` to fill `Photo`.
- [ ] **Step 1: Write failing tests:**
  - `test_licence_filter`: allows `CC BY 4.0`, `CC BY-SA 2.0`, `CC0`, `Public domain`; rejects `CC BY-NC 2.0`, `Fair use`, `All rights reserved`, `""`.
  - `test_credit_strips_html`.
  - `test_build_uses_approved_photo` (mini fixture plus a photos.json fixture).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Network code stays outside the tested functions.
- [ ] **Step 4:** Run the tests. Expected: PASS. Then run `candidates` and give James the contact-sheet path. **Do not approve photos yourself.** Only James approves.
- [ ] **Step 5:** Stage (no photos yet). Proposed commit: `feat(tools): fetch freely licensed player photo candidates`.

---

### Task 7: Frontend data layer and shared components

**Files:**
- Create: `frontend/badminton-ai/src/features/pros/types.ts` (TypeScript mirror of the Task 5 contract, names identical)
- Create: `frontend/badminton-ai/src/features/pros/proData.ts`
- Create: `frontend/badminton-ai/src/features/pros/hooks/useProData.ts`
- Create: `frontend/badminton-ai/src/features/pros/components/Panel.tsx`, `PlayerPhoto.tsx`, `ProAttribution.tsx`, `ProShell.tsx`

**Interfaces:**
- Produces:
  - `proData.ts`: `fetchPlayerIndex(): Promise<Result<PlayerIndex, ProDataError>>`, `fetchPlayer(id: string)`, `fetchTournamentIndex()`, `fetchTournament(id: string)`, using `Result` from `src/lib/result.ts`. `type ProDataError = { kind: "not-found" } | { kind: "network"; message: string }` (404 → not-found).
  - `useProData<T>(load: () => Promise<Result<T, ProDataError>>, deps: unknown[]): { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: ProDataError }`
  - `<Panel title subtitle? className? children>`: raised surface (`bg-card rounded-2xl p-6`), `h2` title at 18px/600, subtitle in muted 14px.
  - `<PlayerPhoto photo name size>`: `object-cover` with `objectPosition: "{focusX}% {focusY}%"`, the credit under it. Initials tile when `photo` is null.
  - `<ProAttribution />`: the exact footer copy from Global Constraints.
  - `<ProShell>`: the public page frame. Top bar with the Shuttleye wordmark linking `/`, links Players and Tournaments, the theme toggle and Sign in. Max width 1600px, 48px gutters (16px under 760px). `<ProAttribution />` at the bottom.
- [ ] **Step 1:** Implement the files above.
- [ ] **Step 2:** Run `cd frontend/badminton-ai && npm run lint && npm run build`. Expected: no new errors. The existing `useAnalysisData.ts` warning is allowed.
- [ ] **Step 3:** Stage. Proposed commit: `feat(frontend): add pro data loaders and shared pro components`.

---

### Task 8: Player profile page

**Files:**
- Create: `frontend/badminton-ai/src/features/pros/components/FindingsPanel.tsx`, `WatchPanel.tsx`, `RallyLengthPanel.tsx`, `ShotChoicePanel.tsx`, `ProfileHeader.tsx`
- Create: `frontend/badminton-ai/src/pages/PlayerProfilePage.tsx`
- Modify: `frontend/badminton-ai/src/App.tsx` (lazy route `/players/:playerId`, public, outside `ProtectedRoute`)

**Interfaces:**
- Consumes: Task 7 exports and the `Player` and `View` types.
- Layout (matches mockup v9b):
  - Header: photo, name, context line `"{Men's|Women's} singles. {matches} matches from {firstYear} to {lastYear}, compared with {comparedWith} other pros."`, the summary, and a filter `<select>` (label "Matches", visually hidden) bound to `?view=<filterId>` in the URL, defaulting to `all`.
  - Grid `grid-cols-12 gap-6`:
    - Findings `col-span-4`, Watch `col-span-5`, Rally length `col-span-3`, Shot choice `col-span-12` (two columns of rows).
    - Under 1180px: Watch is full width first, Findings and Rally length `col-span-6` each, Shot choice full width.
    - Under 760px: everything one column.
- Behaviour:
  - Findings are `<button aria-pressed>`. The first is selected on load. Selecting one swaps the Watch panel's title, clips and tip.
  - Strength/Weakness tags appear on `kind` strength/weakness only.
  - Watch embeds an `<iframe>` (`youtube-nocookie`, `title="{matchLabel}"`, `allow="encrypted-media; picture-in-picture"`, `loading="lazy"`). Previous/next buttons (44px, `aria-label`) step through clips with a "1 of N" counter.
  - No clips → the text "No clips available for these matches yet".
  - Findings `[]` → the line "Nothing stands far out from other pros in this data", and the Watch panel shows the first `rallyBrowser` clip, if any.
  - Filtered view: Findings is replaced by a "Rallies in this selection" list from `rallyBrowser`. A note reads "Rankings and findings use all matches." Shot rows show share and count with "Typical pro {typical}%" instead of a rank bar. A band with `winRate` null shows "Too few to compare".
  - Shot choice bar width = `(of - rank) / (of - 1) * 100%`. Footnote "A longer bar means {he} plays that shot more often than most pros. It's about style, not skill."
  - Rally length: paired bars (player in ink, typical pro in muted) per band, with `{rallies} rallies`.
  - Not found → "We don't have a profile for this player." plus a link to `/players`.
- [ ] **Step 1:** Implement.
- [ ] **Step 2:** `npm run lint && npm run build`. Expected: pass.
- [ ] **Step 3: Visual check.** Start the dev server. Screenshot `/players/viktor-axelsen` at 1440×900, 1024, 768 and 390 with the taste-skill `shoot.mjs` (or the run skill). Compare against mockup v9b and fix differences.
  - Findings, video and tip are visible without scrolling at 1440×900.
  - Numbers match the Task 4 test values.
  - Keyboard: Tab reaches each finding and the clip buttons with a visible ring.
  - `?view=m:<some match>` shows no ranks and no findings.
  - `/players/nobody` shows the not-found state.
- [ ] **Step 4:** Stage. Proposed commit: `feat(frontend): add pro player profile page`.

---

### Task 9: Player list, tournaments, routes and nav

**Files:**
- Create: `frontend/badminton-ai/src/pages/PlayersPage.tsx`, `TournamentsPage.tsx`, `TournamentPage.tsx`
- Modify: `frontend/badminton-ai/src/App.tsx` (lazy public routes `/players`, `/tournaments`, `/tournaments/:editionId`)
- Modify: `frontend/badminton-ai/src/pages/LandingPage.tsx` (nav links Players and Tournaments, left of Sign in)
- Modify: `frontend/badminton-ai/src/components/Navbar.tsx` (the same two links in the signed-in navbar)

**Interfaces:**
- Consumes: Task 7 loaders and components.
- Behaviour:
  - **Players:**
    - Title "Pro players", subtitle "Singles players from BWF World Tour matches, 2018 to 2022."
    - A search `<input type="search">` (visible label "Search players") filtering by name, case- and accent-insensitive.
    - Two sections, "Men's singles" and "Women's singles", as a grid of cards: photo, name and "{n} matches". Cards link to `/players/:id`. Unranked players show "Not enough data to rank" in muted text.
  - **Tournaments:**
    - Title "Tournaments", subtitle "Selected matches, mostly later rounds. Not every match of each tournament."
    - Editions grouped under season headings, newest first. Each card shows the name and "{n} matches in the data", linking to `/tournaments/:id`.
  - **Tournament page:**
    - Header with name and season.
    - Panel "Matches": rows of round, winner, loser and game scores. Player names link to `/players/:id?view=t:<editionId>`.
    - Panel "Players": a card grid linking the same way.
    - Not found → "We don't have this tournament." plus a link to `/tournaments`.
- [ ] **Step 1:** Implement.
- [ ] **Step 2:** `npm run lint && npm run build`. Expected: pass.
- [ ] **Step 3: Visual check** at 1440 and 390 for the three pages.
  - Search "axel" finds Axelsen, and "an se" finds An Se Young.
  - A tournament player link opens the profile filtered to that tournament.
  - Nav links work on the landing page and inside the signed-in app.
- [ ] **Step 4:** Stage. Proposed commit: `feat(frontend): add pro player list and tournament pages`.

---

### Task 10: Final verification and Gate 2

- [ ] **Step 1:** Run `cd tools && SHUTTLESET_DIR=<checkout> python -m pytest pro_profiles/tests -v` (all pass), `cd worker && pytest tests/` (unchanged suite still passes), and `cd frontend/badminton-ai && npm run lint && npm run build`.
- [ ] **Step 2:** Rebuild the JSON and confirm `git status` shows no diff in `public/pro-data/`.
- [ ] **Step 3:** Review the full diff for unintended changes. Confirm no dataset CSVs or unapproved photos are staged.
- [ ] **Step 4: Gate 2.** Present the per-task commit messages and files, plus the clip timing spot-check table, the photo contact-sheet path, and the open items (licence email, tip review, photo approvals). Wait for "Commit these changes".
