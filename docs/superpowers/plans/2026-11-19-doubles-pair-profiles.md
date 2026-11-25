# Doubles Pair Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Signed-in pair profile pages for the 46 DShuttleNet doubles pairs, led by serve and receive, plus a pair list and doubles matches on the tournament pages.

**Architecture:** New `doubles_*` modules in the existing stdlib-only `tools/pro_profiles/` script read a local DShuttleNet download, compute every number, finding and summary, and write static JSON to `frontend/badminton-ai/public/pro-data/doubles/` (CC BY-NC-SA, separate from the MIT-licensed singles output). The React app only renders that JSON.

**Tech Stack:** Python 3.11 stdlib and pytest; React 19, TypeScript, Tailwind v4 and react-router 7 (all existing).

**Spec:** `docs/superpowers/specs/2026-11-19-doubles-pair-profiles-design.md`. It builds on the singles spec `2026-11-17-pro-player-profiles-design.md` and the singles code from PR #66.

## Global Constraints

- **Process (AGENTS.md):**
  - Work on `feature/<issue>-doubles-pair-profiles`.
  - **No commits until James says "Commit these changes" (Gate 2).**
  - Each task stages its files and records a proposed Conventional Commit message.
  - No Co-Authored-By trailers.
- **Dataset:** `DSHUTTLENET_DIR` or `--source` points at a local DShuttleNet download. Raw CSVs are never committed. The input SHA-256 checksums live in `content/doubles_checksums.json`.
- **Licence:** all doubles output goes under `public/pro-data/doubles/`, with a `LICENSE` file (CC BY-NC-SA 4.0 plus attribution). No singles file contains doubles data.
- **Doubles footer copy (exact):** "Doubles data from DShuttleNet (Kaggle, CC BY-NC-SA 4.0), labelled by professional players from BWF World Tour matches. Shared under the same licence; non-commercial use only."
- **Events:** code `1` → `MD` (Men's doubles), `2` → `WD` (Women's doubles), `3` → `XD` (Mixed doubles).
- **Thresholds:**
  - A pair is ranked with **2 or more matches**.
  - Minimums are **30 serves**, **30 returns** and **30 rallies** per stat.
  - **Typical** is the median of the event's ranked pairs, including the pair itself.
- **Findings:**
  - A candidate must be **top or bottom 2** of its event group (only **top or bottom 1 when the group has fewer than 8**) **and** at least **5 percentage points** from typical.
  - A weakness is the lowest of the serving, receiving and first-4 win rates, when it's **3 or more points below** typical.
  - At most **4** findings, with serve and receive first.
  - The summary leads with a serve or receive finding.
  - Wording rules from singles, adapted: "rarely" (singles: "almost never") only below 0.5× typical, "more than any other pair" only when strictly first, "Better than every other pair" when it beats the whole group, and no "far".
- **Definitions:**
  - attacking shot = smash, drop or push
  - rally winner = from the score change
  - receiver = the shot 2 hitter
  - `ball_up_down` and the shot-file `Win`/`Lose`/`score_team` columns are unused
- **UI:**
  - routes inside `ProtectedRoute`/`PrivateLayout`
  - semantic theme tokens only
  - the singles panel style, 12-column grid at up to 1600px
  - focus rings, 44px tap targets on new controls
  - Strength/Weakness written in words
- **No clips at launch.** The Watch panel copy is exactly: "Clips for doubles are coming. They'll be added match by match."

## Review Focus

1. **A rally with blank `score_team`:** the winner still comes from the score change, and the rally counts in win rates. Test `test_winner_from_score_change_when_score_team_blank` (Task 1).
2. **A one-match pair:** the page has raw numbers, "Not ranked: only one match in the data.", no ranks, no findings and no summary. Tests `test_one_match_pair_unranked` (Task 2) and `test_unranked_pair_json` (Task 4).
3. **The mixed group of 5:** only first or last qualifies as a finding. Test `test_small_group_uses_edge_one` (Task 3).
4. **A doubles-only tournament, or a singles-only one:** the tournament page works when either file is missing. This is a Task 6 verification step.
5. **The dataset file changes on Kaggle:** the build fails with the changed file named. Test `test_checksum_mismatch_names_file` (Task 1).

