# Third-party code in `worker/`

Code below was ported or vendored from MIT-licensed projects. Each file also
names its source in its header. Model weights and datasets are not in this
repository and are not covered here.

## COURTSIDE

- Repository: https://github.com/jayclim/BadmintonAI
- Commit: `5c356f05cde0ed90c75316c133e0aba495e5232b`
- License: MIT, Copyright (c) 2026 Jayden Lim

| File in this repo | Ported from (upstream path) |
|---|---|
| `fullmatch/segment.py` | `src/badminton/segment.py`, plus `_combined_score` / `attribute_hits` from `src/badminton/hits.py`; thresholds re-tuned on our tracks |
| `fullmatch/serves.py` | `src/badminton/hits.py` (the serve-onset pass of `detect_hits`) |
| `fullmatch/scoreboard.py` | `src/badminton/scoreboard.py`, plus `align_scores` and `side_map` from `build()` in `src/badminton/labelfree.py`; strip thresholds relaxed for the 2021 graphic |
| `fullmatch/score_seq.py` | `src/badminton/score_seq.py`, vendored unchanged below its header |
| `fullmatch/contact.py` | `src/badminton/contact.py` |
| `fullmatch/bst_inputs.py` | `src/badminton/bst_eval.py` (the BST-0 input recipe: window, joint normalisation, bones, shuttle scaling) |
| `fullmatch/shot_features.py` | the stacked shot classifier in `src/badminton/pipeline.py` (`classify`) and `src/badminton/shotclass.py`: feature set, mirroring and plausibility gates |
| `fullmatch/units.py` | not ported code: converts COURTSIDE's 30 fps / 1280x720 thresholds to our fps and resolution |
| `detectors/stroke_classifier.py` (`BST0Adapter`) | feeds BST-0 COURTSIDE's input recipe through `fullmatch/bst_inputs.py` |
| `train/harvest_scoreboard.py` | `harvest_templates` in `src/badminton/scoreboard.py` |
| `train/train_shot_stack.py` | the `HistGradientBoostingClassifier` settings of `_model()` in `src/badminton/shotclass.py` |
| `train/eval_scoring.py` (`ZH_TO_TEN`) | the ShuttleSet CN->EN shot map in `src/badminton/shuttleset.py` |

## BST: Badminton Stroke-type Transformer

- Repository: https://github.com/Va6lue/BST-Badminton-Stroke-type-Transformer
- Commit: `c93acfa736ed784ba7bea4ec9d360001dea9b728` (BST-0)
- License: MIT, Copyright (c) 2025 Jing-Yuan Chang
- Paper: "BST: Badminton Stroke-type Transformer for Skeleton-based Action
  Recognition in Racket Sports" (CVPRW 2026)

| File in this repo | Vendored from (upstream path) |
|---|---|
| `detectors/bst_model.py` | `stroke_classification/model/bst.py` (BST-CG-AP and `BST_0`) and the TemPose building blocks they depend on from `stroke_classification/model/tempose.py`; inference only, with an inline `PositionalEncoding1D` replacing the `positional-encodings` package |

## MIT License text

Both projects use the MIT License. The text below applies to each, with that
project's copyright line:

- Copyright (c) 2026 Jayden Lim (COURTSIDE)
- Copyright (c) 2025 Jing-Yuan Chang (BST)

```text
MIT License

Copyright (c) <year> <copyright holder>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
