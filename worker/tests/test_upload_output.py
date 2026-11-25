"""The upload webhook's analysis.json drops BST-0's per-hit `probs` (final
review #3, Ruling 25): BST-0 runs on the upload path too, but its 25
probabilities are an input to the full-match steps, not a result.

worker/app.py can't be imported in tests (module-level modal.App() /
Volume.from_name()), so upload_output's source is pulled out of app.py with
ast and run on its own: the real code, without importing modal.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def _app_tree():
    return ast.parse(APP.read_text())


def _upload_output():
    tree = _app_tree()
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upload_output")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(APP), "exec"), ns)
    return ns["upload_output"]


def test_upload_output_drops_probs_and_keeps_the_rest():
    upload_output = _upload_output()
    results = {"summary": {"totalShots": 2}, "geometry": None, "tracking": [], "shuttle_debug": [],
               "events": [{"frame": 1, "type": "Clear", "detailType": "clear", "side": "Top",
                           "probs": [0.04] * 25},
                          {"frame": 9, "type": "Drop"}]}
    out = upload_output(results)
    assert all("probs" not in e for e in out["events"])
    assert out["events"][0] == {"frame": 1, "type": "Clear", "detailType": "clear", "side": "Top"}
    assert out["events"][1] == {"frame": 9, "type": "Drop"}
    assert out["summary"] == {"totalShots": 2} and "tracking" in out
    assert "probs" in results["events"][0]          # input not mutated


def test_webhook_writes_upload_output_not_raw_results():
    """The json.dump in process_badminton_video dumps upload_output(results)."""
    tree = _app_tree()
    hook = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "process_badminton_video")
    dumps = [n for n in ast.walk(hook) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "dump"]
    assert len(dumps) == 1
    arg = dumps[0].args[0]
    assert isinstance(arg, ast.Call) and getattr(arg.func, "id", None) == "upload_output"
