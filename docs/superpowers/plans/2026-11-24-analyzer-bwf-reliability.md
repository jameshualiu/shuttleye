# Analyzer Reliability on BWF Broadcasts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a full BWF singles broadcast into rallies, serves, hitter sides, shot types and scores, scored end to end against ShuttleSet and BFMD.

**Architecture:** A new pure-Python package `worker/fullmatch/` holds the logic ported from COURTSIDE (rally segmentation, serve onset, score decoding, scoreboard reading) plus our side decode and stacked shot classifier. A local orchestrator cuts the broadcast into frame-exact chunks, runs our existing per-clip pipeline on each chunk in parallel on Modal, then segments, classifies and scores locally. BST input switches to COURTSIDE's BST-0 recipe. The eval (`worker/train/`) gains full-match scoring.

**Tech Stack:** Python 3.11, NumPy, OpenCV, PyTorch (BST), scikit-learn (HistGradientBoosting), Modal (T4), ffmpeg, pytest; TypeScript type update in the frontend.

**Spec:** `docs/superpowers/specs/2026-11-24-analyzer-bwf-reliability-design.md`

## Global Constraints

- Issues: #72 rally splitting, #73 full-match eval, #74 shot type, #75 alternating sides. Branch `feature/72-full-match-analyzer`, one PR closing all four.
- **No commits until James says "Commit these changes" (AGENTS.md Gate 2).** Each task ends with a tree snapshot (`git add -A && git write-tree`) recorded in the ledger. Commits are built from the snapshots at Gate 2, one per task, Conventional Commits, no Co-Authored-By trailer, no "Generated with Claude Code".
- COURTSIDE source is pinned at `jayclim/BadmintonAI@5c356f05cde0ed90c75316c133e0aba495e5232b`. Every ported file starts with a header naming the upstream file, that commit and "MIT License, Copyright (c) Jayden Lim" (copy the exact holder line from upstream `LICENSE`); `worker/THIRD_PARTY.md` lists each ported file.
- Preserve model fallbacks: TrackNetV3 → TrackNet; learned hit detector → heuristics; BST-0 → BST_CG_AP → LSTM → rules; stacked classifier → BST-0 argmax.
- Preserve the explicit coordinate scaling between the 512×288 and 1280×720 readers in `pipeline.py`.
- Never commit match videos, ShuttleSet CSVs, BFMD annotations, model weights or eval results. Caches live under `~/.cache/shuttleye-eval/`.
- `worker/fullmatch/` modules must import without torch, ultralytics or modal (tests import them directly). Heavy imports stay inside functions or in `detectors/`.
- Product shot types stay the 6 classes `Clear, Drive, Drop, Lob, Net, Smash` plus `"Serve"` for serves; the 10-class name goes in a new `detailType` field. 10 classes = COURTSIDE `insights.SHOT_ORDER` at the pinned commit.
- Thresholds ported from COURTSIDE start at their values (`segment.py`: `MERGE_GAP=45, MIN_RUN=45, RUN_PAD=30, SPLIT_GAP=90, MIN_SOLO_SCORE=3.0, RESTART_SPEED=2.5, BBOX_TOL=0.25, GROUP_WRIST_PX=150, TRAIL_WRIST_PX=130, MIN_PAIR_DT=13, MERGE_SEG=120`; `hits.py`: `MIN_SPEED=3.0, MIN_GAP=8`) and are re-tuned only on the tuning match (Axelsen v Christie), then confirmed on held-out matches.
- Targets (held-out): rally segmentation F1 ≥ 94; exact set scores; hit F1 ≥ 88 with serves; side ≥ 95%; shot type ≥ 75% on 10 classes.
- Worker tests run from `worker/` with `.venv/bin/pytest tests/<file> -q`; CI runs `pytest tests/`.

## Review Focus

1. **Source video not at 30 fps** (BWF uploads at 25 or 50): every frame↔second conversion must use the probed fps; ShuttleSet scoring only accepts 30 fps. Test in Task 4.
2. **A chunk with no visible court** (starts in a replay, ad or pre-match graphics): the chunk returns no hits and `court_found: false` instead of crashing or reusing another chunk's homography. Test in Task 4.
3. **A hit inside a chunk overlap** is reported once, not twice. Test in Task 4.
4. **A 1-hit rally** (serve fault or ace) is kept only when its score clears `MIN_SOLO_SCORE`, and a pickup tap before a serve doesn't become its own rally. Test in Task 5.
5. **Deciding set, ends swap at 11:** the side map flips mid-set, so player identity per rally stays right. Test in Task 8.

