# 2026-08-19 — Backlog Triage for Recruiter/Engineering Signal

Re-sorted the (then-)46 open tickets by resume/interview value, not just severity, per request.

## Tiering rationale

- **Tier 1** (now "High Priority" in `BACKLOG.md`): everything worth featuring on its own — named CVEs/CWEs (unauthenticated endpoint, path traversal, unsafe deserialization), real correctness/data-integrity bugs, quantifiable cost/perf engineering (GPU cold-start reuse, bundle splitting), testing/CI maturity, and the ML evaluation work. 15 tickets remained in this tier as of 2026-08-31; several have since shipped — see [`2026-08-31-shipped-work.md`](2026-08-31-shipped-work.md).
- **Tier 2** (now "Medium Priority"): 22 tickets still worth doing but individually low-signal (env var validation, CORS headers, keyboard nav, code-style consistency), consolidated into 6 batch tickets (BATCH-01 through BATCH-06) so they didn't crowd out the list.
- **Flagged to close**: 5 tickets recommended for closing outright rather than scheduled — dead code, moot-once-superseded, or zero functional impact. Disposition of each is below.

## Ticket lineage

Original ticket IDs are preserved in the active backlog for traceability back to the audits that found them. Merged/batched tickets got a new ID:

- BATCH-01 = BE-10, BE-12, BE-13, BE-18
- BATCH-02 = BE-16, BE-17
- BATCH-03 = WK-11, WK-12, WK-14, WK-15
- BATCH-04 = WK-13, WK-17, EVAL-06, REPO-06 (script half only)
- BATCH-05 = FE-08, FE-10, FE-13, FE-16
- BATCH-06 = FE-12, FE-14
- COMBINED-01 = BE-08 + BE-14 (shipped, PR [#28](https://github.com/jameshualiu/shuttleye/pull/28))

## Disposition of the "flagged to close" tickets

| Ticket | Reasoning | Outcome |
|---|---|---|
| **FE-11** | `useUserVideos`, `VideoCard`, `ShotHeatmap` were confirmed unused anywhere in the app (grep-verified). No bug living in dead code is worth fixing. | Closed outright, dropped from tracking. |
| **WK-18** | The confidence cutoff (`0.25`) and `FRAME_H` (`288.0`) are already functionally correct today; naming them changes zero observable behavior. | Closed outright, dropped from tracking. |
| **REPO-06** *(render.yaml half)* | Only mattered for the Render deployment BE-07 is tearing down — fixing env var names on a service about to be deleted is wasted effort. | Closed outright, dropped from tracking. The `list_files.py` half of this ticket is still real and lives on in BATCH-04. |
| **EVAL-04** | Not independent engineering work — "don't cite an unvalidated number" is an acceptance criterion of EVAL-01, not separate effort. | Folded into EVAL-01, not tracked separately. |
| **BE-07** | Ops task (delete `render.yaml`, click "delete" in the Render dashboard), not code — but it's still a real outstanding action once Vercel's stability is confirmed. | Kept, under "Deferred / Cleanup" in the active backlog. |
