"""The full-match eval caches the merged result before post-processing
(Ruling 23) in a form --from-merged can load back."""
import json

from train.eval_shuttleset import _load_merged, _save_merged


def _merged():
    return {"fps": 30.0, "totalFrames": 300, "chunks": [{"court_found": True}], "court": None,
            "court_outliers": [], "verify": [], "timings": {"analyze_s": 5.0},
            "events": [{"frame": 10}, {"frame": 40}],
            "tracking": [[] for _ in range(300)], "shuttle": [None] * 300}


def test_save_merged_round_trips_through_load_merged(tmp_path):
    out = _save_merged(_merged(), tmp_path, "20260101-000000", "Some-Match", labels="bfmd")
    saved = json.loads(out.read_text())
    assert saved["match"] == "Some-Match" and saved["labels"] == "bfmd" and saved["stage"] == "merged"
    res, path, match = _load_merged(out)
    assert path == out and match == "Some-Match"
    assert [e["frame"] for e in res["rawEvents"]] == [10, 40]
    assert res["totalFrames"] == 300 and len(res["tracking"]) == 300 and len(res["shuttle"]) == 300
