# Badminton AI Analyst — Data Flow & Pipeline

---

## 1. Frontend → Backend Pipeline

### Upload flow (3 steps)

The user opens the `UploadModal`, selects a video file, and the `createAndUploadVideo()` function in `videoService.ts` orchestrates a three-step handshake:

**Step 1 — Init** (`POST /api/videos/init`)
The frontend sends `{ filename, contentType, size }` with a Firebase JWT in the `Authorization` header. The Express backend's `authMiddleware` verifies the token, then `VideoService.initializeUpload()` does two things atomically: it generates a presigned `PUT` URL (valid 1 hour) pointing directly at Cloudflare R2, and creates a Firestore document at `users/{uid}/videos/{videoId}` with status `uploading`. The presigned URL and `videoId` are returned to the frontend.

**Step 2 — Direct upload to storage**
The frontend `PUT`s the raw video file directly to the presigned E2 URL — the backend is never in the upload path. This keeps the Express server lightweight and avoids proxying large files.

**Step 3 — Complete** (`POST /api/videos/:videoId/complete`)
The frontend notifies the backend that the upload finished. The backend marks the Firestore doc as `queued` and then **fire-and-forgets** a `POST` to `MODAL_WEBHOOK_URL` with `{ videoId, userId, videoE2Key }`, authenticated with an `Authorization: Bearer <MODAL_WEBHOOK_SECRET>` header. The user gets an instant `{ status: "queued" }` response while the ML worker boots asynchronously.

### Status polling via Firestore real-time subscription

The frontend's `useUserVideos` hook opens a Firestore `onSnapshot` listener on `users/{uid}/videos` ordered by `createdAt`. Any status change written by the backend or ML worker (`uploading → queued → running → done / failed`) is pushed to the frontend in real time — no polling needed. The `DashboardPage` renders these as `VideoCard` components showing current status.

### Results fetch

When a video reaches `done`, the user navigates to `AnalysisPage`. It calls `getVideoResults(videoId, token)` which hits `GET /api/videos/:videoId/results`. The backend generates a time-limited presigned `GET` URL for the `analysis.json` stored in E2 and returns `{ status, urls: { originalVideo, analysisJson } }`. The frontend then fetches the JSON payload directly from E2 using that URL.

---

## 2. ML Pipeline (Python Worker on Modal)

The worker runs as a Modal `fastapi_endpoint` on an NVIDIA T4 GPU with a 20-minute timeout. It receives `{ videoId, userId, videoE2Key }` from the backend webhook.

**Processing-length constraint (WK-09)**
There is no artificial frame cap — `process_video()` processes the full video by default. The real constraint on how long a match can be is the Modal function's own 20-minute (`timeout=1200`) wall-clock limit covering download + model loading + the full pipeline + upload; a video that doesn't finish within that window fails the request rather than being silently truncated. If a caller does pass an explicit `limit_frames`, `analysis.json`'s `summary.truncated` is set `true` so the frontend can surface that the result is a partial prefix.
**Webhook authentication & input validation (SEC-01)**
Before touching Firestore or S3, the endpoint validates the `Authorization: Bearer <token>` header via a constant-time comparison against `MODAL_WEBHOOK_SECRET` (stored in the Modal secret `badminton-ai-secrets`; the backend sends the matching value from its own `MODAL_WEBHOOK_SECRET` env var) — a missing/mismatched token gets a 401. `videoId` must parse as a UUID (real ids are `crypto.randomUUID()` from the backend) or the request gets a 400, preventing path-traversal via `/tmp/{videoId}...` paths. `videoE2Key` must start with `uploads/{userId}/` or the request gets a 403, preventing one user's request from pulling another user's (or an arbitrary) object out of the bucket.

### Model loading

Five models are resolved from a persistent Modal Volume (with R2 as a fallback if missing):

| Key | File | Purpose |
|---|---|---|
| `tracknet` | `ball_track.pt` | Shuttle position heatmaps (TrackNet) |
| `court_kprcnn` | `court_kpRCNN.pth` | 6-point + 35-point court keypoints |
| `net_kprcnn` | `net_kpRCNN.pth` | Net keypoint detection |
| `yolo_pose` | `yolo11x-pose.pt` | Player bounding boxes + 17-point COCO skeleton |
| `lstm` | `15Matches_LSTM.onnx` | Shot type classifier |

### Pipeline steps

**Homography setup**
The first 150 frames are scanned in steps of 10. Once a frame yields 6 court keypoints (TL, TR, ML, MR, BL, BR), `cv2.findHomography` computes a perspective matrix mapping pixel coordinates → real-world meters (court is 6.1m × 13.4m). All downstream `location_m` values are produced by this transform.

**Pass 1 — Shuttle tracking (TrackNet, batch size 8)**
Every frame is processed. Each batch stacks three consecutive RGB frames into a `(N, 9, 288, 512)` float32 tensor (normalized 0–1). TrackNet outputs a `(288, 512)` heatmap per frame; the argmax gives `(x, y)` in pixels. Detections with confidence < 0.25, or outside the court's y-bounds, are dropped. Result: `shuttle_traj` — a list of `{ frame, pos: [x,y]|None, confidence }`.

**Pass 2 — Pose inference (YOLO11x-pose, batch size 16)**
Frames are decoded at 512×288 and passed to YOLO in batches. Per-frame player detections are filtered to those whose body center or ankle midpoint falls within the court boundary (with 80px padding). Players are sorted top-to-bottom (far player first). Result: `player_tracking` — a list of `{ frame, players: [{ skeleton, box }] }`.

