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
If the LSTM is available, a 31-frame window (15 before + hit + 15 after) is built per hit. The hitter is identified as the player whose foot x-coordinate is closest to the shuttle x at the hit frame, and that player index is locked for the entire window. 13 COCO keypoints per frame (`[15, 7, 11, 13, 5, 9, 0, 16, 8, 12, 14, 6, 10]`) are extracted, zero-padded for missing frames, and passed to `ShotClassifierAdapter.classify()`. Without LSTM, a rule-based fallback uses post-hit shuttle trajectory (average vertical velocity and speed) to determine shot type: Clear, Lob, Smash, Drive, Drop, or Net.

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

### Frontend TypeScript types (`types.ts`)

The `AnalysisData` interface mirrors the JSON payload exactly. `DashboardVideoCard` is the lean type derived from the Firestore doc for the dashboard list (id, title, date, status, totalShots, duration). `AnalysisShot` maps to each event in `events[]`.

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
Inspired by ShuttleSet (Wang et al., KDD 2023) — which provides 36,492 labeled strokes as the training backbone for most badminton ML — the pipeline classifies each detected hit into one of six shot types (Clear, Smash, Drop, Drive, Net, Lob) using the LSTM over 31-frame skeleton sequences. The `shotCounts` summary in both the JSON and Firestore gives the dashboard its primary metric.

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
