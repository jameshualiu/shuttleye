# Pro player profiles and tournament browsing: design

Status: draft for approval · 2026-11-17

## Why

Casual badminton players want to get better by learning from pros, but match footage on its own doesn't tell them what to look for. ShuttlEye will give each top singles player a profile that says, in plain language, what is distinctive about how they play, backs every claim with numbers compared against other pros, and lets you watch the rallies that show it.

This also gives ShuttlEye something competitors don't have. Most badminton AI apps analyse your own footage (goSmash, SmashAI, BadmintonPeak and others). A browsable library of pro player profiles built from labelled match data is a different product.

It must be **legal** and **small**: no downloading or hosting of broadcast video, no new infrastructure, and no ML pipeline in the loop.

## Goals

1. A **profile page for each pro** in the dataset, showing what stands out about them, their shot choice, and how rally length changes their results, all compared with other pros.
2. **Every claim opens the rallies behind it**, played from BWF's own YouTube video at the right moment.
3. **Browse by tournament**: a list of tournaments, and a page per tournament edition showing its matches and the players in it, with links into profiles filtered to that tournament.
4. A **player list** to find profiles.
5. Pages are **public** (no sign-in), so casual players can find them.

## Non-goals (v1)

- Adding matches beyond the existing datasets. New tournaments need a legal data source and better pipeline accuracy (see Future work).
- Doubles. The data is singles only.
- Running our CV/ML pipeline on pro footage.
- User features on profiles: favourites, comments, comparisons between two chosen players.
- Editing data in the app. The data is generated offline.

## Anti-goals (would make this a failure even if it works)

- **Showing a stat without its sample size**, or presenting numbers from a handful of shots as meaningful.
- **Invented or wrong claims.** Every number on a page must come from the data. Earlier mockups made up a "41% drops" figure that the real data contradicted; that must not happen.
- **Hosting or downloading BWF footage.**
- **A dense stats dump.** A casual player should get the point from the first screen.

## Data source

- **ShuttleSet** (KDD 2023) and **ShuttleSet22** (IJCAI 2023), from the CoachAI-Projects repo (`github.com/wywyWang/CoachAI-Projects`). Hand-labelled, stroke-level data from BWF World Tour singles matches.
- Combined and de-duplicated: **94 matches, 31 tournament editions (2018–2022), 43 players.** 39 players have 300+ shots, which is the comparison group. Some ShuttleSet22 matches duplicate ShuttleSet ones and must be counted once (match on the `video` folder name).
- Each shot has: rally, shot order, time in video, frame, score, hitter (A = match winner, B = loser), shot type (18 Chinese labels), backhand / around-the-head flags, hit and landing positions, player and opponent positions, and for the last shot, who won the point and why (`lose_reason`, `getpoint_player`).
- **Licence:** the repo is MIT-licensed. The dataset folders have no separate licence file, so **email the authors to confirm** the data is covered (owner: James, before launch). Credit the datasets and their papers on every page.
- **Known data issues the builder must handle:**
  - A label typo: passive drop appears as `過度切球` in the data and `過渡切球` in the README. Map both.
  - `未知球種` (unknown type): exclude from shot-type stats.
  - Player names are inconsistent across files (`SHI Yuqi` / `SHI_Yu Qi`, `An Se Young` / `AN Seyoung`). Normalise them to one ID per player through a name map.
  - Tournament names are inconsistent (sponsor prefixes, "World Tour Finals" without a year, the 2020 Finals played in January 2021). Normalise through a tournament map to a canonical name and season.
  - ShuttleSet22 has **no YouTube URLs**, and one ShuttleSet match is missing its URL too. Some ShuttleSet22 folders are named `_Trim`, which suggests its times are relative to trimmed copies of the video. See Clips.

## Approaches considered

