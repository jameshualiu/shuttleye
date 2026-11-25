"""BST stroke-type classification for detected hits.

Two adapters with the same classify_hits contract:
  - BST0Adapter (preferred): BST-0 fed COURTSIDE's input recipe, built in
    fullmatch/bst_inputs.py (+-15 frame window, no court position input)
  - BSTStrokeClassifierAdapter (fallback): BST-CG-AP, described below

The 25-class index contract (BONE_PAIRS, MERGED_TYPES_ZH, index -> side/type
decoding via class_label) lives in fullmatch/bst_inputs.py for both.

BSTStrokeClassifierAdapter wraps the pretrained BST-CG-AP checkpoint (25 merged ShuttleSet classes,
"between 2 hits with max limits" segmentation, seq_len=100). Replaces the
6-class LSTM shot classifier -- BST's raw 12-class (+Unknown) output is
collapsed onto that same 6-class taxonomy via PRODUCT_TYPE below, since
that's what the frontend and analysis.json schema expect; serve classes
have no home in the 6-class taxonomy and are dropped from the output.

Input construction mirrors the official preprocessing
(prepare_train_on_shuttleset.py, MIT License):
  - joints: bbox-relative, normalized by bbox diagonal, center-aligned
  - position: feet midpoint -> court coords (homography) -> [0,1] by court rect
  - shuttle: normalized by frame resolution (512x288 pipeline space)
  - player order: Top (smaller court y) first; frames without both players
    are all-zero
"""

import numpy as np
import torch

from detectors.bst_model import BST_0, BST_CG_AP
from fullmatch import bst_inputs

SEQ_LEN = 100
N_JOINTS = bst_inputs.N_JOINTS
BONE_PAIRS = bst_inputs.BONE_PAIRS
FRAME_W, FRAME_H = 512.0, 288.0
COURT_W, COURT_H = 6.1, 13.4   # pipeline homography target (meters)

# Merged ShuttleSet classes: index 0 unknown, 1-12 Top_, 13-24 Bottom_
MERGED_TYPES_ZH = bst_inputs.MERGED_TYPES_ZH
TYPE_EN = {
    "放小球": "Net Drop",
    "擋小球": "Block",
    "殺球": "Smash",
    "挑球": "Lift",
    "長球": "Clear",
    "平球": "Drive",
    "切球": "Drop",
    "推球": "Push",
    "撲球": "Net Kill",
    "勾球": "Cross-court Net",
    "發短球": "Short Serve",
    "發長球": "Long Serve",
}

# Collapses BST's 12-class TYPE_EN vocabulary onto the product's 6-class
# taxonomy (Clear/Smash/Drop/Drive/Net/Lob) that the frontend (shotUtils.ts
# SHOT_COLORS) and analysis.json schema (data-flow.md) expect. TYPE_EN itself
# stays untouched -- it's still needed at full granularity to score BST
# against ShuttleSet ground truth. None = drop the hit: BST's two serve
# classes aren't part of this taxonomy, consistent with hit-detection
# already excluding serves from its own ground truth/training labels
# upstream (see train/extract_features.py's SERVICE_TYPES_ZH).
PRODUCT_TYPE = {
    "Net Drop": "Net",
    "Block": "Net",
    "Smash": "Smash",
    "Lift": "Lob",
    "Clear": "Clear",
    "Drive": "Drive",
    "Drop": "Drop",
    "Push": "Drive",
    "Net Kill": "Net",
    "Cross-court Net": "Net",
    "Short Serve": None,
    "Long Serve": None,
}


def _normalize_joints(joints: np.ndarray, bbox: np.ndarray) -> np.ndarray:
    """joints (m, J, 2), bbox (m, 4) -> bbox-diagonal normalized, center-aligned."""
    dist = np.linalg.norm(bbox[:, 2:] - bbox[:, :2], axis=-1, keepdims=True)
    dist = np.where(dist > 0, dist, 1.0)

    arr_x = joints[:, :, 0]
    arr_y = joints[:, :, 1]
    x_n = np.where(arr_x != 0.0, (arr_x - bbox[:, None, 0]) / dist, 0.0)
    y_n = np.where(arr_y != 0.0, (arr_y - bbox[:, None, 1]) / dist, 0.0)

    center = (bbox[:, :2] + bbox[:, 2:]) / 2
    c_n = (center - bbox[:, :2]) / dist
    x_n = x_n - c_n[:, None, 0]
    y_n = y_n - c_n[:, None, 1]
    return np.stack((x_n, y_n), axis=-1)


