# SPR Execution Plane (Repo 48)

This repository serves as the implementation and execution plane for the **Semantic Protocol Runtime (SPR)** system.

## Responsibilities
- **Blockchain Integration**: Hosting the Rust Solana programs and TypeScript clients.
- **Runtime Implementation**: Providing the core `semantic_protocol_runtime.py` engine.
- **Integration Logic**: Managing the bridge between on-chain data and the semantic protocol.
- **Executable Tests**: Maintaining the suite of runtime and integration tests.

## Structure
- `programs/`: Rust Solana program code.
- `clients/`: TypeScript client and interaction logic.
- `src/runtime/`: The SPR engine and integration bridge.
- `tests/runtime/`: Runtime and integration tests.
- `docs/`: Deployment and implementation documentation.

## Branches
- `main`: Latest stable compatible release of the execution plane.
- `runtime`: Active development branch for implementation and runtime changes.

## Coupled Repository
- [SPR Control Plane (Repo 47)](https://github.com/overandor/47)

## Quick Start
```bash
python3 src/runtime/semantic_protocol_runtime.py init
python3 src/runtime/semantic_protocol_runtime.py run src/runtime/examples/demo.spr
```
