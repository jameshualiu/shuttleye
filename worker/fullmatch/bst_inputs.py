"""BST-0 input building: pure numpy, no torch.

Ported from COURTSIDE's bst_eval.py (jayclim/BadmintonAI, commit
5c356f05cde0ed90c75316c133e0aba495e5232b, MIT License), which feeds the
pretrained BST-0 (bst_0_JnB_bone_merged.pt) the inputs it was trained on:

- window: +-15 frames around the hit, SEQ_LEN = 30 (frames hit-15 .. hit+14)
- joints: 17 COCO keypoints per player, offset by bbox top-left and scaled by
  the bbox diagonal; zeros stay zero (= missing). Players ordered
  [far = Top, near = Bottom]. Plus 19 COCO bones -> JnB (t, 2, 36 * 2)
- shuttle: pixel position / video size (1280x720); invisible -> 0

Class order is BST's merged set: '未知球種' + 12 Top_ + 12 Bottom_ types
(get_merged_stroke_types in the BST repo).
"""
import numpy as np

SEQ_LEN, HALF = 30, 15
N_JOINTS = 17
# get_bone_pairs('coco') in BST's preparing_data/shuttleset_dataset.py
BONE_PAIRS = [
    (0, 1), (0, 2), (1, 2), (1, 3), (2, 4),   # head
    (3, 5), (4, 6),                            # ears to shoulders
    (5, 7), (7, 9), (6, 8), (8, 10),           # arms
    (5, 6), (5, 11), (6, 12), (11, 12),        # torso
    (11, 13), (13, 15), (12, 14), (14, 16),    # legs
]
IN_DIM = (N_JOINTS + len(BONE_PAIRS)) * 2      # 72

MERGED_TYPES_ZH = [
    "放小球", "擋小球", "殺球", "挑球",
    "長球", "平球", "切球", "推球",
    "撲球", "勾球", "發短球", "發長球",
]
CLASSES = (["未知球種"] + [f"Top_{t}" for t in MERGED_TYPES_ZH]
           + [f"Bottom_{t}" for t in MERGED_TYPES_ZH])

# BST merged type -> the 10 canonical classes; same values as
# train/eval_scoring.ZH_TO_TEN (COURTSIDE's ShuttleSet CN->EN map).
MERGED_TO_TEN = {
    "放小球": "net shot",
    "擋小球": "defensive shot",
    "殺球": "smash",
    "挑球": "lob",
    "長球": "clear",
    "平球": "drive",
    "切球": "drop",
    "推球": "push/rush",
    "撲球": "push/rush",
    "勾球": "net shot",
    "發短球": "short service",
    "發長球": "long service",
}


def class_label(idx: int):
    """Class index -> (side 'Top'|'Bottom'|None, merged zh type, 10-class name)."""
    if idx == 0:
        return None, None, None
    zh = MERGED_TYPES_ZH[(idx - 1) % 12]
    return ("Top" if idx <= 12 else "Bottom"), zh, MERGED_TO_TEN[zh]


def normalize_joints(joints: np.ndarray, bbox: np.ndarray) -> np.ndarray:
    """COURTSIDE bst_eval._normalize_joints: joints (m, J, 2), bbox (m, 4) as
    x1,y1,x2,y2 -> offset by bbox top-left, scaled by bbox diagonal. Zeros
    stay zero (= missing)."""
    joints = np.asarray(joints, dtype=np.float32)
    bbox = np.asarray(bbox, dtype=np.float32)
    dist = np.linalg.norm(bbox[:, 2:] - bbox[:, :2], axis=-1, keepdims=True)
    dist = np.where(dist > 0, dist, 1.0)
    out = np.zeros_like(joints)
    for d in (0, 1):
        v = joints[:, :, d]
        out[:, :, d] = np.where(v != 0.0, (v - bbox[:, None, d]) / dist, 0.0)
    return out


def window_frames(hit_frame: int, half: int = HALF) -> list:
    """The 2*half frames BST-0 sees for a hit. COURTSIDE takes hit-15..hit+15
    (31 frames) and make_seq_len_same(30) keeps the first 30 (stride 1)."""
    return list(range(hit_frame - half, hit_frame + half))


