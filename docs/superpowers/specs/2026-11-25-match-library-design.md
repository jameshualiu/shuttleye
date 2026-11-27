# Match library: database, add-a-match command, match pages — design

Status: draft for approval, 2026-11-25. Issues: #77 (database), #76 (add-a-match command), #78 (library pages). Built in that order.

## Intent

Shuttleye is a library of pre-analysed BWF singles matches with player profiles that grow as matches are added (direction set 2026-11-24). The people who open a profile or match page are **players and coaches who want to understand why a pro is good**: playstyle, strengths, weaknesses, a new angle backed by data. Success is that they leave with something they didn't know, and can watch it happen in the video. Failure, even if it all technically works: numbers without meaning, or a stat that quietly means something different from one match to the next.

The analyzer (PR #81, `worker/fullmatch/`) now produces, per match: rallies, every shot with type (6-class `type`, 10-class `detailType`), hitter side, hitter court position in metres, serves, timing, and (when the scoreboard is readable) the score and rally winner. This work stores that, turns it into profiles, and shows it.

## Goals

- Matches, players and tournaments live in the existing Firestore project.
- One command adds a match from a YouTube link; nothing but results is kept; matches stay unpublished until James publishes them.
- Player profiles are computed **only from analyzer output**, so every match is measured the same way. The 43 ShuttleSet singles matches that have a YouTube link are re-run through the analyzer to seed the library (James, 2026-11-25; the other 51 hand-labelled matches have no known video and are dropped); ShuttleSet's hand labels become the accuracy check, not profile data.
- A match page and a match list, with YouTube playback that jumps to rallies and shots.

## Non-goals

- Doubles. The doubles pages stay on their current static files (separate CC BY-NC-SA data).
- An admin UI. Adding, reviewing and publishing are commands.
- Casual / uploaded footage, public (signed-out) access, comments or social features.
- New stats beyond the six listed below (James: "I wouldn't wanna try and add more").
- The 2025 scoreboard reader, serve-flagging fix and side-inversion fix (separate follow-up issues from #81). This design must degrade cleanly without them.

## Constraints

- Sign-in required for every library page and every Firestore read. Only James's commands write (Admin SDK; client writes denied). Unpublished matches are readable only by James (admin uid or custom claim).
- Videos are downloaded on James's machine (YouTube blocks Modal), analysed, then deleted. Playback is the YouTube IFrame embed.
- Analysis runs on Modal (~$1.20 per 50-min match, $30/month credit) or locally on James's M5 Pro laptop. The first step of #76 times one 1-minute chunk locally, estimates a full match from it, and re-checks accuracy on one match before `--local` is relied on; the re-runs are then split between Modal and the laptop.
- Existing contracts: `data-flow.md` is updated in the same change as any schema; frontend types mirror the stored shapes; theme is neutral black/white with colour only for data.
- No visible regression on the pro pages during the switch (#77): the current hand-label profiles stay live until the analyzer re-runs cover them, then switch in one go.
- Conventional commits, feature branches, Gate 1/Gate 2 per AGENTS.md; no attribution lines.

## Approaches considered (storage layout)

- **A. One document per match (chosen).** `matches/{id}` holds metadata, scores and every rally with its shots (~700 shots, ~70 KB, well under Firestore's 1 MB limit). Profiles precomputed into `players/{id}` plus one small doc per filter. Match page = 1 read; commands easy to write and re-run. Cost: no cross-match shot queries in Firestore, which isn't needed because stats are computed in Python.
- B. One document per rally (`matches/{id}/rallies/{n}`). ~60 reads per match page and more bookkeeping for no gain.
- C. Metadata in Firestore, full result as a file in private storage via backend-issued short-lived link (the current `analysis.json` pattern). Adds a backend step and a second place to keep in sync for data that fits in one document.

James picked A. Database: Firestore, which the project already uses (James's call).

## Decided parts of the how

### Data (Firestore)

- `matches/{matchId}`: YouTube id, tournament edition, round, date, players (A/B with player ids, which one starts near), games/scores (when read), status `unpublished | published`, analyzer version/commit, timings, warnings and skipped steps from the analyzer, and `rallies[]` each with start/end time, score before, winner (or null), and `shots[]` (time, hitter, `type`, `detailType`, court position, isServe). Compact field names are fine; the exact shape is documented in `data-flow.md`.
- `players/{playerId}`: identity (name, aliases, event "MS"/"WS", photo), context (matches, years, compared-with count), summary, filters list. `players/{playerId}/views/{filterId}`: the profile view per filter (`all`, `t:<edition>`, `m:<match>`), same idea as today's static `View`.
- `tournaments/{editionId}`: name, season, match list (as today's tournament files).
- An index for the list pages (players, tournaments, matches) — one small doc each or a collection query; builder's choice.
- Player matching on ingest: by id/name/alias from the existing `tools/pro_profiles/content/players.json` alias map; unknown names create a new player (command reports it).

### What a profile and a match page show — the six insights

Each is compared with the player's own usual and with other pros, is written as a plain sentence (finding = style / strength / weakness, as today), and links to clips:

1. Shot mix by rally phase (first four shots, mid, long rallies).
2. Replies: what they play after each opponent shot (e.g. after being smashed at).
3. Court position: where they hit from (front/mid/rear × forehand/backhand side).
4. Rally length and tempo: win rate by rally length band; seconds between shots.
5. Serve: short vs long, and what follows.
6. Winning shots: rallies won right after their smash (and similar).

Insights 4 (win rate part), 5 (points won) and 6 need rally winners, which need a readable scoreboard. Matches without a read score are excluded from those numbers only, and the UI says so ("shown only for matches whose score we can read"). Minimum-sample rules like today's (e.g. under 30 rallies → no figure) apply.

### Add-a-match command (#76)

1. `ingest <youtube-url> --players "<A>" "<B>" --near-first <A|B> [--tournament … --round … --date …]` downloads 720p locally, analyses (Modal by default, `--local` for the laptop), runs the full-match pipeline, deletes the video, writes the match as `unpublished`. Re-running an ingested match is a no-op unless `--force`. Per-stage timings saved. A failed optional step is recorded, never fatal (as in `assemble_result`).
2. James reviews it on its match page (visible only to him while unpublished).
3. `publish <matchId>` marks it published and recomputes both players' profile views, the tournament doc and indexes.
4. A batch mode runs a list (the ShuttleSet re-runs), resumable.

`--near-first` exists because without a read scoreboard the analyzer cannot tell which named player is on which side; with a read scoreboard the command checks it agrees.

### Profile computation

Reuse `tools/pro_profiles/` (stats, findings, templates, tips) with a new loader that reads analyzer matches from Firestore instead of ShuttleSet CSVs; output goes to Firestore instead of `public/pro-data/`. Findings wording for the six insights extends the existing templates.

### Five-match checkpoint (James, 2026-11-25)

After the database, the command and the match pages work, only **5 matches** are ingested and published (visible to James), then everything stops for James to judge the data quality on the real pages and decide whether the other 38 are worth running. Use the 5 ShuttleSet matches already analysed during #81 (Axelsen v Christie, Axelsen v Ng, Axelsen v Liew, Ng v Lee, An Se Young v Intanon) where their saved merged results can be re-processed locally with the merged #81 code, so the checkpoint costs little or no GPU time. The local M5 Pro timing test also happens before this checkpoint.

### Switch-over

Until the re-runs cover the 43 matches, the pro pages keep reading `public/pro-data/`. A single switch (config flag or one commit) moves players and tournaments pages to Firestore once coverage is complete; the static singles files are then removed. Doubles files stay.

### Library pages (#78)

Match page per the accepted mockup (`.superpowers/brainstorm/…/match-page.html`, "use this for now, change later"):

- Header: winner d. loser, tournament/round, game scores, rally count, average shots.
- YouTube player with the rally list beside it (score, winner dot, length bar; filters: long rallies, lost points, game). Selecting a rally seeks the video.
- Selected rally as two lanes (one per player), shots placed in time and coloured by type; selecting a shot seeks; a line saying how the rally ended.
- "How this match was won": the six insights for this match.

Match list with search/filter by player, tournament and year. Profiles link to their matches; match pages link to both profiles. Works at phone width and in both themes.

## Settled after the builder check (Claude's calls, James can overrule)

- **Accuracy gate for the switch.** Every re-run ShuttleSet match is scored against its hand labels with the existing eval (`worker/train/eval_shuttleset.py` scoring), and the score is saved on the match. The switch needs all re-runs scored, with pooled results no worse than #81's measured ShuttleSet numbers by more than 5 points (hit F1 ~90, side ~100, 6-type ~88). A match that scores far below is left unpublished and listed for a look.
- **Profile content becomes the six insights.** Today's shot-choice table, rally-length bands and findings map onto insights 1 and 4 and the findings format. Anything that needs landing spots or how points ended is dropped, as agreed. "No visible regression" means no empty, broken or missing pages at the switch, not identical content. The `View` shape and frontend types change with it.
- **Re-run inputs.** YouTube URLs come from `tools/pro_profiles/content/clip_sources.json`; names, tournament, round and date from ShuttleSet `match.csv`; `--near-first` from ShuttleSet's labelled hitter positions. No hand research is needed for those matches.
- **Match-page insights are precomputed** by `publish` into the match doc; the browser does no stats.
- **Doubles stays on its own routes** (`/pairs`) and files; nothing is merged.
- **Comparison baseline.** Comparisons with other pros need at least 10 qualifying players (today's rule: 300+ shots). Below that, profiles show the player's own numbers without ranks or "vs other pros" findings, and say so.
- **Re-running a published match** (`--force`) keeps it published, recomputes the affected profiles, and prints what changed. `unpublish <matchId>` exists and recomputes too.

## Left to the builder

- Exact Firestore field names and the index-doc vs query choice, documented in `data-flow.md`.
- Admin identification (uid allowlist vs custom claim) and the security rules file (the repo has none today; add one).
- Where the commands live (`tools/` vs `worker/`), and how the YouTube download is done (yt-dlp locally).
- How the six insights' thresholds (zones, phases, bands) are defined, starting from today's band definitions and COURTSIDE's insight code where it exists.
- Order of the 43 re-runs within the monthly Modal budget and laptop time (~$52 if all on Modal).