| | Approach | Trade-offs | Decision |
|---|---|---|---|
| 1 | **Profiles computed from ShuttleSet / ShuttleSet22, shown in the existing web app** | Legal, accurate (human labels), no GPU, small. Limited to 43 players, singles, 2018–2022. | **Chosen** |
| 2 | Run our pipeline on new broadcast clips | Unlimited players and current matches, but needs YouTube downloads (against YouTube's terms), shot types are ~54% accurate and hitters ~81% (ShuttleSet eval, #61), and it costs GPU time. | Rejected for v1 |
| 3 | Start with 1, feed the pipeline in later | The long-term route if a licensed footage or data source appears and accuracy improves. | Future work |

The earlier idea of a Chrome extension that records YouTube rallies was dropped. It was legally risky (the Chrome Web Store rejects YouTube download tools) and bigger than wanted.

## What the pages show

### Player profile (`/players/:playerId`)

Design reference: the approved mockup `profile-layout-v9b.html` (kept in `.superpowers/brainstorm/`). The layout follows patterns from FotMob and Sofascore and the research in `docs/superpowers/research/2026-11-17-sports-dataviz-research.md`.

**Header (on the page background, not in a panel):**
- Photo (see Photos), name, one context line: event (men's or women's singles), match count, year range, and how many pros they're compared with.
- A one-sentence **summary** generated from the findings (see Findings).
- A **match filter** dropdown: "All N matches", each tournament they played, or a single match. **(My call.)** Filtered views follow these rules, because one match has too few shots to rank fairly:
  - **"All matches"** is the full profile: ranks, findings, summary, Strength/Weakness tags.
  - **A tournament or match filter** shows that subset's **raw numbers with sample sizes**, next to the **typical pro's all-match value** for reference. No ranks, findings, summary or tags. A note says "Rankings and findings use all matches."
  - The Watch panel in a filtered view lists that subset's rallies. In a filtered view it's a rally browser, not a findings view.
  - Thresholds still apply. Where a subset is below them, the row shows its raw count and "Too few to compare".

**Panels, on a 12-column grid at up to 1600px wide:**

| Panel | Width (desktop) | Content |
|---|---|---|
| What stands out | 4 columns | Up to 4 findings, each a selectable row: a plain-English claim, the key number, and the comparison ("A typical pro: 18.9%" / "Better than 37 of 38 pros"). Win-rate findings carry a Strength or Weakness tag; style findings carry no tag. The first finding is selected on load. |
| Watch | 5 columns | Title = the selected finding. An embedded BWF YouTube player starting at an example rally, the match and score under it, previous/next through up to 5 example rallies, and a "Try this" tip for that finding. |
| Rallies won by length | 3 columns | Three bands: 4 shots or fewer, 5 to 8, 9 or more (borrowed from ATP rally analysis). Each shows the player's win rate and a typical pro's as paired bars, plus the rally count. |
| Shot choice | 12 columns | Each grouped shot type: share of their shots, a bar filled to their rank among pros, and the rank ("1st of 39"). Two columns of rows. Footnote: a longer bar means they play it more often; it's about style, not skill. |

Below 1180px the Watch panel moves to the top at full width and the others pair up beneath it. Below 760px everything is one column.

**Rules every number follows (from the research):**
- It is compared with other pros, as a rank, a typical-pro value or both. The "typical pro" is the **median** of the comparison group.
- Its sample size is visible (panel subtitles state it).
- A stat built on too few events is not shown or ranked. Thresholds: a player needs **300+ shots** to be ranked in shot choice, and a rally-length band needs **30+ rallies** for that player. Below the threshold the row shows "Not enough rallies" instead of a number.
- No radar charts, no plain heatmaps.

### Shot-type grouping

The 18 labels are grouped into 8 types for display: **Net** (net shot, return net, cross-court net), **Lift** (lob, defensive lob), **Smash** (smash, wrist smash), **Drop** (drop, passive drop), **Clear**, **Drive** (drive, driven flight, back-court drive, defensive drive), **Push**, **Net kill** (rush). Serves are excluded from shot choice. Net kill is too rare (~1.5%) to show in the shot-choice panel by default.

### Stat definitions (these produce the pinned Axelsen numbers)

The mockup numbers came from a throwaway analysis script. These definitions reproduce them, and the build script must use them:
- **De-duplication:** when a match folder appears in both datasets, keep the **ShuttleSet** copy.
- **Players:** `A` is the match winner and `B` the loser, per `match.csv`. Each player has a sex/event field (men's or women's singles) in the name map, used for pronouns and the player list.
- **Shot share:** numerator = the player's shots of a grouped type. Denominator = **all the player's shots in the 8 grouped types**, net kill included. Serves (`發短球`, `發長球`) and unknown (`未知球種`) are excluded from both.
- **Rally length** = number of rows in the rally, **serve included**. Bands: ≤4, 5–8, ≥9.
- **Rally winner** = `getpoint_player` on the rally's last row. A player's band win rate = rallies won ÷ rallies played in that band.
- **Rallies with no recorded winner are excluded from rally-band counts, win rates and game scores.** There are 267 of them, mostly single unlabelled rows (`未知球種`), not real rallies. Their shots still count in shot shares. (Corrected 2026-11-18: counting them as losses had produced a false short-rally weakness for Axelsen.)
- **Comparison group:** players with **300+ grouped shots**, men and women pooled (39 players). Ranks run **1 to 39, the player included** ("1st of 39"). "Better than N of 38 pros" counts the others below them.
- **Typical pro** = the **median over the comparison group, the player included**. For rally bands, the group is players with **30+ rallies in that band**.
- With these definitions, Axelsen comes out at: net 35.6%, lift 27.7% (1st), smash 15.6% (5th), push 6.4%, drop 5.0% (38th), drive 4.7%, clear 3.8% (36th), from 7,080 grouped shots. Rally bands: 349 / 344 / 695 rallies, won 56% / 60% / 58%; typical 50% / 51% / 49%. Snapshot-test these numbers.

### Findings

Generated, not hand-written, so every profile works the same way:
1. Compute candidate findings: each shot-type share, and each rally-band win rate, for players who clear the thresholds.
2. **(My call.)** A candidate qualifies when it ranks in the **top 4 or bottom 4** of the comparison group for that measure. Shot-type findings are **style** (no tag). Rally-band findings in the top 4 are a **Strength**.
3. **Weakness rule:** a player's **lowest rally-band win rate, if it's at least 3 percentage points below the typical pro's**, is always a candidate tagged Weakness, even when it isn't bottom 4. A gap under 3 points isn't a weakness (it's noise; e.g. 50% vs 51%). (Amended 2026-11-18.) Its comparison line states the gap ("A typical pro: 50%"), not a rank, so it never claims more than the data shows. A player who is above typical in every band has no Weakness (Axelsen, after the 2026-11-18 correction).
4. Order candidates by **distance of their percentile from 50**. Take **at most 4**, always keeping the Weakness if there is one.
5. **Wording must not overstate.** "Almost never" is used only when the player's share is under half the typical pro's. Otherwise a bottom-4 shot finding says "{He} {verb_s} less than most pros". (Amended 2026-11-18.)
6. Each finding type has a **claim template** ("He lifts more than any other pro", "He almost never drops", "Long rallies go his way", "Short rallies are where he loses"), with pronouns from the player's event (men's / women's singles).
7. The header summary joins the top two or three findings into one sentence from templates.
8. A player with no qualifying findings gets the line "Nothing stands far out from other pros in this data", and the page still shows the other panels.