**Hit detection — trajectory signal (primary)**
`_detect_hits_from_traj()` splits the shuttle trajectory into continuous segments (gap > 4 frames = new segment). A gap of 8–50 frames between segments where the incoming and outgoing velocity vectors have a negative dot product (direction reversal) is classified as a hit. A secondary pass scans within segments for in-segment direction reversals using a 3-frame velocity window. Minimum 20-frame debounce between hits.

**Hit detection — pose signal (secondary)**
`_detect_hits_from_pose()` computes per-frame wrist speed by matching players frame-to-frame (within 100px). Frames where wrist speed > 22 px/frame and the shuttle is within 80px of a wrist are flagged as hits. This catches cases where TrackNet loses the shuttle but the swing is clearly visible.

**Hit merging**
`_merge_hits()` cross-validates both signals. Hits within 25 frames of each other in both signals are marked `confirmed: True` (both agree). Solo trajectory or solo pose hits are kept but marked `confirmed: False`. Final debounce of 20 frames with preference for confirmed hits.

**Shot classification**
The stroke classifier is the first of BST-0 → BST-CG-AP → LSTM → rules that loads (`inference.py`); see section 3 for the event fields each one sets. The LSTM and rules paths work as follows. If the LSTM is available, a 31-frame window (15 before + hit + 15 after) is built per hit. The hitter is identified as the player whose foot x-coordinate is closest to the shuttle x at the hit frame, and that player index is locked for the entire window. 13 COCO keypoints per frame (`[15, 7, 11, 13, 5, 9, 0, 16, 8, 12, 14, 6, 10]`) are extracted, zero-padded for missing frames, and passed to `ShotClassifierAdapter.classify()`. Without LSTM, a rule-based fallback uses post-hit shuttle trajectory (average vertical velocity and speed) to determine shot type: Clear, Lob, Smash, Drive, Drop, or Net.

**Output**
`analysis.json` is written to E2 at `outputs/{userId}/{videoId}/analysis.json`. Firestore is updated: `status: "done"`, `analysisJson` (the E2 key), `totalShots`, `duration`.

---

## 3. Data Structures

### Firestore document — `users/{uid}/videos/{videoId}`

```json
{
  "title": "string",
  "ownerId": "uid",
  "createdAt": "Timestamp",
  "updatedAt": "Timestamp",
  "status": "uploading | queued | running | done | failed",
  "progress": { "stage": "string", "pct": 0 },
  "input": {
    "e2Key": "uploads/{uid}/{videoId}/{filename}",
    "contentType": "video/mp4",
    "sizeBytes": 0,
    "originalFilename": "string"
  },
  "analysisJson": "outputs/{uid}/{videoId}/analysis.json",
  "duration": 0,
  "totalShots": 0,
  "artifacts": {
    "track": null, "events": null, "poses": null, "metrics": null,
    "heatmapImage": null, "heatmapPoints": null, "summary": null,
    "annotatedVideo": null, "thumbnail": null
  },
  "summary": {
    "durationSec": null, "totalShots": null, "shotCounts": {},
    "trackingQuality": { "ballVisiblePct": null }
  }
}
```

### `analysis.json` — the ML output payload

```json
{
  "summary": {
    "durationSec": 60.0,
    "totalShots": 42,
    "shotCounts": { "Clear": 12, "Smash": 8, "Drop": 7, "Drive": 6, "Net": 5, "Lob": 4 },
    "resolution": [512, 288],
    "truncated": false
  },
  "geometry": {
    "court": [[x,y], ...],
    "net": [[x,y], ...],
    "court_keypoints_6": [[TL], [TR], [ML], [MR], [BL], [BR]],
    "court_keypoints_35": [[x,y], ...]  // 7 rows × 5 cols grid
  },
  "events": [
    {
      "frame": 142,
      "location_px": [210, 180],
      "location_m": [3.1, 2.4],
      "type": "Clear",
      "detailType": "clear",       // BST-0 only
      "side": "Bottom",            // BST-0 / BST-CG-AP only
      "typeConfidence": 0.91,      // BST-0 / BST-CG-AP only
      "confirmed": true
    }
  ],
  "tracking": [
    {
      "frame": 0,
      "players": [
        {
          "skeleton": [[x,y], ...],  // 17 COCO keypoints
          "box": [x1, y1, x2, y2]
        }
      ]
    }
  ],
  "shuttle_debug": [
    { "frame": 0, "pos": [210, 180], "confidence": 0.87 }
  ]
}
```

