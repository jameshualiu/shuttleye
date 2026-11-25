# Analyzer reliability on BWF broadcasts — design

Issues: #72 (rally splitting), #73 (full-match eval), #74 (shot-type loss), #75 (alternating sides). Builds on the merged #61 eval (`worker/train/eval_scoring.py`, `worker/train/eval_shuttleset.py`).

## Why

Shuttleye is becoming a library of pre-analysed BWF singles matches with player profiles that grow as matches are added. Everything downstream (profiles, match pages) is only as good as the analyzer, and today it is not good enough to publish from:

- It has no idea of a rally or a serve. A full broadcast is treated as one stream of hits, so it can't count rallies, and replays, close-ups and breaks feed every model.
- On pre-cut rallies (#61 baseline, Axelsen v Christie, set 1): hits F1 91.0%, hitter side 81.2%, shot type 54.4% on 6 classes.
- A full broadcast (45–80 min) would most likely hit the worker's 20-minute timeout.

Analysis runs offline (videos downloaded on James's machine, analysed on Modal, then deleted), so no user waits. Accuracy comes first; every stage is timed because speed decides how fast the library grows and is part of the portfolio story.

## Prior art we build on

James asked not to rebuild what others have solved. Research (2026-11-24) found one system that solves almost exactly this problem, plus a few targeted improvements.

**COURTSIDE** ([jayclim/BadmintonAI](https://github.com/jayclim/BadmintonAI), MIT, live at badminton.jaydenclim.com). BWF broadcasts in, per-shot data out, ShuttleSet as the answer key, YouTube embeds, same models as ours (YOLO11 pose, TrackNetV3, BST). Its self-reported results over 4 matches, one held out from all tuning:

| Stage | COURTSIDE | Ours today |
|---|---|---|
| Rally segmentation | F1 94.0–97.6 | none |
| Hit detection | F1 86.8–88.8 | F1 91.0 |
| Hitter attribution | 95–97% | 81.2% |
| Shot type (10 classes) | 75.7–88.3% | 54.4% (6 classes) |
| Score from the scoreboard | exact final scores, 4/4 matches | none |

What we take from it (methods ported into our pipeline with MIT attribution; their `HANDOFF.md` records what failed):

- **Rally segmentation** (`segment.py`): play-camera runs are frames where *both* players are tracked inside the court, with their box heights inside a band calibrated from the dominant run (removes close-ups and zoomed replays); hits grouped at gaps over ~3 s; groups split at dead-shuttle restarts; keep rules (hitter alternates in 3+ hit groups, minimum spacing in 2-hit groups); fragments re-merged. Their recorded dead ends: a pixel court-line check (detected corners sit 2–5 px off the painted line), a serve-stance gate, and shuttle visibility (TrackNet fires on replays).
- **Serve detection** (`hits.py`): a serve starts from a near-still shuttle, so it can't show as a velocity kink; detect it as motion onset. No retraining.
- **BST input recipe** (`bst_eval.py`): BST-0 (no court-position input), a ±15-frame window centred on the hit, BST's own joint normalisation, shuttle scaled by 1280×720. With no fine-tuning: 71.8% (10 classes) and 98.2% side at labelled hits, 72.6–83.4% at detected hits.
- **Stacked shot classifier** (`shotclass.py`, `pipeline.py`): gradient-boosted trees over BST-0's probabilities plus court geometry (positions, landing, timing) and contact height (`contact.py`).
- **Scoreboard reading** (`scoreboard.py`, `score_seq.py`): BWF score digits read by template matching (Tesseract fails on ~12 px digits), templates harvested once from a labelled match and reused across tournaments; a rule-based decoder repairs impossible readings, splits multi-point jumps and completes games the broadcast cut away from. Gives rally count, point winners, set boundaries and which player is on which end (winner serves next).
- **Eval gotchas:** ShuttleSet's shuttle frames are off by a per-match offset (−1 and −3 frames on their two matches); `ffmpeg -ss` cuts by seconds aren't frame-exact; players swap ends between sets and at 11 in a deciding set.

What we keep of ours, because it's better or COURTSIDE lacks it: our learned hit detector (F1 91.0 vs 88), automatic court detection (COURTSIDE clicks four corners per match), cloud processing on Modal, multi-match player profiles and doubles pairs.

**Also adopted:**

- **Neighbouring-stroke context** (TemPose-TF-ASF, [arXiv 2605.02558](https://arxiv.org/abs/2605.02558), May 2026): feeding the predicted types of the previous and next strokes back in improved accuracy ~2 points over its baseline. We add those predictions as features to the stacked classifier (a second pass), rather than adopting a new model.
- **BFMD** ([Ning-D/BFMD](https://github.com/Ning-D/BFMD), CVSports 2026): annotations for 12 men's singles matches from 2025 BWF World Tour events with hit frames, shot types, rally boundaries and poses; videos re-downloaded from BWF TV. ShuttleSet ends in 2021, so BFMD tests the analyzer on current broadcasts and score graphics. No licence is stated: used for evaluation only, never redistributed or committed.

Considered and not adopted: Birdseye (3D reconstruction, hit F1 92.7 on BFMD; needs heavy 3D models and has no licence), table-tennis rally segmentation (EventAnchor, 98.5%; different sport cues), general temporal action localisation models (need training data we'd have to build).

## Goals

1. Split a full BWF singles broadcast into rallies, with serves, discarding non-play footage, and count them.
2. Read the scoreboard for scores, point winners, set boundaries and which player is on which end.
3. Raise hitter side and shot-type accuracy using the BST recipe, the stacked classifier and side alternation.
4. Score all of it end to end on full matches (ShuttleSet and BFMD), with time per stage.
5. Record a "before" baseline so every change has a measured before/after.

## Non-goals

- Doubles (BST is singles-trained; doubles comes after singles is reliable).
- Casual or non-broadcast footage.
- The ingest command (#76), database (#77) and library pages (#78). This design produces what they consume.
- Retraining the hit detector or shuttle tracker; 3D reconstruction.

## Anti-goals

- Any speed change that lowers an accuracy score. Every change is re-scored before and after.
- Tuning thresholds until the eval match looks good. Tune on one match, confirm on held-out ones.
- Copying code without attribution, or committing BFMD/ShuttleSet data or match videos.

## Targets

Measured on full matches, singles, held-out:

| Metric | Today | Target |
|---|---|---|
| Rally segmentation F1 | n/a | ≥ 94 (COURTSIDE held-out) |
| Rally count vs scoreboard | n/a | exact per set after score decoding |
| Hit F1 (serves now included in ground truth) | 91.0 (no serves) | ≥ 88 with serves |
| Hitter side | 81.2% | ≥ 95% |
| Shot type, matched hits | 54.4% (6 classes) | ≥ 75% on 10 classes; also reported on our 6 |
| Full match completes | likely times out | yes, with per-stage timings |

## Approaches considered

**Overall:** (1) adopt COURTSIDE wholesale; (2) **port its methods into our pipeline, keep our stronger parts (chosen)**; (3) design our own from scratch. (1) would discard our better hit detector and automatic court detection and bring in a local, DuckDB-based design that doesn't fit Modal. (3) repeats solved work, which James ruled out.

**Rally segmentation:** (1) court-line pixel check (our first idea; failed in COURTSIDE); (2) **players-in-court camera runs + hit grouping + restart splits (chosen, ported)**; (3) train a play/not-play classifier (fallback only if (2) misses the target on our pipeline).

**Hitter side:** (1) **BST-0's side probabilities with an alternation decode (chosen)**; (2) nearest wrist (COURTSIDE's fallback, 90–95%). BST-0's side is 96–98% in COURTSIDE; the alternation decode is a cheap guard on top.

## Design

### 1. Pipeline shape for a full match

```
full broadcast (720p, local)
  → cut into fixed chunks locally (frame-exact)        ── upload only what's needed
  → per chunk on Modal, in parallel: court + pose + shuttle + hits
  → play-camera runs from player tracks, rally grouping, serves, restarts
  → per rally: BST-0 → side decode → stacked shot classifier
  → scoreboard pass: read scores → decode → align to rallies
  → full-match result
```

Pose and shuttle tracking have to run on all frames anyway (segmentation is driven by player tracks), so the parallel unit is a fixed-length chunk of the broadcast with a small overlap, not a play span. Chunks are cut locally with a frame-exact method; only the chunks go to Modal. Rally grouping, BST and the stacked classifier run on the joined result.

**Where it lives (my call).** A reusable local module in `worker/`: full video in, full-match result out. The #73 eval calls it now; the #76 ingest command calls it later. The hidden upload webhook in `app.py` is unchanged and only has to keep working for a single clip.

### 2. Rally segmentation and serves (#72)

Port COURTSIDE's `segment.py` logic onto our tracks and hits: camera runs where both players are tracked in court; box-height band self-calibrated from the dominant run cluster; our hit detector plus a motion-onset serve detector; grouping at long gaps; restart splits; alternation and spacing keep rules; fragment re-merge. Thresholds are re-tuned on our pipeline's outputs (our hit detector behaves differently from theirs) on one match and confirmed on held-out matches.

### 3. Scoreboard (#72)

Port the template-matching digit reader and the score decoder. Templates are harvested from a labelled ShuttleSet match and checked on BFMD's 2025 broadcasts (newer graphics). Outputs: score after each rally, point winner, set boundaries, which player is on which end per set (and the mid-set swap at 11 in a deciding set). Scores are aligned to rallies by order within a set, because the overlay lags 2–15 s behind and pauses during replays.

### 4. Shot type and side (#74, #75)

1. **Switch BST input to COURTSIDE's BST-0 recipe** (section "Prior art"). Measure at labelled hits and at detected hits.
2. **Side decode:** per rally, sum BST-0's probabilities per side; a two-state decode strongly prefers alternation and allows a same-side step at a cost (missed or extra hit). Hits where the decode overrode strong evidence are flagged (`sideOverridden`). Each hit's type is then the best class within its decoded side.
3. **Stacked classifier:** gradient-boosted trees over BST-0 probabilities, court geometry (positions, landing, time since previous hit), contact height, and the previous and next strokes' predicted types (second pass). Trained leave-one-match-out on ShuttleSet so every reported number is held out.
4. The diagnosis in #74 shrinks to confirming each step's gain; the stage-by-stage loss attribution is only needed if step 1 doesn't reproduce COURTSIDE's ~72%.

### 5. Output contract (#72)

`analysis.json` gains rallies, serves and scores; events keep their shape with frames in full-video space plus seconds:

```json
"fps": 30,
"rallies": [
  { "id": 1, "set": 1, "startFrame": 12880, "endFrame": 13410, "startSec": 429.3, "endSec": 447.0,
    "eventIndices": [0, 1, 2], "scoreAfter": [0, 1], "winner": "far" }
],
"sets": [ { "set": 1, "nearPlayer": "A", "finalScore": [21, 15] } ],
"events": [ { "...": "existing fields", "isServe": true, "timeSec": 429.6, "sideOverridden": false } ],
"summary": { "...": "...", "rallyCount": 1 }
```

My calls: seconds alongside frames (the source is deleted and match pages seek a YouTube embed in seconds); no per-frame `tracking`/`shuttle_debug` in the full-match result (an hour of it is very large; overlays can get a per-rally file later). Producer (`worker/`), consumer type (`frontend/.../analysis/types.ts`) and `data-flow.md` change together.

### 6. Full-match eval (#73)

Extend `eval_shuttleset.py` with a full-match mode that runs the module end to end and scores:

- Rally segmentation precision/recall/F1 (ShuttleSet rally first-to-last shot, BFMD rally boundaries), rallies split or merged, play time kept vs discarded.
- Scoreboard: per-rally score sequence match, final set scores, side map.
- Hits (now including serves), side, shot type (10 classes and our 6), confusion matrices.
- Per-stage timings: chunk cut, upload, per-chunk analysis (min/median/max), segmentation, classification, scoreboard, total.
- Per-match frame offset for ShuttleSet labels, fitted and stored per match, not hard-coded.
- Frame-exact cuts verified (decoded frame N of a clip equals frame start+N of the source).

Eval set: Axelsen v Christie (in our hit detector's held-out split) for tuning; at least one more held-out ShuttleSet match and two BFMD 2025 matches for confirmation. Videos are downloaded locally; nothing is committed.

### 7. Baseline (before any change)

1. Today's pipeline on pre-cut rallies of the eval matches (re-run of #61).
2. Today's pipeline on one full set as a single video, with a long timeout: did it finish, how long, accuracy with non-play footage included.

Recorded on #73 as the "before".

## Order of work

1. Baseline (section 7) and the full-match eval mode (section 6).
2. BST-0 input recipe (section 4.1) — the biggest single expected gain, and small.
3. Chunked full-match processing and rally segmentation with serves (sections 1–2).
4. Side decode and stacked classifier (sections 4.2–4.3).
5. Scoreboard reading (section 3).
6. Output contract and docs (section 5).

Each step ends with an eval run recorded on its issue.

## Constraints

- Feature branches and PRs; Conventional Commits; no commits without James's approval.
- Ported code carries COURTSIDE's MIT notice (file header plus a `THIRD_PARTY` note); BST stays credited as today.
- Preserve existing model fallbacks (TrackNetV3 → TrackNet, learned hit detector → heuristics, BST → LSTM → rules).
- Preserve the explicit coordinate scaling between the 512×288 and 1280×720 readers.
- Videos, ShuttleSet and BFMD data stay outside git.
- Worker tests that can't import heavy ML dependencies mirror the logic, as existing tests do.

## Left to the builder

- Chunk length and overlap, containers per run, per-call timeout.
- All thresholds, re-tuned on our pipeline by measurement.
- Stacked-classifier features beyond those listed, and its hyperparameters.
- Which held-out ShuttleSet match and which BFMD matches.

## Separate follow-ups (not this design)

- The repo is public with no licence file; choose one.
- YOLO11 pose is AGPL-3.0 (copyleft, including network use). Decide whether to accept that or move to a permissively licensed pose model (e.g. RTMPose, Apache-2.0) — would need re-validating BST's input.
