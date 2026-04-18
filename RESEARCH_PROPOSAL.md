# Research Proposal: Semantic Protocol Runtime for Multi-Runtime Program Authoring

## Title

**Semantic Protocol Runtime: A Terminal-Native System for Authoring Typed Intent and Automatically Lowering It Across Multiple Execution Runtimes**

## Abstract

Modern software systems are increasingly assembled from multiple languages and runtimes such as Python, SQL, shell, JavaScript, HTTP APIs, workflow engines, and cloud services. This fragmentation creates large amounts of glue code, weak observability, brittle orchestration, and unnecessary cognitive overhead. This proposal studies a new programming model in which developers author a single semantic protocol artifact that expresses typed intent, effects, policies, capabilities, and optimization priorities, while a planning and lowering system compiles fragments of that artifact into the most appropriate target runtimes.

The proposed prototype, the **Semantic Protocol Runtime**, treats source code as an executable protocol rather than language-bound syntax. A user writes a compact, terminal-native semantic language with explicit effect markers and resource bindings. The system parses the artifact into an intermediate representation, constructs dependency and effect graphs, applies capability and policy verification, selects legal implementation targets, lowers subgraphs into concrete backends such as SQL and Python, and executes the resulting unified plan. A local Hugging Face Transformers model may optionally assist in runtime selection or bounded inference, but the semantic representation remains the source of truth.

This research investigates whether such a system can reduce glue code, improve runtime placement, and preserve developer trust through explicit policies and inspectable execution plans.

## Problem Statement

Current programming workflows are shaped by language-specific authoring rather than by semantic intent. Developers commonly express a single end-to-end task using multiple artifacts:

- shell commands for orchestration,
- Python for transformation logic,
- SQL for pushdown into data stores,
- HTTP clients for APIs,
- configuration files for workflow behavior,
- ad hoc scripts for effects such as notifications or exports.

This model has several costs:

1. **Fragmented meaning**
   A single operation is spread across files, runtimes, and configuration layers.

2. **Manual runtime choice**
   Developers must decide by hand what should execute in SQL, what should execute in Python, and what should be handled by orchestration code.

3. **Unsafe or implicit side effects**
   File writes, network calls, shell access, and notifications are often hidden inside code paths rather than declared explicitly.

4. **Poor inspectability**
   It is hard to ask, before execution, “what exactly will run where?”

5. **High glue-code burden**
   Significant engineering time is spent on connectors, adapters, wrappers, and repeated orchestration logic rather than on core semantics.

The research question is whether a **single semantic protocol file** can serve as the authoritative source for execution while the system automatically selects and lowers fragments into appropriate runtimes under explicit constraints.

## Core Hypothesis

A typed semantic protocol language with explicit effects, capability policies, and bounded runtime lowering can:

- reduce cross-language glue code,
- improve execution placement,
- preserve developer trust through inspectable plans,
- and provide a practical terminal-native authoring model for multi-runtime workflows.

## Research Objectives

The project has six core objectives.

### Objective 1: Define a semantic authoring surface

Design a compact protocol language in which symbols and tokens represent execution semantics rather than the syntax of any single programming language.

### Objective 2: Separate meaning from lowering

Implement a compiler pipeline in which source artifacts are parsed into a semantic intermediate representation before any target language is chosen.

### Objective 3: Make side effects explicit

Represent writes, notifications, network access, and other external actions as first-class effect nodes with declared capabilities.

### Objective 4: Support mixed lowering

Allow different fragments of a single semantic program to be lowered into different runtimes, such as SQL pushdown for filtering and projection and Python for orchestration or custom mapping.

### Objective 5: Bound LLM involvement

Use an optional local Hugging Face model only for constrained ranking or inference tasks. The LLM must not invent program meaning.

### Objective 6: Evaluate usefulness

Measure whether the system improves brevity, inspectability, and execution planning relative to a comparable manually assembled baseline.

## Proposed System

The proposed system is a prototype called **Semantic Protocol Runtime**. It is terminal-native and single-file by default.

### Authoring model

Instead of writing multiple files in multiple languages, a user writes a semantic artifact such as:

```text
policy {
  optimize: latency > cost
  deterministic: true
  allow database[db.main]
  allow filesystem[*]
  allow network[slack.ops]
  deny shell[*]
}

users := source @db.main "select id, email, score from users"
hot   := users -> filter score > 0.8 -> project [id, email, score]
write! hot @file:"hot_users.jsonl"
notify! hot @slack.ops:"#risk"
```

This artifact declares:

- source location,
- transformation semantics,
- effects,
- capability policy,
- optimization preference.

It does not require the user to manually choose a separate source language for each fragment.

### Key semantic operators

The prototype uses a small set of canonical operators:

- `:=` bind a value or stream
- `->` pure transform
- `!` explicit effect
- `@` runtime or resource binding
- `:` type or refinement
- `?` unresolved or inferable parameter
- `|` pipeline or fallback
- `~` approximate or heuristic execution
- `#` planner hint

These symbols are interpreted by the semantic runtime, not by Python, SQL, or shell parsers.

## System Architecture

The prototype architecture consists of the following layers:

1. **Parser**
   Parses semantic source files into a structured program representation.

2. **Intermediate representation**
   Stores bindings, transforms, effects, and policies in a typed-ish internal model.

3. **Graph builder**
   Builds dependency and effect graphs for execution ordering and static reasoning.

4. **Policy verifier**
   Enforces declared capabilities such as allowed databases, filesystems, and network targets.

5. **Planner**
   Selects legal lowerings for each transform and effect using a deterministic cost model with optional bounded LLM ranking.

6. **Lowerers**
   Convert semantic fragments into concrete target code or operations. The first prototype includes:
   - SQL lowering for source-side filtering/projecting/grouping,
   - Python lowering for orchestration and runtime execution.