---

### Task 0: Workspace and docs

**Files:**
- Create: worktree `../shuttleye-analyzer` on `feature/72-full-match-analyzer` from `origin/main`
- Add: `docs/superpowers/specs/2026-11-24-analyzer-bwf-reliability-design.md`, this plan (move both from the main checkout)

- [ ] **Step 1:** `git worktree add -b feature/72-full-match-analyzer ../shuttleye-analyzer origin/main`; move the spec and plan into it; `git add` them.
- [ ] **Step 2:** Create the ledger `.superpowers/sdd/2026-11-24-analyzer-bwf-reliability/progress.md` with the plan path as its first line.
- [ ] **Step 3:** Snapshot: `git add -A && git write-tree` → record `T0=<sha>` in the ledger.

### Task 1: Full-match scoring functions (#73)

**Files:**
- Modify: `worker/train/eval_scoring.py`
- Test: `worker/tests/test_eval_scoring.py`

**Interfaces:**
- Produces:
  - `ZH_TO_TEN: dict[str, str]` — ShuttleSet Chinese type → COURTSIDE 10-class name (copy from COURTSIDE `shuttleset.py` CN→EN map at the pinned commit).
  - `parse_rallies(rows, h, far_corner, near_corner)` unchanged in shape; each shot gains `"ten": str | None`.
  - `score_rally(pred_events, gt_shots, tolerance=3, include_serves=False)` — when `include_serves`, serves count as hits and a predicted event with `isServe` matches them; adds `"ten_correct"`, `"ten_total"` to the result.
  - `score_segments(pred: list[tuple[int, int]], gt: list[tuple[int, int]], min_overlap=0.5) -> dict` — one-to-one matching of predicted vs ground-truth rally intervals (inclusive frames) by overlap fraction of the ground-truth interval; returns `{"tp", "fp", "fn", "precision", "recall", "f1", "split", "merged"}`.
  - `fit_frame_offset(pred_frames: list[int], gt_frames: list[int], search=range(-8, 9), tolerance=3) -> int` — the offset added to gt frames that maximises one-to-one matches.

- [ ] **Step 1: Write failing tests**

```python
def test_score_segments_exact_and_split():
    gt = [(100, 400), (600, 900)]
    pred = [(90, 410), (600, 740), (745, 905)]
    s = score_segments(pred, gt)
    assert (s["tp"], s["fn"], s["split"]) == (2, 0, 1)
    assert s["fp"] == 0  # the second half of a split rally is not a false positive

def test_score_segments_merged():
    s = score_segments([(100, 900)], [(100, 400), (600, 900)])
    assert s["merged"] == 1 and s["tp"] == 1 and s["fn"] == 1

def test_fit_frame_offset_finds_shift():
    gt = [10, 50, 90, 130]
    pred = [f - 3 for f in gt]
    assert fit_frame_offset(pred, gt) == -3

def test_score_rally_counts_serve_when_included():
    gt = [{"frame": 10, "serve": True, "type": None, "ten": "short service", "side": "Bottom"},
          {"frame": 40, "serve": False, "type": "Net", "ten": "net shot", "side": "Top"}]
    pred = [{"frame": 11, "isServe": True, "type": "Serve", "detailType": "short service", "side": "Bottom"},
            {"frame": 40, "type": "Net", "detailType": "net shot", "side": "Top"}]
    s = score_rally(pred, gt, include_serves=True)
    assert s["tp"] == 2 and s["ten_correct"] == 2
    assert score_rally(pred, gt)["tp"] == 1  # default unchanged: serves excluded
```

- [ ] **Step 2:** Run `cd worker && .venv/bin/pytest tests/test_eval_scoring.py -q` → the new tests fail with ImportError/KeyError.
- [ ] **Step 3:** Implement the four interfaces in `eval_scoring.py`; keep existing behaviour when `include_serves=False`. `summarize` also totals `ten_correct`/`ten_total` and the segment counts when present.
- [ ] **Step 4:** Run the same command → all pass, existing tests still pass.
- [ ] **Step 5:** Snapshot → `T1`.

