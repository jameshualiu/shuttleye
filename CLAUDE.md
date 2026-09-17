# CLAUDE.md

@AGENTS.md

This file provides technical context and project-specific guidance for Claude Code working in this repository.

## Project overview

Badminton AI Analyst: users upload match video, a Python CV/ML pipeline extracts shuttle tracking, court geometry, player poses, hit events, and shot-type classification, and the frontend visualizes the results.

The project consists of three independently deployed pieces:

- `frontend/badminton-ai` — React 19 + TypeScript + Vite SPA with Firebase Auth and Tailwind v4
- `backend` — Node/Express 5 API for presigned uploads, Firestore state, and triggering processing
- `worker` — Python ML pipeline deployed to Modal with a T4 GPU

Read `data-flow.md` at the repository root before making cross-cutting changes. It is the source of truth for the upload → processing → results flow, Firestore schema, and `analysis.json` payload shape.

## Commands

### Frontend (`frontend/badminton-ai`)

```bash
npm run dev       # Vite dev server (localhost:5173)
npm run build     # tsc -b && vite build
npm run lint      # eslint .
```

### Backend (`backend`)

```bash
npm run dev       # nodemon server.js (localhost:3000)
npm start         # node server.js
```

### Worker (`worker`)

```bash
pip install -r requirements.txt
pytest worker/tests/
pytest worker/tests/test_shuttle_in_court.py -v
```

Worker tests deliberately reimplement small pieces of `pipeline.py` locally because importing the runtime pipeline requires heavy ML dependencies and model weights. When changing geometry or hit-detection logic, update the corresponding mirrored test logic in `worker/tests/`.

### Full stack

```bash
docker compose up --build
```

Docker Compose runs the frontend and backend only. The worker runs on Modal because it requires a GPU and model volume.

## Architecture

### Backend

The backend uses manual dependency injection:

```text
VideoRepository → VideoService → VideoController → Express routes
```

`server.js` wires the dependencies. Authentication is handled by `authMiddleware`, which verifies Firebase JWTs and sets `req.user.uid`. `AppError` and `errorHandler` provide centralized error handling, while `asyncHandler` forwards rejected promises to Express.

The backend does not handle raw video bytes. Browser/worker uploads and downloads go directly through the S3-compatible object storage layer using presigned URLs.

The backend owns the Firestore video document as the source of truth for processing state and triggers the Modal worker through `MODAL_WEBHOOK_URL`.

### Worker

`worker/app.py` is the Modal entry point and calls `BadmintonPipeline.process_video()` in `worker/pipeline.py`.

Model adapters live in `worker/detectors/` and are composed by `worker/inference.py`. Optional learned models must preserve the existing fallback pattern:

- Shuttle tracking: TrackNetV3 when available, otherwise legacy TrackNet
- Hit detection: learned CNN when available, otherwise the heuristic detector
- Shot classification: BST classifier → LSTM → rule-based fallback

Optional model paths should gracefully fall back rather than failing the entire pipeline.

`process_video()` currently runs the major stages in order:

```text
court/homography
→ shuttle tracking
→ pose inference
→ hit detection
→ hit merging
→ shot classification
→ optional refinement
```

The pipeline intentionally uses different video resolutions for different tasks. Preserve the explicit coordinate scaling between the low-resolution shuttle/homography reader and the HD pose reader.

Training/reference code under `worker/train/` and `.bst-ref/` is not part of the runtime path.

### Frontend

Analysis functionality lives under `src/features/analysis/`.

- `videoService.ts` handles API/upload orchestration
- `types.ts` contains the `AnalysisData` contract
- `hooks/` contains analysis-related hooks
- `components/` contains analysis UI
- `src/lib/firebase.ts` contains Firebase configuration
- `src/auth/` contains authentication logic

The dashboard uses Firestore `onSnapshot` for real-time video status updates. The analysis page obtains presigned URLs from the backend and reads `analysis.json` directly from object storage.

`src/lib/result.ts` defines the `Result<T, E>` discriminated union. Prefer it over exceptions for expected failure paths where callers should explicitly branch on success/failure.

The current UI theme is blue-black (`theme-ai-saas`) with `#3B82F6` as the primary color. Tailwind v4 configuration lives in `src/styles/tailwind.css`.

## Working across the stack

Frontend, backend, and worker communicate through shared Firestore state and the `analysis.json` contract rather than direct service-to-service calls.

When changing a shared data shape or contract, check all affected layers:

1. `worker/pipeline.py` — producer
2. `frontend/badminton-ai/src/features/analysis/types.ts` — consumer/type definition
3. Backend/worker Firestore writes — persisted state

Update `data-flow.md` whenever a shared contract changes.

Do not assume all video coordinates use the same resolution; preserve the existing scaling between pipeline stages.

## Git conventions

Use feature branches and pull requests for changes. Do not push directly to `main`.

All commits must follow Conventional Commits, for example:

```text
feat(worker): add hit detection fallback
fix(backend): validate upload filenames
test(frontend): add analysis hook coverage
```