7. **Runtime**
   Executes the plan and records outputs.

8. **Terminal interface**
   Supports parsing, explaining, compiling, running, and interactive inspection.

## Methodology

The project will proceed in five phases.

### Phase 1: Language design

Define a minimal grammar sufficient for:
- sources,
- pure transforms,
- effects,
- policy rules,
- runtime hints.

### Phase 2: IR and verification

Represent semantic programs as a graph of bindings and effects. Enforce:
- deterministic mode constraints,
- allowed capabilities,
- simple dependency correctness,
- effect visibility.

### Phase 3: Lowering

Implement initial lowerers:
- SQL for pushdown-eligible transformations,
- Python for execution and orchestration.

### Phase 4: Optional bounded LLM assistance

Add a local Transformers adapter for:
- ranking legal runtime candidates,
- optional metadata completion,
- explanation support.

This LLM is advisory only. It may never override policy or create new semantics.

### Phase 5: Evaluation

Run benchmark tasks comparing:
- semantic protocol authoring,
- conventional multi-file glue-code implementations.

## Evaluation Plan

The evaluation will focus on four criteria.

### 1. Authoring efficiency

Measure:
- lines of source required,
- number of files required,
- time to complete representative tasks.

### 2. Execution quality

Measure:
- whether pushdown opportunities are captured,
- whether generated plans are valid,
- whether outputs match expected results.

### 3. Trust and inspectability

Measure:
- ability to explain execution plans,
- clarity of visible side effects,
- ease of understanding runtime placement before execution.

### 4. Robustness

Measure:
- policy enforcement behavior,
- failure handling,
- reproducibility of compiled plans.

## Example Tasks for Evaluation

Initial benchmarks will include:

1. **Database filter and export**
   - Read from a database
   - Filter rows
   - Project fields
   - Write to a file

2. **Grouping and aggregation**
   - Group records
   - Compute aggregate values
   - Export results

3. **Transformation plus effect**
   - Apply a Python-side transformation
   - Trigger a notification

4. **Policy-constrained execution**
   - Attempt a denied capability
   - Confirm the verifier blocks execution

## Expected Contributions

This work aims to contribute:

- a concrete prototype for semantic protocol programming,
- a design pattern for explicit effect-first authoring,
- a bounded model for LLM-assisted lowering,
- an evaluation of whether a terminal-native semantic system can replace common glue workflows.

## Novelty and Positioning

The project does not claim that every component is unprecedented in isolation. Related ideas exist across:

- intermediate representations,
- workflow systems,
- query planners,
- code generation,
- formal verification,
- LLM-assisted coding.

The proposed novelty lies in the integration of these ideas into one authoring and execution surface:

- one semantic artifact,
- one policy model,
- one inspectable plan,
- many possible lowerings.

In this framing, languages become backends rather than authoring environments.

## Risks

The main risks are:

### Ambiguity risk
If the semantic language is too loose, the system becomes untrustworthy.

### Overreach risk
If too many runtimes or operators are introduced too early, the prototype becomes difficult to reason about.

### Verification risk
Formal correctness beyond a narrow scope is difficult. Early versions should prioritize practical policy checks and explainable planning.

### Adoption risk
Developers may resist a new abstraction layer unless the benefits are immediate and obvious.

## Risk Mitigation

To reduce these risks, the research will:

- keep the initial grammar small,
- make all effects explicit,
- treat the LLM as optional and bounded,
- provide explain and dry-run modes,
- start with a narrow workflow-focused use case.

## Deliverables

Planned deliverables include:

1. A single-file runnable prototype runtime
2. A semantic protocol grammar and examples
3. A planner and verifier
4. SQL and Python lowerers
5. A terminal CLI and REPL
6. A small benchmark suite
7. A comparative evaluation report
8. A roadmap for expanded runtimes and stronger verification

## Timeline

### Weeks 1–2
- finalize minimal grammar
- parser and IR
- simple verifier

### Weeks 3–4
- planner
- SQL lowering
- Python lowering
- CLI explain and compile paths

### Weeks 5–6
- evaluation tasks
- bounded local LLM integration
- dry-run and inspectability improvements

### Weeks 7–8
- benchmark comparisons
- write-up and next-stage architecture

## Success Criteria

The project will be considered successful if it demonstrates that:

- a single semantic protocol file can replace a multi-file glue workflow,
- runtime placement can be automatically selected for at least a small set of operations,
- side effects and capability policies remain inspectable and enforceable,
- local LLM assistance improves ergonomics without weakening determinism or trust.

## Broader Impact

If successful, this work could influence:

- data engineering workflows,
- DevOps and infrastructure automation,
- API orchestration systems,
- agent runtimes,
- future language design centered on semantics rather than syntax.

The broader thesis is that developers should author **meaning**, while runtimes and compilers determine **realization**.

## Current Prototype Status

A first prototype has already been implemented in this repository. It includes:

- semantic parsing,
- a typed internal representation,
- graph construction,
- policy verification,
- deterministic planning,
- SQL and Python lowering,
- local Hugging Face LLM adapter support,
- CLI and REPL entry points,
- a demo semantic protocol program.

This proposal therefore supports an active prototype research program rather than a purely speculative concept.

## Conclusion

This research explores a practical rethinking of terminal programming as semantic protocol authoring. The central claim is that a single protocol artifact can express typed intent, explicit effects, and policy constraints, while a planner and lowering system safely realize that intent across multiple languages and runtimes.

The immediate goal is not a universal language replacement. It is a narrow, credible demonstration that semantic authoring can reduce glue code and improve execution planning for real workflows. If the prototype succeeds in that wedge, it may provide the foundation for a broader class of multi-runtime semantic programming systems.