def _fit_seq_len(joints, pos, shuttle, target_len=SEQ_LEN):
    """Subsample/pad to target_len (same as make_seq_len_same)."""
    video_len = len(pos)
    if video_len > target_len:
        need_padding = (video_len % target_len) > (target_len // 2)
        stride = video_len // target_len + int(need_padding)
        joints = joints[::stride][:target_len]
        pos = pos[::stride][:target_len]
        shuttle = shuttle[::stride][:target_len]
        new_len = len(pos)
        if need_padding:
            pad = target_len - new_len
            joints = np.pad(joints, ((0, pad), (0, 0), (0, 0), (0, 0)))
            pos = np.pad(pos, ((0, pad), (0, 0), (0, 0)))
            shuttle = np.pad(shuttle, ((0, pad), (0, 0)))
    else:
        new_len = video_len
        pad = target_len - new_len
        joints = np.pad(joints, ((0, pad), (0, 0), (0, 0), (0, 0)))
        pos = np.pad(pos, ((0, pad), (0, 0), (0, 0)))
        shuttle = np.pad(shuttle, ((0, pad), (0, 0)))
    return joints, pos, shuttle, new_len


class BSTStrokeClassifierAdapter:
    def __init__(self, weights_path: str, device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        in_dim = (N_JOINTS + len(BONE_PAIRS)) * 2   # JnB_bone, 2D -> 72
        self._model = BST_CG_AP(in_dim=in_dim, seq_len=SEQ_LEN, n_class=25,
                                depth_tem=2, depth_inter=1)
        state = torch.load(weights_path, map_location=self.device, weights_only=True)
        self._model.load_state_dict(state)
        self._model.to(self.device).eval()
        print(f"[bst] BSTStrokeClassifierAdapter loaded: {weights_path} (device={self.device})")

    # -- segment input construction -------------------------------------------

    def _build_segment(self, start_f, end_f, shuttle_traj, tracking_by_frame,
                       pixel_to_meters):
        t_len = end_f - start_f + 1
        joints = np.zeros((t_len, 2, N_JOINTS, 2), dtype=np.float32)
        pos = np.zeros((t_len, 2, 2), dtype=np.float32)
        shuttle = np.zeros((t_len, 2), dtype=np.float32)

        for i, f in enumerate(range(start_f, end_f + 1)):
            s = shuttle_traj[f] if f < len(shuttle_traj) else None
            if s and s.get("pos") is not None:
                shuttle[i, 0] = s["pos"][0] / FRAME_W
                shuttle[i, 1] = s["pos"][1] / FRAME_H

            players = tracking_by_frame.get(f, [])
            if len(players) < 2:
                continue   # all-zero frame, same as BST's failed frames

            two = players[:2]   # pipeline sorts top player first (box y)
            kp = np.array([p["skeleton"] for p in two], dtype=np.float32)
            bbox = np.array([p["box"] for p in two], dtype=np.float32)
            joints[i] = _normalize_joints(kp, bbox)

            for m, p in enumerate(two):
                sk = p["skeleton"]
                ankles = [sk[idx] for idx in (15, 16)
                          if len(sk) > idx and (sk[idx][0] or sk[idx][1])]
                if not ankles:
                    continue
                fx = float(np.mean([a[0] for a in ankles]))
                fy = float(np.mean([a[1] for a in ankles]))
                court = pixel_to_meters(fx, fy)
                if court is not None:
                    pos[i, m, 0] = court[0] / COURT_W
                    pos[i, m, 1] = court[1] / COURT_H

        return _fit_seq_len(joints, pos, shuttle)

    # -- main entry point ------------------------------------------------------

    def classify_hits(self, hits: list, shuttle_traj: list, player_tracking: list,
                      fps: float, pixel_to_meters) -> list:
        """Assign stroke type + hitter side to each hit (mutates and returns hits).

        Segment per hit = previous hit .. next hit + 0.25s, clamped to
        +-1.5s around the hit ("between_2_hits_with_max_limits").
        """
        if not hits:
            return hits

        tracking_by_frame = {e["frame"]: e["players"] for e in player_tracking}
        total = len(shuttle_traj)
        t_half = int(fps) // 2          # 0.5 s
        eps = t_half // 2               # 0.25 s
        limit = int(fps) * 3 // 2       # 1.5 s

        frames = [h["frame"] for h in hits]
        batch_jnb, batch_pos, batch_shuttle, batch_len = [], [], [], []

        for i, f in enumerate(frames):
            start_f = frames[i - 1] if i > 0 else f - t_half
            end_f = (frames[i + 1] + eps) if i < len(frames) - 1 else f + t_half
            start_f = max(start_f, f - limit, 0)
            end_f = min(end_f, f + limit + eps, total - 1)

            joints, pos, shuttle, v_len = self._build_segment(
                start_f, end_f, shuttle_traj, tracking_by_frame, pixel_to_meters)

            bones = bst_inputs.create_bones(joints)
            jnb = np.concatenate((joints, bones), axis=-2)   # (s, 2, J+B, 2)
            jnb = jnb.reshape(SEQ_LEN, 2, -1)                # flatten joints*xy

            batch_jnb.append(jnb)
            batch_pos.append(pos)
            batch_shuttle.append(shuttle)
            batch_len.append(v_len)

        jnb_t = torch.from_numpy(np.stack(batch_jnb)).to(self.device)
        pos_t = torch.from_numpy(np.stack(batch_pos)).to(self.device)
        shuttle_t = torch.from_numpy(np.stack(batch_shuttle)).to(self.device)
        len_t = torch.tensor(batch_len, dtype=torch.long, device=self.device)

        with torch.no_grad():
            logits = self._model(jnb_t, shuttle_t, pos_t, len_t)
            probs = torch.softmax(logits, dim=1).cpu().numpy()

        for hit, p in zip(hits, probs):
            idx = int(p.argmax())
            conf = float(p[idx])
            side, zh, _ = bst_inputs.class_label(idx)
            hit["type"] = "Unknown" if zh is None else PRODUCT_TYPE[TYPE_EN[zh]]
            hit["side"] = side
            hit["typeConfidence"] = round(conf, 3)

        # Drop serve-classified hits -- PRODUCT_TYPE maps them to None (see
        # comment above PRODUCT_TYPE for why).
        hits = [h for h in hits if h["type"] is not None]

        counts = {}
        for h in hits:
            counts[h["type"]] = counts.get(h["type"], 0) + 1
        print(f"[bst] Stroke types assigned: {counts}")
        return hits


class BST0Adapter:
    """BST-0 (bst_0_JnB_bone_merged.pt, 2D poses) fed COURTSIDE's input recipe.

    Same classify_hits contract as BSTStrokeClassifierAdapter, plus per hit
    "probs" (25 floats, bst_inputs.CLASSES order) and "detailType" (the
    10-class name, e.g. "net shot"). Inputs are built in fullmatch/bst_inputs.py
    (+-15 frames around the hit, bbox-normalised joints + bones, shuttle / frame
    size, players [Top, Bottom]).
    """

    # Pipeline shuttle and player coordinates are 512x288; COURTSIDE's inputs
    # were 1280x720, so tracks and shuttle are scaled by 2.5 in x and y first.
    PIPELINE_SIZE = (512, 288)

    def __init__(self, weights_path: str, device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = BST_0(in_dim=bst_inputs.IN_DIM, seq_len=bst_inputs.SEQ_LEN,
                            n_class=len(bst_inputs.CLASSES), depth_tem=2, depth_inter=1)
        state = torch.load(weights_path, map_location=self.device, weights_only=True)
        self._model.load_state_dict(state)
        self._model.to(self.device).eval()
        print(f"[bst0] BST0Adapter loaded: {weights_path} (device={self.device})")

    def probs_at(self, hit_frames: list, shuttle_traj: list, player_tracking: list,
                 frame_size=(1280, 720)) -> np.ndarray:
        """Softmax probabilities (n, 25) for windows centred on hit_frames."""
        n_class = len(bst_inputs.CLASSES)
        if not hit_frames:
            return np.zeros((0, n_class), dtype=np.float32)
        shuttle_by_frame = {s["frame"]: s.get("pos") for s in shuttle_traj}
        players_by_frame = {e["frame"]: e["players"] for e in player_tracking}

        windows = [bst_inputs.build_window(int(f), shuttle_by_frame, players_by_frame,
                                           src_size=self.PIPELINE_SIZE, dst_size=frame_size)
                   for f in hit_frames]
        jnb = torch.from_numpy(np.stack([w[0] for w in windows])).to(self.device)
        shuttle = torch.from_numpy(np.stack([w[1] for w in windows])).to(self.device)
        video_len = torch.full((len(windows),), bst_inputs.SEQ_LEN,
                               dtype=torch.long, device=self.device)
        with torch.no_grad():
            logits = self._model(jnb, shuttle, video_len)
            return torch.softmax(logits, dim=1).cpu().numpy()

    def classify_hits(self, hits: list, shuttle_traj: list, player_tracking: list,
                      fps: float, pixel_to_meters) -> list:
        """Assign type/side/typeConfidence/detailType/probs to each hit (drops
        serve-classified hits, like BSTStrokeClassifierAdapter). fps and
        pixel_to_meters are unused: BST-0 has a fixed 30-frame window and no
        court-position input."""
        if not hits:
            return hits
        probs = self.probs_at([h["frame"] for h in hits], shuttle_traj, player_tracking)

        for hit, p in zip(hits, probs):
            idx = int(p.argmax())
            side, zh, ten = bst_inputs.class_label(idx)
            hit["side"] = side
            hit["type"] = "Unknown" if zh is None else PRODUCT_TYPE[TYPE_EN[zh]]
            hit["detailType"] = ten
            hit["typeConfidence"] = round(float(p[idx]), 3)
            hit["probs"] = [round(float(x), 4) for x in p]

        hits = [h for h in hits if h["type"] is not None]

        counts = {}
        for h in hits:
            counts[h["type"]] = counts.get(h["type"], 0) + 1
        print(f"[bst0] Stroke types assigned: {counts}")
        return hits
