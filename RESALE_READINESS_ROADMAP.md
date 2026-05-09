# Resale Readiness Roadmap — Semantic Protocol Runtime / Completefication

**Repository:** `overandor/48`  
**Current status:** early research prototype  
**Target status:** commercially packageable developer tool / enterprise AI terminal protocol  
**Assessment:** not resale-ready today

---

## 1. Honest current-state assessment

The repository currently represents a strong research prototype, not a finished product.

It demonstrates real technical depth:

- semantic parsing;
- typed-ish intermediate representation;
- graph construction;
- policy verification;
- deterministic planning;
- SQL and Python lowering;
- explicit effects;
- CLI / REPL entry points;
- optional local LLM support;
- voice terminal experiments;
- one-command LLM programming experiments;
- neomorphic control-surface experiments.

However, it is not yet a product that can be credibly resold as a polished developer tool or enterprise platform.

The current repository proves the concept. It does not yet package, document, harden, test, distribute, support, or legally frame the concept well enough for resale.

---

## 2. Product truth

### What it is today

**A working research prototype for semantic protocol programming and terminal-native LLM-assisted software operations.**

### What it is not yet

- not a polished CLI product;
- not a PyPI package;
- not a maintainable modular library;
- not an enterprise-ready platform;
- not a supported commercial offering;
- not ready for resale without significant productization.

### Best current label

> **Research-grade prototype with strong commercial potential.**

---

## 3. Gap table

| Area | Current state | Resale-ready requirement | Priority |
|---|---|---|---:|
| Packaging | Loose scripts | `pyproject.toml`, installable package, CLI entry points | P0 |
| Architecture | Large single-file runtime | Modular package layout with stable APIs | P0 |
| Docs | Research proposal | install guide, quickstart, examples, API docs, tutorials | P0 |
| Tests | Minimal / unclear | parser, planner, policy, lowering, runtime, CLI, regression tests | P0 |
| Examples | Sparse | working `.spr` demo suite with expected outputs | P0 |
| CLI UX | Basic | `spr explain/run/compile/repl/voice/complete` polished UX | P1 |
| Error handling | Prototype-level | typed errors, actionable messages, recovery hints | P1 |
| Config | hardcoded defaults | config files, env vars, profiles, safe defaults | P1 |
| Observability | limited | logs, run artifacts, audit manifests, trace mode | P1 |
| Security | basic policy | stronger path, command, secret, network, model controls | P1 |
| Distribution | GitHub only | PyPI, Docker image, GitHub release, install script | P1 |
| Legal | MIT only | commercial license option, EULA, support terms, disclaimers | P2 |
| Support | none | issue templates, docs site, support channel, SLA option | P2 |
| Adoption proof | none | demo videos, benchmarks, examples, case studies | P2 |

---

## 4. Resale readiness definition

The project becomes resale-ready only when a fresh user can do all of the following without hand-holding:

```bash
pip install semantic-protocol-runtime
spr init demo
spr explain examples/hot_users.spr
spr run examples/hot_users.spr --dry-run
spr compile examples/hot_users.spr --out build/
spr repl
```

And the repository provides:

- full installation instructions;
- a stable CLI;
- example protocols;
- tests passing in CI;
- package metadata;
- versioning;
- clear license terms;
- clear risk disclaimers;
- clear positioning;
- repeatable demos.

---

## 5. Commercial target product

### Product name

**Semantic Protocol Runtime**

### Product category

**Terminal-native semantic programming and LLM-assisted execution planning.**

### Enterprise extension

**Completefication Protocol**

### Best commercial statement

**Semantic Protocol Runtime lets developers express typed workflow intent once, then compile, inspect, and execute it across runtimes under explicit policy controls. Completefication extends this into a governed LLM terminal operator that turns normal-English engineering tasks into audited plans, bounded edits, terminal checks, repair loops, and grounded completion reports.**

---

## 6. Minimum sellable product scope

The first sellable version should not try to sell everything.

### MVP product scope

1. Installable CLI package.
2. Stable `.spr` grammar subset.
3. Parser → IR → verifier → planner → dry-run execution.
4. SQL pushdown for basic filter/project/limit/sort.
5. Python local execution for simple transforms.
6. Explicit effects for file output and notification stubs.
7. Policy enforcement with allow/deny rules.
8. Example suite.
9. Test suite.
10. Documentation.
11. Audit run artifact output.

### Exclude from v0.1 resale