---

### Task 0: Issue, branch, docs

- [ ] **Step 1:** Create a GitHub issue titled "feat: doubles pair profiles from DShuttleNet", labels `frontend` and `feature`. The body links the spec and lists its Goals as acceptance criteria. Record the number `67`.
- [ ] **Step 2:** Create the branch.
  - If PR #66 is merged, use a new worktree from `origin/main`.
  - Otherwise, branch from `feature/64-pro-player-profiles` and target the eventual PR at `main` after #66 merges.
  - Name it `feature/67-doubles-pair-profiles`.
- [ ] **Step 3:** Copy this plan and the spec into the branch's `docs/superpowers/`, then stage them. Proposed commit: `docs: add doubles pair profiles spec and plan (#67)`.

---

### Task 1: Load DShuttleNet

**Files:**
- Create: `tools/pro_profiles/doubles_load.py`
- Create: `tools/pro_profiles/content/doubles_checksums.json` (SHA-256 of each of the 7 CSVs)
- Create: `tools/pro_profiles/content/doubles_tournaments.json`
- Create: `tools/pro_profiles/tests/test_doubles_load.py`
- Create: `tools/pro_profiles/tests/fixtures/doubles_mini/` (all 7 CSVs, 2 matches, hand-made)

**Interfaces:**
- Consumes: `load_content(name)` and `MappingError` from `load.py`. `content/tournaments.json`, for the shared editions.
- Produces (`doubles_load.py`):
  - `EVENTS = {"1": "MD", "2": "WD", "3": "XD"}`
  - `ATTACK_TYPES = frozenset({"smash", "drop", "push"})`
  - `class ChecksumError(ValueError)`
  - `@dataclass(frozen=True) DPlayer: id: str; name: str; last_name: str; gender: str; nationality: str`
  - `@dataclass(frozen=True) Pair: id: str` (kebab slug of the two last names in player-id order, with event suffix only on a clash); `event: str; players: tuple[str, str]` (player ids, sorted)
  - `@dataclass(frozen=True) DShot: num: int; player: str; type: str | None; formation: str | None; met_at: tuple[float, float] | None` (`return_x`, `return_y`)
  - `@dataclass(frozen=True) DRally: match_id: str; set_no: int; number: int; server: str; receiver: str | None; winner: str | None` (pair id); `serve_type: str | None` ("short" / "long"); `shots: tuple[DShot, ...]; lose_reason: str | None; fault_player: str | None; before: tuple[int, int]` (score before the rally, match-winner pair first)
  - `@dataclass(frozen=True) DMatch: id: str; edition_id: str; round: str; date: str; event: str; winner: str; loser: str` (pair ids); `rallies: tuple[DRally, ...]; set_scores: tuple[tuple[int, int], ...]`
  - `def verify_checksums(source_dir: Path, expected: dict[str, str]) -> None`
  - `def load_doubles(source_dir: Path, tournaments: dict) -> tuple[list[DMatch], dict[str, Pair], dict[str, DPlayer]]`
- `doubles_tournaments.json` maps each DShuttleNet `tournament_id` to an existing singles `edition_id` when the event is the same: `{"2": "korea-masters-2022", …, "10": "indonesia-open-2023", "12": "indonesia-open-2023"}`. Ids 10 and 12 both map to `indonesia-open-2023`. New editions also need `name` and `season`, in the same format as `tournaments.json`.

