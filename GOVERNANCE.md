# Repository Governance and Branch Policy

## 1. Coordinated Two-Repository System
- **Repo 47**: Control Plane (Specifications, Contracts, Governance, Schemas).
- **Repo 48**: Runtime Plane (Implementation, Execution, Client Libraries).

## 2. Branching and Pull Request Policy
To maintain a clean canonical history and prevent duplicate work, the following rules are strictly enforced:

### Canonical Task Integrity
- **One Task = One Branch per Repository**: Do not create multiple branches for the same logical task or intent.
- **One Task = One PR per Repository**: Maintain a single open pull request for each task. Update the existing PR with new commits rather than opening duplicates.

### Branch Naming Convention
- Use task-scoped names (e.g., `feat/protocol-v2`, `fix/solana-bridge`).
- Share task identifiers in branch metadata when work spans both repositories.

### Merge Discipline
- **Intent-based Merging**: Prefer the most complete and subsuming PR over the newest one.
- **Supersession**: Duplicate or near-duplicate PRs must be closed with an explicit link to the canonical PR (e.g., "Superseded by PR #X").
- **Cleanup**: Delete task branches immediately after successful merge to `main`.

## 3. Synchronization Rules
- **Contract-First Development**: Changes to interfaces must be proposed and merged in Repo 47 before they are finalized in Repo 48.
- **Cross-Repo Validation**: No breaking changes reach `main` in either repo without verified compatibility between the Control Plane and Runtime Plane.