- broad arbitrary terminal agent autonomy;
- unbounded LLM file editing;
- unsupported voice mode as a core feature;
- complex UI claims;
- enterprise compliance claims;
- production security claims beyond actual implemented controls.

Voice, Completefication, and neomorphic UI should be marketed as experimental add-ons until hardened.

---

## 7. Required repository restructuring

Target layout:

```text
semantic-protocol-runtime/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  src/
    spr/
      __init__.py
      cli.py
      parser.py
      ir.py
      graph.py
      policy.py
      planner.py
      lowerers/
        __init__.py
        sql.py
        python.py
      runtime.py
      llm.py
      audit.py
      errors.py
      voice.py
      completefication.py
  examples/
    hot_users.spr
    aggregate_sales.spr
    policy_denied_network.spr
    file_export.spr
  tests/
    test_parser.py
    test_policy.py
    test_planner.py
    test_sql_lowerer.py
    test_runtime.py
    test_cli.py
  docs/
    quickstart.md
    language-reference.md
    policy-model.md
    examples.md
    architecture.md
    commercial-roadmap.md
```

The current large `semantic_protocol_runtime.py` can remain temporarily as a compatibility wrapper, but the product should move into `src/spr/`.

---

## 8. Packaging milestone

### Required files

`pyproject.toml`:

```toml
[project]
name = "semantic-protocol-runtime"
version = "0.1.0"
description = "Terminal-native semantic protocol runtime for typed intent, explicit effects, and multi-runtime lowering."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Joseph Skrobynets" }]
dependencies = []

[project.optional-dependencies]
llm = ["transformers", "torch"]
voice = ["SpeechRecognition", "pyttsx3"]
dev = ["pytest", "ruff", "mypy"]

[project.scripts]
spr = "spr.cli:main"
```

### Acceptance criteria

```bash
python -m pip install -e .
spr --help
spr explain examples/hot_users.spr
spr run examples/hot_users.spr --dry-run
pytest -q
```

All must work from a clean clone.

---

## 9. Documentation milestone

The README should stop being only a research proposal.

It should be rewritten into:

1. What this is.
2. Why it exists.
3. Install.
4. Quickstart.
5. Example `.spr` file.
6. CLI commands.
7. Safety model.
8. Current limitations.
9. Roadmap.
10. Commercial status.

The academic proposal should move to:

```text
docs/research-proposal.md
```

### Required docs

| Doc | Purpose |
|---|---|
| `docs/quickstart.md` | first 10 minutes |
| `docs/language-reference.md` | grammar and operators |
| `docs/policy-model.md` | capability rules and effects |
| `docs/examples.md` | walkthroughs |
| `docs/architecture.md` | internals |
| `docs/completefication.md` | experimental terminal agent layer |
| `docs/resale-readiness.md` | honest commercial roadmap |

---

## 10. Testing milestone

### Required test categories

1. Parser tests
   - policies;
   - sources;
   - transforms;
   - effects;
   - invalid syntax.

2. Policy tests
   - allowed database;
   - denied network;
   - denied shell;
   - filesystem effects.

3. Planner tests
   - SQL pushdown candidate;
   - Python fallback;
   - deterministic mode;
   - approximate transform rejection.

4. Lowerer tests
   - filter;
   - project;
   - limit;
   - sort;
   - group/sum if supported.

5. Runtime tests
   - dry-run;
   - file effect;
   - SQLite demo;
   - error handling.

6. CLI tests
   - `spr --help`;
   - `spr explain`;
   - `spr run --dry-run`;
   - invalid input response.

### Acceptance criteria

- `pytest -q` passes;
- CI runs on every push;
- minimum target: 70% coverage for core modules;
- every example has at least one snapshot or expected-output test.

---

## 11. Demo suite milestone

Create ready-to-run examples:

```text
examples/
  hot_users.spr
  sales_aggregate.spr
  local_file_export.spr
  denied_network.spr
  sqlite_demo.spr
  python_map.spr
```

Each example should have:

- protocol file;
- expected plan JSON;
- expected dry-run output;
- README walkthrough.

Best first demo:

```text
policy {
  optimize: latency > cost
  deterministic: true
  allow database[db.main]
  allow filesystem[*]
  deny network[*]
  deny shell[*]
}

users := source @db.main "select id, email, score from users"
hot   := users -> filter score > 0.8 -> project [id, email, score]
write! hot @file:"hot_users.jsonl"
```

---

## 12. Product hardening milestone

### Error handling

Replace generic tracebacks with domain errors:

