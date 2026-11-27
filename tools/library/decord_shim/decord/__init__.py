"""Minimal cv2-backed stand-in for decord (no macOS arm64 wheel exists).
Local-runner environment only; lives in the venv, not the repo. Implements what
worker/pipeline.py uses: VideoReader(path, ctx, width, height), len, [i].asnumpy(),
get_batch(idx).asnumpy(), get_avg_fps(). Frames are decoded once, in order, to a
temp memmap (RGB uint8, resized with cv2 INTER_AREA) and read back from it."""
import os, tempfile
import cv2
import numpy as np


def cpu(i=0):
    return i


class _Arr:
    def __init__(self, a):
        self._a = a

    def asnumpy(self):
        return np.asarray(self._a)


class VideoReader:
    def __init__(self, path, ctx=None, width=-1, height=-1):
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"cannot open {path}")
        self._fps = cap.get(cv2.CAP_PROP_FPS)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w0, h0 = int(cap.get(3)), int(cap.get(4))
        w, h = (width, height) if width > 0 and height > 0 else (w0, h0)
        fd, self._tmp = tempfile.mkstemp(suffix=".decord.u8")
        os.close(fd)
        mm = np.memmap(self._tmp, dtype=np.uint8, mode="w+", shape=(max(n, 1), h, w, 3))
        i = 0
        while i < n:
            ok, fr = cap.read()
            if not ok:
                break
            fr = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            if (fr.shape[1], fr.shape[0]) != (w, h):
                fr = cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)
            mm[i] = fr
            i += 1
        cap.release()
        mm.flush()
        self._n = i
        self._mm = np.memmap(self._tmp, dtype=np.uint8, mode="r", shape=(max(n, 1), h, w, 3))
        os.unlink(self._tmp)      # stays readable through the open map

    def __len__(self):
        return self._n

    def __getitem__(self, i):
        if i < 0:
            i += self._n
        if not 0 <= i < self._n:
            raise IndexError(i)
        return _Arr(np.array(self._mm[i]))

    def get_batch(self, idx):
        idx = [min(max(int(i), 0), self._n - 1) for i in idx]
        return _Arr(np.stack([self._mm[i] for i in idx]))

    def get_avg_fps(self):
        return self._fps
