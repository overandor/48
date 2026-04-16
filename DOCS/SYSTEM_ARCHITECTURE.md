# System Architecture: Semantic Protocol System

## Overview
The system is architected as a decoupled, synchronized two-repository system separating intent (Control Plane) from implementation (Runtime Plane).

## Topology

### Repo 47: Control Plane (Orchestration & Governance)
**Branches**: `main`, `control`
**Responsibilities**:
- System specification (`specs/`)
- Interface contracts (`contracts/`)
- JSON schemas & Event formats
- Shared version manifest
- Governance & Roadmap

### Repo 48: Runtime Plane (Execution & Implementation)
**Branches**: `main`, `runtime`
**Responsibilities**:
- Solana DEX Program (Rust)
- Client implementation (TypeScript)
- `semantic_protocol_runtime.py` engine
- Deployment & Integration logic
- Runtime verification

## Coordinated Folder Structure

### Repo 47 (Proposed)
```text
/
├── contracts/
│   ├── manifest.json
│   ├── events.json
│   └── schemas/
├── specs/
│   └── protocol.md
└── governance/
    └── roadmap.md
```

### Repo 48 (Current)
```text
/
├── programs/
│   └── solana_dex/
├── client/
│   └── src/
├── scripts/
├── tests/
│   └── examples/
├── semantic_protocol_runtime.py
└── DOCS/
    ├── SYSTEM_ARCHITECTURE.md
    └── SYNC_STRATEGY.md
```

## Governance & Synchronization
The Control Plane (`47/control`) defines the "what." The Runtime Plane (`48/runtime`) implements the "how." They are permanently coupled via automated cross-repo validation and a shared version manifest.
