# Shipped Ticket Log

Running log of backlog tickets confirmed shipped via merged PRs, kept for traceability since ticket IDs are preserved in the active backlog but merged work is removed from the active list.

## 2026-08-31

WK-19 (PR [#24](https://github.com/jameshualiu/shuttleye/pull/24)), SEC-01 (PR [#25](https://github.com/jameshualiu/shuttleye/pull/25)), SEC-02 (PR [#26](https://github.com/jameshualiu/shuttleye/pull/26)), WK-09 (PR [#27](https://github.com/jameshualiu/shuttleye/pull/27)), COMBINED-01/BE-08+BE-14 (PR [#28](https://github.com/jameshualiu/shuttleye/pull/28)), BE-09 (PR [#29](https://github.com/jameshualiu/shuttleye/pull/29)) — all merged to `main`.

## Identified during 2026-09-16 workflow audit

The following tickets were still listed as open checkboxes in `BACKLOG.md`, but `git log` confirmed they were already merged to `main` — the backlog file simply hadn't been updated to reflect it:

- **BE-11** — Validate upload metadata (PR [#32](https://github.com/jameshualiu/shuttleye/pull/32))
- **FE-06** — Fix upload stuck at ~90% on ID-token refresh failure (PR [#33](https://github.com/jameshualiu/shuttleye/pull/33))
- **FE-07** — Enforce client-side file validation on upload (PR [#34](https://github.com/jameshualiu/shuttleye/pull/34))
- **FE-09** — Guard against malformed `analysis.json` freezing the canvas render loop (PR [#35](https://github.com/jameshualiu/shuttleye/pull/35))
- **WK-10** — Reuse loaded models across warm Modal containers (PR [#36](https://github.com/jameshualiu/shuttleye/pull/36))
- **FE-15** — Add route-level code splitting (PR [#37](https://github.com/jameshualiu/shuttleye/pull/37))
- **REPO-05** — Make CI actually enforce the existing test suites (PR [#39](https://github.com/jameshualiu/shuttleye/pull/39), with a same-day follow-up fix in commit `2dd7acd` to install pytest for the worker CI job)

## 2026-09-17

- **BE-07** — Tore down the Render deployment; Vercel confirmed as the production backend (issue [#52](https://github.com/jameshualiu/shuttleye/issues/52)). `render.yaml` removed from the repo and the Render service deleted from the dashboard.