### Task 2: Baseline (#73)

No code. Records the "before". Runs on Modal (a few dollars of T4 time); videos download locally.

- [ ] **Step 1:** `python -m modal run worker/train/eval_shuttleset.py --set-num 1` on Axelsen v Christie (default match) and on one more held-out ShuttleSet singles match. Pick the second match from those outside `train_detector.split_npz_files`' training split; note which in the ledger.
- [ ] **Step 2:** Time today's pipeline on set 1 of Axelsen v Christie as one video (cut set 1 from its first shot −30 frames to last shot +45 frames; run `EvalWorker.analyze` once with `timeout=3600`). Record wall clock, whether it finished, and hit/side/type scores with `fit_frame_offset` applied.
- [ ] **Step 3:** Post both results as a comment on #73 titled "Baseline (before)". Record the numbers in the ledger.

### Task 3: BST-0 with COURTSIDE's input recipe (#74)

**Files:**
- Modify: `worker/detectors/bst_model.py` (add `BST_0`, vendored from `Va6lue/BST-Badminton-Stroke-type-Transformer`, MIT, credited like `BST_CG_AP`)
- Modify: `worker/detectors/stroke_classifier.py` (add `BST0Adapter`)
- Modify: `worker/inference.py`, `worker/app.py` (`OPTIONAL_MODEL_TARGETS["bst0"] = "bst_0_JnB_bone_merged.pt"`; prefer BST-0 when present)
- Modify: `worker/train/eval_shuttleset.py` (`--gt-hits` mode)
- Test: `worker/tests/test_bst0_inputs.py`

**Interfaces:**
- Produces:
  - `BST0Adapter(weights_path, device=None)` with `probs_at(hit_frames: list[int], shuttle_traj, player_tracking, frame_size=(1280, 720)) -> np.ndarray` shape `(n, 25)`, class order = BST merged types (`'未知球種'` + 12 Top + 12 Bottom), and `classify_hits(hits, shuttle_traj, player_tracking, fps, pixel_to_meters)` with the same contract as `BSTStrokeClassifierAdapter.classify_hits` plus `hit["probs"]` (list of 25 floats) and `hit["detailType"]`.
  - Window: ±15 frames centred on the hit (`SEQ_LEN=30`), players ordered `[far=Top, near=Bottom]`, joints normalised by COURTSIDE `bst_eval._normalize_joints` (offset by bbox top-left, scale by bbox diagonal, zeros for missing), shuttle divided by `frame_size`, invisible → 0. Port the input building from COURTSIDE `bst_eval.py` at the pinned commit.
  - Pipeline coordinates are 512×288; scale tracks and shuttle to 1280×720 before normalising (state the factor in a comment).
  - Pure helpers in `worker/fullmatch/bst_inputs.py`: `normalize_joints(joints: (m,J,2), bbox: (m,4)) -> (m,J,2)`, `window_frames(hit_frame: int, half: int = 15) -> list[int]`, `shuttle_input(points: list[tuple|None], src_size, dst_size) -> (n,2)` (divided by `dst_size`).
- Model fallback: `bst0` → existing `bst` → LSTM → rules, logged like today.

- [ ] **Step 1: Write failing tests** (pure numpy mirrors of the input functions, per the worker test pattern)

```python
def test_normalize_joints_matches_courtside_scheme():
    j = np.array([[[110., 220.], [0., 0.]]])            # one joint visible, one missing
    bb = np.array([[100., 200., 130., 240.]])            # x1,y1,x2,y2 -> diag 50
    out = normalize_joints(j, bb)
    assert np.allclose(out[0, 0], [10 / 50, 20 / 50])
    assert np.allclose(out[0, 1], [0, 0])                # missing stays zero

def test_window_is_centred_and_30_long():
    assert window_frames(100) == list(range(85, 115))

def test_shuttle_scaled_from_pipeline_space():
    assert np.allclose(shuttle_input([(256, 144)], (512, 288), (1280, 720)), [[0.5, 0.5]])
```

- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_bst0_inputs.py -q` → fail.
- [ ] **Step 3:** Put `normalize_joints`, `window_frames`, `shuttle_input` as pure functions in `worker/fullmatch/bst_inputs.py` (no torch); `BST0Adapter` imports them. Vendor `BST_0`. Add the `--gt-hits` eval mode: run BST-0 at ShuttleSet's labelled hit frames (after `fit_frame_offset`) and report 10-class and 6-class accuracy plus side accuracy.
- [ ] **Step 4:** Tests pass. James downloads `bst_0_JnB_bone_merged.pt` from BST's "Weights trained on ShuttleSet" Drive folder (merged); upload with `modal volume put badminton-models <file> /bst_0_JnB_bone_merged.pt`.
- [ ] **Step 5:** Run `--gt-hits` and the normal eval on Axelsen v Christie set 1. Expected near COURTSIDE: ~72% 10-class at labelled hits, side ≥ 95%. If 10-class is under 65%, stop and compare our inputs frame by frame against COURTSIDE's recipe before going on. Record results on #74.
- [ ] **Step 6:** Snapshot → `T3`.

### Task 4: Chunked full-match processing (#72, #73)

**Files:**
- Create: `worker/fullmatch/__init__.py`, `worker/fullmatch/chunks.py`, `worker/fullmatch/run.py`
- Modify: `worker/app.py` (Modal function `analyze_chunk`), `worker/train/eval_shuttleset.py` (`--full-match` mode)
- Test: `worker/tests/test_chunks.py`

**Interfaces:**
- Produces:
  - `plan_chunks(total_frames: int, chunk: int = 1800, overlap: int = 60) -> list[tuple[int, int]]` — inclusive `[start, end]` covering every frame.
  - `merge_chunks(results: list[dict], plan: list[tuple[int, int]], overlap: int = 60) -> dict` — offsets each chunk's `events`, `tracking`, `shuttle` frames to full-video frames; in an overlap keeps items from the chunk whose interior they fall in (the later chunk owns frames from `start + overlap // 2` on); returns `{"events", "tracking", "shuttle", "chunks": [{"start", "end", "court_found", "geometry"}]}`.
  - `cut_exact(src: Path, start: int, n_frames: int, out: Path, fps: float) -> None` — frame-exact cut (re-encode, constant fps, no B-frames, as `eval_shuttleset._cut_rally`), and `verify_cut(src, out, start, samples=3) -> bool` comparing decoded frames.
  - `analyze_full_match(video: Path, fps: float | None = None) -> dict` in `run.py` — probe fps, plan, cut, `analyze_chunk.starmap`, merge, then (later tasks) segment, classify, score; records `timings` per stage.
  - Modal `analyze_chunk(chunk_id: int, clip: bytes) -> dict` — runs `BadmintonPipeline.process_video` and returns `events`, `tracking`, `shuttle_debug`, `geometry`, `summary`; a chunk with no court returns `court_found: False` and empty events.
  - Eval `--full-match`: runs `analyze_full_match` on the downloaded match and scores every labelled set with `fit_frame_offset`, hits with `include_serves=True`, and prints timings.

- [ ] **Step 1: Write failing tests**

```python
def test_plan_chunks_covers_everything_with_overlap():
    p = plan_chunks(4000, chunk=1800, overlap=60)
    assert p[0] == (0, 1799) and p[-1][1] == 3999
    assert all(b[0] == a[1] - 60 + 1 for a, b in zip(p, p[1:]))

def test_merge_keeps_overlap_hit_once():
    plan = [(0, 1799), (1740, 3539)]
    r0 = {"events": [{"frame": 1770}], "tracking": [], "shuttle_debug": [], "geometry": {}, "court_found": True}
    r1 = {"events": [{"frame": 30}], "tracking": [], "shuttle_debug": [], "geometry": {}, "court_found": True}
    assert [e["frame"] for e in merge_chunks([r0, r1], plan)["events"]] == [1770]

def test_chunk_without_court_contributes_nothing():
    plan = [(0, 1799)]
    r = {"events": [], "tracking": [], "shuttle_debug": [], "geometry": None, "court_found": False}
    m = merge_chunks([r], plan)
    assert m["events"] == [] and m["chunks"][0]["court_found"] is False

def test_seconds_use_probed_fps():
    assert frame_to_sec(50, fps=25.0) == 2.0
```

- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_chunks.py -q` → fail.
- [ ] **Step 3:** Implement `chunks.py` (pure; `frame_to_sec(frame, fps)` lives here) and `run.py`. In `--full-match` eval, refuse non-30 fps downloads for ShuttleSet scoring (as today) but let `analyze_full_match` accept any fps.
- [ ] **Step 4:** Tests pass. Run `--full-match` on Axelsen v Christie; check `verify_cut` on 3 chunks; record total and per-stage timings in the ledger. Hits/side/type should match Task 3's numbers within noise (no segmentation yet).
- [ ] **Step 5:** Snapshot → `T4`.

### Task 5: Rally segmentation and serves (#72)

**Files:**
- Create: `worker/fullmatch/segment.py`, `worker/fullmatch/serves.py` (ported from COURTSIDE `segment.py` and the serve-onset pass of `hits.py`)
- Modify: `worker/fullmatch/run.py`, `worker/train/eval_shuttleset.py` (segment metrics)
- Test: `worker/tests/test_segment.py`

**Interfaces:**
- Consumes: merged `tracking` (per frame `players` with `box`, `skeleton`), `shuttle` (per frame `pos`), `events` from Task 4.
- Produces:
  - `both_tracked(tracking: list[dict], total_frames: int) -> np.ndarray` (bool per frame: two in-court players).
  - `camera_runs(tracked: np.ndarray, merge_gap=45, min_run=45) -> list[tuple[int, int]]`.
  - `filter_runs_by_bbox(runs, box_heights: np.ndarray, tol=0.25) -> list[tuple[int, int]]` — keep runs whose median player box height is within `tol` of the dominant run cluster.
  - `serve_onset(xy: np.ndarray, frames: np.ndarray, hit_frames: list[int], min_speed=3.0, min_gap=8) -> dict | None` — first 3-frame stretch with speed ≥ `2*min_speed` and no hit within `2*min_gap`; returns `{"frame", "isServe": True}`.
  - `split_at_restarts(group: list[dict], restart_speed=2.5) -> list[list[dict]]` — a non-first hit with `v_in` below `restart_speed` starts a new group (upstream `_split_at_restarts`).
  - `keep_group(group: list[dict]) -> bool` — upstream `_keep_group`: 1-hit groups need `score ≥ MIN_SOLO_SCORE`; 2-hit groups need ≥ `MIN_PAIR_DT` frames between hits; 3+ hit groups need alternating `side`.
  - `segment_rallies(events, tracking, shuttle, total_frames) -> list[dict]` — `[{"startFrame", "endFrame", "eventIndices"}]`, applying runs → serve onset per run → grouping at `SPLIT_GAP` → restart splits (`RESTART_SPEED`) → keep rules (`_keep_group` incl. alternation and `MIN_PAIR_DT`, `MIN_SOLO_SCORE`) → wrist gates → fragment re-merge (`MERGE_SEG`). Serve events are inserted into `events` with `type: "Serve"`.

- [ ] **Step 1: Write failing tests** (synthetic arrays)

```python
def test_camera_runs_bridge_short_dropouts_and_drop_short_runs():
    t = np.zeros(400, bool); t[10:200] = True; t[220:300] = True; t[350:370] = True
    assert camera_runs(t, merge_gap=45, min_run=45) == [(10, 299)]

def test_bbox_filter_drops_closeup_run():
    runs = [(0, 99), (200, 299), (400, 499)]
    h = np.r_[np.full(100, 80.), np.full(100, 0.), np.full(100, 82.), np.full(100, 0.), np.full(100, 200.)]
    assert filter_runs_by_bbox(runs, h, tol=0.25) == [(0, 99), (200, 299)]

def test_serve_onset_from_rest():
    xy = np.r_[np.full((20, 2), 100.), np.cumsum(np.full((10, 2), 8.), axis=0) + 100]
    assert serve_onset(xy, np.arange(30), hit_frames=[])["frame"] == 19

def test_one_hit_group_needs_solo_score():
    weak = [{"frame": 100, "score": 1.5, "side": "Top"}]
    strong = [{"frame": 100, "score": 4.0, "side": "Top"}]
    assert keep_group(weak) is False and keep_group(strong) is True