Event fields depend on which stroke classifier loaded (section 2). With BST-0 (`bst_0_JnB_bone_merged.pt` on the volume, the default since #74) each hit carries `type`, `side` (`"Top"` far / `"Bottom"` near), `typeConfidence` and `detailType` (ShuttleSet's 10-class name, e.g. `"net shot"`), and hits whose top class is a serve are dropped. If BST-0 fails to load, BST-CG-AP sets the same fields except `detailType` and drops serve-classified hits too; the LSTM and rules set `type` only. `location_m` is re-derived from the BST side's player. BST-0 also computes 25 class probabilities per hit (`probs`); the webhook strips them before writing `analysis.json` (`upload_output` in `worker/app.py`), so they never reach the upload payload. Hit-detector fields (`confidence`, `source`, `confirmed`) are as before.

### Frontend TypeScript types (`types.ts`)

The `AnalysisData` interface mirrors the JSON payload. It also covers the full-match result (section 7), so fields the upload path always sets (`geometry`, `tracking`, `summary.resolution`) are optional there. `DashboardVideoCard` is the lean type derived from the Firestore doc for the dashboard list (id, title, date, status, totalShots, duration). `AnalysisShot` maps to each event in `events[]`.

---

## 4. End-to-End Data Flow (incorporating Notion research context)

The app's architecture is shaped by the research insight from VIRD (Lin et al., IEEE TVCG 2024) that coaches want *actionable, stroke-level* feedback rather than raw video. Every layer of the system is designed to progressively distill raw video into meaningful metrics.

**Raw video → E2 storage**
The user uploads an MP4 from the browser. The file travels directly from the browser to Cloudflare R2 via a presigned URL — never touching the Express server. The Firestore document is the single source of truth for job state throughout.

**E2 → Modal worker → analysis.json**
The worker downloads the video to `/tmp`, runs the full pipeline, and writes `analysis.json` back to E2 under `outputs/`. The Firestore doc is updated at key milestones (`running` on start, `done` or `failed` on finish), which the frontend reflects in real time.

**analysis.json → frontend visualization**
The `AnalysisPage` fetches a time-limited presigned URL from the backend, then downloads `analysis.json` directly from E2. The payload drives two primary views:

- **ShotHeatmap**: Takes `events[].location_m` — real-world meter coordinates on the 6.1m × 13.4m court — and normalizes them to percentages for SVG overlay. The `court_keypoints_35` (35-point grid) is projected via `projectToPercent()` to draw accurate court lines using 57 predefined edges. Each shot dot is colored by type and animated in.

- **LiveTracker** (planned): Uses `tracking[].players[].skeleton` and `shuttle_debug` to replay player movement and shuttle position frame-by-frame.

**Shot classification as the key insight layer**
Inspired by ShuttleSet (Wang et al., KDD 2023) — which provides 36,492 labeled strokes as the training backbone for most badminton ML — the pipeline classifies each detected hit into one of six shot types (Clear, Smash, Drop, Drive, Net, Lob). The upload path uses BST-0 (a skeleton + shuttle transformer over a 30-frame window, trained on ShuttleSet) when its weights are on the volume, which also gives each hit a `detailType` (ShuttleSet's 10 classes) and the hitter's `side`; it falls back to BST-CG-AP, then the LSTM over 31-frame skeleton sequences, then rules. The `shotCounts` summary in both the JSON and Firestore gives the dashboard its primary metric.

**Footwork analysis (planned, per research)**
The Frontiers in Sports (2026) paper on world-class footwork validates court coverage heatmaps and center court recovery distance as meaningful metrics. The `location_m` data on each shot event — and potentially `tracking[].players[].skeleton` ankle positions — feeds directly into this. The homography transform is the bridge: pixel coordinates become real meter positions on a standardized 6.1 × 13.4m court, enabling distance calculations that are comparable across different video angles.

**Comparison to pro players (V4 vision)**
The roadmap notes inspiration from swing.vision and ambition to compare a player's shot distribution and court coverage against world-class benchmarks. The ShuttleSet dataset and CoachAI-Plus (AAAI 2023) provide exactly this reference data — labeled strokes from professional matches that the LSTM was trained on, making the gap between "what you hit" and "what pros hit" a direct output of the existing data structures.

---

## 5. Pro profile data (static JSON)

Independent of the upload/analysis flow above. **Producer:** the offline build script `tools/pro_profiles/build.py` (see its README). **Consumer:** the frontend types in `frontend/badminton-ai/src/features/pros/types.ts`. No backend or Firestore involvement: the files are served with the SPA from `public/pro-data/` and only change when the script is re-run (CI fails if the committed JSON is stale). Keys are camelCase, files are compact and deterministic. Percentages are 0-100 rounded to 1 decimal, win rates and `typical` band values are whole numbers.

| File | Shape |
|---|---|
| `players/index.json` | `{ generatedFrom: <dataset sha>, players: [{ id, name, event: "MS"\|"WS", matches, ranked, photo }] }`, men first, then by name |
| `players/<id>.json` | `{ id, name, event, context: { matches, firstYear, lastYear, comparedWith }, summary: string\|null, photo, filters: [{ id, label, kind: "all"\|"tournament"\|"match", matches }], views: { <filterId>: View } }` |
| `tournaments/index.json` | `{ editions: [{ id, name, season, matches }] }`, season descending then name |
| `tournaments/<id>.json` | `{ id, name, season, matches: [{ id, round, date, winner: {id,name}, loser: {id,name}, games: [[a,b],...], incomplete: [setIndex,...] }], players: [{ id, name, event }] }` |

Filter ids are `all`, `t:<edition_id>` and `m:<match_id>`. `games` are each set's maximum `roundscore_A`/`roundscore_B` over its rows (not counted from rally winners), match winner's score first. `incomplete` lists the 0-based indexes of sets whose recorded score isn't a finished game (21+ with a 2-point lead, or 30); the UI marks them "incomplete in the data" and never pads them. A clip's `scoreLabel` is the score before the rally (`roundscore` is the score after it), so a set's first rally reads "game N at 0–0".

```ts
View    = { kind, shots, rallies, shotChoice: ShotRow[], bands: BandRow[], findings: Finding[], rallyBrowser: Clip[] }
ShotRow = { group, share, count, rank: number|null, of: number|null, typical }   // typical = all-match median
BandRow = { band: "short"|"mid"|"long", label, rallies, winRate: number|null, typical }  // winRate null under 30 rallies
Finding = { key, kind: "style"|"strength"|"weakness", claim, figure, comparison, tip: string|null, clips: Clip[] }
Clip    = { youtubeId, startSec, endSec, matchLabel, scoreLabel }
Photo   = { src: "/pro-data/photos/<id>.jpg", credit, sourceUrl, focusX, focusY }   // focus 0-100
```

Rules: `findings` is non-empty only in the `all` view. `rallyBrowser` holds the selection's rallies in filtered views; in the `all` view it is empty when there are findings, otherwise up to 5 example rallies (distinct matches first, then date, set, rally). Filtered views have `rank`/`of` null and `typical` from all matches. `context.comparedWith` is the comparison group size minus the player (39 grouped-shot-qualified players, so 38 for a ranked player). Players under 300 grouped shots are unranked: `ranked` false, all ranks null, no findings, `summary` null.

---

## 6. Doubles pair data (static JSON, CC BY-NC-SA)

Independent of sections 1-5. **Producer:** `tools/pro_profiles/doubles_build.py` (see its README), which verifies the DShuttleNet CSV checksums first. **Consumer:** the frontend pair pages and the doubles part of tournament pages. Files live under `public/pro-data/doubles/` only, so none mixes the singles (MIT/ShuttleSet) and doubles (CC BY-NC-SA 4.0, DShuttleNet from Kaggle) licences; `doubles/LICENSE` states the licence and attribution. Keys are camelCase, files are compact and deterministic, shares are 0-100 rounded to 1 decimal. The singles `diff -r` stale check in CI ignores `doubles/`; the doubles JSON is rebuilt and checked locally.

| File | Shape |
|---|---|
| `pairs/index.json` | `{ pairs: [{ id, event: "MD"\|"WD"\|"XD", players: [{ id, name, nationality }, x2], matches, ranked }] }`, by event, then the two names |
| `pairs/<id>.json` | `{ id, event, players: [{ id, name, nationality, gender }, x2], context: { matches, firstYear, lastYear, comparedWith }, ranked, summary: string\|null, filters: [{ id, label, kind: "all"\|"tournament"\|"match", matches }], views: { <filterId>: PairView } }` |
| `tournaments/index.json` | `{ editions: [{ id, name, season, doublesMatches }] }`, season descending then name |
| `tournaments/<edition>.json` | `{ id, name, season, matches: [{ id, event, round, date, winner: { id, names }, loser: { id, names }, games: [[a,b],...], incomplete: [setIndex,...] }], pairs: [{ id, event, names }] }` |
| `LICENSE` | CC BY-NC-SA 4.0, the footer attribution text and the Kaggle link |

Edition ids match singles (`tournaments/<edition>.json` outside `doubles/`). For editions shared with singles, `name` and `season` come from `content/tournaments.json`; doubles-only editions take them from `content/doubles_tournaments.json`. A tournament page loads both files and treats a missing one as "none". `names` is the pair's display name, "Chen / Jia" (partners sharing a last name use given names: "Benyapa / Nuntakarn Aimsaard"; when two pairs in the same event would get the same name, each partner not in both is shown by full name: "Baek / Lee So Hee", "Baek / Lee Yu Lim"). The same name is used in match filter labels and in `summary` (joined with "and"). Player `name` is player.csv's full name with all-capital words title-cased, except Western players stored surname-first, whose given-name-first form comes from `content/doubles_full_names.json` ("Kim Astrup"). `games` and `incomplete` follow the singles rules (each set's maximum score, match winner first; `incomplete` marks sets that are not a finished game). Filter ids are `all`, `t:<edition_id>` and `m:<match_id>`; a match label reads "<Tournament> <season> <round> against <opponent pair>".

```ts
PairView = {
  kind, rallies,                                  // rallies: those with a known winner
  serve:   { shortShare, winRate, thirdDown, placement: { centre, middle, wide, backCentre, backWide }, serves },
  receive: { attackShare, winRate, mix: { <shot type>: share }, returns },
  first4:  { share, winRate },
  mixed:   { serveBy: { man, woman }, receiveBy: { man, woman } } | null,   // XD only
  rest:    { attackShare, formationAttack, roles: [{ playerId, smashShare, netShare }, x2],
             pointsLost: { <reason>: share }, pointsWon: { winner, oppError } },
  ranks:   { <measureKey>: { rank, of, typical } },
  samples: { <measureKey> | "serve.placement" | "receive.mix" | "points.lost" | "points.won"
             | "mixed.serve_by" | "mixed.receive_by": number },   // mixed.* XD only
  typical: { <measureKey>: number },
  findings: Finding[]                              // singles Finding, clips always []
}
```

Rules:
- Every value is a number, or null below its minimum sample (30 serves, returns or rallies; distributions are null as a whole under 30). `serves` and `returns` are the counts behind `shortShare` and the return mix.
- `samples` holds the count behind every value, always present (also when the value is null): serves (`serve.short_share`, `serve.placement`, `mixed.serve_by`), rallies with a known winner that they served or received (`serve.win_rate`, `receive.win_rate`), their typed third shots (`serve.third_down`), returns (`receive.attack_share`, `receive.mix`, `mixed.receive_by`), rallies with a known winner (`first4.share`) and the 4-shot-or-fewer ones among them (`first4.win_rate`), their typed shots or shots with a formation after the serve (`rally.*`), and points with a known reason (`points.lost`, `points.won`). The page shows each stat with its own count.
- `measureKey` is one of `serve.short_share`, `serve.win_rate`, `serve.third_down`, `receive.attack_share`, `receive.win_rate`, `first4.share`, `first4.win_rate`, `rally.attack_share`, `rally.formation_attack`.
- `ranks` and `findings` are non-empty only in the `all` view of a ranked pair (2 or more matches); they are empty in tournament and match views and for unranked pairs. `ranked` is false and `summary` null for unranked pairs, and `comparedWith` is the event group size minus the pair (0 when unranked).
- `typical` is the median over the event's ranked pairs, always from all matches, and is present in every view (including filtered ones and unranked pairs' pages) so the UI can show "Typical pair x%". A measure no ranked pair has a value for is missing. In the `all` view of a ranked pair, `ranks[k].typical` equals `typical[k]`.

---

## 7. Full-match result (`worker/fullmatch`)

`fullmatch.run.analyze_full_match(video, ...)` analyses a whole broadcast: it cuts the video into overlapping chunks locally, runs the per-clip pipeline on each chunk on Modal (`analyze_chunk`), merges the chunks back into full-video frames, segments rallies (with serves), decodes alternating sides, re-classifies shots with the stacked classifier, and reads the score graphic locally. Its default return value is the product result below, built by `fullmatch.run.assemble_result`.

How it differs from the upload path (sections 1–4):

- Both run the same per-clip pipeline (`BadmintonPipeline.process_video()`, BST-0 first in the classifier chain); the full-match path adds the steps after it.
- It is a local module, called today by the eval (`eval_shuttleset.py --full-match`) and later by the #76 ingest command. The upload webhook still runs `BadmintonPipeline.process_video()` on one clip and writes the `analysis.json` above. The full-match path writes no Firestore state.
- Frames are full-video frames, not clip frames, and every frame has a seconds twin (`frame / fps`, rounded to milliseconds). The source video is deleted after ingest and match pages seek a YouTube embed by seconds.
- It has no `geometry`, `tracking` or `shuttle_debug`: an hour of per-frame data is far too large. Overlays can get a per-rally file later. Because of this, the current analysis page cannot render it yet.

Example (values from Axelsen v Christie; lists shortened):

```json
{
  "fps": 30.0,
  "totalFrames": 91050,
  "court": [[180, 123], [330, 123], [165, 175], [346, 175], [137, 264], [371, 264]],
  "summary": {
    "durationSec": 3035.0, "totalShots": 686, "serveCount": 34, "rallyCount": 62,
    "shotCounts": { "Net": 213, "Lob": 146, "Smash": 112, "Serve": 34, "Unknown": 8 },
    "resolution": [512, 288]
  },
  "rallies": [
    { "id": 1, "set": 1, "startFrame": 8126, "endFrame": 8234, "startSec": 270.867, "endSec": 274.467,
      "eventIndices": [0, 1, 2, 3], "scoreAfter": [0, 0], "winner": null, "nearPlayer": "B", "scoreRead": false }
  ],
  "sets": [ { "set": 1, "nearPlayer": "B", "finalScore": [21, 14] } ],
  "events": [
    { "frame": 8142, "timeSec": 271.4, "type": "Clear", "detailType": "clear", "typeConfidence": 0.945,
      "isServe": false, "side": "Bottom", "sideOverridden": false,
      "location_px": [332, 97], "location_m": [5.13, 12.09], "confidence": 0.997, "confirmed": true, "source": "hitnet" }
  ],
  "timings": { "cut_s": 52.6, "analyze_s": 969.1, "chunk_median_s": 136.3, "upload_mb": 1055.2,
               "segment_s": 0.4, "scoreboard_s": 14.2, "total_s": 1039.6 },
  "skippedSteps": [],
  "models": { "strokes": "BST0Adapter", "shotStack": "/models/shot_stack.joblib",
              "scoreboardTemplates": "/models/scoreboard_digits.npz" },
  "warnings": []
}
```

Fields (every key below is always present unless marked "optional"):

- `fps`: the probed video fps; all seconds use it. `totalFrames` and `summary.durationSec` cover the whole video. Both are always set by `analyze_full_match`; they are `null` only when `assemble_result` is called without `total_frames`.
- `court`: the match-wide mode of the per-chunk 6-point court (`[TL, TR, ML, MR, BL, BR]`), in pipeline pixels (`summary.resolution`), or `null` if no chunk found a court.
- `rallies[]`: rally order. `startFrame`/`endFrame` (and `startSec`/`endSec`) run from the rally's first hit (the serve when one was found) to the landing of the last hit, or to the last hit when the track does not show a landing. `eventIndices` index `events`. Every rally always carries every key. The scoreboard keys are `null` (and `scoreRead` false) when the scoreboard step did not run (no digit templates, or it failed):
  - `set`: 1-based set number.
  - `scoreAfter`: `[A, B]` after the rally, where A is the player who wins the match (ShuttleSet's convention). A rally whose score change was not read keeps the previous score, with `scoreRead: false` and `winner: null`.
  - `winner`: `"A"`, `"B"` or `null`.
  - `nearPlayer`: which player (`"A"` or `"B"`) is at the near (Bottom) end during this rally. This follows the end change at 11 in a deciding set.
- `sets[]`: `set`, `nearPlayer` at the start of the set, and `finalScore` `[A, B]`. Empty without the scoreboard.
- `events[]`: hits inside rallies, including serves, frame-sorted. Always present: `frame`, `timeSec`, `type`, `detailType`, `isServe`, `side`, `sideOverridden`, `location_px`, `location_m` (the last three may be `null`). Optional: `typeConfidence`, `confidence`, `confirmed`, `source`; inserted serves have no `typeConfidence` or `confirmed`, and their `confidence` is `null`.
  - `side`: `"Top"` is the far end and `"Bottom"` the near end, or `null` when unknown.
  - `sideOverridden`: true when the per-rally alternation decode overrode strong evidence for the other side.
  - `isServe`: true only for a serve found by the serve-onset detector and inserted at the start of a rally. It has `type: "Serve"` and `detailType: null` (serve length is not classified yet). These are the only serves in the result: BST-0 drops every detected hit whose top class is a serve, so a detected serve either disappears there (and comes back only if the serve-onset pass finds it) or, when BST-0 scored it as another stroke, stays an ordinary hit with `isServe: false` and that stroke's type.
  - `type`: never null. The 6 product classes (`Clear`, `Smash`, `Drop`, `Drive`, `Net`, `Lob`), `"Serve"`, or `"Unknown"` when no product class applies (no classifier decided, or the 10-class pick on a hit is a service).
  - `detailType`: ShuttleSet's 10 classes (`short service`, `long service`, `clear`, `drive`, `drop`, `lob`, `net shot`, `smash`, `push/rush`, `defensive shot`) or `null`. `type` is derived from the same pick, so the two never contradict. `push/rush` maps to Drive or Net. The stacked classifier re-types only hits that carry BST-0's 25 probabilities; a hit typed by a fallback classifier (BST-CG-AP, LSTM, rules) keeps its type.
  - `typeConfidence` (optional): the winning class's probability.
  - `location_px`: the shuttle at the hit, pipeline pixels. `location_m`: the hitter's feet in court metres, as in the upload path. Both `null` on inserted serves. `location_m` is also `null` when the side decode moved a hit to the other side: it was measured on the other player, and the decode has no tracks to re-measure it.
  - `confidence` (optional, may be `null`), `confirmed` (optional), `source` (optional; `"hitnet"`, `"serve_onset"`, ...): hit-detector provenance, as in the upload path.
- `summary`: `totalShots` counts all events, serves included. `shotCounts` is keyed by `type`, and `serveCount` and `rallyCount` count serves and rallies. `resolution` (optional) is the pipeline frame size `[w, h]`, present when a chunk reported it.
- `skippedSteps`: `[{ "step", "error" }]` for optional steps that raised and for chunks whose analysis failed (step `"chunk <id>"`; see below); `[]` when none did.
- `models`: what actually ran. `strokes` is the stroke classifier the chunks loaded (`"BST0Adapter"`, `"BSTStrokeClassifierAdapter"`, `"LSTM"`, `"rule-based"`; comma-joined if chunks differ; `null` when no chunk reported one). `shotStack` is the stacked classifier's model path when it ran, else `null` (no model found, or it failed). `scoreboardTemplates` is the digit-template path when the score graphic was read with it, else `null`. Model files are looked up in `$SHOT_STACK_PATH` / `$SCOREBOARD_TEMPLATES`, then `/models/` (Modal volume), then `~/.cache/shuttleye-eval/`.
- `warnings`: strings for conditions that make the result less trustworthy, `[]` when none. Today one: a source whose fps differs from 30 by more than 0.01 (`"source fps 25.000: models were trained at 30 fps; accuracy unmeasured"`). The model windows are fixed 30-fps frame counts and no eval covers 25/50 fps; resampling to 30 fps is planned in #76.
- `timings`: per-stage seconds (keys appear only for stages that ran). These are `probe_s`, `cut_s`, `verify_s`, `analyze_s`, `merge_s`, `segment_s` and `scoreboard_s`; `chunk_s` (per chunk) with its `chunk_min_s`, `chunk_median_s`, `chunk_max_s` and `chunk_sum_s`; `first_chunk_start_s` and `last_chunk_end_s` (relative to dispatch); `upload_mb`; and `total_s`.

Stripped from the internal result: per-frame `tracking` and `shuttle`, and `rawEvents` (every merged hit before segmentation). The chunk list, `verify`, `court_outliers` and the score timeline and score events also go. On events, `probs` (BST-0's 25 probabilities), `hitterM`, `receiverM` and `contactHeightM` (the stacked classifier's court-metre features), `detailId` and `serveScore` are dropped. These are inputs to later steps or diagnostics, not results, and they make up most of the size. The eval keeps the internal result (`analyze_full_match(..., internal=True)`) in its cache, so `--from-merged` can re-segment and re-score offline.

A chunk whose analysis raised (the chunk runner returns the exception in its place, e.g. Modal `starmap(..., return_exceptions=True)`) is treated as a chunk without a court and listed in `skippedSteps`; the rest of the match is merged as usual. Only when every chunk fails does the run raise.

The side decode, the shot stack, the scoreboard and the court check are optional post-GPU steps. If one raises, its partial changes are rolled back, the step is logged, recorded in `skippedSteps` (step name and error) and skipped, and the result is kept. A failed scoreboard leaves the scoreboard keys `null`, a failed side decode or stack leaves the earlier sides and types, and a failed court check leaves `court` `null`. `skippedSteps` tells a failure apart from a step that did not run by design (for example no digit templates, which leaves the scoreboard keys `null` with nothing in `skippedSteps`).

The frontend types this in `types.ts`: `AnalysisShot` (optional event fields), `AnalysisRally`, `AnalysisSet`, and the optional `AnalysisData` keys `fps`, `totalFrames`, `court`, `rallies`, `sets`, `timings`, `skippedSteps`, `models`, `warnings` and `summary.rallyCount` / `serveCount`. They are optional in TypeScript only because the upload path does not send them; in a full-match result they follow the presence rules above.

---

## 8. Match library (Firestore)

Pre-analysed BWF singles matches, built by `tools/library` (Admin SDK, run by hand) and read by signed-in users. Pro-profile JSON (section 5) is a separate, static copy. Numbered 8 because section 7 is the full-match result; the plan called this "7".

### `matches/{id}` (source of truth, built from a full-match result by `match_doc.py`)

```json
{
  "id": "string", "youtubeId": "string", "editionId": "string", "round": "string",
  "date": "YYYY-MM-DD",
  "players": { "A": {"id": "string", "name": "string", "event": "MS | WS"}, "B": {"id": "string", "name": "string", "event": "MS | WS"} },
  "winner": "A",
  "games": [{"a": 21, "b": 15}, {"a": 21, "b": 18}],
  "attributed": true,
  "status": "unpublished | published",
  "analyzer": { "models": {}, "warnings": [], "skippedSteps": [{"step": "string", "error": "string"}], "timings": { "ingest": {} } },
  "accuracy": { "hitF1": 0.0, "side": 0.0, "type6": 0.0, "ten": 0.0 },
  "summary": { "rallies": 0, "avgShots": 0.0, "durationSec": "0 | null" },
  "rallies": [{
    "n": 1, "set": "1 | null", "startSec": 0.0, "endSec": 0.0, "scoreBefore": "[0, 0] | null", "winner": "A | B | null",
    "shots": [{ "t": 0.0, "p": "A | B | null", "g": "group | null", "d": "detailType | null", "z": "zone | null", "s": false }]
  }],
  "insights": null
}
```

`A` is always the match winner (resolved at ingest). `players.*.event` is written by ingest (from `players.json`, or `--event` for a new player) and is what `profiles.people()` uses for a player not in `players.json` (else `MS`). `games` is `null` unless every set's final score was read; it is a list of maps (`a` = winner A, `b` = B) because Firestore forbids arrays nested in arrays. `library/index` matches and `tournaments/{id}` match rows use the same form. `attributed` is true only when every rally knows its near-side player and the analyzer agrees with the ingest's winner/near side: it is false (with a warning in `analyzer.warnings`) when rally 1's near player disagrees with `--near-first`, or when the read games show B winning more games than A. `publish` refuses an unattributed match and lists its warnings. `status` starts `unpublished`; `insights` is `null` until publish and is set back to `null` on unpublish. `analyzer.skippedSteps` lists the analysis steps that crashed and were skipped, as `{step, error}` objects. `summary.durationSec` is `null` when the frame count was not known, and a rally's `set` is `null` when the game number was not read. `scoreBefore` is `[0, 0]` for a game's first rally and `null` once an earlier rally of that game had no read score; clip score labels then say "game N, score not read" instead of a score.

`insights` once published is `{ "A": {"insights": Insights, "findings": Finding[]}, "B": {...} }`: that player's `Insights` over this match alone, plus up to four findings comparing it with their other published matches (none if they have no other match). `Finding` is `{key, kind, claim, figure, comparison, tip, clips[]}` as in section 5, with `tip` always `null`.

### `Insights` (six per-player insights, `insights.py`)

```json
{
  "phaseMix": { "start|mid|late": { "Smash|Net|Lift|Drop|Clear|Drive|Push...": 0.0, "shots": 0 } },
  "replies":  { "<opponent shot group>": { "<own reply group>": 0.0, "shots": 0 } },
  "zones":    { "front-left|front-right|mid-left|mid-right|rear-left|rear-right": 0.0, "shots": 0 },
  "tempo":    { "secPerShot": 0.0, "rallyShots": 0.0 },
  "bands":    [{ "band": "short|mid|long", "label": "string", "rallies": 0, "winRate": 0.0 }],
  "serve":    { "serves": 0, "shortShare": 0.0, "pointsWonShort": 0.0, "pointsWonLong": 0.0 },
  "smashWins":{ "smashes": 0, "winShare": 0.0 }
}
```

Shares are percentages to one decimal. A value is `null` below its minimum sample (50 shots for shares, 50 gaps for `secPerShot`, 30 rallies for `rallyShots`, 30 serves for serve rates, `MIN_BAND_RALLIES` per band).

`serve.serves` counts rallies whose first shot is a serve (`s` true) hit by the player. A serve's length is its `detailType` when that is `short service` / `long service` (ShuttleSet data); otherwise (analyzer serves carry no detail) it comes from the receiver's reply, shot 2, when the opponent hit it and its zone is known: a `rear-*` zone means long, `front-*` / `mid-*` short. Serves with no length are left out of `shortShare` and the points-won rates, whose minimum (30) counts serves with a length; the page says "Serve length not known for these serves" when there are 30+ serves but `shortShare` is still `null`.

### Derived documents (`profiles.py`, rebuilt from the published matches only)

- `players/{id}`: `{id, name, event, context: {matches, firstYear, lastYear, comparedWith}, summary, photo, filters[]}`. Each filter is `{id, label, kind: "all|tournament|match", matches}`; ids are `all`, `t:<editionId>`, `m:<matchId>`.
- `players/{id}/views/{filterId}`: `{kind, shots, rallies, insights: Insights, findings: Finding[], rallyBrowser: Clip[]}`. Only `all` carries findings (and only when at least 10 players have enough shots to be ranked against each other). `rallyBrowser` is every read rally for tournament and match views, and a sample of clips for `all` when it has no findings. Clip is `{youtubeId, startSec, endSec, matchLabel, scoreLabel}`.
- `tournaments/{editionId}`: `{id, name, season, matches[], players[{id, name, event}]}`.
- `library/index`: `{players: [{id, name, event, matches, ranked, photo}], editions: [{id, name, season, matches}], matches: [{id, editionId, round, date, players, games, youtubeId}]}`. Exists (possibly with empty lists) after any recompute.

### Security rules (`firestore.rules`, deployed by hand: `firebase deploy --only firestore:rules`)

- `users/{uid}`: owner read and write (`ensureUserDoc` creates/updates it on sign-in).
- `users/{uid}/videos/{videoId}`: owner read, no client writes.
- `matches/{id}`: read if signed in and (`status == "published"` or the `admin` custom claim is true).
- `players/**`, `tournaments/{id}`, `library/{id}`: read if signed in.
- Every library write is `false`; only the Admin SDK writes, bypassing rules.

### Commands (from `tools/`, with `GOOGLE_APPLICATION_CREDENTIALS` set to a service-account key outside the repo)

```bash
python -m library.publish publish <matchId>     # refuses unattributed matches
python -m library.publish unpublish <matchId>
python -m library.publish recompute             # rebuild everything; prints changed paths
python -m library.set_admin <uid>               # custom claim {admin: true}
```

After `set_admin`, sign out and back in so the browser's ID token carries the new claim. If `recompute` fails after `publish`, `unpublish` or a `--force` ingest already wrote the match, the command prints "Run `python -m library.publish recompute` to rebuild the library." and re-raises. A published match whose `editionId` is not in `tournaments.json` is left out of the library with a warning (ingest refuses such an edition up front, also on `--dry-run`).

`recompute` writes only documents whose content changed, deletes `players/*`, `players/*/views/*`, `tournaments/*` and `library/index` documents the new build no longer produces, and sets each published match's `insights` (`null` for unpublished). A second run returns nothing.

### Ingest (`python -m library.ingest`, from `tools/`)

```bash
python -m library.ingest <youtube-url> --players "<winner>" "<loser>" --near-first winner|loser \
    --tournament <editionId> --round <round> --date <YYYY-MM-DD> \
    [--event MS|WS] [--runner modal|local|merged:<fullmatch_*.json>] [--video <path>] \
    [--shuttleset <ShuttleSet match>] [--force] [--keep-video] [--dry-run]
python -m library.ingest --batch <file.json> [--dry-run]
```

- Match id `<editionId>-<winner id>-<loser id>`. Players resolve by name or alias against `pro_profiles/content/players.json`; a new player gets a slug id, is printed, and needs `--event`.
- Steps, each timed (seconds) into `analyzer.timings.ingest` as `download_s, analyse_s, segment_s, scoreboard_s[, accuracy_s]`: download (yt-dlp `bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]` into a temp dir; skipped with `--video`, which must exist), analyse, segment (`apply_segmentation`, with the shot stack when found), scoreboard (`apply_scoreboard`; a crash is recorded in `skippedSteps`), accuracy, then the store. A downloaded video is deleted afterwards, also on failure, unless `--keep-video`; a `--video` file is never deleted.
- Runners: `modal` cuts locally and analyses chunks with the deployed `badminton-ai-worker` / `BadmintonWorker.analyze_chunk` (starmap, up to 50 containers); `local` runs `analyze_chunk_clip` on this machine with the model files in `$SHUTTLEYE_MODELS_DIR` (default `~/.cache/shuttleye-models`); `merged:<path>` loads a saved merged result from the eval cache (`eval_shuttleset._load_merged`) and skips chunk analysis; it still needs the video for the scoreboard.
- An existing id is skipped unless `--force`. `--force` keeps the stored `status`; if it was `published`, `recompute` runs and the changed paths are printed (a re-run that is no longer attributed is stored `unpublished`, with a warning).
- `--shuttleset <match>` scores the internal result with the eval's own `_labels` + `_score_full_match` (labels fetched from GitHub, tolerance 3 frames) and stores `accuracy` (0-100, one decimal; `null` without `--shuttleset`, except that a `--force` re-run keeps the stored value). Mapping from the eval's whole-match OVERALL (hits after segmentation, serves excluded, `hits_after.excl_serves`): `hitF1` = `hits.f1`, `side` = `side.accuracy`, `type6` = `type.accuracy` (the six product groups), `ten` = `ten.accuracy` (`detailType`).
- Batch file: a JSON list of `{"url", "meta": {"players": [winner, loser], "nearFirst": "winner|loser", "tournament", "round", "date", "event"?}, "shuttleset"?, "runner"?, "video"?, "force"?}`. Stored ids are skipped, so a batch can be re-run; a failing entry is reported and the rest go on (exit code 1 if any failed).
- `--dry-run` prints each resolved meta, runner and source and touches nothing (no download, no store); it still checks player events, runner specs and `--video` paths. Without `--shuttleset`, a `--force` re-run keeps the previously stored `accuracy`.

---

## Summary: How data moves

```
Browser (React/TS)
  │
  ├─ POST /api/videos/init ──────────► Express backend
  │                                        │
  │  ◄── { videoId, uploadUrl } ───────────┤
  │                                        │ creates Firestore doc
  ├─ PUT video ──────────────────────► Cloudflare R2
  │
  ├─ POST /api/videos/:id/complete ──► Express backend
  │                                        │ marks "queued"
  │  ◄── { status: "queued" } ─────────────┤
  │                                        │ fire-and-forget POST
  │                                        ▼
  │                                   Modal Worker (T4 GPU)
  │                                        │ pulls video from E2
  │                                        │ TrackNet → shuttle traj
  │                                        │ YOLO pose → player skeletons
  │                                        │ hit detection + merge
  │                                        │ LSTM classification
  │                                        │ writes analysis.json → E2
  │                                        │ updates Firestore → "done"
  │
  ├─ Firestore onSnapshot ◄─ status "done" (real-time push)
  │
  ├─ GET /api/videos/:id/results ────► Express backend
  │  ◄── { status, urls: { analysisJson } }
  │
  ├─ GET analysis.json ──────────────► Cloudflare R2
  │  ◄── AnalysisData payload
  │
  └─ Renders ShotHeatmap + LiveTracker from AnalysisData
```