```text
SPR_PARSE_ERROR
SPR_POLICY_DENIED
SPR_PLANNING_FAILED
SPR_LOWERING_UNSUPPORTED
SPR_RUNTIME_FAILED
SPR_CONFIG_ERROR
```

Each error should include:

- what happened;
- where it happened;
- why it matters;
- how to fix it;
- documentation link.

### Configuration

Support:

```bash
spr --config spr.yaml run examples/hot_users.spr
```

Example config:

```yaml
runtime:
  default_build_dir: build
  dry_run_default: true
llm:
  provider: none
  local_model: null
policy:
  default_deny_network: true
  default_deny_shell: true
logging:
  level: info
  audit_dir: .spr_runs
```

---

## 13. Audit and proof milestone

A commercial-grade tool should create run artifacts:

```bash
spr run examples/hot_users.spr --audit-dir .spr_runs
```

Output:

```text
.spr_runs/<run_id>/
  source.spr
  parsed_ir.json
  graph.json
  plan.json
  policy_result.json
  command_outputs.json
  final_report.md
  proof_manifest.json
```

This is the first truly expensive feature because it makes the tool accountable.

---

## 14. Commercial positioning

### Do not sell as

- autonomous coding replacement;
- guaranteed production compiler;
- enterprise compliance platform today;
- universal programming language;
- secure sandbox unless fully implemented.

### Sell as

- semantic workflow authoring prototype;
- policy-visible runtime planner;
- inspectable multi-runtime lowering system;
- developer research tool;
- early-access AI terminal programming protocol;
- customizable internal automation framework.

### Best honest sales sentence

**Semantic Protocol Runtime is an early-access developer tool for writing typed workflow intent once, inspecting how it will execute, and lowering it into concrete runtimes under explicit effect and policy controls.**

---

## 15. Realistic timeline

### Phase 0 — Freeze prototype baseline, 1 week

- tag current research prototype;
- move research docs out of primary README;
- define supported grammar subset;
- remove or mark unstable experimental files.

### Phase 1 — Package and docs, 2–3 weeks

- create `pyproject.toml`;
- module split;
- CLI entry point;
- quickstart;
- examples;
- basic tests.

### Phase 2 — Harden core runtime, 3–5 weeks

- parser tests;
- policy tests;
- lowerer tests;
- better errors;
- config file;
- dry-run reliability;
- audit artifacts.

### Phase 3 — Product demo, 2–3 weeks

- demo suite;
- docs site;
- GIF/video walkthrough;
- Dockerfile;
- GitHub release;
- CI badges;
- benchmark writeup.

### Phase 4 — Commercial packaging, 4–8 weeks

- commercial license option;
- paid support statement;
- enterprise policy pack;
- audit/proof mode;
- compliance disclaimers;
- pilot customer workflow.

### Total realistic time

**10–20 focused weeks** to make this credibly sellable as an early-access developer product.

---

## 16. Immediate next build order

The next commits should be practical, not more concept expansion.

1. Add `pyproject.toml`.
2. Add `examples/hot_users.spr`.
3. Add `tests/test_parser.py`.
4. Add `tests/test_policy.py`.
5. Add `tests/test_cli.py`.
6. Add GitHub Actions CI.
7. Split `semantic_protocol_runtime.py` into modules.
8. Rewrite README into product quickstart.
9. Move research proposal into `docs/research-proposal.md`.
10. Add audit artifact mode.

---

## 17. Resale readiness score

Current score:

```text
Concept strength:        8/10
Prototype functionality: 6/10
Product packaging:       1/10
Documentation:           2/10
Testing:                 2/10
UX polish:               2/10
Enterprise readiness:    1/10
Commercial readiness:    1/10
Overall resale readiness: 2/10
```

Target for early-access resale:

```text
Concept strength:        8/10
Prototype functionality: 7/10
Product packaging:       7/10
Documentation:           7/10
Testing:                 6/10
UX polish:               6/10
Enterprise readiness:    4/10
Commercial readiness:    6/10
Overall resale readiness: 6/10
```

Target for enterprise resale:

```text
Overall resale readiness: 8/10+
```

---

## 18. Bottom line

This repository should not be marketed as resale-ready today.

It should be marketed as:

> **a promising research prototype with a concrete path to a sellable developer tool.**

The commercial opportunity is real, but the next stage is product discipline:

- package it;
- document it;
- test it;
- modularize it;
- demo it;
- audit it;
- then sell it.
