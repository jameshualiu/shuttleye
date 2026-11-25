# worker/train/train_shot_stack.py
"""
Train the stacked shot classifier (fullmatch.shot_features) leave-one-match-out
on saved --full-match results, and save the all-matches model.

For every ShuttleSet match with a saved full-match result under --cache-dir
(<match>/fullmatch_<stamp>.json + _tracks.json.gz; the latest one is used):

  1. re-segment + side-decode it with the current code (no stack), exactly as
     eval_shuttleset.py --from-merged does
  2. score it with eval_shuttleset's full-match scoring: that is the baseline
     (BST-0 + side decode) and gives the fitted label frame offset
  3. build the stack's features at every detected non-serve hit and label the
     hits matched to a ShuttleSet shot (eval_scoring.label_matched_events,
     same matching as the scoring; unmatched hits are not used)

Then for each match: train on all the others, re-classify this match's hits and
re-score it with the same scoring, so every "with stack" number is held out
with respect to the stack. Caveat: BST-0 was trained upstream on ShuttleSet
with its own split, so its probabilities on these matches may be optimistic;
the numbers are held out only with respect to the stack itself.

Two heads, both COURTSIDE's HistGradientBoostingClassifier settings: "ten"
(ShuttleSet's 10 classes -> detailType) and "six" (product 6-class -> type).

Train with the worker image's pins (numpy==1.26.4, scikit-learn==1.4.2; see
requirements.txt): a model pickled under numpy 2.x does not load in the image
(PCG64 BitGenerator error) and inference then falls back to BST-0 types.

The model file goes to the Modal volume, never into git:
    python -m modal volume put badminton-models <out> /shot_stack.joblib

Usage (plain script, no Modal):
    python worker/train/train_shot_stack.py [--matches a,b,...] [--out ~/.cache/shuttleye-eval/shot_stack.joblib]
"""
import argparse
import contextlib
import datetime
import io
import pathlib
import sys

import numpy as np

_WORKER_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKER_DIR))

from fullmatch.run import apply_segmentation  # noqa: E402
from fullmatch.shot_features import FEATURES, apply_bundle, stack_inputs, stack_targets  # noqa: E402
from train.eval_scoring import label_matched_events  # noqa: E402

DEFAULT_CACHE = pathlib.Path.home() / ".cache" / "shuttleye-eval"


def _model():
    # COURTSIDE shotclass._model()
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                          max_leaf_nodes=31, random_state=0)


def _latest_merged(match_dir: pathlib.Path):
    cands = sorted(p for p in match_dir.glob("fullmatch_*.json")
                   if not p.name.endswith("_resegmented.json")
                   and p.with_name(p.name[:-5] + "_tracks.json.gz").exists())
    return cands[-1] if cands else None


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _headline(report: dict) -> dict:
    ex, inc = report["hits_after"]["excl_serves"], report["hits_after"]["incl_serves"]
    return {"ten": ex["ten"]["accuracy"], "ten_n": ex["ten"]["scored"],
            "type6": ex["type"]["accuracy"], "type6_n": ex["type"]["scored"],
            "ten_incl_serves": inc["ten"]["accuracy"]}


def load_match(match: str, path: pathlib.Path, tolerance: int) -> dict:
    """Segmented result, baseline scores, features and labels for one match."""
    from train.eval_shuttleset import _labelled_sets, _load_merged, _score_full_match

    res, _, _ = _load_merged(path)
    _quiet(apply_segmentation, res, log=lambda *_: None, shot_stack=False)
    _, sets = _labelled_sets(match)
    base = _quiet(_score_full_match, res, sets, tolerance)
    offset, windows = base["frame_offset"], base["windows"]

    X = stack_inputs(res)
    targets = set(stack_targets(res))
    events = res["events"]
    labels = {}
    for set_num, rallies in sets.items():
        w = windows[set_num]
        idx = [i for i, e in enumerate(events) if w[0] <= e["frame"] <= w[1]]
        gt = sorted(({**s, "frame": s["frame"] + offset} for shots in rallies.values() for s in shots),
                    key=lambda s: s["frame"])
        for k, g in label_matched_events([events[i] for i in idx], gt, tolerance).items():
            if idx[k] in targets:
                labels[idx[k]] = g
    rows = sorted(labels)
    return {"match": match, "path": path, "res": res, "sets": sets, "baseline": _headline(base),
            "X": X[rows], "y10": [labels[i]["ten"] for i in rows], "y6": [labels[i]["type"] for i in rows]}


