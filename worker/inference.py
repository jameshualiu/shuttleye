import numpy as np
from device_fallback import CpuFallback
from detectors.court_detector import CourtDetectorAdapter, NetDetectorAdapter, YoloPoseAdapter, TrackNetAdapter, ShotClassifierAdapter


class BadmintonInference:
    def __init__(self, tracknet_path, court_kprcnn_path, net_kprcnn_path, yolo_pose_path, lstm_path=None,
                 tracknet_v3_path=None, inpaintnet_path=None, hit_detector_path=None, bst_path=None,
                 bst0_path=None, device=None):
        # device=None keeps each adapter's own default (cuda if available, else
        # cpu). The local runner passes "mps"; a torch model that fails to load
        # there is rebuilt on CPU and recorded in self.device_fallbacks.
        self.device = device
        self.device_fallbacks = []
        # Prefer TrackNetV3 (median-background windows + InpaintNet rectification);
        # fall back to the legacy single-frame TrackNet if V3 weights are absent.
        self.tracknet_v3 = None
        if tracknet_v3_path:
            try:
                from detectors.tracknet_v3 import TrackNetV3Adapter
                self.tracknet_v3 = self._on_device('tracknet_v3', TrackNetV3Adapter, tracknet_v3_path, inpaintnet_path)
            except Exception as e:
                print(f"[tracknetv3] WARNING: failed to load V3 weights ({e}); using legacy TrackNet")

        self.tracknet   = self._on_device('tracknet', TrackNetAdapter, tracknet_path) if self.tracknet_v3 is None else None
        self.court_det  = self._on_device('court', CourtDetectorAdapter, court_kprcnn_path)
        self.net_det    = self._on_device('net', NetDetectorAdapter, net_kprcnn_path)
        self.pose_det   = self._on_device('yolo_pose', YoloPoseAdapter, yolo_pose_path)
        self.shot_clf = None
        if lstm_path:
            try:
                self.shot_clf = ShotClassifierAdapter(lstm_path)
            except Exception as e:
                print(f"[lstm] WARNING: failed to load ({e}); using rule-based shot classification")

        # Learned hit detection (CNN over trajectory windows); heuristic fallback
        self.hit_det = None
        if hit_detector_path:
            try:
                from detectors.hit_detector import HitDetectorAdapter
                self.hit_det = HitDetectorAdapter(hit_detector_path)
            except Exception as e:
                print(f"[hitnet] WARNING: failed to load ({e}); using heuristic hit detection")

        # Stroke-type classifier: BST-0 (COURTSIDE input recipe), then
        # BST-CG-AP, then LSTM, then rules. Both BST adapters share the
        # classify_hits contract, so the pipeline only sees bst_clf.
        self.bst_clf = None
        if bst0_path:
            try:
                from detectors.stroke_classifier import BST0Adapter
                self.bst_clf = self._on_device('bst0', BST0Adapter, bst0_path)
            except Exception as e:
                print(f"[bst0] WARNING: failed to load ({e}); trying BST-CG-AP")
        if self.bst_clf is None and bst_path:
            try:
                from detectors.stroke_classifier import BSTStrokeClassifierAdapter
                self.bst_clf = self._on_device('bst', BSTStrokeClassifierAdapter, bst_path)
            except Exception as e:
                print(f"[bst] WARNING: failed to load ({e}); using LSTM shot classifier")

        shuttle_model = "TrackNetV3" if self.tracknet_v3 else "TrackNet"
        hit_model = "HitNet" if self.hit_det else "heuristic"
        clf_model = type(self.bst_clf).__name__ if self.bst_clf else ("LSTM" if self.shot_clf else "rule-based")
        self.strokes_model = clf_model     # reported per chunk in the full-match result's "models"
        print(f"[start] All Models Loaded Successfully ({shuttle_model} + RCNN + YOLO Pose + "
              f"{hit_model} hits + {clf_model} strokes)")

    def _on_device(self, name, cls, *args):
        """Build a torch adapter on self.device. If it fails to load, or a call
        later fails with a device-support error (see device_fallback.is_device_error),
        it is rebuilt on CPU, logged in self.device_fallbacks, and the call retried."""
        if self.device is None:
            return cls(*args)
        try:
            return CpuFallback(self, name, cls, args, cls(*args, device=self.device))
        except Exception as e:
            if self.device == "cpu":
                raise
            print(f"[device] {name} failed to load on {self.device} ({e}); falling back to cpu")
            self.device_fallbacks.append(name)
            return cls(*args, device="cpu")

    def detect_hits(self, shuttle_traj: list):
        """Learned hit detection, or None if unavailable (caller falls back)."""
        if self.hit_det is None:
            return None
        return self.hit_det.detect(shuttle_traj)

    def track_shuttle(self, vr, total_frames: int, batch_size: int = 4):
        """
        Full-video shuttle tracking with TrackNetV3, or None if V3 is unavailable
        (caller should fall back to predict_ball_batch).
        Returns:
            [{"frame", "pos": [x,y]|None, "confidence", "inpainted"}, ...]
        """
        if self.tracknet_v3 is None:
            return None
        return self.tracknet_v3.track_video(vr, total_frames, batch_size)

    def predict_ball_batch(self, batch_tensor: np.ndarray) -> np.ndarray:
        """
        Args:
            batch_tensor: (N, 9, 288, 512) float32 in [0, 1]
        Returns:
            (N, 1, 288, 512) float32 heatmap for the centre frame
        """
        if self.tracknet is None:
            raise RuntimeError("Legacy TrackNet not loaded (TrackNetV3 is active); use track_shuttle()")
        return self.tracknet.predict_batch(batch_tensor)

    def predict_pose_batch(self, frames: list) -> list:
        """
        Args:
            frames: list of HxWx3 uint8 numpy arrays
        Returns:
            list of per-frame player lists:
            [[{"id", "skeleton": [[x,y]*17], "box": [x1,y1,x2,y2]}, ...], ...]
        """
        return self.pose_det.detect_batch(frames)

    def detect_geometry(self, first_frame) -> dict:
        """
        Detect court keypoints (RCNN) and net keypoints (RCNN).
        Returns:
            {
                "court": [[x,y]*4] | None,             # 4-corner quad for homography
                "net": [[x,y]*4] | None,               # corrected net rectangle
                "court_keypoints_6": list | None,      # [TL, TR, ML, MR, BL, BR]
                "court_keypoints_35": list | None,     # 7x5 expanded grid
            }
        """
        court_result = self.court_det.detect(first_frame)
        kp6  = court_result["keypoints_6"]  if court_result["success"] else None
        kp35 = court_result["keypoints_35"] if court_result["success"] else None
        court_poly = [kp6[0], kp6[1], kp6[5], kp6[4]] if kp6 else None

        net_result = self.net_det.detect(first_frame)
        net_kp4 = net_result["keypoints_4"] if net_result["success"] else None

        return {
            "court": court_poly,
            "net": net_kp4,
            "court_keypoints_6": kp6,
            "court_keypoints_35": kp35,
        }

    def classify_shot(self, skeleton_sequence: list) -> str:
        if self.shot_clf is None:
            return "Unknown"
        return self.shot_clf.classify(skeleton_sequence)