def test_restart_tap_is_split_off():
    g = [{"frame": 100, "v_in": 9.0}, {"frame": 160, "v_in": 1.0}, {"frame": 190, "v_in": 12.0}]
    assert [[h["frame"] for h in s] for s in split_at_restarts(g, restart_speed=2.5)] == [[100], [160, 190]]
```

- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_segment.py -q` → fail.
- [ ] **Step 3:** Port the logic as pure functions (no DuckDB, no `match_id`); events need `score` and `v_in` — compute them from the merged shuttle track in `segment.py` (port `_combined_score` for `score`). Wire `segment_rallies` into `run.py`; add `score_segments` output to `--full-match`.
- [ ] **Step 4:** Tests pass. Run `--full-match` on Axelsen v Christie: tune thresholds only here, record F1, then run the second held-out match untouched. Target F1 ≥ 94 held-out. If it misses because of camera runs (not hits), note it on #72; the trained-classifier fallback is a follow-up issue, not this plan.
- [ ] **Step 5:** Snapshot → `T5`.

### Task 6: Alternating side decode (#75)

**Files:**
- Create: `worker/fullmatch/sides.py`
- Modify: `worker/fullmatch/run.py`
- Test: `worker/tests/test_sides.py`

**Interfaces:**
- Consumes: per-event `probs` (25) from Task 3; rallies from Task 5.
- Produces:
  - `side_probs(probs: np.ndarray) -> np.ndarray` — `(n,)` P(Top) = sum of the 12 Top classes ÷ (Top + Bottom); falls back to 0.5 when both sums are 0.
  - `decode_sides(p_top: np.ndarray, p_alternate: float = 0.95, strong: float = 0.9) -> tuple[list[str], list[bool]]` — Viterbi over states Top/Bottom with transition P(switch)=`p_alternate`; returns sides and `overridden` flags (decoded side disagrees with a hit whose own probability for the other side ≥ `strong`).
  - `best_type_within_side(probs: np.ndarray, side: str) -> int` — argmax over that side's 12 classes.
- Applied per rally; when probs are missing (LSTM fallback) use positional side evidence from `stroke_classifier`/`_refine_locations_by_side` as `p_top` (0.8/0.2).

- [ ] **Step 1: Write failing tests**

```python
def test_alternation_fixes_one_weak_flip():
    p = np.array([0.9, 0.2, 0.55, 0.1, 0.9])     # third hit weakly says Top
    sides, over = decode_sides(p)
    assert sides == ["Top", "Bottom", "Top", "Bottom", "Top"]
    assert not any(over)

def test_strong_contrary_evidence_is_flagged():
    p = np.array([0.9, 0.05, 0.03, 0.1])          # hits 2 and 3 both strongly Bottom
    sides, over = decode_sides(p)
    assert over.count(True) >= 1

def test_type_picked_within_decoded_side():
    probs = np.zeros(25); probs[3] = 0.6; probs[13 + 5] = 0.3   # Top class 3 wins overall
    assert best_type_within_side(probs, "Bottom") == 13 + 5
```

- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_sides.py -q` → fail.
- [ ] **Step 3:** Implement; wire into `run.py` after segmentation; set `event["side"]`, `event["sideOverridden"]`, and re-pick `detailType`/`type` from `best_type_within_side`. Also set `event["detailId"]` = index of `detailType` in the 10-class list (Task 7 reads it).
- [ ] **Step 4:** Tests pass. Re-run `--full-match` on both matches; record side and type before/after on #75. Side must not drop; target ≥ 95%.
- [ ] **Step 5:** Snapshot → `T6`.

### Task 7: Stacked shot classifier (#74)

**Files:**
- Create: `worker/fullmatch/shot_features.py`, `worker/fullmatch/contact.py` (ported from COURTSIDE `contact.py`), `worker/train/train_shot_stack.py`
- Modify: `worker/fullmatch/run.py`, `worker/requirements.txt` (`scikit-learn`), `worker/requirements-eval.txt` if separate
- Test: `worker/tests/test_shot_features.py`

**Interfaces:**
- Consumes: events with `probs`, decoded `side`, positions (court metres via homography), rallies.
- Produces:
  - `FEATURES: list[str]` — the 25 BST-0 probs, hitter and receiver normalised court positions, landing position (next hitter's feet, as COURTSIDE), time since previous hit, contact height (m), and the previous and next events' predicted 10-class ids (second pass; `-1` at rally ends).
  - `build_features(events: list[dict], rallies: list[dict]) -> np.ndarray` (`len(events) × len(FEATURES)`, NaN for missing).
  - `contact_height(box_heights_near: np.ndarray, ..., shuttle_y: float) -> float` — the person-ruler from COURTSIDE `contact.py` (`BODY_M=1.78`, `RULER_Q=0.80`, `BIN_PX=30`).
  - `train_shot_stack.py`: builds features from `--full-match` cached results for every ShuttleSet match available, trains `HistGradientBoostingClassifier` leave-one-match-out, prints per-match held-out 10-class and 6-class accuracy, saves the all-matches model to `shot_stack.joblib` (uploaded to the Modal volume, never committed).
  - In `run.py`: if `shot_stack.joblib` is available, overwrite `detailType`/`type` with its prediction; otherwise keep Task 6's result.

- [ ] **Step 1: Write failing tests**

```python
def test_features_have_fixed_width_and_nan_for_missing():
    ev = [{"probs": [0.04] * 25, "side": "Top", "frame": 10}]
    X = build_features(ev, [{"startFrame": 0, "endFrame": 50, "eventIndices": [0]}])
    assert X.shape == (1, len(FEATURES)) and np.isnan(X).any()

def test_neighbour_context_columns():
    ev = [{"probs": [0.04] * 25, "side": "Top", "frame": f, "detailId": i} for i, f in enumerate([10, 40, 70])]
    X = build_features(ev, [{"startFrame": 0, "endFrame": 90, "eventIndices": [0, 1, 2]}])
    prev, nxt = FEATURES.index("prev_type"), FEATURES.index("next_type")
    assert X[0, prev] == -1 and X[1, prev] == 0 and X[1, nxt] == 2 and X[2, nxt] == -1
```

- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_shot_features.py -q` → fail.
- [ ] **Step 3:** Implement features, contact height and the training script.
- [ ] **Step 4:** Tests pass. Run `--full-match` on every ShuttleSet singles match you have cached (at least 4), then `train_shot_stack.py`. Record held-out accuracy per match on #74. Target ≥ 75% (10 classes). Keep the stack only if it beats Task 6 on held-out matches.
- [ ] **Step 5:** Snapshot → `T7`.

### Task 8: Scoreboard reading (#72)

**Files:**
- Create: `worker/fullmatch/score_seq.py` (vendored from COURTSIDE `score_seq.py`, pure), `worker/fullmatch/scoreboard.py` (ported from COURTSIDE `scoreboard.py`), `worker/train/harvest_scoreboard.py`
- Modify: `worker/fullmatch/run.py`
- Test: `worker/tests/test_score_seq.py`, `worker/tests/test_scoreboard_align.py`

**Interfaces:**
- Produces:
  - `score_seq.point_log(reads, max_fill=3)`, `set_finals(points)`, `sets_won(points)` — same behaviour as upstream.
  - `scoreboard.read_frame(frame: np.ndarray, box, templates) -> dict | None` and `timeline(video: Path, fps: float, step: int = 30, templates=...) -> list[dict]` (local, cv2 only; runs on the full local video, not on Modal).
  - `scoreboard.events(timeline) -> list[dict]` — debounced score changes (2 identical consecutive reads).
  - `align_scores(rallies: list[dict], score_events: list[dict]) -> list[dict]` — each score event goes to the latest already-ended unassigned rally in the same set; sets `rally["scoreAfter"]`, `rally["winner"]`, `rally["set"]`.
  - `side_map(rallies) -> list[dict]` — per set which player (A = match winner) is near; winner serves next; includes the end change at 11 in a deciding set.
  - `harvest_scoreboard.py` builds digit templates from a labelled ShuttleSet match (sample just before the next serve, as upstream) and saves `scoreboard_digits.npz` to the eval cache (not committed; uploaded with the models).

- [ ] **Step 1: Write failing tests**

