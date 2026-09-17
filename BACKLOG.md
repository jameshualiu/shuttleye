# Project Backlog — Badminton AI Analyst

Lightweight, scannable roadmap. Ticket IDs are preserved as-is for now so they can be mapped to GitHub Issues in a later phase — do not renumber them. Detailed rationale and acceptance criteria belong in the eventual GitHub Issue, not here.

Audit findings, prioritization history, and shipped-ticket log live in `[docs/audits/](docs/audits/)`.

## High Priority

### Testing & CI Maturity

- [ ] **[BE-15]** Add test coverage for the real Express router/DI wiring.
- [ ] **[WK-16]** Add test coverage for hit-merging and rule-based classification fallback.
- [ ] **[FE-17]** Stand up a frontend test suite (Vitest + RTL).



### ML Evaluation & Benchmarking

- [ ] **[EVAL-01]** Build a held-out shot-classifier accuracy eval against ShuttleSet.
- [ ] **[EVAL-02]** Re-run and record hit-detector precision/recall for citation.
- [ ] **[EVAL-03]** Build a homography reprojection-error eval.
- [ ] **[EVAL-05]** Instrument end-to-end processing time as a queryable metric.



### Correctness & Reliability

- [ ] **[BE-06]** Confirm rate limiting is serverless-safe (verify `REDIS_URL` in production).



## Medium Priority

- [ ] **[BATCH-01]** Backend defensive hardening. *(BE-10, BE-12, BE-13, BE-18)*
- [ ] **[BATCH-02]** Baseline security headers. *(BE-16, BE-17)*
- [ ] **[BATCH-03]** Worker failure-path hardening. *(WK-11, WK-12, WK-14, WK-15)*
- [ ] **[BATCH-04]** Worker & eval housekeeping. *(WK-13, WK-17, EVAL-06, REPO-06 script half)*
- [ ] **[BATCH-05]** UI consistency & accessibility. *(FE-08, FE-10, FE-13, FE-16)*
- [ ] **[BATCH-06]** Frontend code-consistency. *(FE-12, FE-14)*