# Semantic Protocol System: Runtime Plane

This repository (Repo 48) contains the executable implementation of the Semantic Protocol System. It hosts the runtime engines, smart contracts, and client libraries required to realize the intent defined in the Control Plane.

## Components
- **Programs**: Solana DEX program written in Rust (`programs/solana_dex`).
- **Client**: TypeScript library for interacting with the protocol (`client/`).
- **Runtime Engine**: `semantic_protocol_runtime.py`, the core interpreter for the Semantic Protocol.
- **Tests**: Comprehensive runtime tests and protocol examples (`tests/`).

## Architecture & Governance
This repository is part of a coordinated two-repo system:
1. **Repo 47 (Control Plane)**: Owns specifications and contracts.
2. **Repo 48 (Runtime Plane)**: Owns execution and implementation.

For detailed architecture and synchronization rules, see:
- [System Architecture](DOCS/SYSTEM_ARCHITECTURE.md)
- [Synchronization Strategy](DOCS/SYNC_STRATEGY.md)

## Development
- Use the `runtime` branch for implementation changes.
- Ensure all changes validate against the latest contracts in the Control Plane.
- Stable releases are merged into `main`.

## Usage
```bash
# Initialize examples
python3 semantic_protocol_runtime.py init --dir tests/

# Explain a protocol
python3 semantic_protocol_runtime.py explain tests/examples/demo.spr
```