```python
def test_point_log_repairs_spike_and_expands_jump():
    reads = [(0, 0), (1, 0), (0, 8), (2, 0), (4, 0)]
    assert [p[:2] for p in point_log(reads)] == [(1, 0), (2, 0), (3, 0), (4, 0)]

def test_align_assigns_to_latest_ended_rally():
    rallies = [{"id": 1, "endFrame": 100}, {"id": 2, "endFrame": 300}]
    ev = [{"frame": 180, "score": (1, 0)}, {"frame": 420, "score": (1, 1)}]
    out = align_scores(rallies, ev)
    assert out[0]["scoreAfter"] == (1, 0) and out[1]["scoreAfter"] == (1, 1)

def test_deciding_set_ends_swap_at_11():
    rallies = make_deciding_set_rallies(near_first="A", swap_after=(11, 7))   # test helper
    sm = side_map(rallies)
    before, after = sm[0], sm[-1]
    assert before["near"] == "A" and after["near"] == "B"
```

Adjust the `point_log` expectation to upstream's exact output if it differs (run upstream on the same reads once and pin it).

- [ ] **Step 2:** Run both test files → fail.
- [ ] **Step 3:** Port; wire `timeline → events → align_scores → side_map` into `analyze_full_match` (local pass over the full video at `step=30`).
- [ ] **Step 4:** Tests pass. Harvest on Axelsen v Christie; run on the second ShuttleSet match and on two BFMD 2025 matches (Task 9 provides the loader; check final set scores by hand against the broadcast if BFMD lacks them). Target: exact set finals. Record on #72.
- [ ] **Step 5:** Snapshot → `T8`.

### Task 9: Output contract, BFMD eval, docs (#72, #73)

**Files:**
- Modify: `worker/fullmatch/run.py` (final result shape), `frontend/badminton-ai/src/features/analysis/types.ts`, `data-flow.md`
- Create: `worker/train/bfmd.py` (annotation loader), `worker/THIRD_PARTY.md`
- Test: `worker/tests/test_fullmatch_output.py`

**Interfaces:**
- `assemble_result(fps: float, events: list[dict], rallies: list[dict], sets: list[dict], timings: dict) -> dict` in `run.py` produces the full-match result (spec section 5): top-level `fps`, `rallies` (`id, set, startFrame, endFrame, startSec, endSec, eventIndices, scoreAfter, winner`), `sets` (`set, nearPlayer, finalScore`), `events` (existing fields plus `isServe, timeSec, sideOverridden, detailType`), `summary.rallyCount`, `timings`. No `tracking` or `shuttle_debug` in the full-match result.
- `bfmd.load_match(path: Path) -> {"video_id": str, "fps": float, "rallies": [(start, end)], "shots": [...]}` mapped to the same dicts `parse_rallies` returns. Read the BFMD JSON layout from its README before writing; BFMD data stays in the eval cache.
- `types.ts`: add the new optional fields and `"Serve"` to the shot type union; nothing else in the frontend changes.

- [ ] **Step 1: Write failing test**

```python
def test_full_match_result_shape():
    r = assemble_result(fps=25.0, events=[{"frame": 50, "type": "Serve", "isServe": True}],
                        rallies=[{"startFrame": 40, "endFrame": 120, "eventIndices": [0]}], sets=[], timings={})
    assert r["rallies"][0]["startSec"] == 1.6 and r["events"][0]["timeSec"] == 2.0
    assert r["summary"]["rallyCount"] == 1 and "tracking" not in r
```

- [ ] **Step 2:** Run → fail. **Step 3:** Implement `assemble_result` in `run.py`, the BFMD loader and an `eval_shuttleset.py --bfmd <match>` path; update `types.ts` and `data-flow.md` (new section: full-match result). Write `THIRD_PARTY.md`.
- [ ] **Step 4:** Test passes; `cd frontend/badminton-ai && npm run lint && npm run build` pass.
- [ ] **Step 5:** Final eval: `--full-match` on the tuning match, the held-out ShuttleSet match and two BFMD 2025 singles matches. Post an "After" comment on #73 with the same table as the baseline plus timings. Snapshot → `T9`.

## Gate 2

Present the per-task commits (one per task 1, 3–9; Task 0's docs go in with Task 1 as `docs:`), the before/after table and the affected files. Wait for "Commit these changes". Then push, open one PR closing #72–#75 with labels `worker`, `ML`, `evaluation`, `feature`.