def shuttle_input(points, src_size, dst_size) -> np.ndarray:
    """Shuttle points in src_size pixels -> (n, 2) scaled to dst_size, then
    divided by dst_size. None (invisible) -> 0."""
    sx = dst_size[0] / src_size[0]
    sy = dst_size[1] / src_size[1]
    out = np.zeros((len(points), 2), dtype=np.float32)
    for i, p in enumerate(points):
        if p is None:
            continue
        out[i, 0] = p[0] * sx / dst_size[0]
        out[i, 1] = p[1] * sy / dst_size[1]
    return out


def create_bones(joints: np.ndarray) -> np.ndarray:
    """BST create_bones: joints (t, m, J, 2) -> (t, m, B, 2), zero where
    either end is missing."""
    bones = []
    for start, end in BONE_PAIRS:
        s = joints[:, :, start, :]
        e = joints[:, :, end, :]
        bones.append(np.where((s != 0.0) & (e != 0.0), e - s, 0.0))
    return np.stack(bones, axis=-2)


def _box_centre(p):
    b = p["box"]
    return np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])


def assign_slots(frames_players: list) -> list:
    """Per frame, [Top player | None, Bottom player | None].

    Two players keep the pipeline's order (sorted Top first by court y). A lone
    player goes to whichever slot's box centre, in the nearest frame (in this
    list) that had both players, is closer; with no such frame it is dropped.
    COURTSIDE has persistent far/near track ids; this is our substitute.
    """
    two = [i for i, ps in enumerate(frames_players) if len(ps) >= 2]
    out = []
    for i, ps in enumerate(frames_players):
        if len(ps) >= 2:
            out.append([ps[0], ps[1]])
        elif len(ps) == 1 and two:
            ref = frames_players[min(two, key=lambda k: abs(k - i))]
            c = _box_centre(ps[0])
            d_top = np.linalg.norm(c - _box_centre(ref[0]))
            d_bottom = np.linalg.norm(c - _box_centre(ref[1]))
            out.append([ps[0], None] if d_top <= d_bottom else [None, ps[0]])
        else:
            out.append([None, None])
    return out


def build_window(hit_frame: int, shuttle_by_frame: dict, players_by_frame: dict,
                 src_size=(512, 288), dst_size=(1280, 720)):
    """(JnB (SEQ_LEN, 2, 72), shuttle (SEQ_LEN, 2)) for one hit.

    shuttle_by_frame: frame -> (x, y) | None in src_size pixels.
    players_by_frame: frame -> [player, ...] (pipeline order, Top first), each
    {"box": [x1,y1,x2,y2], "skeleton": [[x,y]*17]} in src_size pixels.
    Tracks and shuttle are scaled src -> dst first so values are in the 1280x720
    space COURTSIDE used (joint normalisation is scale-invariant; the shuttle
    is then divided by dst_size).
    """
    frames = window_frames(hit_frame)
    sx = dst_size[0] / src_size[0]
    sy = dst_size[1] / src_size[1]
    scale = np.array([sx, sy], dtype=np.float32)

    joints = np.zeros((SEQ_LEN, 2, N_JOINTS, 2), np.float32)
    slots = assign_slots([players_by_frame.get(f, []) for f in frames])
    for t, pair in enumerate(slots):
        kp = np.zeros((2, N_JOINTS, 2), np.float32)
        bb = np.zeros((2, 4), np.float32)
        for m, p in enumerate(pair):
            if p is None:
                continue
            sk = np.asarray(p["skeleton"], np.float32)[:N_JOINTS, :2]
            kp[m, :len(sk)] = sk * scale
            bb[m] = np.asarray(p["box"], np.float32) * np.tile(scale, 2)
        joints[t] = normalize_joints(kp, bb)

    shuttle = shuttle_input([shuttle_by_frame.get(f) for f in frames], src_size, dst_size)
    jnb = np.concatenate((joints, create_bones(joints)), axis=-2)   # (t, 2, 36, 2)
    return jnb.reshape(SEQ_LEN, 2, -1).astype(np.float32), shuttle
