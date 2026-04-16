# Coordinated Two-Repository System Architecture

## 0. Scope and framing

This design keeps repository **47** and repository **48** separate, while treating them as one canonical system with strict contract synchronization.

- Repo 47 role: **control plane** (protocol governance + contracts).
- Repo 48 role: **runtime plane** (implementation + execution).
- Branch topology: exactly four long-lived branches.

## 1. Required branch topology

### Repository 47 (control plane)
- `main`: latest stable, release-approved control artifacts.
- `control`: active protocol and contract development branch.

### Repository 48 (runtime plane)
- `main`: latest stable, release-approved runtime implementation.
- `runtime`: active implementation branch.

## 2. Ownership boundaries

### Repo 47 owns (authoritative)
- System specification.
- Interface contracts.
- JSON Schemas.
- Event/message formats.
- Shared version manifest.
- Synchronization rules.
- Roadmap.
- Cross-repo governance policy.

### Repo 48 owns (conforming)
- Rust Solana program code.
- TypeScript client code.
- Integration logic.
- Deployment logic.
- Runtime tests.
- Executable implementation details.

## 3. Proposed folder structures

### 3.1 Repo 47 structure (control)

```text
repo-47/
  docs/
    architecture/
      system-spec.md
      sync-rules.md
    governance/
      change-policy.md
      conflict-resolution.md
    roadmap/
      roadmap.md
  contracts/
    schemas/
      manifest.schema.json
      events/
        order-request.schema.json
        order-accepted.schema.json
        order-rejected.schema.json
    protocol/
      protocol-versioning.md
      compatibility-matrix.yaml
  manifests/
    system-manifest.json
  tools/
    validate-contracts.sh
  .github/
    workflows/
      control-validate.yml
      control-sync-runtime.yml
```

### 3.2 Repo 48 structure (runtime)

```text
repo-48/
  programs/
    solana-dex/
      Cargo.toml
      src/
        lib.rs
  client/
    package.json
    src/
      index.ts
      protocol/
        generated/
  integration/
    adapters/
    bridges/
  deployment/
    scripts/
    environments/
  tests/
    contract/
      schema-conformance.test.ts
    integration/
    runtime/
  external/
    control-contracts/
      manifest.lock.json
      schemas/
  tools/
    sync-control-contracts.sh
    validate-runtime-compat.sh
  .github/
    workflows/
      runtime-validate.yml
      runtime-contract-check.yml
      runtime-sync-report.yml
```

## 4. Canonical synchronization model

1. `repo-47/control` is source of truth for protocol contracts.
2. `repo-48/runtime` consumes contracts from repo 47 and must validate conformance.
3. `repo-47/main` and `repo-48/main` only move when both are cross-repo compatible.
4. Every sync cycle updates a shared manifest version and immutable contract digest.

## 5. Shared manifest schema (control-authored)