def fit_bundle(data: list[dict]) -> dict:
    import sklearn

    X = np.vstack([d["X"] for d in data])
    y10 = np.array(sum((d["y10"] for d in data), []), dtype=object)
    y6 = np.array(sum((d["y6"] for d in data), []), dtype=object)
    m10, m6 = y10 != None, y6 != None   # noqa: E711  (elementwise)
    return {"features": FEATURES,
            "ten": _model().fit(X[m10], y10[m10].astype(str)),
            "six": _model().fit(X[m6], y6[m6].astype(str)),
            "trained_on": [d["match"] for d in data],
            "n_train": {"ten": int(m10.sum()), "six": int(m6.sum())},
            "sklearn": sklearn.__version__, "numpy": np.__version__,
            "created": datetime.datetime.now().isoformat(timespec="seconds")}


def held_out(d: dict, bundle: dict, tolerance: int) -> dict:
    """Re-classify d's hits with `bundle` and re-score with the eval's scoring."""
    from train.eval_shuttleset import _score_full_match

    res = {**d["res"], "events": [dict(e) for e in d["res"]["events"]]}
    apply_bundle(res, bundle)
    return _headline(_quiet(_score_full_match, res, d["sets"], tolerance))


def importances(d: dict, bundle: dict, top: int = 15):
    from sklearn.inspection import permutation_importance

    m = np.array([y is not None for y in d["y10"]])
    y = np.array(d["y10"], dtype=object)[m].astype(str)
    r = permutation_importance(bundle["ten"], d["X"][m], y, n_repeats=5, random_state=0)
    return r.importances_mean


def _pct(x):
    return "  n/a" if x is None else f"{100 * x:5.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--matches", default="", help="comma-separated; default: every cached full-match result")
    ap.add_argument("--out", default=str(DEFAULT_CACHE / "shot_stack.joblib"))
    ap.add_argument("--tolerance", type=int, default=3)
    a = ap.parse_args()
    if not np.__version__.startswith("1.26."):
        print(f"[stack] WARNING: numpy {np.__version__}; the worker image pins 1.26.4, "
              f"so this model may not load there")

    cache = pathlib.Path(a.cache_dir).expanduser()
    names = a.matches.split(",") if a.matches else sorted(p.name for p in cache.iterdir() if p.is_dir())
    data = []
    for name in names:
        path = _latest_merged(cache / name)
        if path is None:
            continue
        d = load_match(name, path, a.tolerance)
        print(f"[stack] {name}: {len(d['y10'])} labelled hits from {path.name}")
        data.append(d)
    if len(data) < 2:
        raise SystemExit("[stack] need saved full-match results for at least 2 matches")

    print("\nLEAVE-ONE-MATCH-OUT (hits after segmentation, serves excluded; % of matched hits)")
    print(f"{'match':<72} {'n10':>4} {'ten base':>9} {'ten stack':>9} {'n6':>4} {'6 base':>7} {'6 stack':>7}")
    imp, rows = [], []
    for k, d in enumerate(data):
        bundle = fit_bundle([o for j, o in enumerate(data) if j != k])
        s, b = held_out(d, bundle, a.tolerance), d["baseline"]
        rows.append((d["match"], b, s))
        imp.append(importances(d, bundle))
        print(f"{d['match']:<72} {s['ten_n']:4d} {_pct(b['ten']):>9} {_pct(s['ten']):>9} "
              f"{s['type6_n']:4d} {_pct(b['type6']):>7} {_pct(s['type6']):>7}")

    def pooled(key, which):
        n = sum(r[2][f"{key}_n"] for r in rows)
        return sum(r[which][key] * r[2][f"{key}_n"] for r in rows) / n

    print(f"{'pooled (weighted by matched hits)':<72} {'':4} {_pct(pooled('ten', 1)):>9} "
          f"{_pct(pooled('ten', 2)):>9} {'':4} {_pct(pooled('type6', 1)):>7} {_pct(pooled('type6', 2)):>7}")

    mean_imp = np.mean(imp, axis=0)
    print("\nPERMUTATION IMPORTANCE (10-class head, held-out, mean over folds; accuracy drop)")
    for i in np.argsort(mean_imp)[::-1][:15]:
        print(f"  {FEATURES[i]:<16} {mean_imp[i]:+.4f}")

    final = fit_bundle(data)
    import joblib
    out = pathlib.Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, out)
    print(f"\n[stack] all-matches model ({final['n_train']}) -> {out}")
    print(f"[stack] upload: python -m modal volume put badminton-models {out} /shot_stack.joblib")


if __name__ == "__main__":
    main()
