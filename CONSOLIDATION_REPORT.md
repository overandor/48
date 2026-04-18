# Repository Consolidation and Governance Report

## 1. Repo 47 (Control Plane) Inventory
### Branch Map
- `main`: Current canonical head.
- `codex/develop-semantic-protocol-programming-language`: Foundational spec work.
- `codex/develop-semantic-protocol-runtime-prototype`: Early runtime code (to be moved).
- `codex/develop-semantic-protocol-runtime-prototype-ajp300`: Duplicate of the above.
- `codex/redesign-and-synchronize-repo-47-and-48`: Primary architecture redesign.
- `codex/redesign-and-synchronize-repo-47-and-48-5injtp`: Duplicate/near-duplicate of architecture redesign.
- `feat/semantic-protocol-runtime-2576904215308849958`: Implementation-heavy branch (runtime concerns).

### PR Map (Inferred)
- **PR #1, #2, #3**: Early foundation, specifications, and initial runtime prototype.
- **PR #4, #5**: Control-plane architecture and two-repo coordination (Duplicate set).
- **PR #6, #7**: Documentation and research proposal (Duplicate set).

## 2. Repo 48 (Runtime Plane) Inventory
### Branch Map
- `main`: Current canonical head (contains merged runtime prototype and architecture stubs).
- `codex/design-synchronized-two-repository-system`: Early design work for coordination.
- `codex/evaluate-dual-product-concept-and-market-potential`: Market research / Innovation assessment.
- `codex/implement-semantic-protocol-runtime-prototype`: Implementation of SPR.
- `codex/implement-semantic-protocol-runtime-prototype-hy3win`: Duplicate of implementation.
- `runtime-15228000534994507618`: Advanced runtime features and structured examples.
- `semantic-protocol-prototype-17120032671447831757`: Recent major restructuring into programs/client/tests.

### PR Map (Inferred)
- **PR #1**: Foundational runtime prototype.
- **PR #2, #3, #4**: Runtime architecture and directory restructuring (Duplicate set).
- **PR #5, #6**: Documentation updates (Duplicate set).

## 3. Duplicate and Superseded Map
| Intent | Repo 47 (Keep / Supersede) | Repo 48 (Keep / Supersede) |
| :--- | :--- | :--- |
| **Foundational SPR** | `feat/...2576904` / `codex/...ajp300` | `main` / `codex/...hy3win` |
| **Architecture** | `codex/...48` / `codex/...5injtp` | `semantic-protocol...` / `codex/...system` |
| **Documentation** | `PR #6` / `PR #7` | `PR #5` / `PR #6` |

## 4. Canonical Merge and Consolidation Plan
### Step 1: Repo 47 Cleanup
- **Target Content**: Strictly `specs/`, `contracts/`, `governance/`, `manifests/`.
- **Action**: Move `semantic_protocol_runtime.py`, `examples/`, and `tests/` to Repo 48.
- **Source**: Adopt the contract structure from `codex/redesign-and-synchronize-repo-47-and-48`.

### Step 2: Repo 48 Cleanup
- **Target Content**: Strictly `programs/`, `client/`, `scripts/`, `tests/`, `semantic_protocol_runtime.py`.
- **Action**: Move `DESIGN/CONTROL_PLANE/` artifacts to Repo 47.
- **Source**: Adopt the structure from `semantic-protocol-prototype-17120032671447831757`.

## 5. Branch/PR Management
### PRs to Close
- **Repo 47**: PR #5 (as dup of #4), PR #7 (as dup of #6).
- **Repo 48**: PR #3, #4 (as dup of #2), PR #6 (as dup of #5).

### Branches to Delete (After Consolidation)
- **Repo 47**: `codex/...ajp300`, `codex/...5injtp`.
- **Repo 48**: `codex/...hy3win`, `codex/...system`.

## 6. Final Canonical Architecture
- **Repo 47 (Control Plane)**: `SPEC.md`, `contracts/`, `governance/`, `manifests/`.
- **Repo 48 (Runtime Plane)**: `semantic_protocol_runtime.py`, `programs/solana_dex/`, `client/src/`, `tests/examples/`.
