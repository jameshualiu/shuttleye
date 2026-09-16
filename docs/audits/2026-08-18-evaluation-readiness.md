# 2026-08-18 — Evaluation Readiness Audit

Triggered by wanting to cite real, defensible model-performance numbers on a resume rather than guessed ones. Covers the WK-19 and EVAL-01 through EVAL-06 ticket range.

## Headline finding: WK-19 was a production correctness bug, not just an eval gap

The BST stroke classifier — the most accurate model, already deployed — emitted a 12-class vocabulary that didn't match the product's advertised 6-class taxonomy (Clear/Smash/Drop/Drive/Net/Lob). Roughly 7 of its 12 classes rendered as unlabeled grey dots/bars in the UI. This needed fixing first, since it also blocked a clean shot-classifier accuracy number.

**Status:** WK-19 has since shipped (PR [#24](https://github.com/jameshualiu/shuttleye/pull/24)) — see [`2026-08-31-shipped-work.md`](2026-08-31-shipped-work.md).

## Eval infrastructure was in better shape than expected

- **ShuttleSet is already fully integrated locally**: 153 stroke-level CSVs, ground-truth court corners (`homography.csv`), and 43 of 44 real match videos, all gitignored/local-only.
- A proper held-out-set harness already exists and has already produced one real, reproducible number: `worker/train/evaluate_detector.py` → HitDetectorCNN 93% event-level precision/recall. This just needs re-running and recording for citation.

## Caution: the "76%" BST figure is not resume-defensible as-is

That number comes from `.bst-ref/validate_bst.py`, a one-off script hardcoded to a single ~22-second rally window on one machine — not a benchmark. It should not be cited anywhere external until a proper held-out eval (across all test matches, per-class confusion matrix, on the 6-class taxonomy WK-19 fixed) replaces it. This constraint was originally tracked as its own ticket (EVAL-04) but was folded into EVAL-01's acceptance criteria instead, since "don't cite an unvalidated number" isn't independent engineering work.
