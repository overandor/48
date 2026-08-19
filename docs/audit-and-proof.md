# Audit and Proof Manifests

## Why this matters

The audit trail is the most commercially valuable part of Semantic Protocol Runtime.

A normal script produces output. SPR produces evidence:

- source protocol;
- parsed intent;
- graph;
- policy result;
- execution plan;
- lowered artifacts;
- outputs;
- final report;
- proof manifest hashes.

This makes the system credible for R&D teams, technical buyers, investors, and compliance-sensitive pilots.

---

## Audit artifact contract

A run folder should contain:

```text
.spr_runs/<run_id>/
  source.spr
  parsed_ir.json
  graph.json
  policy_result.json
  plan.json
  lowered_sql.sql
  lowered_python.py
  outputs.json
  final_report.md
  proof_manifest.json
```

Each file has a purpose.

| Artifact | Purpose |
|---|---|
| `source.spr` | Original semantic protocol source |
| `parsed_ir.json` | Structured representation of the source |
| `graph.json` | Dependency/effect graph |
| `policy_result.json` | Proof that policy verification ran |
| `plan.json` | Planned runtime steps and effects |
| `lowered_sql.sql` | SQL lowering output where possible |
| `lowered_python.py` | Python lowering output or placeholder |
| `outputs.json` | Execution or dry-run result metadata |
| `final_report.md` | Human-readable run summary |
| `proof_manifest.json` | Hashes of all artifacts |

---

## Proof manifest

The proof manifest is a tamper-evident hash index.

Example shape:

```json
{
  "manifest_version": "1.0",
  "created_at_utc": "2026-08-19T21:17:00Z",
  "artifact_count": 4,
  "artifacts": [
    {
      "path": "plan.json",
      "sha256": "sha256:...",
      "bytes": 1234
    }
  ]
}
```

If any artifact changes after the manifest is generated, verification fails.

---

## Commands

Generate a dry-run audit:

```bash
spr run examples/hot_users.spr --dry-run
```

Inspect latest audit:

```bash
spr audit .spr_runs/latest
```

Generate or verify proof directly:

```bash
python -m spr.proof .spr_runs/latest
python -m spr.proof .spr_runs/latest --verify
```

---

## Commercial use

Audit folders can become:

- demo proof packs;
- R&D evidence;
- compliance evidence;
- customer onboarding artifacts;
- investor technical diligence materials;
- internal change-control records.

This is why audit mode should be treated as a first-class product surface, not an afterthought.
