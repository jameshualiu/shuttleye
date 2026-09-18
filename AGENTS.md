# AGENTS.md

## Agent Protocol

Use GitHub Issues as the source of truth for active engineering work. `BACKLOG.md` is a lightweight roadmap for deferred or future work and does not need to be converted entirely into Issues.

Prefer simple, focused changes over unnecessary abstractions or process.

## Before implementation

1. Identify the GitHub Issue being addressed.
2. Read the relevant source files and documentation before proposing changes.
3. Check recent git history when it is unclear whether functionality already exists.
4. Identify relevant dependencies or cross-stack impacts.
5. Propose a concise implementation plan tied to the Issue's requirements and acceptance criteria.
6. **[GATE 1]** Stop and wait for the user to say `Proceed`.

Do not modify code before Gate 1.

## Implementation

1. Create a feature branch from `main`:

   `feature/[issue-number]-[short-kebab-case-description]`

2. Implement only the scope necessary to address the Issue.
3. Run the relevant tests, linting, and build checks.
4. Review the resulting diff for unintended changes.
5. Do not commit automatically.
6. Present the proposed Conventional Commit message(s) and affected files. When an Issue's acceptance criteria cover multiple distinct changes, split the work into one commit per item instead of a single combined commit — each commit should be independently reviewable and pass tests on its own.
7. **[GATE 2]** Stop and wait for the user to say `Commit these changes`.

## Commit and PR

After approval:

1. Verify `git status` and review the final diff.
2. Create the approved Conventional Commit(s), split per acceptance-criteria item as proposed at Gate 2.
3. Push the feature branch to GitHub.
4. Open a Pull Request referencing the GitHub Issue.
5. Use a Conventional Commit-style PR title.
6. Include a concise summary of the changes.
7. Apply relevant GitHub labels.
8. Do not merge the PR unless explicitly instructed by the user.

## Cross-stack changes

When an Issue changes behavior or data shared between the frontend, backend, and worker:

1. Identify every affected layer before implementation.
2. Read `data-flow.md` and the relevant source code.
3. Update affected producers and consumers together.
4. Run checks for each affected layer.
5. Do not leave one layer using an outdated contract.

## GitHub Issues

Create or work from an Issue when the change is meaningful and independently trackable.

Do not create Issues for:

- trivial fixes
- tiny cleanup
- changes that naturally belong inside another Issue
- work that has already shipped

Use labels to categorize work, such as:

- `frontend`
- `backend`
- `worker`
- `security`
- `testing`
- `performance`
- `bug`
- `tech-debt`

GitHub Issue numbers should be used for active work rather than maintaining a separate ticket-ID system.

## Scope and engineering judgment

- Avoid unrelated refactors while implementing an Issue.
- Do not introduce dependencies or abstractions solely to make the project appear more production-grade.
- Preserve existing ML fallback behavior unless the Issue explicitly changes it.
- If requested functionality appears to already exist, verify the implementation before changing it.
- If implementation reveals a larger architectural issue, explain it before expanding scope.
- Prefer fixing the underlying problem over adding superficial checks or documentation.
