# Match Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store analysed BWF singles matches and player profiles in Firestore, add them with one command, show them on match pages with YouTube playback, then stop after 5 matches for James's review.

**Architecture:** A new offline Python package `tools/library/` turns the analyzer's full-match product result (`worker/fullmatch/run.py: assemble_result`) into a compact Firestore match document, and recomputes player profiles, tournaments and the index from all published matches using the existing `tools/pro_profiles` stats/findings code plus a new `insights.py` for the six insights. The ingest command downloads locally, analyses on Modal (or locally), stores the match unpublished and deletes the video. The frontend gains a Firestore data layer, a match page per the accepted mockup, a match list, and profile pages that render the six insights; the pro pages keep their static files until the switch, which happens after this plan.

**Tech Stack:** Python 3.11 (firebase-admin, yt-dlp, the worker's `fullmatch` package), Firestore, React 19 + TypeScript + Vite + Tailwind v4, Firebase JS SDK v12, YouTube IFrame Player API.

**Spec:** `docs/superpowers/specs/2026-11-25-match-library-design.md` (approved 2026-11-25).

## Global Constraints

- Base: PR #81 (`feature/72-full-match-analyzer`) must be merged first, or this branch (`feature/77-match-library`) is cut from it. `worker/fullmatch/` is required.
- Gate 2 (AGENTS.md): no commits during execution. Each task ends with a tree snapshot (`git add -A && git write-tree`) recorded in the ledger; commits are made after James says "Commit these changes". No `Co-Authored-By` / "Generated with Claude Code" anywhere.
- Never write credential values to files. Firestore admin credentials come from `GOOGLE_APPLICATION_CREDENTIALS` (path to a service-account JSON outside the repo).
- Never commit videos, datasets, weights or analysis results. Downloaded videos are deleted after analysis.
- Only the commands write Firestore (Admin SDK). Client writes are denied. Every read requires sign-in. Unpublished matches are readable only by a user with custom claim `admin == true`.
- Profiles are computed only from analyzer output. ShuttleSet hand labels are used only for the accuracy score.
- Six insights, no others: shot mix by rally phase; replies; court position; rally length and tempo; serve; winning shots.
- Minimum samples: rally-based figures need ≥ 30 rallies (`MIN_BAND_RALLIES`), shot-share figures ≥ 50 shots (`MIN_SHARE_SHOTS`); below that the figure is `null`. A player is ranked at ≥ 300 grouped shots (`MIN_GROUPED_SHOTS`). Comparisons with other pros (ranks, "vs other pros" findings) appear only when ≥ 10 players are ranked (`MIN_COMPARED = 10`).
- Score-dependent figures (win rate by rally length, points won on serve, winning shots) use only rallies whose score was read; the UI says "Shown only for matches whose score we can read."
- The pro pages (`/players`, `/tournaments`) keep reading `public/pro-data/` in this plan. Doubles pages are untouched. The existing static build (`tools/pro_profiles/build.py`) output must stay byte-identical (CI checks it).
- Frontend: neutral black/white theme, colour only for data; works at phone width and in both themes; `npm run lint` and `npm run build` pass.
- `data-flow.md` is updated with every new stored shape.
- Stop at Task 12 (five-match checkpoint). The other 38 re-runs, the switch and the static-file removal are not in this plan.

## Review Focus

1. A match whose scoreboard was not read (no `nearPlayer` per rally): shots can't be attributed to named players. Expected: ingest stores it with `attributed: false` and a warning; `publish` refuses with a clear message. (Test in Task 1 and Task 5.)
2. A rally with shots whose `side` is `null` or `type` `"Unknown"`: they are kept in the rally (time line stays complete) but excluded from shares. (Task 1, Task 3.)
3. Re-running ingest on an existing match id: no-op without `--force`; with `--force` on a published match it stays published, profiles are recomputed, and a change summary is printed. (Task 6.)
4. Unknown player name at ingest: a new player id is created from the name (slug) and reported; a name matching an alias resolves to the existing id. (Task 1.)
5. Profile pages for a player with 1 match / under the minimums: every insight renders its "not enough data" state, no `NaN`, no empty cards. (Task 3 tests, Task 10 check.)

---

### Task 1: Match document from an analyzer result

**Files:**
- Create: `tools/library/__init__.py`, `tools/library/match_doc.py`, `tools/library/players.py`
- Create: `tools/library/tests/__init__.py`, `tools/library/tests/conftest.py`, `tools/library/tests/fixtures/product_result.json`, `tools/library/tests/test_match_doc.py`, `tools/library/tests/test_players.py`
- Modify: `tools/pro_profiles/content/players.json` (add optional `"hand": "R"|"L"` only where known; not required)

**Interfaces:**
- Consumes: the product result of `worker/fullmatch/run.py: assemble_result` (events with `timeSec, type, detailType, side ("Top"|"Bottom"|null), isServe, location_m`; rallies with `id, set, startSec, endSec, eventIndices, scoreAfter, winner ("A"|"B"|null), nearPlayer ("A"|"B"|null), scoreRead`; `sets`; `summary`; `timings`; `models`; `warnings`; `skippedSteps`). A = match winner.
- Produces:
  - `resolve_player(name: str, players: dict) -> tuple[str, bool]` in `players.py` — (player id, created). Matches `name` or any alias case-insensitively; otherwise returns `slugify(name)` and `True`.
  - `GROUP_OF_DETAIL: dict[str, str | None]` in `match_doc.py`: `clear→Clear, drive→Drive, drop→Drop, lob→Lift, net shot→Net, smash→Smash, push/rush→Push, defensive shot→Lift, short service→None, long service→None`.
  - `zone_of(location_m: list[float] | None, hitter_near: bool) -> str | None` — `"<depth>-<side>"`, depth by distance from the net (court 6.1 × 13.4 m, net at y = 6.7): `front` < 1.98 m, `rear` > 4.72 m, else `mid`; side `left`/`right` of the centre line **from the hitter's view** (flip for the far player). `None` when location is missing.
  - `match_doc(result: dict, meta: MatchMeta) -> dict` where `MatchMeta = TypedDict(id, youtubeId, editionId, round, date, playerA, playerB, nearFirst)` (A = winner). Returns the Firestore match document:

```text
{ id, youtubeId, editionId, round, date,
  players: { A: {id, name}, B: {id, name} }, winner: "A",
  games: [[a, b], ...] | null,            # from result.sets finalScore, A first
  attributed: bool,                         # every rally has nearPlayer
  status: "unpublished",
  analyzer: { models, warnings, skippedSteps, timings },
  accuracy: null,                           # filled by Task 6 for ShuttleSet matches
  summary: { rallies, avgShots, durationSec },
  rallies: [ { n, set, startSec, endSec, scoreBefore: [a, b] | null, winner: "A"|"B"|null,
               shots: [ { t, p: "A"|"B"|null, g: group|null, d: detailType|null, z: zone|null, s: isServe } ] } ],
  insights: null }                          # filled by publish (Task 5)
```
  `p` = `nearPlayer` if `side == "Bottom"`, the other player if `"Top"`, `null` when either is unknown. `scoreBefore` = previous rally's `scoreAfter` in the same set, `[0, 0]` for a set's first rally, `null` when unread. If rally 1's `nearPlayer` disagrees with `meta.nearFirst`, append the warning `"near side at rally 1 disagrees with --near-first"`.

- [ ] **Step 1: Fixture.** Build `fixtures/product_result.json` by hand: 3 rallies in set 1, one with `nearPlayer: null`, one event with `side: null`, one `type: "Unknown"`, one serve with `location_m: null`; plus a `sets` entry with `finalScore`.
- [ ] **Step 2: Write failing tests** in `test_match_doc.py`:
  - `test_hitter_from_side_and_near` — Bottom shot in a rally with `nearPlayer "B"` → `p == "B"`; Top → `"A"`.
  - `test_unattributed_rally_sets_flag` — the rally with `nearPlayer: null` has all `p is None` and `doc["attributed"] is False`.
  - `test_unknown_and_null_side_kept` — shot counts per rally equal `len(eventIndices)`.
  - `test_score_before` — `[0,0]`, then the previous `scoreAfter`.
  - `test_zone_of` — court coordinates have the far baseline at y = 0 and x = 0 on the image's left: `zone_of([1.0, 12.0], True) == "rear-left"`, `zone_of([1.0, 1.0], False) == "rear-right"`, `zone_of([5.0, 7.5], True) == "front-right"`, `zone_of([3.5, 3.5], False) == "mid-left"`, `zone_of(None, True) is None`. (Verify the axis convention against `worker/pipeline.py`'s court template before writing; if it differs, keep the meaning and adjust the inputs.)
  - `test_group_map` — every `TEN_CLASSES` name in `worker/fullmatch/bst_inputs.py` has a `GROUP_OF_DETAIL` entry.
  - `test_doc_size_under_limit` — `len(json.dumps(doc)) < 900_000` for a synthetic 120-rally × 20-shot result.