- [ ] **Step 1: Write failing tests:**
  - `test_winner_from_score_change_when_score_team_blank`
  - `test_receiver_is_shot_two_hitter`
  - `test_blank_serve_type_is_none_but_rally_kept`
  - `test_set_scores_use_max_scores_winner_first`
  - `test_lose_reason_trimmed`
  - `test_fault_player_only_if_on_losing_pair`
  - `test_indonesia_open_ids_merge` (two tournament ids map to one edition)
  - `test_unknown_tournament_raises` (`MappingError` naming the id)
  - `test_checksum_mismatch_names_file`
  - `test_real_counts` (skipped without `DSHUTTLENET_DIR`): 58 matches, 46 pairs, events `{"MD": 19, "WD": 16, "XD": 11}` pairs, 4,846 rallies
- [ ] **Step 2:** Run `cd tools && python -m pytest pro_profiles/tests/test_doubles_load.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Read CSVs with `utf-8-sig`. Use `rally.csv` for rally fields and `shot.csv` for shots (`player_formation` comes from `shot_merge_all.csv`, joined on `shot_id`). Order rallies by `(set, rally_num)`. Then write the checksums and tournament content files from the real download.
- [ ] **Step 4:** Run with `DSHUTTLENET_DIR` set. Expected: all PASS.
- [ ] **Step 5:** Stage. Proposed commit: `feat(tools): load DShuttleNet doubles data (#67)`.

---

### Task 2: Pair stats

**Files:**
- Create: `tools/pro_profiles/doubles_stats.py`
- Create: `tools/pro_profiles/tests/test_doubles_stats.py`
- Modify: `tools/pro_profiles/stats.py`. Add a public `rank_value(values: dict[str, float], player: str) -> Ranked` that wraps `_rank`, so it's not imported privately.

**Interfaces:**
- Consumes: Task 1's types. `Ranked` and `rank_value` from `stats.py`.
- Produces:
  - `MIN_MATCHES = 2`, `MIN_SAMPLE = 30`
  - `MEASURES` (ordered; the key is used everywhere):
    - `serve.short_share`, `serve.win_rate`, `serve.third_down`
    - `receive.attack_share`, `receive.win_rate`
    - `first4.share`, `first4.win_rate`
    - `rally.attack_share`, `rally.formation_attack`
  - plus display-only distributions:
    - `serve.placement` (`centre`, `middle`, `wide`, `back_centre`, `back_wide`)
    - `receive.mix` (shares by shot type)
    - `roles` (per partner: share of the pair's smashes and of its net shots)
    - `points.lost` (by reason) and `points.won` (`winner` / `opp_error`)
    - `mixed.serve_by` and `mixed.receive_by` (`man` / `woman` shares; XD only)
  - `@dataclass PairStats: pair: str; matches: int; values: dict[str, float | None]; samples: dict[str, int]; dists: dict[str, dict]`. `values` holds a measure key mapping to its share, or None below `MIN_SAMPLE`.
  - `def pair_stats(matches: list[DMatch], pair: Pair, players: dict) -> PairStats`
  - `def ranked_pairs(all_stats: dict[str, PairStats], pairs: dict[str, Pair], event: str) -> list[str]`
  - `def rank_measure(all_stats, pairs, pair_id, key) -> Ranked | None`: None if the pair is unranked or the value is None.
  - `def placement_zone(met_at: tuple[float, float], serve_type: str) -> str`. Uses court units of 10 cm: centre line x = 30.5. A short serve is centre if |x − 30.5| ≤ 10 and wide if within 8 of a sideline (x ≤ 8 or x ≥ 53). A long serve is back_wide if within 8 of a sideline, otherwise back_centre. Check against a histogram of the real `met_at` values and record the result in the report.

- [ ] **Step 1: Write failing tests:**
  - `test_measures_on_fixture`, with hand-computed values for each measure
  - `test_below_min_sample_is_none`
  - `test_one_match_pair_unranked` (`rank_measure` returns None)
  - `test_typical_includes_pair`
  - `test_placement_zone_boundaries`
  - `test_mixed_serve_by_gender`
  - `test_real_snapshot` for Baek / Lee (WD, 10 matches), skipped without data. Compute the values in Step 4, sanity-check them by hand against the CSV for one match, then pin them.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run with data. Pin the snapshot values and record them in the report. Expected: PASS.
- [ ] **Step 5:** Stage. Proposed commit: `feat(tools): compute doubles serve, receive and rally stats (#67)`.

---

### Task 3: Pair findings and summary

**Files:**
- Create: `tools/pro_profiles/doubles_findings.py`
- Create: `tools/pro_profiles/content/doubles_templates.json`
- Create: `tools/pro_profiles/content/doubles_tips.json` (`"_status": "draft — James to review"`)
- Create: `tools/pro_profiles/tests/test_doubles_findings.py`

**Interfaces:**
- Consumes: Task 2. `Finding` from `findings.py` (reuse the dataclass; `clips` is always `[]` here).
- Produces:
  - `EDGE = 2`, `EDGE_SMALL = 1`, `SMALL_GROUP = 8`, `MIN_GAP = 0.05`, `WEAKNESS_GAP = 0.03`
  - `def select_pair_findings(pair_id: str, all_stats, pairs) -> list[Finding]`. Keys look like `serve.short_share.top`, `receive.attack_share.bottom` and `first4.win_rate.weakness` (a win rate is only ever `.top` or `.weakness`; one weakness per pair). Order: serve and receive measures before `rally.*` when tied on percentile distance. Weakness last. At most 4.
  - `def pair_summary(pair_id, findings, pairs, players) -> str | None`. It starts with the first serve or receive finding's phrase, and names the pair by last names ("Baek and Lee …").
- Templates use `{pair}` and plural verbs ("They serve short more than any other pair"). Tips cover every reachable key.

- [ ] **Step 1: Write failing tests:**
  - `test_needs_rank_and_gap`. Top 2 but 4 points from typical gives no finding; top 2 and 6 points gives a finding.
  - `test_small_group_uses_edge_one`. In a 5-pair group, 2nd place gives no finding.
  - `test_weakness_lowest_win_rate_3_points`
  - `test_serve_receive_first_on_ties`
  - `test_wording_rules` (strictly first; every other pair; no "far")
  - `test_every_key_has_template_and_tip`
  - `test_unranked_pair_no_findings`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement and write both content files.
- [ ] **Step 4:** Run with data. Expected: PASS. Print the findings and summary for 4 real pairs (one per event, plus Baek / Lee) and include them in the report.
- [ ] **Step 5:** Stage. Proposed commit: `feat(tools): generate doubles pair findings and summaries (#67)`.

---

### Task 4: Doubles JSON build

**Files:**
- Create: `tools/pro_profiles/doubles_build.py`
- Create: `tools/pro_profiles/tests/test_doubles_build.py`
- Create: `tools/pro_profiles/content/clip_sources_doubles.json` (`{}`)
- Create (generated, committed): `frontend/badminton-ai/public/pro-data/doubles/` with `LICENSE`, `pairs/index.json`, `pairs/<id>.json`, `tournaments/index.json` and `tournaments/<edition>.json`
- Modify: `data-flow.md` (add "6. Doubles pair data (static JSON, CC BY-NC-SA)")
- Modify: `.github/workflows/ci.yml`. Add `-x doubles` to the singles `diff -r` step so the singles stale check ignores the doubles folder. The doubles fixture tests already run as part of the existing pytest step.
- Modify: `tools/pro_profiles/README.md` (doubles section: download from Kaggle, checksums, how to run it, licence)

**Interfaces:**
- Consumes: Tasks 1–3. The `game_finished` rule from `build.py` (import it).
- Produces the JSON contract (camelCase, shares 0–100 to 1 decimal place):
  - `pairs/index.json`: `{ "pairs": [{ "id", "event": "MD"|"WD"|"XD", "players": [{ "id", "name", "nationality" }, …2], "matches", "ranked" }] }`, sorted by event, then by the two names.
  - `pairs/<id>.json`:
    - top level: `{ "id", "event", "players": [{"id","name","nationality","gender"}…2], "context": { "matches", "firstYear", "lastYear", "comparedWith" }, "ranked": boolean, "summary": string|null, "filters": [{ "id", "label", "kind", "matches" }], "views": { "<filterId>": PairView } }`
    - `comparedWith` is the number of other pairs in the event's group when ranked, and 0 when unranked.
  - `PairView`: `{ "kind", "rallies", "serve": { "shortShare", "winRate", "thirdDown", "placement": { "centre", "middle", "wide", "backCentre", "backWide" }, "serves" }, "receive": { "attackShare", "winRate", "mix": { "<type>": share }, "returns" }, "first4": { "share", "winRate" }, "mixed": { "serveBy": { "man", "woman" }, "receiveBy": {…} } | null, "rest": { "attackShare", "formationAttack", "roles": [{ "playerId", "smashShare", "netShare" }…2], "pointsLost": { "<reason>": share }, "pointsWon": { "winner", "oppError" } }, "ranks": { "<measureKey>": { "rank", "of", "typical" } }, "findings": [Finding] }`
    - Each value is a number, or null below its minimum sample.
    - `ranks` and `findings` are empty in filtered views and for unranked pairs.
    - `typical` always comes from all matches.
    - Findings use the singles Finding JSON shape, with `clips: []`.
  - `tournaments/index.json`: `{ "editions": [{ "id", "name", "season", "doublesMatches" }] }`
  - `tournaments/<edition>.json`: `{ "id", "name", "season", "matches": [{ "id", "event", "round", "date", "winner": {"id","names"}, "loser": {"id","names"}, "games": [[a,b]…], "incomplete": [setIndex…] }], "pairs": [{ "id", "event", "names" }] }`
  - `LICENSE`: "CC BY-NC-SA 4.0" plus the footer attribution text and a link to the Kaggle dataset.
- CLI: `python -m pro_profiles.doubles_build --source <dir> --out ../frontend/badminton-ai/public/pro-data/doubles`. It verifies checksums first and produces deterministic output.

- [ ] **Step 1: Write failing tests:**
  - `test_unranked_pair_json`
  - `test_filtered_view_has_no_ranks_or_findings`
  - `test_typical_from_all_matches`
  - `test_doubles_tournament_games_and_incomplete`
  - `test_output_deterministic`
  - `test_license_file_written`
  - `test_no_singles_paths_written` (only under `--out`)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, update the docs and CI, then run the real build.
- [ ] **Step 4:** Run the tests with data. Expected: PASS. Check the output size with `du -sh` (expect under 2 MB). Rebuild and confirm the output is byte-identical.
- [ ] **Step 5:** Stage. Proposed commit: `feat(tools): build doubles pair and tournament JSON (#67)`.

---

### Task 5: Pair pages

**Files:**
- Modify: `frontend/badminton-ai/src/features/pros/types.ts` (add the Task 4 types, with names matching the JSON)
- Modify: `frontend/badminton-ai/src/features/pros/proData.ts`. Add `fetchPairIndex()`, `fetchPair(id)`, `fetchDoublesTournamentIndex()` and `fetchDoublesTournament(id)` under `doubles/...`, using the same not-found handling.
- Modify: `frontend/badminton-ai/src/features/pros/components/ProAttribution.tsx`. Add a `source?: "singles" | "doubles"` prop. `"doubles"` renders the exact doubles footer copy.
- Create: `frontend/badminton-ai/src/features/pros/components/ServeReceivePanel.tsx`, `RestOfRallyPanel.tsx`, `PairHeader.tsx` and `PairCard.tsx`
- Create: `frontend/badminton-ai/src/pages/PairsPage.tsx` and `PairProfilePage.tsx`
- Modify: `frontend/badminton-ai/src/App.tsx` (lazy `/pairs` and `/pairs/:pairId` inside `PrivateLayout`)
- Modify: `frontend/badminton-ai/src/components/Navbar.tsx` (a **Pairs** link between Players and Tournaments, in the same style as Sessions)

**Behaviour:**
- **Pair profile, top to bottom:**
  - Header: both players' initials, "Name / Name", and the context line "{Men's|Women's|Mixed} doubles. {n} match(es) {span}, compared with {comparedWith} other pairs.", or "…, not ranked: only one match in the data." for unranked pairs. Then the summary and the match filter, following the singles pattern.
  - **Serve & receive panel (full width, first):**
    - findings on the left, following FindingsPanel
    - "When they serve": short share, placement as five labelled shares, win rate, third shot down
    - "When they receive": attacking return share, return mix, win rate
    - "First 4 shots": share and win rate
    - mixed pairs only: "Who serves" and "Who receives"
    - every value shows a "Typical pair {x}%" comparison in the all-matches view, and its sample count
  - **Rest of the rally panel:** attacking share, formation attack share, a roles row per player (smash and net shares), points lost by reason, and points won split into winner and opponent error.
  - **Watch panel:** the exact no-clips copy.
- **Pair list:**
  - title "Pro pairs", subtitle "Doubles pairs from BWF World Tour matches, 2022 to 2025."
  - "Search pairs", matching either name with the singles normaliser
  - sections "Men's doubles", "Women's doubles", "Mixed doubles"
  - unranked cards also show "Not enough data to rank"
- **Not found:** "We don't have a profile for this pair." and a link to `/pairs`.

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `npm run lint && npm run build`. Expected: pass. The only allowed warning is the existing one in `useAnalysisData.ts`.
- [ ] **Step 3: Visual check (signed in).**
  - Screenshot Baek / Lee, one mixed pair and one unranked pair at 1440×900 and 390, plus `/pairs`.
  - Serve and receive must be above the fold at 1440×900.
  - The numbers must match the Task 4 JSON.
  - Without a signed-in browser session, check routing by reading the code and say so in the report.
- [ ] **Step 4:** Stage. Proposed commit: `feat(frontend): add doubles pair list and profile pages (#67)`.

---

### Task 6: Doubles on tournament pages

**Files:**
- Modify: `frontend/badminton-ai/src/pages/TournamentsPage.tsx` (merge the singles and doubles indexes by edition id, with counts "{n} singles · {m} doubles matches in the data")
- Modify: `frontend/badminton-ai/src/pages/TournamentPage.tsx` (load both files; not-found means "none"; add a "Doubles" section of match rows and pair cards linking to `/pairs/:id?view=t:<edition>`; "incomplete in the data" as in singles)

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `npm run lint && npm run build`. Expected: pass.
- [ ] **Step 3: Verify.**
  - Korea Masters 2022 shows both singles and doubles.
  - A doubles-only edition (2023–2025) shows only doubles, with no empty singles section.
  - A singles-only edition still renders unchanged.
  - An unknown edition still shows "We don't have this tournament."
  - Take screenshots at 1440.
- [ ] **Step 4:** Stage. Proposed commit: `feat(frontend): show doubles matches on tournament pages (#67)`.

---

### Task 7: Final verification and Gate 2

- [ ] **Step 1:** Run all pytest tests with both `SHUTTLESET_DIR` and `DSHUTTLENET_DIR` set, then `npm run lint && npm run build`.
- [ ] **Step 2:** Rebuild the singles and doubles JSON, and confirm `git status` shows no changes in `public/pro-data/`.
- [ ] **Step 3:** Confirm no raw CSVs are staged, and that no singles file contains doubles data (grep the singles output for DShuttleNet pair ids).
- [ ] **Step 4: Gate 2.** Present the commits, the draft tips for review and the threshold defaults. Wait for "Commit these changes".
