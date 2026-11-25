# Library tools

Ingest, publish and the local analysis runner for the pre-analysed BWF match library.

## Local runner (`--runner local`)

Runs the same per-chunk analysis as the Modal worker (1800-frame chunks, sequentially) on this machine.

Setup (once):

```bash
# venv outside the repo; Python 3.12 works (3.11 not installed here)
python3.12 -m venv ~/.cache/shuttleye-local-venv
V=~/.cache/shuttleye-local-venv/bin
grep -v '^decord' worker/requirements.txt > /tmp/req-nodecord.txt   # decord has no macOS arm64 wheel
$V/pip install -r /tmp/req-nodecord.txt modal                       # worker/app.py imports modal for MODEL_TARGETS
# decord stand-in (cv2-backed, tools/library/decord_shim); copy into the venv's site-packages
cp -R tools/library/decord_shim/decord "$($V/python -c 'import site;print(site.getsitepackages()[0])')/"

# weights (never committed); the file list is worker/app.py MODEL_TARGETS + OPTIONAL_MODEL_TARGETS
mkdir -p ~/.cache/shuttleye-models && cd ~/.cache/shuttleye-models
for f in ball_track.pt court_kpRCNN.pth net_kpRCNN.pth yolo11x-pose.pt 15Matches_LSTM.onnx \
         TrackNet_best.pt InpaintNet_best.pt hit_detector_v3.onnx bst_stroke_classifier.pt bst_0_JnB_bone_merged.pt; do
  modal volume get badminton-models $f .
done
```

Commands (from `tools/`, with the venv's python):

```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/keys/shuttleye-service-account.json   # ingest/publish only
# time one chunk and estimate a 50-minute match, comparing hits with a saved Modal result
$V/python -m library.time_local <match.mp4> --start-frame 19140 --compare-merged <fullmatch_*.json>
# ingest with the local runner
$V/python -m library.ingest <url> ... --runner local
```

`SHUTTLEYE_MODELS_DIR` overrides the weights folder. The worker takes `device="mps"` for the torch
models: tracknet_v3 (+ InpaintNet) and BST-0 run on MPS. The court and net keypoint R-CNNs fail on MPS
("Placeholder tensor is empty") and are rebuilt on CPU at their first call; the ONNX models (LSTM, hit
detector) are CPU only; YOLO pose runs on MPS (ultralytics warns about a known MPS pose bug).
`time_local --compare-merged` saves its agreement to `~/.cache/shuttleye-models/local-check.json` (keyed by device);
below 95% `--runner local` prints a warning that results differ from Modal.

### Measured on the M5 Pro (24 GB), 2026-11-25

Viktor Axelsen vs Jonatan Christie, Thailand Open 2021 QF, frames 19140-20939 (one 60 s chunk, court found).

| | |
|---|---|
| Local, 1 chunk | 392.7 s (model load 2.1 s extra) |
| 50-minute match (52 chunks) | about 340 min (5.7 h) |
| Hit agreement with saved Modal result | 92.9% (39 of 42 saved hits have a local hit within 3 frames) |

Agreement is below 95%, so `--runner local` warns. A chunk with no court (frames 9000-10799, an intro/replay
stretch the saved run also found no court in) took 326 s on CPU court search alone.

Agreement is one-directional (saved hits that have a local hit, not the reverse) and measured on a single
chunk against the merged full-match result, so chunk-boundary and merge effects (overlap dedupe) are part of
the gap; it is a rough check, not an accuracy score.
