# Synchronization Strategy

## Branch Topology
### Repo 47 (Control Plane)
- `main`: Stable, verified protocol specifications.
- `control`: Active development and staging of interface contracts.

### Repo 48 (Runtime Plane)
- `main`: Stable, verified implementation (Solana + TS).
- `runtime`: Active development of the execution engine.

## Synchronization Rules
1. **Source of Truth**: Repo 47 `control` is the source of truth for all protocol contracts.
2. **Conformity**: Repo 48 `runtime` must always conform to Repo 47 `control`.
3. **Stability**: No breaking changes reach `main` in either repo without cross-repo validation.
4. **Validation Trigger**: Changes in `47/control` trigger CI checks in `48/runtime`.

## Release Flow
1. Propose changes in `47/control`.
2. Verify implementation in `48/runtime`.
3. Update `manifest.json` with new version and component hashes.
4. Merge `47/control` -> `47/main`.
5. Merge `48/runtime` -> `48/main`.

## Conflict Resolution
- If the Runtime Plane cannot implement a Control Plane requirement, the Control Plane specification must be revised to maintain feasibility.
- Implementation details (Repo 48) must not leak into Specification (Repo 47).