- [ ] **Step 3:** In `test_players.py`: alias match (`"Viktor AXELSEN"` → `viktor-axelsen`, False); unknown name → slug, True.
- [ ] **Step 4:** Run `cd tools && python -m pytest library/tests -q` → FAIL.
- [ ] **Step 5:** Implement `players.py` and `match_doc.py` (pure Python, stdlib only; `conftest.py` puts `worker/` on `sys.path` for the `TEN_CLASSES` import).
- [ ] **Step 6:** Run the tests → PASS. Run `cd tools && python -m pytest pro_profiles/tests -q` → still PASS.
- [ ] **Step 7:** Snapshot the tree (no commit).

### Task 2: Analyzer matches in the profile model

**Files:**
- Modify: `tools/pro_profiles/load.py` (add optional fields to `Shot`)
- Create: `tools/library/to_model.py`, `tools/library/tests/test_to_model.py`

**Interfaces:**
- Consumes: Task 1 match documents.
- Produces:
  - `Shot` gains `detail: str | None = None` and `zone: str | None = None` (defaults keep ShuttleSet loading and the static build unchanged).
  - `to_match(doc: dict) -> pro_profiles.load.Match` — `id=doc.id`, `source="Analyzer"` (widen the `Literal`), `winner/loser` = A/B player ids, `youtube_url=f"https://www.youtube.com/watch?v={youtubeId}"`; one `Rally` per rally (`set_no=set or 1`, `number=n`, `winner` mapped to player id or `None`, `score_a/score_b` from `scoreBefore` or 0); one `Shot` per shot (`player` = id or `"?"` when `p` is null, `group=g`, `time_sec=t`, `is_serve=s`, `detail=d`, `zone=z`, `order` = 1-based index); `set_scores` from `games`.
