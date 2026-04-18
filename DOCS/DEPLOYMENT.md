# Deployment Guide: SPR Execution Plane

## 1. Prerequisites
- Rust and Cargo (for Solana programs)
- Node.js and npm/yarn (for TypeScript clients)
- Python 3.8+ (for the SPR runtime and bridge)

## 2. Solana Program Deployment
```bash
cd programs/
cargo build-sbf
solana program deploy target/deploy/solana_dex.so
```

## 3. Client Setup
```bash
cd clients/
npm install
```

## 4. Runtime Execution
The SPR runtime can be executed directly or via the bridge:
```bash
python3 src/runtime/semantic_protocol_runtime.py run src/runtime/examples/demo.spr
```

## 5. Continuous Integration
The execution plane is validated against the control plane schemas in Repo 47. Ensure Repo 47 is accessible to the CI environment.