The manifest is authored in repo 47 and copied/locked into repo 48 as a read-only compatibility target.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/schemas/system-manifest.schema.json",
  "title": "CanonicalSystemManifest",
  "type": "object",
  "required": [
    "system",
    "version",
    "release_date",
    "control",
    "runtime",
    "contracts",
    "compatibility"
  ],
  "properties": {
    "system": { "type": "string", "const": "semantic-protocol-system" },
    "version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "release_date": { "type": "string", "format": "date" },
    "control": {
      "type": "object",
      "required": ["repo", "branch", "commit"],
      "properties": {
        "repo": { "type": "string" },
        "branch": { "type": "string", "enum": ["main", "control"] },
        "commit": { "type": "string", "pattern": "^[a-f0-9]{7,40}$" }
      }
    },
    "runtime": {
      "type": "object",
      "required": ["repo", "branch", "commit"],
      "properties": {
        "repo": { "type": "string" },
        "branch": { "type": "string", "enum": ["main", "runtime"] },
        "commit": { "type": "string", "pattern": "^[a-f0-9]{7,40}$" }
      }
    },
    "contracts": {
      "type": "object",
      "required": ["schema_version", "digest_sha256", "schema_set"],
      "properties": {
        "schema_version": { "type": "string" },
        "digest_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
        "schema_set": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        }
      }
    },
    "compatibility": {
      "type": "object",
      "required": ["status", "validated_at", "evidence"],
      "properties": {
        "status": { "type": "string", "enum": ["pass", "fail"] },
        "validated_at": { "type": "string", "format": "date-time" },
        "evidence": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["check", "result"],
            "properties": {
              "check": { "type": "string" },
              "result": { "type": "string", "enum": ["pass", "fail"] },
              "details": { "type": "string" }
            }
          }
        }
      }
    }
  }
}
```

## 6. Compatibility rules

- **Rule C1:** Runtime message payloads must validate against control-owned JSON Schemas.
- **Rule C2:** Runtime-generated IDs and enums must match control-defined cardinality and naming.
- **Rule C3:** Any contract field removal or semantic type change is breaking.
- **Rule C4:** Breaking changes require synchronized PRs in `repo-47/control` and `repo-48/runtime` and joint approval.
- **Rule C5:** `main` promotion requires successful cross-repo validation on pinned commits.

## 7. Sync workflow design

### 7.1 Control-to-runtime (contract-first)
1. Contract PR merges into `repo-47/control`.
2. Repo 47 workflow publishes immutable contract bundle artifact + digest.
3. Repo 47 triggers `repository_dispatch` in repo 48 with manifest pointer and digest.
4. Repo 48 runtime workflow fetches bundle, updates `external/control-contracts/`, runs conformance tests.
5. Repo 48 posts result status back to repo 47 commit status/check run.

### 7.2 Runtime-to-control (implementation evidence)
1. Runtime PR merges into `repo-48/runtime`.
2. Repo 48 validates against pinned control digest from lock manifest.
3. Repo 48 emits compatibility report artifact.
4. Optional status callback updates repo 47 dashboard (read-only status, no contract mutation).

## 8. GitHub Actions plan

### 8.1 Repo 47 workflows

- `control-validate.yml`
  - Trigger: PRs into `control` and `main`.
  - Tasks: schema lint, semantic compatibility check vs previous manifest, version bump enforcement.

- `control-sync-runtime.yml`
  - Trigger: push to `control`.
  - Tasks: package contract bundle, compute digest, dispatch validation event to repo 48/runtime.

### 8.2 Repo 48 workflows

- `runtime-contract-check.yml`
  - Trigger: repository_dispatch from repo 47, and PR to `runtime`.
  - Tasks: pull contract bundle, replace lock snapshot, run contract tests.

- `runtime-validate.yml`
  - Trigger: PR/push to `runtime` and `main`.
  - Tasks: Rust build/test, TypeScript build/test, integration tests, schema conformance.

- `runtime-sync-report.yml`
  - Trigger: end of runtime validation.
  - Tasks: generate compatibility report, upload artifact, optional status callback to repo 47.

## 9. Release flow (control/runtime to both mains)

1. Complete contract + runtime compatibility on `control` and `runtime`.
2. Freeze manifest version `X.Y.Z` in repo 47 and update runtime lock in repo 48.
3. Create promotion PRs:
   - `repo-47/control -> repo-47/main`
   - `repo-48/runtime -> repo-48/main`
4. Gate merges on both repos passing cross-repo checks against the same digest.
5. Merge both promotion PRs in close sequence (same release window).
6. Tag both mains with `system-vX.Y.Z` and publish release notes referencing both commit SHAs.

## 10. Conflict resolution policy

- Contract conflict precedence: repo 47/control always wins.
- Runtime urgent fix that violates control contracts is prohibited from `main`; route to hotfix workflow with emergency contract patch on repo 47/control first.
- If sync failure occurs:
  1. mark manifest compatibility as `fail`,
  2. block both `main` promotions,
  3. open linked incident issues in both repos,
  4. restore compatibility through either contract revert or runtime adaptation PR,
  5. rerun full cross-repo validation.

## 11. Example event/message schema (control-owned, runtime-consumed)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/schemas/events/order-request.schema.json",
  "title": "OrderRequest",
  "type": "object",
  "required": [
    "event_type",
    "protocol_version",
    "event_id",
    "timestamp",
    "market",
    "side",
    "amount",
    "price_limit"
  ],
  "properties": {
    "event_type": { "type": "string", "const": "order.requested" },
    "protocol_version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "event_id": { "type": "string", "format": "uuid" },
    "timestamp": { "type": "string", "format": "date-time" },
    "market": { "type": "string", "pattern": "^[A-Z]{2,10}/[A-Z]{2,10}$" },
    "side": { "type": "string", "enum": ["buy", "sell"] },
    "amount": { "type": "string", "pattern": "^[0-9]+(\\.[0-9]+)?$" },
    "price_limit": { "type": "string", "pattern": "^[0-9]+(\\.[0-9]+)?$" },
    "client_meta": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "client_id": { "type": "string" },
        "trace_id": { "type": "string" }
      }
    }
  },
  "additionalProperties": false
}
```

## 12. Minimal operating constraints

- Repositories remain separate indefinitely.
- Contracts are authored only in repo 47/control.
- Runtime artifacts in repo 48 are always validated against a pinned control digest.
- Stable releases are dual-repo artifacts, never single-repo declarations.
