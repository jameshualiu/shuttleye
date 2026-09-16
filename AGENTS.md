# AGENTS.md

## Agent Protocol Instructions

When requested to run the backlog automation protocol, execute the following multi-step pipeline for the target tickets in `backlog.md` starting with Tier 1. You are permitted to execute file-reads, file-writes, local tests, and terminal/git commands autonomously, but you must halt and wait for user input at the specified `[GATE]` markers.

### Conflict Prevention Pre-Check
Before detailing a plan for the active ticket, inspect its target file modifications. Cross-reference those files against the target files of the next 3 downstream tickets in `backlog.md`. If an overlap is detected, explicitly report it to the user with a recommended merging or execution strategy before proceeding.

### Pipeline Steps

#### Step 1: Context Gathering & Plan Proposal
1. Read `BACKLOG.md` in full, even if it was already read earlier in the conversation — treat the file on disk as the source of truth, since tickets can ship (via a merged PR) without the file being updated.
2. Select the highest-priority, incomplete ticket from Tier 1 (ignore open PR tasks like `[WK-19]`).
3. Run the Conflict Prevention Pre-Check.
4. Dynamically open, read, and analyze the listed target source code files.
5. Output a concise engineering strategy outlining exactly what code/logic will change to meet the ticket's Acceptance Criteria.
6. **[GATE 1]**: Completely halt execution and wait for the user to say "Proceed".

#### Step 2: Branch Creation & Implementation
1. Create and switch to a new git branch: `feature/[Ticket-ID]-[short-kebab-case-description]`.
2. Implement the code modifications across the codebase.
3. Run the specific local test suites (e.g., `pytest` for worker modifications) to verify compliance.
4. Do NOT execute any git commits yet. Instead, display a bulleted list of proposed atomic commits using the Conventional Commits specification. Include file paths underneath each message.
5. **[GATE 2]**: Completely halt execution and wait for the user to say "Commit these changes".

#### Step 3: Git Operations & PR Creation
1. Verify `git status` to ensure all changes are accounted for cleanly.
2. Commit the modifications locally with the approved conventional commit structures.
3. Update `BACKLOG.md` to reflect the ticket just shipped — check off / remove it from Tier 1 (or the relevant Tier 2 batch), and add a note in the file's existing "shipped" log style (see the "2026-08-31 shipped" entry for the format). Commit this as one more commit on the same branch — do not open a separate PR for it.
4. Run `git push origin HEAD` to push the feature branch to GitHub.
5. Use the GitHub CLI tool (`gh pr create`) to open a brand-new Pull Request. Title the PR using your primary conventional commit message. Draft a professional, clear 2-sentence description summarizing the structural alterations for an engineering reviewer.
