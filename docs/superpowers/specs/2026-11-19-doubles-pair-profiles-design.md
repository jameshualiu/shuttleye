# Doubles pair profiles (DShuttleNet): design

Status: draft for approval · 2026-11-19 · builds on the singles pro profiles (spec `2026-11-17-pro-player-profiles-design.md`, PR #66)

## Why

ShuttlEye's singles pro profiles stop at 2022 and cover singles only. DShuttleNet adds **58 recent doubles matches (2022–2025)**, labelled by professional players, which gives ShuttlEye more recent data and the other half of the sport.

The audience is the same: casual players learning from pros. In doubles, **serve and receive matters most**: the serve, the return and the third shot decide a large share of rallies (coaching analyses put it at 30–40% of pro rallies ending within 4 shots). So a pair profile **leads with serve and receive**.

ShuttlEye is a **non-commercial portfolio project** (James, 2026-11-18), which is what makes DShuttleNet's licence acceptable.

## Decisions made by James

- Profiles are about **pairs**, not individual doubles players.
- **Serve and receive is the lead section** of a broader page. The rest of the rally follows, in a shorter section.
- **Every pair gets a page.**
- **Doubles launches without clips.** Clips are added later.
- **Approach A:** extend the existing `tools/pro_profiles/` build script, with doubles output kept separate.

## Goals

1. A profile page for each of the **46 pairs** (`/pairs/:pairId`), led by serve and receive, then the rest of the rally.
2. A **pair list** (`/pairs`), grouped by event (men's, women's and mixed doubles), with search by either player's name.
3. Doubles matches appear on the **tournament pages** next to singles, with real game scores.
4. The same rules as singles: every number is compared with peers, sample sizes are visible, thin stats are hidden, and the wording doesn't overstate.
5. All pages are **behind sign-in**, like the singles pro pages.

## Non-goals

- Clips at launch.
- Profiles of individual doubles players, or comparing a player across partners.
- Mixing singles and doubles stats, or comparing pairs across events (for example, a mixed pair against men's pairs).
- Photos for doubles players at launch. Pairs show initials. The singles photo pipeline can be extended later.
- Commercial use. If ShuttlEye is ever monetised, this data must be dropped or relicensed.

## Anti-goals

- Inventing or overstating claims. Groups are small here, so the bar for a finding is **higher** than for singles.
- Ranking a pair on one match's worth of serves.
- Mixing CC BY-NC-SA data into the MIT-licensed singles output.

## Data source

- **DShuttleNet**, Kaggle `anonymousay58dki/dshuttlenet` (DOI 10.34740/kaggle/dsv/16097938), with its paper on arXiv as 2610.14016. The uploader is anonymous, so the dataset may change. **The build records each input file's SHA-256 checksum and fails loudly if a file changes.**
- **Licence: CC BY-NC-SA 4.0.** Derived output must be credited, used non-commercially and shared under the same licence.
- **Files:** `match`, `player`, `rally`, `set`, `shot`, `shot_merge_all` and `tournament` CSVs (35.7 MB). The raw files are **never committed**. The script reads a local download (`--doubles-source` or `DSHUTTLENET_DIR`).
- **Verified facts** (from James's download, 2026-11-19):
  - 58 matches, with event codes 1 = men's doubles (24), 2 = women's doubles (24) and 3 = mixed (10). The codes were confirmed by player gender.
  - Years: 5 matches from 2022, 25 from 2023, 21 from 2024 and 7 from 2025.
  - 46 pairs: 19 men's, 16 women's and 11 mixed. 20 pairs have 1 match, 13 have 2, and 13 have 3 or more.
  - Some players appear in more than one pair, with different partners.
  - About 83 rallies per match, so about 40 serves per pair per match.
  - Shot types: lift, net shot, smash, drive, push, short serve, drop, clear and long serve. 519 shots have a blank type, and there's no separate "rush" label.
  - `rally.serve_player` gives the server, and the receiver is the player who hits shot 2.
  - Each rally has a winner and a `lose_reason`: Net Fault, Opp Grounded within Boundaries, Out of Bounds, Failed Return, Judgment Error or Faults. Some have trailing spaces and a few are blank. `fault_player` is also present.
  - The authors derived extra columns in `shot_merge_all`: `player_formation` (Attack or Defense), `ball_up_down`, `Partner_Angle`, `mid_cover` and others.
  - Player positions and return positions use court units of about 10 cm: x runs 0–61 across the width and y runs 0–134 along the length. **The serve's `hit_x`/`hit_y` are unreliable (out of range), so don't use them.**
  - There are **no video links**.
- **Identity:** players are identified by `player_id`, never by name, because names differ in case (`Lee`/`LEE`). A pair id is the event plus the two player ids sorted, and its slug is the two last names in kebab-case. Display names come from `player.csv`.

### Column meanings (checked against the data, 2026-11-19)

- **Teams.** In `match.csv`, `win_A`/`win_B` are the match-winning pair and `lose_C`/`lose_D` the losing pair. In `rally.csv`, `current_win_score`/`current_lose_score` are the scores of the **match-winning pair / match-losing pair** after the rally, not of whoever won that rally.
- **Rally winner.** Derive it from which of the two scores went up compared with the previous rally in the set (0–0 before rally 1). This matches `score_team` (0.0 = match-winning pair scored, 1.0 = match-losing pair) on all 4,817 rallies where `score_team` is filled in, and it also covers the 29 rallies where `score_team` is blank. Don't use the `Win`/`Lose`/`score_team` columns in `shot.csv` or `shot_merge_all.csv`, because they disagree with `rally.csv`.
- **Game scores.** Each set's score is the highest `current_win_score`/`current_lose_score` reached in that set, shown winner first. The same "incomplete in the data" rule as singles applies. `set.csv` is a cross-check only: 4 of its 132 sets differ from the rally scores. `set_win = 0` means the match-winning pair won that set.
- **Server and receiver.** `rally.serve_player` is always one of the four players, and it equals the shot 1 hitter in every rally. The receiver is the shot 2 hitter. Every shot's `player` belongs to the match's four players (2 are blank). Rallies whose shot 1 has a blank type (344) are excluded from the serve mix and placement, but still count in win rates.
- **How points end.** Use `rally.lose_reason`, trimmed, not the Chinese values in `shot_merge_all`. The reason describes why the pair that lost the point lost it:
  - "Opp Grounded within Boundaries" means the shuttle landed in on the losing pair's side, so the winning pair hit a winner.
  - Net Fault, Out of Bounds, Failed Return, Judgment Error and Faults are the losing pair's errors.

  `fault_player` names someone on the losing pair in about 85% of rallies. Use it for "who" only when it belongs to the losing pair. 109 rallies have a blank reason and are left out of this breakdown only.
- **Attacking shots.** Use the shot type: smash, drop and push are attacking. Don't use `ball_up_down`. It codes smash and drop as 2 and lift as 1, but marks most clears as 0 and splits drives and net shots across all three values, so it isn't a clean up/down flag. **(My call.)**
- **Shots with a blank type** (519) count in no shot-type share. They still count toward rally length.
- **Rally length** is the number of shot rows. `rally.shot_count` is always blank.
- **Pairs.** A pair is identified by its event plus its two player ids. The same two players in different events would be two pairs; that doesn't happen in this data.

## The pair profile (`/pairs/:pairId`)

It uses the singles profile's design system (panels, type scale, the 12-column grid capped at 1600px, neutral theme tokens) and its existing components where they fit.

```
[initials][initials]  Kusumawardana / Rambitan
Men's doubles · 4 matches, 2023 to 2024 · compared with 9 other pairs      [All matches ▾]
One-sentence summary from the top findings

┌ Serve & receive ─────────────────────────────────────────────────────────┐
│ What stands out (serve/receive findings)  │  When they serve              │
│                                           │  short/long mix · placement   │
│                                           │  win rate · third shot down   │
│                                           │  When they receive            │
│                                           │  return mix · attacking return│
│                                           │  win rate                     │
│ First 4 shots: share of their rallies decided, and their win rate         │
│ Mixed only: who serves and who receives (man/woman share)                 │
└───────────────────────────────────────────────────────────────────────────┘
┌ The rest of the rally ───────────────────────────────────────────────────┐
│ Attacking share · formation (attack/defence) · who plays which shots ·   │
│ how points end                                                           │
└───────────────────────────────────────────────────────────────────────────┘
Clips for doubles are coming. They'll be added match by match.
```

### Peer groups and thresholds

These are **builder defaults**, and James can change them.
- A pair is compared only with **other pairs in the same event**.
- **Ranked pairs** have **2 or more matches**. The comparison group is the ranked pairs in that event: 10 men's, 11 women's and 5 mixed. The page states the group size ("compared with 9 other pairs").
- **One-match pairs** get a page with raw numbers and sample sizes, plus the line "Not ranked: only one match in the data." They get no ranks, findings or summary.
- **Minimum samples per stat:**
  - 30 serves for serve stats
  - 30 returns for receive stats
  - 30 rallies for win rates and first-4-shot stats

  Below these, a row shows its raw count and "Too few to compare".
- **"Typical pair"** is the median over the event's comparison group, including the pair itself.

### Serve and receive measures

All are counted from the pair's own serves and returns.
- **Serve mix:** the share of their serves that are short.
- **Serve placement:** where the receiver met the serve (`return_x`/`return_y` on the serve shot). It's split into **centre, middle and wide**, relative to the receiver's service court. Zones, checked against the data (2026-11-19): for a short serve, centre if |x − 30.5| ≤ 10, wide if x ≤ 14 or x ≥ 46, middle otherwise. Long serves are counted as back-wide (x ≤ 14 or ≥ 46) or back-centre. Serves whose return position is outside the court are ignored. On the real data, short serves come out 90% centre, 5% middle and 5% wide.
- **Serving win rate:** the share of rallies they serve that they win.
- **Third shot down:** in rallies they serve where their own third shot has a known type, the share where that shot is an **attacking shot** (smash, drop or push). `ball_up_down` isn't used.
- **Return mix:** the shares of their returns that are net shot, push, smash, lift, drive, clear or drop.
- **Attacking return:** the share of their returns that are a smash, drop or push. This stands in for "rush/attack the serve", which the data has no label for.
- **Receiving win rate:** the share of rallies they receive that they win.
- **First 4 shots:** the share of their rallies that end within 4 shots, and their win rate in those rallies.
- **Mixed only:** who serves (the man's share against the woman's) and who receives.

### The rest of the rally

- **Attacking share:** the share of the pair's non-serve shots that are attacking (smash, drop or push). Formation share also excludes serves.
- **Formation:** the share of the pair's shots hit in the authors' `player_formation` Attack state.
- **Who plays which shots:** each partner's share of the pair's smashes and of its net shots, naming the player.
- **How points end:** for rallies they lost, the split by `lose_reason`, normalised to clean labels and noting whether the fault was theirs. For rallies they won, the share won by a winner (Opp Grounded within Boundaries) against an opponent's error.

### Findings and summary

Findings use the singles mechanism: templates, a summary sentence and draft tips. The bar is stricter because the groups are small. **(My call.)**
- **A candidate qualifies** only if the pair ranks **top 2 or bottom 2** of its event's comparison group **and** sits at least **5 percentage points** from the typical pair. **In a comparison group of fewer than 8 pairs (mixed doubles, 5 ranked), only top 1 or bottom 1 qualifies.** (My call.)
- **A weakness** is the pair's win rate (serving, receiving or first-4-shot) that sits **furthest below** its typical value, provided the gap is at least **3 points**. (Amended 2026-11-19: the lowest raw win rate almost always picked serving, because serve win rates are lower for every pair, and that hid real weaknesses.)
- **At most 4 findings**, with **serve and receive first**: serve/receive findings outrank rest-of-rally findings when tied.
- **The summary** leads with a serve or receive finding.
- **Wording rules from singles carry over:**
  - "rarely" (singles says "almost never") only below half the typical rate and at 15% or less
  - "more than any other pair" only when strictly first
  - "Better than every other pair" when it beats the whole group
  - no "far" without a large gap
- **Tips** are drafted per finding key for James to review, as in singles.

### Match filter

The match filter works as in singles. "All matches" shows ranks and findings. A tournament or match selection shows raw numbers next to the typical pair's all-matches value, without ranks or findings.

## Pair list (`/pairs`)

Three sections (Men's doubles, Women's doubles, Mixed doubles), each listing pair cards with both players' initials, both names, nationalities and match count. Unranked pairs also show "Not enough data to rank". A search box matches either player's name, case- and accent-insensitively, as on the singles player list.

## Tournaments

- **List and pages:** DShuttleNet's tournaments appear in the existing tournament list and pages, normalised the same way (canonical name and season) through `content/doubles_tournaments.json`.
- **Shared editions:** two editions already exist in singles, Korea Masters 2022 and Indonesia Masters 2022. These share one page, with singles matches and a doubles section.
- **Merged duplicates:** DShuttleNet ids 10 and 12 are both "KAPAL API GROUP Indonesia Open 2023" and become one edition.
- **Separate files (my call, corrected 2026-11-19 so no file mixes licences):** doubles tournament data goes in its own files, `doubles/tournaments/index.json` and `doubles/tournaments/<edition>.json`, with the same edition ids as singles. The singles tournament files don't change. The tournament list merges both indexes. A tournament page loads the singles file and the doubles file, treating a missing one as "none", and shows whichever exist. The `t:<edition>` filter id uses the same scheme as singles.
- **Doubles matches:** listed under a "Doubles" heading, with round, both pairs and game scores from `set.csv`, winner first. Pair names link to `/pairs/:id?view=t:<edition>`.

## Navigation

The signed-in navbar gains **Pairs** between Players and Tournaments, in the same style.

## Clips

There are no clips at launch. The Watch panel shows "Clips for doubles are coming. They'll be added match by match." A separate `content/clip_sources_doubles.json` (empty at launch) uses the same format as singles, so clips can be added per match later without code changes.

## Licence and attribution

- **Output:** all doubles output goes under `public/pro-data/doubles/`, with a `LICENSE` file there stating CC BY-NC-SA 4.0 and the attribution.
- **Footer:** every doubles page shows "Doubles data from DShuttleNet (Kaggle, CC BY-NC-SA 4.0), labelled by professional players from BWF World Tour matches. Shared under the same licence; non-commercial use only."
- **Separation:** singles output stays under its current paths and its MIT/ShuttleSet attribution. No file mixes the two.

## Architecture (approach A)

**Alternatives considered:**
- (A) extend `tools/pro_profiles/` **(chosen)**
- (B) a separate `tools/doubles_profiles/` package: rejected because it duplicates the rules and templates
- (C) a generic player-or-pair model refactor: rejected because it means reworking unmerged #66 code

**New modules in `tools/pro_profiles/`:**
- `doubles_load.py`: reads DShuttleNet, verifies the checksums and normalises the data
- `doubles_stats.py`: computes the measures above
- `doubles_findings.py`: findings using the shared template machinery
- `doubles_build.py`: writes the JSON

They reuse `stats.py`'s ranking and median helpers and the existing content-file pattern.

**Content files:** `content/doubles_templates.json`, `content/doubles_tips.json`, `content/doubles_tournaments.json` (the tournament name map) and `content/clip_sources_doubles.json`.

**Output:**
- `public/pro-data/doubles/pairs/index.json` and `pairs/<id>.json`
- `public/pro-data/doubles/tournaments/index.json` and `tournaments/<edition>.json`, separate from the singles tournament files

Document all of it in `data-flow.md`.

**Frontend:**
- `src/features/pros/` gains pair types and loaders
- new pages `PairsPage` and `PairProfilePage`
- new serve-and-receive panels
- the tournament page renders the doubles list

Routes go inside `ProtectedRoute`/`PrivateLayout`.

**Tests:**
- fixtures for loading, checksums, measures, thresholds, findings and wording
- real-data tests skipped unless `DSHUTTLENET_DIR` is set
- a real-data snapshot for one well-covered pair (e.g. Baek / Lee, women's doubles, 10 matches), with numbers pinned once computed

**CI:** runs the doubles fixture tests. The real-data and stale-JSON checks for doubles run only if a `KAGGLE_KEY` secret is configured. That's optional, so without it the doubles JSON is checked locally only.

## Identity across singles and doubles

Doubles players aren't linked to singles player profiles, even when the same person has both. (My call: identities come from different datasets with different ids, and there is no reliable join.)

## Open items for James

1. Approve the threshold and finding-bar defaults above, or change them.
2. Review the drafted doubles tips.
3. Optional: add a Kaggle API key as a repo secret so CI can check the doubles JSON.

## Left to the builder

- The exact serve-placement boundaries, verified against the coordinates.
- How `ball_up_down` maps to attack.
- The JSON field names within the shapes above.
- Component reuse versus new components.
- The exact template wording, in the singles voice.

## Future work

- Doubles clips, by finding BWF YouTube videos per match and checking offsets.
- Doubles player photos.
- Per-player views across partners.
- Court maps of serve placement.