- [ ] **Step 1: Failing tests:** `test_to_match_players_and_rallies` (ids, rally count, winners mapped), `test_shot_fields` (detail/zone carried), `test_static_build_unchanged` (run `pro_profiles.build.build` on the existing fixture dir into tmp and compare to the fixture's expected output, as `test_build.py` does — reuse its helper).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run library and pro_profiles tests → PASS. **Step 5:** Snapshot.

### Task 3: The six insights

**Files:**
- Create: `tools/library/insights.py`, `tools/library/tests/test_insights.py`

**Interfaces:**
- Consumes: `list[Match]` from Task 2.
- Produces `player_insights(matches: list[Match], player: str) -> Insights` (a dict, JSON-ready, all percentages 0–100 rounded to 1 decimal, `null` under minimums):

```text
Insights = {
  phaseMix: { start: Mix, mid: Mix, late: Mix },        # shot order 1–4, 5–12, 13+ within the rally; Mix = { group: share } over SHOWN_GROUPS, + "shots": n
  replies:  { <opponentGroup>: Mix },                    # player's next shot after each opponent group
  zones:    { "<depth>-<side>": share, ..., "shots": n },  # six zones
  tempo:    { secPerShot: float|null, rallyShots: float|null },   # mean gap before the player's shots (same rally); mean rally length
  bands:    [ { band, label, rallies, winRate } ],        # reuse pro_profiles.stats.BANDS; score-read rallies only
  serve:    { serves, shortShare, pointsWonShort, pointsWonLong },  # first shot of rallies served by the player whose d is short/long service
  smashWins:{ smashes, winShare }                         # player's smashes that are the last or second-to-last shot of a rally the player won / player's smashes; score-read rallies only
}
```
  Also `rank_insight(all: dict[str, Insights], player: str, path: tuple[str, ...]) -> pro_profiles.stats.Ranked | None` (ranks a scalar at `path` among players with a non-null value; `None` when fewer than `MIN_COMPARED` such players), and constants `MIN_SHARE_SHOTS = 50`, `MIN_COMPARED = 10`, `PHASES = (("start",1,4),("mid",5,12),("late",13,None))`.
  Shots with `player == "?"` or `group is None` are excluded from shares but count for rally length and tempo gaps.
- [ ] **Step 1: Failing tests** with hand-built `Match` objects: `test_phase_mix_split` (exact shares for a 14-shot rally), `test_replies_after_smash`, `test_zones_share`, `test_tempo_gap`, `test_bands_only_read_rallies`, `test_serve_short_share`, `test_smash_wins`, `test_under_minimum_is_null` (49 shots → `null` shares, no division errors), `test_rank_needs_ten_players` (9 ranked → `None`; 10 → `Ranked`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Snapshot.

### Task 4: Findings, profile views and match insights

**Files:**
- Create: `tools/library/profiles.py`, `tools/library/match_insights.py`, `tools/library/content/insight_templates.json`
- Create: `tools/library/tests/test_profiles.py`, `tools/library/tests/test_match_insights.py`

**Interfaces:**
- Consumes: Tasks 2–3; `pro_profiles.findings` helpers (`order_findings`, `pick_clips`/`_spread_clips` pattern, `summary`, pronouns), `pro_profiles.build` helpers (`_clip_json`, `_finding_json`, `_photo_json`, `game_scores`, `_tournament_match_json`, `_match_label`) — import them, do not copy.
- Produces:
  - `build_library(matches: list[Match], players: dict, tournaments: dict, photos: dict) -> dict[str, dict]` — a map from Firestore path to document: `players/{id}`, `players/{id}/views/{filterId}`, `tournaments/{editionId}`, `library/index`. Player doc = today's profile JSON minus `views` (same keys: `id, name, event, context, summary, photo, filters`); view doc = `{ kind, shots, rallies, insights: Insights, findings: Finding[], rallyBrowser: Clip[] }`; tournament doc = today's tournament JSON; `library/index` = `{ players: PlayerIndexEntry[], editions: TournamentEdition[], matches: [{ id, editionId, round, date, players, games, youtubeId }] }`. Only published matches are passed in.
  - Profile findings: for each insight scalar ranked by `rank_insight`, top/bottom `EDGE` (from `pro_profiles.findings`) → style finding; for win-rate scalars top → strength, lowest ≥ 3 points below typical → weakness (same rule as `findings._candidates`). Wording from `insight_templates.json` (claim, comparison, figure keys per insight, `{He}`/`{his}` pronoun placeholders as in `templates.json`). Clips via the same picking rules. No findings and `summary: null` when `rank_insight` returns `None` (fewer than 10 ranked players).
  - `match_insights(doc: dict, usual: dict[str, Insights]) -> dict` in `match_insights.py` — `{ A: { insights, findings }, B: {...} }` where `insights = player_insights([to_match(doc)], pid)` and findings compare the match value with the player's usual (all their other published matches): include a finding when a share differs by ≥ 5 points (rate ≥ 10 points), at most 4 per player, sentence like "Smashed on 20% of shots after the first four, vs 14% in his other matches." When the player has no other published match, findings are `[]`.
- [ ] **Step 1: Failing tests:** `test_paths` (expected path set for 2 matches, 3 players, 1 edition), `test_no_comparison_under_ten` (no findings, `summary None`, `context.comparedWith == 0`), `test_findings_with_twelve_players` (synthetic: one player with the highest late-phase smash share gets a style finding with the template's text), `test_index_only_published_input`, `test_match_insights_vs_usual` (a 6-point gap → one finding; 4-point → none), `test_match_insights_no_history` (`[]`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Snapshot.

### Task 5: Store, publish and security rules

**Files:**
- Create: `tools/library/store.py`, `tools/library/publish.py`, `tools/library/set_admin.py`, `tools/library/requirements.txt` (`firebase-admin`, `yt-dlp`; pin versions)
- Create: `firestore.rules`, `firebase.json` (rules path only)
- Create: `tools/library/tests/test_publish.py`
- Modify: `data-flow.md` (new section "7. Match library (Firestore)": every document shape from Tasks 1 and 4, the rules, the commands), `.github/workflows/ci.yml` (run `tools/library/tests`)

**Interfaces:**
- Produces:
  - `Store` protocol in `store.py`: `get(path) -> dict | None`, `set(path, data) -> None`, `delete(path) -> None`, `list(collection, where: tuple[str, str, object] | None = None) -> list[dict]`. `MemoryStore` (dict-backed, for tests) and `FirestoreStore` (firebase-admin; `set` replaces; deletes stale `players/*/views/*` docs not in the new build).
  - `publish(store, match_id) -> list[str]`, `unpublish(store, match_id) -> list[str]`, `recompute(store) -> list[str]` in `publish.py` (returns changed paths). `publish` refuses (`PublishError`) when the match doesn't exist or `attributed` is False. Both set `status`, then `recompute`: load all `published` matches → `to_match` → `build_library` → write all docs, delete docs no longer produced, and write each published match's `insights` via `match_insights`. CLI: `python -m library.publish {publish|unpublish|recompute} [match_id]`.
  - `set_admin.py <uid>` sets custom claim `{admin: true}`.
  - `firestore.rules`: keep the existing `users/{uid}/videos/{videoId}` owner rules (copy the deployed rules from the Firebase console first — James provides them or `firebase firestore:rules:get`); add: `matches/{id}` read if signed in and (`resource.data.status == "published"` or `request.auth.token.admin == true`); `players/**`, `tournaments/{id}`, `library/{id}` read if signed in; all library writes `false`.
- [ ] **Step 1: Failing tests** (MemoryStore): `test_publish_unattributed_refused`, `test_publish_writes_profiles_and_insights`, `test_unpublish_removes_from_profiles` (player with no remaining matches disappears from `library/index` and their docs are deleted), `test_recompute_idempotent` (second run returns `[]`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Write `firestore.rules`. Deployment is James's step (`firebase deploy --only firestore:rules`), listed in the Gate 2 message; do not deploy.
- [ ] **Step 6:** Snapshot.

### Task 6: Ingest command

**Files:**
- Create: `tools/library/ingest.py`, `tools/library/runners.py`, `tools/library/tests/test_ingest.py`

**Interfaces:**
- Consumes: `fullmatch.run.analyze_full_match(video, fps, analyze_chunks=..., internal=True, on_merged=...)`, `apply_segmentation`, `apply_scoreboard`, `product_result`; Task 1 `match_doc`; Task 5 `Store`; for ShuttleSet accuracy, `worker/train/eval_shuttleset.py: _labels`, `_score_full_match` (import, do not copy).
- Produces:
  - `ChunkRunner = Callable[[list[tuple[int, bytes]]], list[dict | BaseException]]`. `modal_runner(max_containers: int = 50) -> ChunkRunner` uses `modal.Cls.from_name("badminton-ai-worker", "BadmintonWorker")().analyze_chunk.starmap(jobs, return_exceptions=True)`. `merged_runner(path)` loads a saved merged internal result (eval cache format) instead of analysing.
  - `ingest(url_or_file: str, meta: MatchMeta, store: Store, *, runner: str = "modal", force: bool = False, keep_video: bool = False, shuttleset: str | None = None, downloader=download_720p) -> dict` — returns `{ matchId, status: "skipped"|"stored", timings, warnings, accuracy }`. Steps, each timed into `timings`: download (yt-dlp `bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]` into a temp dir), analyse, segment, scoreboard, (accuracy when `shuttleset` names a ShuttleSet match), store. Video deleted in `finally` unless `keep_video`. Existing match id → `skipped` unless `force`; with `force` the previous `status` is kept, and if it was published `recompute` runs and changed paths are printed. Match id = `f"{editionId}-{slug(A)}-{slug(B)}"`.
  - Batch: `python -m library.ingest --batch <file.json>` — list of `{url, meta, shuttleset}`; resumable (skips stored ids); one failure is reported and the batch continues.
  - CLI single: `python -m library.ingest <url> --players "<winner>" "<loser>" --near-first <winner|loser> --tournament <editionId> --round <round> --date <YYYY-MM-DD> [--runner modal|local|merged:<path>] [--force] [--shuttleset <match>]`.
- [ ] **Step 1: Failing tests** (fake downloader writing a tiny file, fake runner returning a canned product result, MemoryStore): `test_ingest_stores_unpublished`, `test_ingest_skip_existing`, `test_force_keeps_published_and_recomputes`, `test_video_deleted_on_failure` (runner raises → file gone, error re-raised), `test_batch_continues_after_failure`, `test_timings_recorded`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Snapshot.

### Task 7: Local runner and M5 Pro timing

**Files:**
- Modify: `tools/library/runners.py` (add `local_runner(device: str = "mps")`)
- Create: `tools/library/time_local.py`, `tools/library/README.md` (setup: venv from `worker/requirements.txt`, weights via `modal volume get badminton-models <file> ~/.cache/shuttleye-models/`, credentials env var, every command)

**Interfaces:**
- Produces: `local_runner(device)` → `ChunkRunner` that builds `inference.BadmintonInference` once from `~/.cache/shuttleye-models` and calls `fullmatch.run.analyze_chunk_clip` per job, sequentially; falls back to CPU for any model that fails on MPS and logs which. `python -m library.time_local <video> [--seconds 60]` cuts one chunk with `fullmatch.chunks.cut_exact`, runs it locally and on Modal, prints local seconds, the estimate for a 50-minute match (`× chunks`), and the hit-frame agreement between local and Modal (share of Modal hits with a local hit within 3 frames).
- [ ] **Step 1:** Implement; unit-test only the estimate arithmetic (`test_estimate_full_match`).
- [ ] **Step 2:** Run on James's laptop (he runs it, or the controller with his OK): record local seconds, estimate and agreement in the ledger and the README. If agreement < 95%, `--runner local` prints a warning that results differ from Modal.
- [ ] **Step 3:** Snapshot.

### Task 8: Frontend data layer

**Files:**
- Create: `frontend/badminton-ai/src/features/library/types.ts`, `libraryData.ts`, `hooks/useLibraryDoc.ts`
- Modify: `frontend/badminton-ai/src/features/pros/types.ts` (export the shared `Clip`, `Finding` types for reuse only)

**Interfaces:**
- Produces: TS types mirroring Task 1/4 shapes exactly (`MatchDoc`, `RallyDoc`, `ShotDoc`, `Insights`, `MatchInsights`, `LibraryIndex`, `LibraryPlayer`, `LibraryView`), and `fetchMatch(id)`, `fetchLibraryIndex()`, `fetchLibraryPlayer(id)`, `fetchLibraryView(playerId, filterId)`, `fetchUnpublishedMatches()` (admin only; query `status == "unpublished"`), each returning `Promise<Result<T, LibraryError>>` with `LibraryError = {kind: "not-found"} | {kind: "permission"} | {kind: "network"; message}`, using `db` from `src/lib/firebase.ts` (`getDoc`, `getDocs`, `query`, `where`). `useLibraryDoc` mirrors `useProData` (stale responses ignored).
- [ ] **Step 1:** Implement. **Step 2:** `npm run lint && npm run build` → pass. **Step 3:** Snapshot.

### Task 9: Match page

**Files:**
- Create: `tools/library/seed_dev.py` (writes the Task 1 fixture as one unpublished match for local page work)
- Create: `frontend/badminton-ai/src/pages/MatchPage.tsx`; components in `src/features/library/components/`: `MatchHeader.tsx`, `YouTubePlayer.tsx`, `RallyList.tsx`, `RallyLanes.tsx`, `MatchInsights.tsx`, `shotColors.ts`
- Modify: `frontend/badminton-ai/src/App.tsx` (route `/matches/:matchId` inside the signed-in routes)

**Interfaces:**
- Layout and content follow the accepted mockup `.superpowers/brainstorm/10475-1795634126/content/match-page.html`:
  - header: winner d. loser (names link to `/library/players/:id`), tournament/round crumb, game scores, rallies, avg shots
  - YouTube player (IFrame API loaded once; `seekTo(sec)` exposed by ref; start ~1 s before the target) with `RallyList` beside it (≥ 900 px) or below (phone): rally n, score before, winner dot, length bar, filters long (13+) / lost points (per selected player) / game
  - `RallyLanes`: two lanes, shots placed by `t` relative to rally start, chip coloured by group from `shotColors.ts` (one map shared with the shot-log colours already in the analysis feature if one exists), click seeks; an end line: "<winner> won the rally" (or "Score not read" when `winner` null)
  - `MatchInsights`: the six cards for A and B from `doc.insights`, each finding sentence; score-dependent cards show "Shown only for matches whose score we can read." when `null`.
  - Unpublished match viewed by admin: a banner "Unpublished — only you can see this".
- [ ] **Step 1:** Implement. **Step 2:** `npm run lint && npm run build`. **Step 3:** With one match ingested (Task 12 dry run or a fixture doc written by `MemoryStore` → a dev seeding script `tools/library/seed_dev.py` that writes one fixture match to Firestore as unpublished), check in the browser at 1280 px and 390 px, both themes: rally click seeks, shot click seeks, filters work. **Step 4:** Snapshot.

### Task 10: Match list and library profiles

**Files:**
- Create: `frontend/badminton-ai/src/pages/MatchesPage.tsx`, `LibraryPlayerPage.tsx`; `src/features/library/components/InsightCards.tsx` (shared by match and profile pages; Task 9's `MatchInsights` uses it)
- Modify: `App.tsx` (routes `/matches`, `/library/players/:playerId`), `src/components/Sidebar.tsx` (add "Matches")

**Interfaces:**
- `MatchesPage`: from `library/index` — search box (player name), filters tournament and year, list rows `winner d. loser · tournament round · year · games`; admin sees an "Unpublished" section from `fetchUnpublishedMatches()`.
- `LibraryPlayerPage`: same header and filter picker as `PlayerProfilePage` (reuse `ProfileHeader`, filter UI), body = `InsightCards` for the selected view + findings with clips (reuse `FindingsPanel`/`WatchPanel` where props fit) + the player's matches linking to `/matches/:id`. When `context.comparedWith == 0`: note "Comparisons with other pros appear once 10 players have enough matches."
- `/players` pages are not changed (switch happens after the checkpoint).
- [ ] **Step 1:** Implement. **Step 2:** lint + build. **Step 3:** Browser check as in Task 9, including a 1-match player (Review Focus 5). **Step 4:** Snapshot.

### Task 11: Checkpoint batch file

**Files:**
- Create: `tools/library/batches/checkpoint.json` (5 entries; no secrets): Axelsen v Christie (QF), Axelsen v Ng (F), Axelsen v Liew (QF), Ng v Lee (QF), An Se Young v Intanon (QF) — all Thailand Open 2021 (YONEX / TOYOTA editions per `tournaments.json`); `url` from `content/clip_sources.json`; names, round, date and winner from ShuttleSet `match.csv`; `nearFirst` from ShuttleSet rally-1 hitter position; `shuttleset` = the ShuttleSet match name; `runner` = `merged:~/.cache/shuttleye-eval/<match>/<latest fullmatch_*.json that is not _resegmented>` when present.
- [ ] **Step 1:** Write the file; validate with `python -m library.ingest --batch library/batches/checkpoint.json --dry-run` (prints the 5 resolved metas, no downloads). **Step 2:** Snapshot.

### Task 12: Five-match checkpoint — STOP

- [ ] **Step 1:** Present Gate 2 for Tasks 1–11 (commits, PR closing #77 and #76's command parts, #78's page parts referenced). After James says "Commit these changes", commit, push, open the PR. James deploys `firestore.rules` and runs `set_admin.py` for his uid.
- [ ] **Step 2:** Run the batch: `python -m library.ingest --batch library/batches/checkpoint.json`. Then `python -m library.publish publish <id>` for each stored match whose `accuracy` is within the gate (hit F1 ≥ 85, side ≥ 95, 6-type ≥ 83, i.e. #81's ShuttleSet numbers minus 5).
- [ ] **Step 3:** Report to James: per match — rallies, scores read, accuracy, warnings, GPU time/cost; links to the 5 match pages and the affected profiles; what profiles show without comparisons (fewer than 10 ranked players at this size).
- [ ] **Step 4: STOP.** Do not run the other 38 matches, switch the pro pages or delete static files. Those wait for James's decision.

## After the checkpoint (not in this plan)

The remaining 38 re-runs (Modal/laptop split from Task 7's numbers), scoreboard coverage for older broadcast graphics (matches without a read score cannot be published), the switch of `/players` and `/tournaments` to Firestore, and removal of the static singles files.