**"Try this" tips:** one hand-written tip per finding type (about 16 short tips in total), written for casual players and focused on tactics, not power. They are stored in a content file, not in code. James reviews the wording before launch.

### Example rallies (clips)

- For a finding, pick up to 5 rallies that show it: for a shot-type finding, rallies where the player plays that shot and wins the point; for a rally-band finding, rallies of that length the player won (or lost, for a Weakness).
- Prefer variety: different matches first.
- A clip plays BWF's YouTube video in the **standard YouTube embed** (no downloading), starting a couple of seconds before the rally's first shot time and ending after its last.
- **Only matches with a known YouTube URL can have clips.** **(Decided by James.)** v1 launches with clips for the **43 matches that have URLs**, all from ShuttleSet. The other 51 get clips in a **follow-up task**, not in v1: 50 ShuttleSet22 matches from 2022, plus one 2020 ShuttleSet match whose URL is missing.
  - The build reads a hand-maintained **clip-source file**: per match, a YouTube URL plus a time offset in seconds. It starts with the 43 ShuttleSet URLs at offset 0.
  - A match with no entry offers no clips. A finding with no playable rallies shows "No clips available for these matches yet".
  - The follow-up adds the missing entries. The `_Trim` folders suggest their times are relative to trimmed copies of the video, so each needs an offset.
- **Timing check (builder, before launch):** spot-check 3 rallies in at least 5 ShuttleSet matches against the YouTube video. If a match is off by a constant amount, record the offset in the clip-source file. If timing is unreliable across ShuttleSet generally, stop and raise it with James before shipping clips.

### Tournaments

- **Tournament list (`/tournaments`):** editions grouped by season, newest first, each showing the name, season and how many matches the data covers. It must be clear that the data covers selected matches, mostly later rounds, not whole tournaments.
- **Tournament page (`/tournaments/:editionId`):** the matches in the data (round, players, score), and the players who appear, each linking to their profile pre-filtered to that tournament. No per-tournament rankings, because the samples are too small (1–8 matches per edition).
- No mockup exists for these two pages. They reuse the profile's panel style, header pattern and type scale.

