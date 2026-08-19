# Production Wedge

## Product boundary

The production version of this repository is **Semantic Protocol Runtime**, not a universal AI agent.

The first credible product promise is:

> Write typed workflow intent once. Inspect what will happen. Enforce allowed effects. Lower safe fragments into SQL/Python. Produce an audit trail.

Everything else—voice terminal, autonomous coding, neomorphic dashboards, and Completefication—is experimental until the core wedge is stable.

---

## Core commands

```bash
spr init demo
spr explain examples/hot_users.spr
spr compile examples/hot_users.spr --out build
spr run examples/hot_users.spr --dry-run
spr audit .spr_runs/latest
```

---

## Signature feature: Execution Firewall

Every `.spr` file must declare explicit capabilities.

```text
policy {
  deterministic: true
  allow database[db.main]
  allow filesystem[*]
  deny network[*]
  deny shell[*]
}
```

The production rule is simple:

- no undeclared file writes;
- no undeclared network;
- no shell by default;
- no hidden side effects;
- no LLM-created execution semantics.

---

## Production v1 scope

Included:

- `.spr` parser;
- intermediate representation;
- graph builder;
- policy verification;
- deterministic planner;
- SQL lowering for safe fragments;
- dry-run mode;
- audit artifacts;
- proof manifests;
- installable CLI;
- examples and tests.

Excluded from v1:

- unbounded agentic code editing;
- arbitrary shell execution;
- silent LLM tool use;
- voice-first UX as core product;
- enterprise compliance claims beyond implemented artifacts.

---

## Audit folder contract

Every dry-run or run should produce:

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

This is the expensive credibility layer. It turns the runtime from “script that says it worked” into “execution planner with evidence.”

---

## Definition of production-ready

The project becomes production-ready only when these pass from a fresh clone:

```bash
python -m pip install -e .[dev]
spr --help
spr explain examples/hot_users.spr
spr run examples/hot_users.spr --dry-run
spr audit .spr_runs/latest
pytest -q
```

And the docs clearly explain installation, policies, examples, audit outputs, limitations, and failure modes.

---

## Commercial position

Use this tagline:

> Semantic Protocol Runtime is a policy-visible execution planner for turning typed workflow intent into inspectable SQL/Python runs with audit trails.

Use this Overworker integration line:

> Overworker uses Semantic Protocol Runtime as its execution firewall: plans before action, policy before tools, audit before completion.