### Player list (`/players`)

All 43 players, split into men's and women's singles, with photo, name and match count. A search box filters by name. Players under the 300-shot threshold are listed and their profiles show what data exists, but they aren't ranked.

### Navigation

Add "Players" and "Tournaments" to the public nav (landing page header) and the signed-in app navbar.

## Photos

- Source: **Wikimedia Commons**, with free licences (CC BY, CC BY-SA). Use only photos whose licence allows reuse with credit. A spot check found free photos for the first 5 players checked (Axelsen, Momota, An Se Young, Chou Tien Chen, Ginting). Coverage for all 43 is unknown.
- Each photo is stored with its source URL, author, licence and a **focus point** (where the face is), so it can be cropped to a square headshot. Show the credit under the photo ("Photo: Fauziananta, CC BY 4.0").
- No free photo: show the player's **initials** in a neutral tile. Never use BWF, Getty or press photos.
- **Process (decided by James):**
  1. A script fetches candidate photos only under **CC BY, CC BY-SA, CC0 or public domain**, with author, licence and source URL. It must be slow and polite, because Wikimedia rate-limits API calls.
  2. It produces a **contact sheet** for review.
  3. **James approves or rejects each photo and adjusts its crop point.** Approvals are saved to a file the build reads.
  4. Players without an approved photo show initials.
- Photos **do not block launch**.

## Architecture (my calls, open to change)

- **Offline build script** (Python, outside the worker runtime path, e.g. `tools/pro-profiles/`) that:
  1. downloads or reads the ShuttleSet and ShuttleSet22 CSVs,
  2. applies the name, tournament and shot-type maps,
  3. de-duplicates matches,
  4. computes per-player stats, the comparison group, ranks, medians, findings and example rallies, for "all matches" and for each tournament and match filter,
  5. writes **static JSON files**: a player index, one file per player, a tournament index, one file per tournament edition.
- The **frontend reads the JSON as static files** (served with the SPA, or from object storage). No backend or Firestore changes. The data changes only when the script is re-run.
- The script has **unit tests** for the tricky parts: name normalisation, de-duplication, label mapping, rally-band and win attribution, rank and median, thresholds, and finding selection. It also has a snapshot test that pins Axelsen's known numbers: lift 27.7% (1st of 39), drop 5.0% (38th of 39), clear 3.8%, smash 15.6%, wins 41% / 60% / 58% across the three bands.
- Per CLAUDE.md, **document the new JSON contract in `data-flow.md`**. Producer: the build script. Consumer: the frontend types.
- The frontend uses the existing stack: React, Tailwind v4, the neutral `theme-ai-saas` tokens and Plus Jakarta Sans. New pages live under a new feature folder (e.g. `src/features/pros/`).

## Accessibility and quality bar

- Text contrast at least 4.5:1; focus rings on every control; findings are real buttons with a pressed state; tap targets at least 44px on touch.
- Information never depends on colour alone (Strength/Weakness are words, not just colours).
- Charts have text equivalents. The numbers are printed next to every bar.
- Respect reduced motion. No scroll-triggered animation.
- Works at 390, 768, 1024, 1440 and 1920 wide.

## Attribution

Every pro page footer: "Shot data from ShuttleSet and ShuttleSet22 by the CoachAI team (Wang et al., KDD 2023; IJCAI 2023), labelled by hand from BWF World Tour matches. Clips play from BWF's YouTube channel." Photo credits sit with each photo.

## Open items for James

1. **Confirm the ShuttleSet data licence** with the authors before launch.
2. **Review the ~16 "Try this" tips** once drafted.
3. **Approve player photos** from the contact sheet. Not launch-blocking.

## Left to the builder

- File layout, JSON shapes and component structure, within the constraints above.
- Exact wording of claim and summary templates (following the voice in the mockups).
- How the match filter is presented when a player has many matches.
- Where the static JSON is hosted (bundled with the SPA, or in object storage).

## Future work (not v1)

- **New tournaments.** Needs a legal source (a data or footage licence from BWF or a data partner, not investigated yet) and better pipeline accuracy, or machine-made stats clearly marked as estimates. Processing would be a scheduled batch job, not constant checking.
- Court maps of where shots are hit from and land, using the homography data, inside a finding's panel.
- Single-rally story view, player-vs-player comparison, doubles.
